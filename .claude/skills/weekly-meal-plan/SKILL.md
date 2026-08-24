---
name: weekly-meal-plan
description: Plan, render, and serve weekly triathlon meal plans. Use when the user asks to "make next week's plan", "create a meal plan", "what's today's menu", "show the shopping list", "what's in the fridge", or "how do I cook X". Pulls planned workouts from the TrainingPeaks MCP, generates a Mon→Sun meal plan tailored to training load, renders it (plus per-day recipes) to PDF via headless Chromium, uploads the PDF to the "Meal Plans" folder in Google Drive, and answers follow-up questions during the week from the cached markdown.
---

# Weekly meal plan

The user is a triathlete based in Portugal. Each week they ask for a meal plan that mirrors their TrainingPeaks training schedule, plus follow-up questions during the week. This skill owns the full lifecycle.

## Path resolution — read this first

This is a **project-scoped** skill. It lives under `<project>/.claude/skills/weekly-meal-plan/`, **not** the global `~/.claude/`. The correct absolute path is handed to you at skill launch as `Base directory for this skill: …`. **Always trust that launch banner over any path written in this file**, and **never use `~/.claude/skills/weekly-meal-plan/…`** — that directory does not exist and writing there creates a phantom tree the renderer/upload steps won't find.

Every shell example below starts by binding `$SKILL_DIR` to that base directory. Do the same — set it once from the launch banner, then use `$SKILL_DIR/...` for every path:

```bash
SKILL_DIR=<the "Base directory for this skill" value from skill launch>
# e.g. /home/dbushev/projects/4e6/claude-skills/.claude/skills/weekly-meal-plan
```

For Read/Write/Edit tool calls (which need a literal absolute path, not a shell variable), substitute that same base directory in by hand. Prose references like "the skill's `plans/`" mean `$SKILL_DIR/plans/`.

## Files this skill owns

Paths are relative to `$SKILL_DIR` (see Path resolution above):

```
$SKILL_DIR/                                     # = <project>/.claude/skills/weekly-meal-plan/
├── SKILL.md                                    # this file
├── plans/
│   ├── meal-plan-week-{month}-{day}-{year}.md  # one per week, source of truth and cache
│   ├── meal-plan-week-{month}-{day}-{year}.pdf # current week's rendered PDF (old ones pruned in A7.5)
│   └── images/week-{month}-{day}-{year}/        # per-recipe photos for the current week
├── reference/                                  # read on demand during action A only
│   ├── plan-schema.md                          # the plan .md schema the renderer parses (A4)
│   └── image-providers.md                      # recipe-image provider chain + pitfalls (A6.5)
└── scripts/
    ├── md-to-pdf.py                            # Markdown → PDF (headless Chromium)
    ├── gen-recipe-images.py                    # recipe photos on the Mac's GPU (A6.5)
    ├── requirements*.txt                       # pinned deps — one file per script
    └── .venv*/                                 # one virtualenv per script (gitignored; made on first use)
```

- The filename date is **the Monday of that week**, lowercase month: `meal-plan-week-may-18-2026.md`.
- The weekly `.md` IS the cache. Do not invent a JSON cache.
- The week runs Monday → Sunday.

## Action routing

Pick the action that fits the user's request. When ambiguous, default to the lightest read action.

| User intent | Action |
|---|---|
| "make / create / plan next week", "new meal plan", a fridge inventory dump | **A. Create the plan** |
| "today's menu / what am I eating today / what's for [meal]" | **B. Today's menu** |
| "shopping list", "what do I need to buy" | **C. Shopping list** |
| "how do I cook / make / prepare X", "recipe for X" | **D. Recipe lookup** |
| "what's in the fridge" (per the plan) | **E. Fridge contents** |

Use parallel tool calls within an action wherever steps are independent (e.g. fetching workouts + fitness from TrainingPeaks).

---

## A. Create the plan

### A1. Determine the target week's Monday

- Default: the **upcoming** Monday (today + days_until_next_monday; if today *is* Monday and the user says "next", advance by 7). When the user says "this week", use the current week's Monday.
- Get today's date in Europe/Lisbon: `TZ=Europe/Lisbon date +%Y-%m-%d` and `TZ=Europe/Lisbon date +%u` (1=Mon … 7=Sun).
- Confirm the target Monday back to the user in one short line before fetching workouts, so they can redirect if they meant a different week.

### A2. Fetch the schedule from TrainingPeaks

