# The bundle's own instruction files

Two files written **into** the bundle by A5, so that the rules for editing it
arrive with the directory instead of having to be sought out. Read this file when
running A5; it is not needed for any other operation.

## Before writing either one

**Check for a collision first.** A bundle that predates A5 may already hold a
concept at one of these paths, or a hand-customised instruction file:

```sh
ls <bundle>/CLAUDE.md <bundle>/AGENTS.md 2>/dev/null
```

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

## Two things about their reach

**Only Claude Code loads either automatically**, and only `CLAUDE.md` — a nested
one is read when Claude reads *any* file at or below that directory, which is what
makes a single file at the bundle root cover every concept under it. `AGENTS.md`
is for hosts that read that name instead; a host that reads neither gets nothing.
An agent that writes a new page without reading one first also gets nothing. This
converts a rule you had to go looking for into one that arrives with the
directory — it is not a gate.

**Do not link them from a generated `index.md`.** `index --write` renders indexes
from concept frontmatter, so a hand-added link to either file is stripped on the
next run unless that index carries the `<!-- okf:manual -->` marker — which costs
the index its regeneration. They are reached by the host, not by navigation.
