---
name: llm-wiki
description: Create and maintain an LLM-wiki — a durable, agent-readable knowledge base for a codebase, stored as an Open Knowledge Format (OKF v0.1) bundle of markdown + YAML frontmatter. Use when the user asks to "create a wiki", "set up an LLM-wiki", "start a knowledge base", "document this project", "sync/update the wiki", "is the wiki stale", "lint the wiki", "record this decision", "add an ADR", or asks a durable question the wiki should answer ("why do we do X", "what does Y mean here", "how do I deploy"). Also consider proactively when the user starts, scaffolds, or initializes a new project, and after any change that alters architecture, a decision, an invariant, a data model, or a third-party integration.
---

# LLM-wiki (Open Knowledge Format)

An **LLM-wiki** is a knowledge base an agent both writes and reads: durable facts
about a project distilled into small, cross-linked markdown pages. It differs
from RAG in *when* the synthesis happens — RAG re-derives an answer from raw
chunks on every query; a wiki pays that cost once, at ingest, and the result
compounds. It differs from a README in that it is structured for retrieval.

**Open Knowledge Format (OKF)** is that pattern, specified. Google Cloud's OKF
v0.1 spec explicitly names "LLM 'wiki' repositories" as the practice it
standardizes, so this skill treats them as one thing: the wiki *is* an OKF
bundle. Following the spec means the wiki is readable by any agent or human, is
diffable in git, needs no SDK, and can be handed to a different tool later.

Read [reference/okf-v0.1.md](reference/okf-v0.1.md) before writing any page. Read
[reference/concept-types.md](reference/concept-types.md) before choosing a `type`.