Run these in parallel (independent):

- `tp_get_workouts` for `{monday}` through `{monday+6}` — planned workouts: sport, duration, planned TSS, title/description.
- `tp_get_fitness` (CTL/ATL/TSB) for context on whether the week is going into fatigue or recovery.
- `tp_get_focus_event` and `tp_get_next_event` (only on the first week of planning a new training block, or when the user mentions a race) — to inform tone (taper week vs. build).

Auth fallback (rare): if any TP call fails on auth, run `tp_auth_status` then `tp_refresh_auth`, then retry.

If TrainingPeaks returns nothing for the week (rest week, off-season, MCP down), ask the user to describe the week's sessions before continuing.

**Race weeks — get the race distance.** If the week contains a workout titled `RACE` / `PRE-RACE` / `WARM-UP | …` on the final day, treat it as race week. The race itself is normally on the TrainingPeaks calendar as an event — call `tp_get_next_event` (and `tp_get_focus_event` if relevant) to pull the race name + distance directly. **Don't infer distance from the workout description** — the coach's notes typically list multiple distance options (e.g. *"In case its a 10K Race … Half Marathon … Marathon …"*) and don't tell you which one applies. If the event lookup doesn't return a clear distance, ask the user once: *"What's the distance for Sunday's race?"* before building the plan. Distance drives Saturday carb-load target (~5–7 g/kg for 10K, ~7–10 g/kg for HM+), in-race fueling (10K rarely needs gels; HM = 2–3 gels + isotonic; Marathon = continuous fueling), and post-race recovery depth.

### A3. Capture the fridge inventory

- If the user already pasted a list, use it.
- If they didn't, ask once, briefly: *"Anything currently in the fridge to use up?"* Accept "nothing" / "skip" and move on.

### A4. Build the meal plan

Follow the schema in [reference/plan-schema.md](reference/plan-schema.md) **exactly** — read that file now if you haven't already this session. It carries the document skeleton, the required per-recipe metadata lines, and how the Recipes section is organised day by day. `parse_plan()` in `scripts/md-to-pdf.py` parses those headings and bullet shapes directly, so any deviation silently drops content from the PDF.

#### Domain rules — follow when filling in the plan

- **Carb load tracks training load.** Use planned TSS first to rank the days (highest TSS = biggest fuel day); fall back to session type/duration only when TSS isn't available. Hard days get bigger carb portions, in-session fuel (bananas, dates, energy bars, isotonic), and post-session recovery (chocolate milk). Easy / recovery days are lighter — fewer carbs, no sports drinks, no recovery shake.
- **Reuse fridge items.** Where a meal uses something already in the fridge, append `*(use what's in fridge)*` to the bullet.
- **Every cooked portion gets eaten within the week.** This is a hard rule — cooked food that isn't scheduled spoils. When a recipe yields more than one serving (batch soups, stews, bolognese, chili, cooked grains, roasted veg, etc.), every serving must map to a specific meal slot inside the same Mon→Sun week. Make the mapping explicit in two places:
  - In the **Meal Plan** bullets: the cooking day says how many portions are made and eaten now, and each later day that finishes the leftovers references it. E.g. Tuesday dinner `Lentil soup (cook 2 — eat 1, reserve 1)` and Thursday lunch `Lentil soup (leftover from Tue)`.
  - In the recipe's serving line: spell out the allocation, e.g. `**Ingredients (2 servings — 1 Tue dinner, 1 Thu lunch)**`.
  - Pick batch sizes that divide cleanly into slots you actually have. If a dish only fits one meal this week, cook **one** serving — don't default to 2. Perishable leftovers (cooked fish, leafy salads, dressed dishes) should be consumed within ~2–3 days of cooking; don't park a Monday leftover on Sunday.
