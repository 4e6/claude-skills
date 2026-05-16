# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A personal collection of Claude Code **skills**, scoped to this project only. Skills live in [.claude/skills/](.claude/skills/) so they're auto-loaded when Claude Code is launched from this directory (or any subdirectory) and are **not** available globally. There is no application to build, deploy, or test — the artifacts here are the skills themselves.

Each subdirectory of `.claude/skills/` is one skill, identified by a `SKILL.md` with YAML frontmatter (`name`, `description`). The `description` field is what Claude reads to decide whether to invoke a skill, so it must enumerate the trigger phrases / user intents that should activate it.

## Skills currently in this repo

- [weekly-meal-plan](.claude/skills/weekly-meal-plan/SKILL.md) — generates a Mon→Sun triathlon meal plan from TrainingPeaks data, renders to PDF, uploads to Google Drive, and answers follow-up questions during the week. Owns its own state under `plans/` (one markdown file per week, which doubles as the cache) and `favorite-recipes.md`.
- [desmor-pool-schedule](.claude/skills/desmor-pool-schedule/SKILL.md) — looks up open-swim hours for the Desmor pool in Rio Maior, with a one-week cache in `cache/current.json` and a Gmail recheck for mid-week schedule corrections.

## External dependencies these skills assume

The skills shell out to tools/services that must be present on the host. None of this is installed by this repo — it's the user's environment:

- **TrainingPeaks MCP** (`mcp__trainingpeaks__tp_*`) — see the user's global CLAUDE.md for tool routing. Used by `weekly-meal-plan` to pull planned workouts, fitness (CTL/ATL/TSB), and the focus/next event.
- **Gmail MCP** (`mcp__claude_ai_Gmail__*`) — `desmor-pool-schedule` uses it to scan for mid-week correction emails from `secretaria.piscinas@desmor.pt`.
- **Composio Gemini** (`COMPOSIO_MULTI_EXECUTE_TOOL` → `GEMINI_GENERATE_IMAGE`, `gemini-2.5-flash-image`) — `weekly-meal-plan` action A6.5 generates per-recipe food photos. Skipping is acceptable; the renderer falls back to emoji banners.
- **`chromium`** + **`python3` with `markdown` module** — required by [scripts/md-to-pdf.py](.claude/skills/weekly-meal-plan/scripts/md-to-pdf.py) for headless PDF rendering. On Arch: `pacman -S chromium`, `pip install --user markdown`.
- **`rclone`** with a pre-configured `gdrive:` remote pointing at the user's Google Drive — used to upload the rendered PDF to the `Meal Plans/` folder. The Google Drive MCP cannot handle a ~1 MB PDF in a single inline-base64 tool call, so `rclone` is the only supported path.
- **`magick`** (ImageMagick) — resizes Gemini's 1248×832 PNGs to 800×533 JPEG q85 before they're embedded in the PDF.

## Editing a skill

1. Edit the relevant `SKILL.md` (or scripts under it).
2. The skill is reloaded the next time Claude Code starts in this directory. No build step.
3. The `description:` frontmatter field is the *only* thing that controls when Claude reaches for the skill — if you change behavior, make sure the description still matches the trigger phrases you want.

## Conventions specific to `weekly-meal-plan`

The PDF renderer is **not** a generic markdown-to-HTML converter — `parse_plan()` in [md-to-pdf.py](.claude/skills/weekly-meal-plan/scripts/md-to-pdf.py) parses the schema documented in SKILL.md section A4 directly (`## Training Overview`, `## Meal Plan`, `### {Day} — {Session}`, `## Shopping List` with `### {Category}`, `## Recipes` with `### {Day}` and `#### {Dish}` plus the `**Tags:**` / `**Per serving:**` / `**Time:**` metadata block). Changing those headings or bullet shapes will silently drop content from the PDF. If you adjust the schema in SKILL.md, update the parser to match.

Recipe images are looked up by slug (`slugify(dish_title)` — NFKD normalize, strip accents, lowercase, non-alphanumerics → `-`) at `plans/images/{week-stem-minus-meal-plan-prefix}/{slug}.{jpg|jpeg|png|webp}`. The same slug function must be used when saving generated images.

## Conventions specific to `desmor-pool-schedule`

`cache/current.json` always reflects the **original** PDF in `pools[*].schedule`; mid-week corrections live in `date_overrides[date][pool]` as a *full replacement list of slots*, not a diff. This separation means the override logic can be re-derived if it changes. The merged view (override wins per-day) is computed at read time, not persisted.
