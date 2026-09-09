# The bundle's own instruction files

Two files written **into** the bundle by A5, so that the rules for editing it
arrive with the directory instead of having to be sought out. Read this file when
running A5; it is not needed for any other operation.

## Contents

- **Before writing either one** — the collision check, which is a `lint` run and
  not an `ls`, and what to do with each kind of file it finds.
- **`<bundle>/CLAUDE.md`** — the template.
- **`<bundle>/AGENTS.md`** — the template, which points at the first rather than
  repeating it.
- **What they reach, and what they do not** — three ways the mechanism does not
  fire, and why a generated index cannot link them.

## Before writing either one

**Check for a collision first**, and check it with `lint` rather than by eye. A
bundle that predates A5 may already hold a concept at one of these names, at any
depth and in any case — `architecture/agents.md` is an ordinary page name under
this skill's own kebab-case convention, and it stops being a concept the moment
these rules apply to it:

```sh
"$OKF/.venv/bin/python" "$OKF/okf.py" --bundle "$WIKI" lint     # read every W018
```

`ls` is the wrong instrument: the exempt names are three, not two, the match is
case-insensitive, and a collision three directories down is the likely one.
**Run `lint` before `index --write`, not in A4's order** — by the time A4's
warning prints, its own `index --write` has already dropped the page's entry.

* **A file with YAML frontmatter is a concept**, not instructions. `okf.py` skips
  these names, so it would drop out of the index, out of `stale`, and out of the
  concept count, silently. `lint` reports it as `W018`. Rename the concept and
  fix its inbound links before writing anything here.
* **A file without frontmatter is already doing this job.** Merge into it; do not
  overwrite. The templates below are a starting point, not a canonical form to
  restore.

## `<bundle>/CLAUDE.md`

````markdown
# This directory is an OKF knowledge bundle

Durable knowledge about this project: decisions and their rationale, invariants,
domain vocabulary, module boundaries, gotchas. **Not** documentation of the code
— the code documents itself, and a page restating it is wrong within a week.

**Invoke the `llm-wiki` skill before writing or editing anything here.** It
carries the frontmatter contract, the concept types, the half-life rule that
decides what may be written at all, and the index and lint steps that follow
every edit. Without it you will produce a page that looks fine and is not:
missing `type`, an unpinned `source_commit`, absent from its index.

Reading needs no skill. Start at `index.md` and drill down; don't read the whole
bundle. If a page contradicts the code, reality wins — say so rather than reading
past it.

Three things hold either way:

- `index.md` and `log.md` are reserved names, and `CLAUDE.md`, `CLAUDE.local.md`
  and `AGENTS.md` are instructions. Every other `.md` here is a concept and needs
  a `type`.
- Every edit is followed by `okf.py index --write` and `okf.py lint`. That script
  ships with the `llm-wiki` skill. If you do not have it, say the index was not
  regenerated rather than skipping the step in silence — a stale index is exactly
  what it catches.
- A wiki change lands in the same commit as the change it describes.
````

## `<bundle>/AGENTS.md`

Points at `CLAUDE.md` rather than repeating it, so the two cannot drift:

````markdown
# AGENTS.md

The instructions for this directory are in [CLAUDE.md](CLAUDE.md). Read it before
writing anything here.

The `llm-wiki` skill it names is Claude Code's. Without it, follow that file
directly and stay conservative: copy the frontmatter shape of a neighbouring
page, and never invent a `type`.
````

## What they reach, and what they do not

**Only Claude Code loads either automatically**, and only `CLAUDE.md` — a nested
one is read when Claude reads *any* file at or below that directory, which is what
makes a single file at the bundle root cover every concept under it. `AGENTS.md`
is for hosts that read that name instead; a host that reads neither gets nothing.

Three ways it does not fire, and the third is the largest:

* An agent that **writes a new page without reading one first** never triggers it.
* A host that reads neither filename gets nothing, by construction.
* **Only the file-reading tools trigger it, not `cat`, `sed` or `grep`.** An agent
  told to prefer shell commands for file work — an increasingly common
  instruction, and the one under which a bundle is most likely to be edited by
  `sed -i` or a heredoc — never loads the file at all. That is the write path,
  which is the path this exists to close.

So it converts a rule you had to go looking for into one that arrives with the
directory. It is not a gate, and only a `PreToolUse` hook is.

**Do not link them from a generated `index.md`.** `index --write` renders indexes
from concept frontmatter, so a hand-added link to either file is stripped on the
next run unless that index carries the `<!-- okf:manual -->` marker — which costs
the index its regeneration. They are reached by the host, not by navigation.