- **Bilingual shopping list.** Each item: English name + Portuguese name in parentheses, then the quantity, e.g. `Chicken breasts (peito de frango) — 1 kg`. Quantities should scale with the week's training load (more bananas/dates/energy bars/chocolate milk on big aerobic weeks).
- **Usage-day tag on every shopping item.** End each item with a parenthesised tag naming the day(s) it's used, so the list doubles as a "what do I need this for / when" reference at the shop. The tag is the *last* thing on the line, after the quantity:
  - Single day: `Salmon fillets (filetes de salmão) — 200 g (Wed)`.
  - Multiple days: list them comma-separated in week order: `Chicken breasts (peito de frango) — 800 g (Tue, Fri)`.
  - Add a short context word when it disambiguates which dish: `Chicken thighs, bone-in (coxas de frango) — 700 g (Sat roast)`, `Ground beef (carne picada) — 500 g (Thu bolognese)`.
  - Staples/pantry refills with no single owning day take a note instead of a day: `Olive oil (azeite) — bottle (top up if low)`; truly generic items (salt, stock cubes, dried herbs) may carry just a refill note or no tag.
  - Training-fuel items get the sessions they cover: `Chocolate milk (leite com chocolate) — 4 bottles (Wed, Thu, Sat, Sun post-session)`.
  - Derive these from the **ingredient → days index** you build in A5 check 1 — read the days off the written recipe **Ingredients** blocks, not off the dish name (a "stir-fry" or "omelette" implies onions or mushrooms it may not actually contain). Write that day set as the tag, then confirm it holds in the A5 check 2 reverse audit.
- **Reference supermarkets.** Pingo Doce, Continente, Lidl. The closing note typically flags which is cheapest for specific categories.
- **Athlete is a triathlete** (swim/bike/run + core/plyometrics). Don't suggest meals that conflict with that (e.g. very heavy/fatty pre-session meals).

### A5. Final consistency pass

Four checks before declaring the plan done:

**1. Ingredient coverage (recipe → shopping list).** Walk every dish across all seven days and confirm every ingredient is either in **Already in the Fridge** or on the **Shopping List**. Add anything missing — named herbs, spices, condiments — including training-load-scaled quantities (bananas, dates, energy bars, chocolate milk). As you walk, **build an ingredient → days index**: read each ingredient straight off the recipe's **Ingredients** block (never off the dish's name or archetype) and record every day whose *written* recipe lists it. That index — not your memory of the week — is the source of truth for the usage-day tags. This direction catches ingredients that are *used but not bought*.

**2. Usage-day tag audit (shopping list → recipe).** The opposite direction, run as a separate pass — do not fold it into check 1. For **every** shopping-list item, take the day(s) in its `(…)` tag and confirm, for each one, that the day genuinely uses the item. Delete any day you can't confirm; add any day that check 1's index has but the tag is missing. The tag's day set must equal the index's day set for that item — no extra days, no missing days.

   Where a day's use is written down — check all three places before deleting a tag:
   - **The day's own Ingredients block**, for a dish cooked fresh that day.
   - **The origin recipe's Ingredients block**, for a repeat or leftover entry. Follow the `See {Day} — {Dish}` / `Same as {Day} — {Dish}` pointer and read the ingredients *there*. Pointer entries carry no Ingredients block of their own **by design**, so "the item isn't written on this day" is never on its own grounds to drop the day — Wednesday still eats the oats when its porridge entry is `*Same as Monday*`.
   - **The day's Meal Plan bullets**, for anything that never gets a recipe entry at all: pre-/during-/post-session fuel (bananas, dates, gels, bars, isotonic, chocolate milk), and extras named only inside a pointer's note (*"grate the reserved parmesan over it"*).

   Two things to keep in mind:
   - This is the *only* check that catches a tag naming a day that doesn't use the item: check 1 walks recipe → list and never visits an item on a day that doesn't list it, so it structurally cannot see an over-tagged day.
   - The failure mode is tagging from the dish's *archetype* instead of its *written recipe*. A "chicken & veg stir-fry" or "veg omelette" reads like it contains onion and mushrooms, so those days get tagged out of habit — but if the recipe you actually wrote lists carrot/pepper/courgette instead, the tag is wrong. Real example this guards against: `Mushrooms — 1 pack (Tue, Fri)` when only Friday's two dishes list mushrooms and Tuesday's stir-fry doesn't — the correct tag is `(Fri)`.

**3. Recipe-section day×meal completeness.** For each day, confirm the Recipes section has a `#### {Dish}` entry for every main meal that day's Meal Plan lists (Breakfast/Lunch/Dinner), each with a `**Meal:**` line. The dish must match the Meal Plan bullet. Every repeat/leftover meal must still appear as its own entry with a working pointer line (`See/Same as {Day} — {Dish}`) whose `{Dish}` matches an origin entry's title on that day. No main meal may be missing from the Recipes section.

