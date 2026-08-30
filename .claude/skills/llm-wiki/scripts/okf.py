#!/usr/bin/env python3
"""Tooling for Open Knowledge Format (OKF) v0.1 bundles used as LLM-wikis.

Subcommands
-----------
  lint    Conformance (OKF v0.1 §9) plus link, orphan and index checks.
  stale   Git-derived staleness of concepts, and coverage gaps in the repo.
  index   Regenerate index.md files from concept frontmatter.

Everything the model cannot reliably eyeball lives here; everything requiring
judgement (what a concept should say) stays in SKILL.md.

Exit codes: 0 = clean, 1 = errors (or warnings under --strict), 2 = bad usage.
S004 coverage gaps are advisory — whether a gap deserves a page is a judgement
call — so `stale` reports them but they never affect the exit code.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pathspec
import yaml

# OKF v0.1 §3.1 — reserved at any level of the hierarchy.
RESERVED = {"index.md", "log.md"}

# An index.md containing this marker is hand-curated: `index --write` leaves it
# alone, and lint treats its links as deliberate (they count against W011).
MANUAL_MARKER = "<!-- okf:manual -->"

# Frontmatter keys OKF defines. Anything else is a producer extension (§4.1).
OKF_KEYS = {"type", "title", "description", "resource", "tags", "timestamp"}

# L0 is a scan line: every index entry is read on the way to any single page, so
# its cost is paid by every query and not just the relevant one. The ceiling is a
# character budget rather than a sentence count because what costs a reader is
# length — a rambling one-sentence L0 is worse than two crisp ones.
#
# The floor catches truncation, which is silent and does not look like an error.
# An unquoted `#` opens a YAML comment and an unquoted `: ` breaks the mapping,
# so `description: White on #0091d9 measures 3.47:1` parses as "White on" and
# every check downstream passes on the two words that are left.
L0_MAX_CHARS = 250
L0_MIN_CHARS = 40

# Paths that never warrant a wiki concept. Overridable via <bundle>/.okfignore.
# Prose and dotfiles are excluded outright: the wiki *is* the prose layer, and a
# coverage report that nags about README.md teaches you to ignore it.
#
# Deliberately NOT merged with the project's .gitignore, for two reasons:
#
#   1. It would be a no-op. Coverage runs over `git ls-files`, i.e. *tracked*
#      files. Anything .gitignore excludes was never added, so it is already
#      invisible here. That is why this list contains no node_modules/, dist/ or
#      .venv/ — those can never reach us. Every entry below is a file that is
#      normally committed.
#   2. It would be wrong. Git's rule is "tracked beats ignored": a file that was
#      committed and *later* added to .gitignore stays tracked, and git does not
#      ignore it. Applying .gitignore here would silently drop such a file from
#      the S004 coverage report — making the wiki look complete when it is not.
#
# Reimplementing .gitignore is also a trap: nested files, `!` negation ordering,
# core.excludesFile and .git/info/exclude. `git ls-files` already gets all of
# that right. Let it.
DEFAULT_IGNORE = [
    ".*",
    "**/.*",
    "**/*.md",
    "**/*.rst",
    "**/*.txt",
    "**/__snapshots__/**",
    "**/testdata/**",
    "**/*.lock",
    "**/*.min.*",
    "**/*_test.*",
    "**/*.test.*",
    "**/*.spec.*",
    "**/test_*.py",
    "tests/**",
    "test/**",
    "spec/**",
    "docs/**",
    "vendor/**",
    "third_party/**",
    "**/LICENSE*",
]

FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
# Inline markdown links, excluding images (leading `!`).
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(\s*<?([^)>\s]+)>?")
SCHEME_RE = re.compile(r"\A[a-zA-Z][a-zA-Z0-9+.\-]*:")
LOG_DATE_RE = re.compile(r"\A##\s+(\d{4}-\d{2}-\d{2})\s*\Z")
GLOB_CHARS = re.compile(r"[*?\[\]]")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def git(repo: Path, *args: str) -> tuple[int, str]:
    """Run git in `repo`. Returns (returncode, stdout).

    Only the trailing newline is stripped: `git status --porcelain` encodes the
    status in columns 0-1, so a leading space is significant.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout.rstrip("\n")


