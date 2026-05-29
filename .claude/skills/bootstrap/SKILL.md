---
name: bootstrap
description: Set up this repository after a fresh clone — initialize git submodules and install their dependencies. Use when the user asks to "bootstrap", "set up the repo", "set up after clone", "install dependencies for the first time", "initial setup", "freshly cloned, what do I do", or any equivalent fresh-checkout request. Distinct from `update-dependencies`, which refreshes already-installed submodules.
---

# Bootstrap the repo

Brings a freshly cloned working copy to a runnable state: pulls submodule sources and installs their per-submodule dependencies. Currently only `trainingpeaks-mcp` needs this; add a section per submodule as more get vendored.

Run everything from the repo root: `/home/dbushev/projects/4e6/claude-skills`.

## Step 1 — initialize submodules

```bash
git submodule update --init --recursive
```

This populates every path listed in `.gitmodules` at the SHA recorded by the parent repo. `--recursive` covers any nested submodules.

If a submodule directory is already populated (e.g. user ran this themselves), the command is a no-op for that path — safe to run.

## Step 2 — per-submodule install

### `trainingpeaks-mcp`

This is a Python package installed in editable mode into a venv that lives **inside the submodule** (`trainingpeaks-mcp/.venv/`), so the `tp-mcp` wrapper script ends up at the path that [.mcp.json](../../../.mcp.json) expects (`trainingpeaks-mcp/.venv/bin/tp-mcp`).

**Authoritative install instructions live in the submodule's [README.md](../../../trainingpeaks-mcp/README.md)** — read it before installing in case upstream changed something (extras, Python version, auth flow). The "Manual Setup → Step 1: Install" and "Step 2: Authenticate" sections are the ones that apply here.

Two project-specific deviations from the README:

1. **Venv path is fixed** — must be `trainingpeaks-mcp/.venv/` (not a sibling, not `~/.venvs/...`), because `.mcp.json` points the MCP server at `trainingpeaks-mcp/.venv/bin/tp-mcp`. Do not move it.
2. **Install with the `[browser]` extra** — the README's Step 1 omits it (it's added later in Step 2 Option A); install it up-front so `tp-mcp auth --from-browser` works without a second `pip install`.

Concrete commands (cross-check against the README before running — extras or commands may have moved):

```bash
python3 -m venv trainingpeaks-mcp/.venv
trainingpeaks-mcp/.venv/bin/pip install -e "trainingpeaks-mcp[browser]"
```

Use the venv's own `pip` so we don't accidentally hit a system Python.

**If `trainingpeaks-mcp/.venv/` already exists**, don't recreate it — assume the user has a working install and skip to Step 3. If they want a clean rebuild they'll ask.

## Step 3 — authentication (user runs this, not Claude)

The cookie auth flow needs a real browser session and stores secrets in the system keyring; both are outside what Claude should drive. Tell the user to run **one** of the following themselves, depending on whether they're logged into TrainingPeaks in a local browser:

- Auto-extract from a logged-in browser (easiest):
  ```
  ! trainingpeaks-mcp/.venv/bin/tp-mcp auth --from-browser auto
  ```
  (Replace `auto` with `chrome`, `firefox`, `safari`, or `edge` if the autodetect picks the wrong one.)

- Manual cookie paste:
  ```
  ! trainingpeaks-mcp/.venv/bin/tp-mcp auth
  ```
  Then follow the README's "Option B: Manual cookie entry" steps — DevTools → Application → Cookies → copy `Production_tpAuth` → paste when prompted.

The `!` prefix runs the command in this Claude Code session so the prompt output lands in the conversation. After auth completes, verify with:

```
! trainingpeaks-mcp/.venv/bin/tp-mcp auth-status
```

## Step 4 — restart Claude Code

The MCP server is registered at project scope in [.mcp.json](../../../.mcp.json) and only spawns when Claude Code starts in this directory. After a fresh bootstrap, remind the user to restart Claude Code (or run `/mcp` to reconnect) so the `mcp__trainingpeaks__tp_*` tools become available.

## Step 5 — report

Tell the user:

1. Which submodules were initialized (and from what URL / at what SHA — `git -C <sub> rev-parse --short HEAD`).
2. Whether each install ran or was skipped (and why — e.g. "venv already present").
3. The exact `tp-mcp auth` command for them to run, plus the restart reminder.

Do **not** attempt to run `tp-mcp auth` yourself — it's interactive and touches the system keyring. Hand it off.

## Failure modes

- **`git submodule update --init` fails with network error** → the submodule URL in `.gitmodules` is a public GitHub repo; check connectivity. Don't fall back to a different URL.
- **`python3 -m venv` fails** → the host likely lacks `python3-venv` (Debian/Ubuntu) or the Python install is broken. Surface the error and stop; don't try alternative interpreters silently.
- **`pip install -e "trainingpeaks-mcp[browser]"` fails on a specific extra** → re-read the submodule README; the extras name may have changed. Don't paper over by dropping the extra.
- **The venv already exists but `tp-mcp` is missing from `.venv/bin/`** → editable install was never run or was interrupted. Re-run the `pip install` step; do not recreate the venv unless the user asks.