**4. Portion balance (leftover ledger).** Walk every recipe that yields more than one serving and confirm `portions cooked == portions eaten` across the week. For each multi-serving dish, list the meal slots that consume it and check the count matches the serving line. If a portion has no slot, either (a) add a meal slot that eats it within the week (respecting the ~2–3 day perishability window), or (b) reduce the batch size so nothing is left over. Do not ship a plan where any cooked portion is unaccounted for — that's the exact failure this guards against (e.g. a 2-portion Tuesday soup with only one portion scheduled).

### A6. Write the file

Save to `$SKILL_DIR/plans/meal-plan-week-{month}-{day}-{year}.md` (lowercase month name, no leading zero on day). For the Write tool, expand `$SKILL_DIR` to the launch base directory.

### A6.5. Generate recipe preview images

Each recipe page in the PDF shows a food photo above its title. A missing image falls back to an emoji banner, so **skipping this step is always acceptable** — the rest of the PDF still ships.

Read [reference/image-providers.md](reference/image-providers.md) before generating any. Images are produced locally on the Mac's GPU by default ([scripts/gen-recipe-images.py](scripts/gen-recipe-images.py) — no API key, no quota), with a hosted fallback chain behind it; that file carries the venv setup, the job-file format, the filename slug the renderer looks images up by, and each provider's pitfalls.

### A7. Render the PDF

```bash
SKILL_DIR=<base directory from skill launch>

# One-time, idempotent: create the renderer's own venv if it's missing. The
# script's only third-party Python dependency is `markdown`, pinned in
# scripts/requirements.txt — never rely on a system/user-site `markdown`.
if [ ! -x "$SKILL_DIR/scripts/.venv/bin/python" ]; then
    python3 -m venv "$SKILL_DIR/scripts/.venv"
    "$SKILL_DIR/scripts/.venv/bin/pip" install -r "$SKILL_DIR/scripts/requirements.txt"
fi

"$SKILL_DIR/scripts/.venv/bin/python" "$SKILL_DIR/scripts/md-to-pdf.py" \
    "$SKILL_DIR/plans/meal-plan-week-{month}-{day}-{year}.md" \
    "$SKILL_DIR/plans/meal-plan-week-{month}-{day}-{year}.pdf"
```

Render the PDF **into `plans/`** (next to its `.md`), not `/tmp` — A7.5 (cleanup) and A8 (upload) both read it from `plans/`. The script prints the absolute output path on success. **Always invoke it through `scripts/.venv/bin/python`** (the snippet above creates that venv from `scripts/requirements.txt` on first run) — do not call bare `python3`, which has no `markdown`. The one remaining external dependency is the system `chromium` binary. If the script fails, surface the stderr to the user; do not silently fall back.

The renderer is **not** a plain markdown-to-HTML dump — it parses the schema in A4 directly and lays it out as a styled PDF (blue/orange palette, Playfair Display titles, cover page, day cards, multi-column shopping list, one-recipe-per-page with numbered steps). The look is modeled on the "2023-01 Meal Template.pdf" the user has on Drive. **Don't change the section headings or bullet shapes in A4** — the parser depends on them; changing them will silently drop content from the PDF. Google Fonts is fetched at render time for best typography; if offline, the layout still works using local serif/sans fallbacks.

### A7.5. Clean up previous weeks' artifacts

Once the new PDF exists locally, remove old PDFs and image directories from `plans/` — but keep every `.md` (those are the historical record and the cache that actions B–E read).

```bash
WEEK_STEM="meal-plan-week-{month}-{day}-{year}"
SKILL_DIR=<base directory from skill launch>
PLANS_DIR="$SKILL_DIR/plans"

find "$PLANS_DIR" -maxdepth 1 -type f -name 'meal-plan-week-*.pdf' \
    ! -name "${WEEK_STEM}.pdf" -delete

find "$PLANS_DIR/images" -mindepth 1 -maxdepth 1 -type d \
    ! -name "week-{month}-{day}-{year}" -exec rm -rf {} +
```

Notes:
- Only `.pdf` files and `images/week-*/` directories are removed. `.md` files are never touched.
- Use the same `{month}-{day}-{year}` slug from A6 so the just-created artifacts survive.
- If `plans/images/` doesn't exist (image generation was skipped), the second `find` is a no-op — that's fine.

### A8. Upload to Google Drive (via rclone)

Use the **rclone** CLI — the `gdrive:` remote is already configured against the user's Google Drive. This bypasses the Drive MCP's inline-base64 path, which doesn't fit a typical 0.9–1.2 MB PDF in a single tool call.

