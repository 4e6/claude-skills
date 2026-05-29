---
name: update-dependencies
description: Pull the latest versions of vendored git submodules in this repo and re-run their install steps when dependency manifests changed. Use when the user asks to "update dependencies", "update submodules", "update deps", "sync deps", "pull latest tp-mcp", "upgrade trainingpeaks-mcp", or any equivalent request to refresh vendored tooling.
---

# Update dependencies

This repo vendors external tooling as git submodules (currently only [trainingpeaks-mcp/](../../../trainingpeaks-mcp)). This skill brings each submodule up to its tracked upstream branch and re-runs the per-submodule install step **only when something that affects the install actually changed**.

Run everything from the repo root: `/home/dbushev/projects/4e6/claude-skills`.

## Step 1 — capture old SHAs

Before pulling anything, record each submodule's current commit so we can diff against it after. Don't rely on `HEAD@{1}` / reflog — a fresh submodule clone has no reflog.

```bash
old_tpmcp=$(git -C trainingpeaks-mcp rev-parse HEAD)
```

Add one line per submodule if more get vendored later.

## Step 2 — fetch latest commits

```bash
git submodule update --remote --merge --recursive
```

`--remote` advances to the tip of the tracked branch (recorded in `.gitmodules`; defaults to the submodule's default branch). `--merge` preserves any local changes you might have inside a submodule by merging rather than detaching. `--recursive` covers nested submodules if any exist.

## Step 3 — per-submodule post-update actions

### `trainingpeaks-mcp` (Python, editable install via `pip install -e .[browser]`)

```bash
new_tpmcp=$(git -C trainingpeaks-mcp rev-parse HEAD)
```

**Case A — `old_tpmcp == new_tpmcp`:** nothing changed upstream. Skip. Report "already up to date."

**Case B — SHAs differ:** check whether any install-affecting file changed between the two:

```bash
git -C trainingpeaks-mcp diff --name-only "$old_tpmcp" "$new_tpmcp" -- \
  pyproject.toml setup.py setup.cfg uv.lock 'requirements*.txt'
```

- **No output** → only source files changed. The editable install reads source live from the submodule path, so the new code is already in effect for *future* server starts. No reinstall needed.
- **Any output** → dependencies and/or `[project.scripts]` entry points may have changed. Re-run the install so pip can sync deps and regenerate the `tp-mcp` wrapper in `.venv/bin/`:

  ```bash
  trainingpeaks-mcp/.venv/bin/pip install -e "trainingpeaks-mcp[browser]"
  ```

  Use the venv's own `pip` so we don't accidentally hit a system Python.

**Do NOT recreate the venv from scratch as part of this skill.** Deleting `trainingpeaks-mcp/.venv/` is appropriate only when the host Python minor version changed, the install got corrupted, or the user asks for a clean rebuild. In that case fall back to the bootstrap recipe in [CLAUDE.md](../../../CLAUDE.md) ("External dependencies these skills assume").

If the submodule advanced but the venv directory doesn't exist at all, that's a bootstrap situation, not an update — point the user at the CLAUDE.md recipe instead of silently running it.

## Step 4 — report and prompt

Tell the user:

1. Which submodules advanced, and by how many commits (`git -C <sub> log --oneline "$old".."$new"` gives a compact summary).
2. For each, whether a reinstall ran and why (which manifest files changed).
3. **If `trainingpeaks-mcp` advanced** — remind them to restart Claude Code. The currently running MCP server process is the *old* binary; project-scope `.mcp.json` only re-spawns it on restart. Editable-install source changes do NOT propagate to the running process.
4. The submodule pointer change is staged-but-not-committed (`git status` will show `modified: trainingpeaks-mcp` and possibly `modified: .gitmodules`). Let the user review and commit themselves — never auto-commit a submodule bump.

## Optional verification (user runs, not Claude)

After restart, the user can confirm the new server is healthy by asking Claude something that exercises a TP tool (e.g. "check my TrainingPeaks auth status") — that round-trips through `mcp__trainingpeaks__tp_auth_status`. Claude cannot run `tp-mcp` directly from the shell here; that's blocked as untrusted-code execution.