def porcelain_paths(output: str) -> list[str]:
    """Extract paths from `git status --porcelain` lines (`XY path`, `R  old -> new`)."""
    paths = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:  # rename/copy: report the destination
            path = path.split(" -> ", 1)[1]
        paths.append(path.strip('"'))
    return paths


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (raw_yaml_or_None, body)."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, text
    return match.group(1), text[match.end() :]


def derive_title(path: Path) -> str:
    return path.stem.replace("-", " ").replace("_", " ").strip().title()


def has_concepts(directory: Path) -> bool:
    """True if any concept (non-reserved, non-hidden .md) lives under `directory`.

    A directory holding only an index.md or log.md carries no knowledge of its
    own, so indexes neither list it nor expect it to have an index.
    """
    return any(
        p.name not in RESERVED
        and not any(part.startswith(".") for part in p.relative_to(directory).parts)
        for p in directory.rglob("*.md")
    )


def resolve_link(target: str, doc: Path, bundle: Path) -> Path | None:
    """Resolve an in-bundle markdown link to a filesystem path, or None if external."""
    if SCHEME_RE.match(target) or target.startswith("#"):
        return None
    target = target.split("#", 1)[0]
    if not target:
        return None
    base = bundle / target.lstrip("/") if target.startswith("/") else doc.parent / target
    resolved = Path(os.path.normpath(base))
    if target.endswith("/") or resolved.is_dir():
        resolved = resolved / "index.md"
    return resolved


def normalize_sources(patterns: list[str], repo: Path, gitlinks: frozenset[str] = frozenset()) -> list[str]:
    """A bare directory means 'everything under it'. Globs pass through.

    A submodule is the exception: `git ls-files` reports it as a single gitlink
    entry at the bare directory path, and none of its files are tracked by the
    parent repo. Expanding it to `sub/**` would match nothing. Left alone, it
    matches exactly — and a pointer bump shows up as a normal diff, which is the
    only thing about a submodule the parent can observe.
    """
    out = []
    for raw in patterns:
        pattern = str(raw).strip().strip("/")
        if not pattern:
            continue
        if pattern in gitlinks:
            out.append(pattern)
            continue
        if not GLOB_CHARS.search(pattern) and (repo / pattern).is_dir():
            pattern = f"{pattern}/**"
        elif "/" not in pattern:
            # gitignore syntax matches a slash-less pattern (`Makefile`,
            # `*.sql`) at any depth, but git's `:(glob)` pathspec anchors it to
            # the root — coverage and diffing would disagree. A leading `**/`
            # means "in all directories, including the root" in both dialects.
            pattern = f"**/{pattern}"
        out.append(pattern)
    return out


# ---------------------------------------------------------------------------
# bundle model
# ---------------------------------------------------------------------------


@dataclass
class Doc:
    path: Path
    rel: str
    meta: dict
    body: str
    raw_frontmatter: str | None
    yaml_error: str | None = None

    @property
    def concept_id(self) -> str:
        return self.rel[: -len(".md")]

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or derive_title(self.path))

    @property
    def description(self) -> str:
        return str(self.meta.get("description") or "").strip()

    @property
    def type(self) -> str:
        return str(self.meta.get("type") or "").strip()


@dataclass
class Bundle:
    root: Path
    repo: Path
    concepts: list[Doc] = field(default_factory=list)
    indexes: list[Doc] = field(default_factory=list)
    logs: list[Doc] = field(default_factory=list)

    @property
    def all_docs(self) -> list[Doc]:
        return [*self.concepts, *self.indexes, *self.logs]


def load_doc(path: Path, bundle_root: Path) -> Doc:
    text = path.read_text(encoding="utf-8")
    raw, body = split_frontmatter(text)
    meta: dict = {}
    err = None
    if raw is not None:
        try:
            parsed = yaml.safe_load(raw)
            if parsed is None:
                meta = {}
            elif isinstance(parsed, dict):
                meta = parsed
            else:
                err = f"frontmatter is {type(parsed).__name__}, expected a mapping"
        except yaml.YAMLError as exc:
            err = str(exc).splitlines()[0]
    return Doc(
        path=path,
        rel=str(path.relative_to(bundle_root)).replace(os.sep, "/"),
        meta=meta,
        body=body,
        raw_frontmatter=raw,
        yaml_error=err,
    )