```bash
SKILL_DIR=<base directory from skill launch>
rclone copy -v --stats=0 \
    "$SKILL_DIR/plans/meal-plan-week-{month}-{day}-{year}.pdf" \
    "gdrive:Meal Plans/"
```

Then get the shareable link to report back to the user:

```bash
rclone link "gdrive:Meal Plans/meal-plan-week-{month}-{day}-{year}.pdf"
```

Notes:
- `rclone copy` is idempotent — re-running won't duplicate the file (it skips if size+modtime match) and will overwrite if the local file changed. Safe to re-run after a re-render.
- The `Meal Plans` folder already exists at Drive root; no need to create it. If `rclone lsd "gdrive:"` ever shows it missing, run `rclone mkdir "gdrive:Meal Plans"` once.
- If `rclone copy` fails (auth expired, network), surface the stderr to the user verbatim and remind them to run `rclone config reconnect gdrive:` if it's a token issue. Don't fall back to the Drive MCP — its inline-base64 path can't handle files this size.

### A9. Confirm to the user

Two-line summary max: the training overview line ("~10:50 / 536 TSS, hard days Wed/Thu/Fri/Sun") and the Drive link / filename. Don't dump the whole plan back at them — they can open the PDF.

---

## B. Today's menu

1. Resolve today: `TZ=Europe/Lisbon date +%A` (e.g. `Friday`) and `TZ=Europe/Lisbon date +%Y-%m-%d`.
2. Find the current week's plan: list the skill's `plans/` directory (`$SKILL_DIR/plans/`, resolved per Path resolution), parse the Monday-date out of each filename, pick the most recent file whose Monday ≤ today ≤ Monday+6.
   - If no current-week file exists, tell the user the plan hasn't been created yet and offer to run action A.
3. Read the file, jump to `### {Today} — ...`, return that day's bullets.
4. If the user asks about a specific meal ("what's for dinner today"), return only that line plus the training context one-liner (e.g. *"Today is Wed — Plyometrics + Zwift VO2max 1h15"*).

---

## C. Shopping list

1. Find the most recent plan file (same logic as B step 2; doesn't have to be the current week if they're shopping ahead).
2. Return the `## Shopping List` section verbatim. Don't reformat; the checkboxes are useful as-is.
3. If they ask for one category ("just the proteins"), return only that subsection.

---

## D. Recipe lookup

1. Find the current week's plan file (or the file the user references — "from last week").
2. Look up the dish under `## Recipes` by case-insensitive substring match on the `#### {Dish}` headings.
3. If the dish is in the meal plan but not in the Recipes section (older file from before this skill, or a fueling snack), generate the recipe on the fly using the same per-recipe format (4–8 ingredients, 3–7 steps), then **append it to the Recipes section of that week's file** so it's there for next time.
4. If the dish is nowhere — the user is asking about something not on the plan — generate a recipe but do NOT write it into the weekly plan (it's not part of that week).

---

## E. Fridge contents

Return the `## Already in the Fridge` section of the current week's plan verbatim. If the user wants to update it ("add chorizo to the fridge"), edit that section in the file in-place. Don't regenerate the plan unless they ask.

---

## Notes & gotchas

- **Date format.** The TrainingPeaks MCP wants `YYYY-MM-DD` for calendar days. The plan filename and `**Week of ...**` header use lowercase month names, no leading zero on day (matches existing files).
- **Don't ask before reading TP.** Reads (`tp_get_workouts`, `tp_get_fitness`, etc.) are safe and cached for the conversation — call them freely. Only confirm before mutating TP (this skill never mutates TP, but still).
- **Don't refetch profile basics** (FTP, zones, A-race) within one conversation unless the user just changed them.
- **Don't generate the PDF speculatively** — only as part of action A (creating a week). Querying actions read the cached `.md` and never touch chromium.
- **If the renderer's venv is missing/broken**, recreate it from the pinned requirements: `python3 -m venv "$SKILL_DIR/scripts/.venv" && "$SKILL_DIR/scripts/.venv/bin/pip" install -r "$SKILL_DIR/scripts/requirements.txt"` (the A7 snippet does this automatically on first run). **If `chromium` is missing**, ask the user to reinstall it (`pacman -S chromium` on Arch) — it's a system binary, not a Python package, so it can't go in the venv. Do not fall back to a different renderer silently; the layout is tuned for this pipeline.
