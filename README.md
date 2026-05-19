# Claude Skills

A personal collection of [Claude Code](https://claude.com/claude-code) skills, scoped to this project. The skills live under [.claude/skills/](.claude/skills/) so they auto-load only when Claude Code is launched from this directory (or a subdirectory) — not globally.

## Skills

### [weekly-meal-plan](.claude/skills/weekly-meal-plan/SKILL.md)

Plans, renders, and serves weekly meal plans. Pulls planned workouts from the TrainingPeaks MCP, generates a Mon→Sun meal plan tailored to training load, renders it (plus per-day recipes) to PDF via headless Chromium, uploads the PDF to Google Drive, and answers follow-up questions during the week from the cached markdown.

**Dependencies**

- **TrainingPeaks MCP** (`mcp__trainingpeaks__tp_*`) — planned workouts, fitness (CTL/ATL/TSB), focus/next event.
- **Composio MCP** (`COMPOSIO_MULTI_EXECUTE_TOOL` → `GEMINI_GENERATE_IMAGE`, model `gemini-2.5-flash-image`) — per-recipe food photos. Optional; the renderer falls back to emoji banners if images are missing.
- **`chromium`** — headless PDF rendering (Arch: `pacman -S chromium`).
- **`python3`** with the **`markdown`** module — driven by [scripts/md-to-pdf.py](.claude/skills/weekly-meal-plan/scripts/md-to-pdf.py) (`pip install --user markdown`).
- **`rclone`** with a pre-configured `gdrive:` remote pointing at the user's Google Drive — uploads the PDF to `Meal Plans/`. The Google Drive MCP can't handle a ~1 MB PDF in a single inline-base64 call, so `rclone` is the only supported path.
- **`magick`** (ImageMagick) — resizes Gemini's 1248×832 PNGs to 800×533 JPEG q85 before they're embedded in the PDF.

### [desmor-pool-schedule](.claude/skills/desmor-pool-schedule/SKILL.md)

Looks up open-swim hours ("horário livre") at the Desmor / Escola de Natação de Rio Maior pool. Caches the current week's schedule from desmor.pt and rechecks Gmail for mid-week correction emails.

**Dependencies**

- **Gmail MCP** (`mcp__claude_ai_Gmail__search_threads`, `mcp__claude_ai_Gmail__get_thread`) — scans for mid-week correction emails from `secretaria.piscinas@desmor.pt`.
- **`curl`** — downloads the weekly `Horario_Livre-*.pdf` from desmor.pt.
- Network access to **`https://desmor.pt`**.