def load_bundle(root: Path, repo: Path) -> Bundle:
    bundle = Bundle(root=root, repo=repo)
    for path in sorted(root.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        doc = load_doc(path, root)
        if path.name == "index.md":
            bundle.indexes.append(doc)
        elif path.name == "log.md":
            bundle.logs.append(doc)
        else:
            bundle.concepts.append(doc)
    return bundle


def doc_links(doc: Doc, bundle: Bundle) -> list[tuple[str, Path | None]]:
    return [(t, resolve_link(t, doc.path, bundle.root)) for t in LINK_RE.findall(doc.body)]


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------


def lint(bundle: Bundle) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []

    def err(code, rel, msg):
        errors.append({"code": code, "file": rel, "message": msg})

    def warn(code, rel, msg):
        warnings.append({"code": code, "file": rel, "message": msg})

    # §9.1/§9.2 — concept conformance.
    for doc in bundle.concepts:
        if doc.raw_frontmatter is None:
            err("E001", doc.rel, "no YAML frontmatter block")
            continue
        if doc.yaml_error:
            err("E002", doc.rel, f"unparseable frontmatter: {doc.yaml_error}")
            continue
        if not doc.type:
            err("E003", doc.rel, "frontmatter has no non-empty `type` field")
        if not doc.description:
            warn("W013", doc.rel, "no `description` (index entries and previews use it)")
        elif len(doc.description) > L0_MAX_CHARS:
            warn(
                "W017",
                doc.rel,
                f"`description` is {len(doc.description)} chars; L0 is a scan line read on "
                f"the way to every page, so budget {L0_MAX_CHARS}. Move the detail into the body",
            )
        elif len(doc.description) < L0_MIN_CHARS:
            warn(
                "W017",
                doc.rel,
                f"`description` is only {len(doc.description)} chars — a stub, or truncated by "
                "an unquoted `#` starting a YAML comment. Quote it and check it reads whole",
            )
        if not doc.meta.get("timestamp"):
            warn("W014", doc.rel, "no `timestamp`")
        tags = doc.meta.get("tags")
        if tags is not None and not isinstance(tags, list):
            warn("W015", doc.rel, "`tags` should be a YAML list")

    # §6 — index files carry no frontmatter, except okf_version at bundle root.
    for doc in bundle.indexes:
        is_root = doc.path.parent == bundle.root
        if doc.raw_frontmatter is None:
            if is_root:
                warn("W005", doc.rel, 'root index.md should declare okf_version: "0.1"')
        elif not is_root:
            err("E004", doc.rel, "non-root index.md must not have frontmatter (§6)")
        elif doc.yaml_error:
            err("E002", doc.rel, f"unparseable frontmatter: {doc.yaml_error}")
        elif "okf_version" not in doc.meta:
            warn("W005", doc.rel, 'root index.md should declare okf_version: "0.1"')

    # §7 — log entries are ISO-dated, newest first.
    for doc in bundle.logs:
        if doc.raw_frontmatter is not None:
            err("E004", doc.rel, "log.md must not have frontmatter (§7)")
        dates = [m.group(1) for line in doc.body.splitlines() if (m := LOG_DATE_RE.match(line.strip()))]
        headings = [l for l in doc.body.splitlines() if l.strip().startswith("## ")]
        if len(dates) != len(headings):
            err("E006", doc.rel, "every `## ` heading must be an ISO 8601 YYYY-MM-DD date (§7)")
        if dates != sorted(dates, reverse=True):
            err("E007", doc.rel, "log entries must be newest-first")

    # §5.3 — broken links are tolerated by consumers, but usually a typo here.
    # Inbound links (for W011) are counted only from concepts, logs and
    # hand-curated (`okf:manual`) indexes: `index --write` links every concept
    # from its directory's index, so auto-generated indexes would satisfy the
    # orphan check by construction and it could never fire.
    known = {d.path.resolve() for d in bundle.all_docs}
    inbound: set[Path] = set()
    for doc in bundle.all_docs:
        curated = doc.path.name != "index.md" or MANUAL_MARKER in doc.body
        for target, resolved in doc_links(doc, bundle):
            if resolved is None:
                continue
            rp = resolved.resolve()
            if rp in known:
                if curated and rp != doc.path.resolve():
                    inbound.add(rp)
            elif resolved.suffix == ".md" and not resolved.exists():
                warn("W010", doc.rel, f"link target does not exist: {target}")

    # Orphans: unreachable concepts are invisible to progressive disclosure.
    for doc in bundle.concepts:
        if doc.path.resolve() not in inbound:
            warn("W011", doc.rel, "orphan — no concept, log or curated index links to it")

    # Index coverage: every concept/subdir listed in its directory's index.md.
    for index_doc in bundle.indexes:
        directory = index_doc.path.parent
        linked = {r.resolve() for _, r in doc_links(index_doc, bundle) if r is not None}
        for child in sorted(directory.iterdir()):
            if child.is_dir():
                if child.name.startswith("."):
                    continue
                if not has_concepts(child):
                    continue
                expected = (child / "index.md").resolve()
                if expected not in linked:
                    warn("W012", index_doc.rel, f"does not link subdirectory `{child.name}/`")
            elif child.suffix == ".md" and child.name not in RESERVED:
                if child.resolve() not in linked:
                    warn("W012", index_doc.rel, f"does not link concept `{child.name}`")

    for directory in {d.path.parent for d in bundle.concepts}:
        if not (directory / "index.md").exists():
            rel = str(directory.relative_to(bundle.root)).replace(os.sep, "/")
            warn("W016", rel or ".", "directory has concepts but no index.md")

    return errors, warnings


# ---------------------------------------------------------------------------
# stale
# ---------------------------------------------------------------------------


def tracked_files(repo: Path) -> list[str]:
    code, out = git(repo, "ls-files")
    if code != 0:
        return []
    return [line for line in out.splitlines() if line]


def gitlink_paths(repo: Path) -> frozenset[str]:
    """Submodule paths, which `git ls-files` reports as mode-160000 entries."""
    code, out = git(repo, "ls-files", "--stage")
    if code != 0:
        return frozenset()
    paths = set()
    for line in out.splitlines():
        if line.startswith("160000 ") and "\t" in line:
            paths.add(line.split("\t", 1)[1])
    return frozenset(paths)


def stale(bundle: Bundle) -> dict:
    repo = bundle.repo
    findings: list[dict] = []
    tracked = tracked_files(repo)
    gitlinks = gitlink_paths(repo)
    covered: set[str] = set()

    code, _ = git(repo, "rev-parse", "--verify", "HEAD")
    has_head = code == 0

    for doc in bundle.concepts:
        raw_sources = doc.meta.get("sources")
        if not raw_sources:
            continue
        if not isinstance(raw_sources, list):
            raw_sources = [raw_sources]
        patterns = normalize_sources(raw_sources, repo, gitlinks)
        if not patterns:
            continue

        spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
        matched = [f for f in tracked if spec.match_file(f)]
        covered.update(matched)

        if not matched:
            findings.append(
                {
                    "code": "S005",
                    "concept": doc.rel,
                    "message": f"`sources` matches no tracked file: {patterns}",
                }
            )
            continue

        pathspecs = [f":(glob){p}" for p in patterns]
        recorded = str(doc.meta.get("source_commit") or "").strip()

        # Uncommitted edits in the concept's sources.
        _, dirty = git(repo, "status", "--porcelain", "--", *pathspecs)
        if dirty:
            findings.append(
                {
                    "code": "S002",
                    "concept": doc.rel,
                    "message": "sources have uncommitted changes",
                    "files": porcelain_paths(dirty)[:20],
                }
            )

        if not has_head:
            continue

        if not recorded:
            findings.append(
                {
                    "code": "S003",
                    "concept": doc.rel,
                    "message": "has `sources` but no `source_commit`; cannot tell if it is current",
                }
            )
            continue

        code, _ = git(repo, "cat-file", "-e", f"{recorded}^{{commit}}")
        if code != 0:
            findings.append(
                {
                    "code": "S006",
                    "concept": doc.rel,
                    "message": f"`source_commit` {recorded[:12]} is not in this repo "
                    "(history rewritten?) — re-review against HEAD",
                }
            )
            continue

        code, _ = git(repo, "merge-base", "--is-ancestor", recorded, "HEAD")
        if code != 0:
            findings.append(
                {
                    "code": "S006",
                    "concept": doc.rel,
                    "message": f"`source_commit` {recorded[:12]} is not an ancestor of HEAD "
                    "— re-review against HEAD",
                }
            )
            continue

        _, changed = git(repo, "diff", "--name-only", f"{recorded}..HEAD", "--", *pathspecs)
        if changed:
            _, commits = git(repo, "log", "--oneline", f"{recorded}..HEAD", "--", *pathspecs)
            findings.append(
                {
                    "code": "S001",
                    "concept": doc.rel,
                    "message": f"sources changed in {len(commits.splitlines())} commit(s) since "
                    f"{recorded[:12]}",
                    "files": changed.splitlines()[:20],
                    "commits": commits.splitlines()[:10],
                }
            )

    # Coverage: tracked source files no concept claims.
    ignore_file = bundle.root / ".okfignore"
    patterns = list(DEFAULT_IGNORE)
    if ignore_file.exists():
        # A user-supplied .okfignore replaces the defaults; it does not extend them.
        patterns = [
            line.strip()
            for line in ignore_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    standalone = False
    try:
        bundle_rel = str(bundle.root.resolve().relative_to(repo.resolve())).replace(os.sep, "/")
        if bundle_rel == ".":
            # The bundle *is* the repo — there is no separate code to cover.
            standalone = True
        else:
            patterns.append(f"{bundle_rel}/**")
    except ValueError:
        pass
    ignore = pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    gaps: dict[str, list[str]] = {}
    for f in [] if standalone else tracked:
        if f in covered or ignore.match_file(f):
            continue
        # A gitlink is a whole vendored repo, not a file at the tree root —
        # report it under its own name rather than bucketing it into ".".
        if f in gitlinks:
            top = f
        elif "/" in f:
            top = f.split("/")[0]
        else:
            top = "."
        gaps.setdefault(top, []).append(f)

    return {
        "findings": findings,
        "coverage_gaps": [
            {"code": "S004", "path": k, "count": len(v), "sample": sorted(v)[:8]}
            for k, v in sorted(gaps.items())
        ],
    }


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------

INDEX_ENTRY_RE = re.compile(r"^\*\s+\[[^\]]*\]\(\s*([^)\s]+)\s*\)\s*(?:-\s*(.*))?$")


def existing_descriptions(index_path: Path) -> dict[str, str]:
    """Preserve hand-written descriptions for entries we cannot derive (subdirs)."""
    if not index_path.exists():
        return {}
    out = {}
    for line in index_path.read_text(encoding="utf-8").splitlines():
        m = INDEX_ENTRY_RE.match(line.strip())
        if m and m.group(2):
            out[m.group(1)] = m.group(2).strip()
    return out


def directory_contents(directory: Path, bundle: Bundle) -> tuple[list[Doc], list[Path]]:
    concepts = [d for d in bundle.concepts if d.path.parent == directory]
    subdirs = [
        c
        for c in sorted(directory.iterdir())
        if c.is_dir() and not c.name.startswith(".") and has_concepts(c)
    ]
    return concepts, subdirs


def render_index(directory: Path, bundle: Bundle) -> str:
    is_root = directory == bundle.root
    kept = existing_descriptions(directory / "index.md")
    concepts, subdirs = directory_contents(directory, bundle)

    groups: dict[str, list[Doc]] = {}
    for doc in concepts:
        groups.setdefault(doc.type or "Concept", []).append(doc)

    lines: list[str] = []
    if is_root:
        lines += ["---", 'okf_version: "0.1"', "---", ""]

    for type_name in sorted(groups):
        lines.append(f"# {type_name}")
        lines.append("")
        for doc in sorted(groups[type_name], key=lambda d: d.title.lower()):
            entry = f"* [{doc.title}]({doc.path.name})"
            desc = doc.description or kept.get(doc.path.name, "")
            if desc:
                entry += f" - {desc}"
            lines.append(entry)
        lines.append("")

    if subdirs:
        lines.append("# Subdirectories")
        lines.append("")
        for child in subdirs:
            target = f"{child.name}/"
            entry = f"* [{derive_title(child)}]({target})"
            desc = kept.get(target) or kept.get(f"{child.name}/index.md", "")
            if desc:
                entry += f" - {desc}"
            lines.append(entry)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def index_dirs(bundle: Bundle) -> list[Path]:
    """Every directory that needs an index: concept/index dirs and all their
    ancestors up to the root, so an intermediate directory with only
    subdirectories still gets the index.md its parent's index links to."""
    dirs = {bundle.root}
    for doc in [*bundle.concepts, *bundle.indexes]:
        directory = doc.path.parent
        while directory != bundle.root:
            dirs.add(directory)
            directory = directory.parent
    return sorted(dirs)


def run_index(bundle: Bundle, write: bool) -> list[dict]:
    changes = []
    for directory in index_dirs(bundle):
        target = directory / "index.md"
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current is not None and MANUAL_MARKER in current:
            continue
        concepts, subdirs = directory_contents(directory, bundle)
        if not concepts and not subdirs and directory != bundle.root:
            # Nothing to render. Never truncate an existing index to an empty file.
            continue
        desired = render_index(directory, bundle)
        if current == desired:
            continue
        rel = str(target.relative_to(bundle.root)).replace(os.sep, "/")
        changes.append({"file": rel, "action": "create" if current is None else "update"})
        if write:
            target.write_text(desired, encoding="utf-8")
    return changes


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------


def emit(payload: dict, as_json: bool, human) -> None:
    if as_json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        human(payload)


def main() -> int:
    # Shared flags are accepted on either side of the subcommand: `okf.py --json
    # stale` and `okf.py stale --json` both work. SUPPRESS keeps the subparser
    # from clobbering a value already set before the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--bundle", default=argparse.SUPPRESS, help="bundle root (default: ./wiki)")
    common.add_argument("--repo", default=argparse.SUPPRESS, help="repo the wiki documents")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="machine-readable output")

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--bundle", default="wiki", help="bundle root (default: ./wiki)")
    parser.add_argument("--repo", default=None, help="repo the wiki documents (default: git root of bundle)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_lint = sub.add_parser("lint", parents=[common], help="conformance, links, orphans, index coverage")
    p_lint.add_argument("--strict", action="store_true", help="treat warnings as errors")

    sub.add_parser("stale", parents=[common], help="git-derived staleness and coverage gaps")

    p_index = sub.add_parser("index", parents=[common], help="regenerate index.md files")
    p_index.add_argument("--write", action="store_true", help="write changes (default: dry run)")

    args = parser.parse_args()

    root = Path(args.bundle).expanduser().resolve()
    if not root.is_dir():
        print(f"error: bundle root not found: {root}", file=sys.stderr)
        return 2

    if args.repo:
        repo = Path(args.repo).expanduser().resolve()
    else:
        code, out = git(root, "rev-parse", "--show-toplevel")
        repo = Path(out) if code == 0 else root

    bundle = load_bundle(root, repo)

    if args.cmd == "lint":
        errors, warnings = lint(bundle)

        def human(_):
            for item in errors:
                print(f"ERROR  {item['code']}  {item['file']}: {item['message']}")
            for item in warnings:
                print(f"warn   {item['code']}  {item['file']}: {item['message']}")
            print(
                f"\n{len(bundle.concepts)} concepts, {len(errors)} error(s), {len(warnings)} warning(s)"
            )
            if not errors:
                print("conformant with OKF v0.1")

        emit({"errors": errors, "warnings": warnings}, args.json, human)
        return 1 if errors or (args.strict and warnings) else 0

    if args.cmd == "stale":
        result = stale(bundle)

        def human(res):
            for item in res["findings"]:
                print(f"{item['code']}  {item['concept']}: {item['message']}")
                for f in item.get("files", []):
                    print(f"        ~ {f}")
                for c in item.get("commits", []):
                    print(f"        · {c}")
            for gap in res["coverage_gaps"]:
                print(f"S004  {gap['path']}: {gap['count']} tracked file(s) no concept claims")
                for f in gap["sample"]:
                    print(f"        ? {f}")
            if not res["findings"] and not res["coverage_gaps"]:
                print("wiki is in sync with the repo")

        emit(result, args.json, human)
        return 1 if result["findings"] else 0

    if args.cmd == "index":
        changes = run_index(bundle, write=args.write)

        def human(res):
            for change in res["changes"]:
                verb = "wrote" if args.write else "would " + change["action"]
                print(f"{verb}: {change['file']}")
            if not res["changes"]:
                print("all index.md files up to date")

        emit({"changes": changes}, args.json, human)
        return 0 if args.write or not changes else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
