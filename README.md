# Claude Skills

A personal collection of [Claude Code](https://claude.com/claude-code) skills, scoped to this project. The skills live under [.claude/skills/](.claude/skills/) so they auto-load only when Claude Code is launched from this directory (or a subdirectory) — not globally.

## Skills

- **[weekly-meal-plan](.claude/skills/weekly-meal-plan/SKILL.md)** — Plans, renders, and serves weekly meal plans. Pulls planned workouts from the TrainingPeaks MCP, generates a Mon→Sun meal plan tailored to training load, renders it (plus per-day recipes) to PDF via headless Chromium, uploads the PDF to Google Drive, and answers follow-up questions during the week from the cached markdown.
- **[desmor-pool-schedule](.claude/skills/desmor-pool-schedule/SKILL.md)** — Looks up open-swim hours ("horário livre") at the Desmor / Escola de Natação de Rio Maior pool. Caches the current week's schedule from desmor.pt and rechecks Gmail for mid-week correction emails.