> **Scope note.** This skill is version-controlled in the `claude-skills` repo but
> symlinked into `~/.claude/skills/llm-wiki`, so it loads globally and operates on
> whatever project you are in. It is the one skill in that repo that targets *other*
> repos. Because of that, always invoke the script by absolute path (see
> [Scripts](#scripts)) — the working directory is the target project, not here.

## The half-life rule

This is the single decision that determines whether the wiki is an asset or a
liability. **Store only what the code and git history cannot already say.**

A page that restates a function signature is wrong within a week and actively
harms the reader, because now two sources disagree. A page that records *why the
signature is that shape* stays true for years.

Rank every candidate fact by half-life. Write the top half; refuse the bottom:

| Write | Never write |
|---|---|
| Why a decision was made, what was rejected, what it cost | Function/class signatures, parameter lists |
| Invariants and the consequence of violating them | File trees, directory listings, line numbers |
| Domain vocabulary as *this project* uses it | Anything `git log` answers ("added in v2") |
| Module responsibility and boundaries | Restated code comments |
| Gotchas, sharp edges, "we tried that, it failed" | Step-by-step code walkthroughs |
| Operational playbooks and their verification steps | Dependency version numbers |
| Third-party quirks discovered the hard way | Content already in `CLAUDE.md` |
| What is still unknown (`Open Question`) | Speculation stated as fact |

When unsure, apply the test: *would this page still be correct after a big
refactor that preserved behaviour?* If no, it belongs in the code.

This rule is also the sync strategy. Low-half-life content is what forces
constant re-syncing; by simply not writing it, most staleness never arises.

## Layout

The bundle lives **inside the project repo**, committed with the code. That is
what lets a single commit change behaviour and the knowledge about it together.

```
<project>/
├── CLAUDE.md            # points at the wiki (see A5) — this is the read path
└── wiki/                # the OKF bundle root
    ├── index.md         # okf_version: "0.1"; the only index with frontmatter
    ├── log.md           # newest-first, ISO-dated change history
    ├── overview.md      # type: Overview
    ├── .okfignore       # optional; gitignore syntax; tunes coverage reporting
    ├── architecture/    # type: Module
    ├── decisions/       # type: Decision  (NNNN-slug.md, never renumbered)
    ├── domain/          # type: Glossary Term | Data Model
    ├── invariants/      # type: Invariant
    ├── playbooks/       # type: Playbook
    ├── integrations/    # type: Integration
    ├── gotchas/         # type: Gotcha
    ├── questions/       # type: Open Question
    └── references/      # type: Reference (mirrored external material)
```

Create directories lazily — only when a real page needs one. An empty
`gotchas/` teaches nothing.

## Frontmatter contract

OKF requires **only `type`** (§4.1). Everything else is recommended or a
producer extension. Use these, and nothing else, so the scripts can reason:

```yaml
---
type: Module                    # REQUIRED. From reference/concept-types.md.
title: Auth                     # recommended
description: One sentence.      # recommended — index entries reuse it verbatim
tags: [auth]                    # recommended
timestamp: 2026-07-10T09:00:00Z # recommended — last *meaningful* change
resource: https://…             # only if a canonical external asset exists
# --- producer extensions this skill defines ---
sources: [src/auth/**]          # repo-relative gitignore-syntax globs this page describes
source_commit: 4f2a1c9e…        # commit at which `sources` was last actually read
status: accepted                # Decision / Open Question only
superseded_by: /decisions/0009-mtls.md
---
```

`sources` + `source_commit` are the entire sync mechanism. A page with `sources`
can be checked against git; a page without them (a `Gotcha`, a `Glossary Term`)
is timeless and is never reported stale. **Only add `sources` to a page whose
truth actually depends on that code.** Over-tagging manufactures false staleness.

Link with plain markdown, bundle-absolute: `[auth](/architecture/auth.md)`.
Not `[[wikilinks]]` — OKF §5. Broken links are legal (§5.3), so linking a page
you intend to write next is fine.

## Operations

### A1 — Bootstrap a new wiki

1. Confirm with the user before creating anything. Ask what the project *is* if
   it isn't obvious; a wiki seeded from a misread is worse than none.
2. Explore the repo to find real subsystems. Do not mirror the directory tree —
   group by responsibility.
3. Write `wiki/index.md` (with `okf_version: "0.1"`), `wiki/overview.md`, and a
   *small* set of pages you can actually support: typically `overview.md`, one
   `Module` per genuine subsystem, and any `Decision` / `Gotcha` the user
   volunteers. **Ten good pages beat sixty generated ones.**
4. For pages with `sources`, set `source_commit` to `git rev-parse HEAD`.
5. Do A5 (wire up the read path), then A4 (index + lint).
6. Seed `log.md` with a `**Initialization**` entry.

Never invent facts to fill a template. If you don't know why a decision was
made, write an `Open Question`, or ask the user — that is the wiki working as
intended.

### A2 — Ingest (add or extend knowledge)

Triggered by "document X", "record this decision", or by you noticing a durable
fact during other work.

1. Decide the `type` from [reference/concept-types.md](reference/concept-types.md).
   If nothing fits, it probably fails the half-life rule.
2. Check for an existing page first — **update in place rather than adding a
   near-duplicate**. Two pages that disagree are the main failure mode of a wiki.
3. Write the page. Prefer headings/lists/tables over prose (OKF §4.2). Cite
   external claims under `# Citations` (§8).
4. Cross-link both ways: the new page links its neighbours, and at least one
   existing page links to it. An unlinked page is invisible (`W011`).
5. Set `timestamp` (`date -u +%Y-%m-%dT%H:%M:%SZ`) and, if it has `sources`,
   `source_commit`.
6. Run A4, append to `log.md`.

`Decision` pages are append-only. To reverse one, write a new ADR, set the old
page's `status: superseded` and `superseded_by:`, and leave its reasoning intact.
The record of a wrong decision is worth more than its deletion.

### A3 — Sync with the code (the important one)

The wiki drifts silently. Run this on request ("sync the wiki", "is the wiki
stale?"), and proactively after landing a change that touched architecture, a
decision, an invariant, a data model, or an integration.

```bash
"$OKF/.venv/bin/python" "$OKF/okf.py" --bundle wiki stale --json
```

Then, per finding:

- **`S001` sources changed since `source_commit`** — read the actual diff before
  touching the page:
  ```bash
  git diff <source_commit>..HEAD -- <sources>
  ```
  Then classify, exactly as `update-dependencies` classifies submodule bumps:

  - **Cosmetic** — renames, formatting, comments, test-only edits, changes that
    preserve responsibility and boundaries. **Touch, don't rewrite:** bump
    `source_commit` to `HEAD`, leave the body and `timestamp` alone, add no log
    entry. The page was already correct.
  - **Semantic** — a boundary moved, a responsibility changed, an invariant was
    added or broken, a dependency appeared. **Rewrite** the affected sections,
    bump `timestamp` *and* `source_commit`, and append to `log.md`.

  Never bump `source_commit` without having read the diff. That is how a wiki
  silently starts lying.

- **`S002` uncommitted changes in sources** — sync describes committed history
  only. Report it and stop; there is no commit to record. Offer to proceed after
  the user commits.

- **`S003` `sources` but no `source_commit`** — backfill from the last commit
  that touched them: `git log -1 --format=%H -- <sources>`.

- **`S005` `sources` matches nothing** — the code it described is gone. For a
  `Module`, delete the page and log a `**Deprecation**` entry. For a `Decision`,
  never delete: set `status: superseded`. Fix any inbound links.

- **`S006` `source_commit` unreachable or not an ancestor of HEAD** — history was
  rewritten (rebase, squash, amend), so the diff is meaningless. Re-review the
  page against HEAD from scratch, then re-pin.

- **`S004` coverage gap** — tracked code no page claims. Do **not** create one
  page per file. Ask whether the gap is a real subsystem worth a `Module`, or
  noise that belongs in `.okfignore`. Silence is a legitimate answer; not all
  code deserves knowledge.

Finish with A4. Show the user the wiki diff. **Never auto-commit** — the wiki is
their voice, and a wrong page is worse than a missing one.

### A4 — Index & lint

Always run both, in this order, after any wiki edit:

```bash
"$OKF/.venv/bin/python" "$OKF/okf.py" --bundle wiki index --write
"$OKF/.venv/bin/python" "$OKF/okf.py" --bundle wiki lint
```

`index` regenerates every `index.md` from concept frontmatter (grouping by
`type`), preserving hand-written subdirectory descriptions it cannot derive. An
`index.md` containing `<!-- okf:manual -->` is left untouched.

`lint` enforces OKF §9 conformance (`E…`) and reports rot (`W…`): broken links,
orphans, concepts missing from their index, absent `description`/`timestamp`.
Errors mean the bundle is non-conformant — fix them. Warnings are judgement:
`W010` on a deliberate forward reference is fine and expected.

### A5 — Wire up the read path

A wiki nobody opens is a liability. On bootstrap, add to the **project's**
`CLAUDE.md` (create it if absent):

```markdown
## Project knowledge

Durable knowledge about this project — architecture boundaries, decisions and
their rationale, invariants, domain vocabulary, gotchas — lives in an OKF
knowledge bundle at [wiki/](wiki/). **Start at [wiki/index.md](wiki/index.md)**
and drill down; don't read the whole bundle.

Keep it current: a change that alters a boundary, a decision, an invariant, a
data model, or an integration must update the wiki in the same commit.
```

That last sentence is the highest-leverage sync mechanism in this skill — same
commit, same review, no drift. Optionally offer a `SessionStart` hook running
`okf.py stale` for a once-per-session nudge (use the `update-config` skill); do
not install hooks unprompted.

### A6 — Query

Answer from the wiki before reading code. Load `wiki/index.md`, follow links to
the two or three relevant pages, answer, and cite them by path. This is what
progressive disclosure (§6) is for.

If the answer isn't there but was worth asking, that is an ingest signal: offer
to write it down (A2). If the wiki contradicts the code, **the code wins** —
then fix the page and log it.

## Scripts

The skill is loaded via a symlink, so **resolve the script by absolute path**;
`$PWD` is the target project. Set this once per session:

```bash
OKF=$(dirname "$(readlink -f ~/.claude/skills/llm-wiki)")/llm-wiki/scripts
# or simply: OKF=~/.claude/skills/llm-wiki/scripts   (symlinks resolve fine)
```

`okf.py` needs a venv, created on first use from `requirements.txt` (same
convention as `weekly-meal-plan`; `.venv/` is gitignored). Create it only if
`"$OKF/.venv/bin/python"` is missing:

```bash
python3 -m venv "$OKF/.venv" && "$OKF/.venv/bin/pip" install -r "$OKF/requirements.txt"
```

Always invoke as `"$OKF/.venv/bin/python" "$OKF/okf.py"` — never a system Python.
It shells out to `git`, so run it from inside the target repo: `--bundle` is
resolved against `$PWD` and `--repo` defaults to the bundle's git root. All three
subcommands accept `--json`.

The split is deliberate: the script does what is mechanically checkable
(conformance, link graph, orphans, git diffs, index rendering). Every judgement
— what a page should say, whether a diff is cosmetic or semantic, whether a
coverage gap deserves a page — stays with the model.

## Gotchas

- `index.md` and `log.md` are **reserved** (§3.1) — never a concept.
- Only the **root** `index.md` may carry frontmatter (§6). `E004` catches this.
- `sources` globs are **gitignore syntax** matched against `git ls-files`, so
  untracked files are invisible to coverage. A bare directory is expanded to
  `dir/**`.
- **The project's `.gitignore` needs no special handling** — coverage only ever
  sees tracked files, so ignored files are already excluded. Never merge
  `.gitignore` into `.okfignore`: a file that was committed and *later* ignored
  stays tracked (git's rule is "tracked beats ignored"), and hiding it would
  make the wiki look complete when it is not.
- **Submodules** are the one exception to the `dir/**` expansion. Git records a
  submodule as a single gitlink entry at its bare path and tracks none of its
  files in the parent, so `sources: [dep]` is matched exactly and *not* expanded.
  That makes a pointer bump fire `S001` on the page describing the vendored
  dependency — the only thing about a submodule the parent repo can observe.
- Coverage ignores prose, dotfiles, and tests by default. Override with
  `wiki/.okfignore` (which *replaces* the defaults rather than extending them).
- A page with no `sources` is never stale by construction. That is a feature —
  prefer timeless pages.
- Don't mirror `CLAUDE.md` into the wiki, or the repo into `architecture/`. Both
  create two sources of truth, which is the one thing a wiki must not do.
