---
name: weekly-meal-plan
description: Plan, render, and serve weekly triathlon meal plans. Use when the user asks to "make next week's plan", "create a meal plan", "what's today's menu", "show the shopping list", "what's in the fridge", "how do I cook X", or "save this recipe / I liked X". Pulls planned workouts from the TrainingPeaks MCP, generates a Mon→Sun meal plan tailored to training load, renders it (plus per-day recipes) to PDF via headless Chromium, uploads the PDF to the "Meal Plans" folder in Google Drive, and answers follow-up questions during the week from the cached markdown.
---

# Weekly meal plan

The user is a triathlete based in Portugal. Each week they ask for a meal plan that mirrors their TrainingPeaks training schedule, plus follow-up questions during the week. This skill owns the full lifecycle.

## Files this skill owns

```
~/.claude/skills/weekly-meal-plan/
├── SKILL.md                                    # this file
├── plans/
│   └── meal-plan-week-{month}-{day}-{year}.md  # one per week, source of truth and cache
├── favorite-recipes.md                         # recipes the user explicitly asked to save
└── scripts/
    └── md-to-pdf.py                            # Markdown → PDF (headless Chromium)
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
| "save this recipe", "I liked the X, save it", "add to favorites" | **E. Save favorite recipe** |
| "what's in the fridge" (per the plan) | **F. Fridge contents** |

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

### A3. Capture the fridge inventory

- If the user already pasted a list, use it.
- If they didn't, ask once, briefly: *"Anything currently in the fridge to use up?"* Accept "nothing" / "skip" and move on.

### A4. Build the meal plan

Follow the existing schema **exactly** — preserve section order and headings so the parser-style lookups in actions B–F keep working:

```markdown
# Weekly Meal Plan
**Week of {Mon Month Day}–{Sun Day, Year}**

## Training Overview
- **Total:** ~{hours} / {TSS}
- **Hard days:** {day list with session type}
- **Easy days:** {day list}

{One-line summary on how the meal plan tracks training load.}

---

## Meal Plan

### Monday — {session(s) or "Recovery"}
- **Breakfast:** ...
- **Lunch:** ...
- **Dinner:** ...
- (Training days add: **Pre-{session}:**, **During {session}:**, **Post-{session}:**)

### Tuesday — ...
... (through Sunday)

---

## Already in the Fridge
- Item 1
- Item 2

---

## Shopping List

### Proteins
- [ ] Item (Portuguese name) — qty

### Carbs
### Fruit
### Vegetables
### Legumes & Pantry
### Nuts & Extras
### Training-specific

---

## Recipes

### Monday
#### {Dish name from Monday's meals}
**Ingredients**
- ...

**Steps**
1. ...

#### {Next dish}
...

### Tuesday
... (through Sunday — one subsection per unique dish that day. If a dish repeats across days, write it under its first day and reference it: *"See Tuesday — Tuna pasta salad"*)

#### Per-recipe metadata (required for the PDF nutrition block)

Every `#### {Dish}` heading must be followed by three lines, before the `**Ingredients**` block, so the renderer can show tag chips and a Prep/Cook/Kcal/Fats/Carbs/Protein/Fibre table at the bottom of each recipe page:

```markdown
#### Bolognese with pasta + broccoli
**Tags:** HP, MP, DF
**Per serving:** 810 kcal · 40 g protein · 31 g fat · 91 g carbs · 5 g fibre
**Time:** 10 min prep · 30 min cook

**Ingredients (4 servings — reserve half for Sunday)**
- ...
```

Field rules:
- **Tags** — comma-separated abbreviations from this set: `GF` (gluten free), `DF` (dairy free), `LC` (low carb, <20 g/serve), `MP` (meal prep / freezer friendly), `HP` (high protein, ≥20 g/serve), `V` (vegetarian), `Q` (quick, ≤30 min total), `N` (contains nuts). Apply them by composition — e.g. an oats+walnuts breakfast is `V, N, Q`.
- **Per serving** — kcal first, then protein/fat/carbs/fibre. Units `g` are optional but recommended. Separators can be `·`, `•`, or `|`. Values are estimates — fine to round to 5 kcal / 1 g. For multi-serving recipes (bolognese, etc.), values are **per serving**, not for the whole pot.
- **Time** — `N min prep · N min cook`. Either field can be omitted; `0 min cook` is valid for no-cook dishes. Total time is what drives the `Q` tag.
- For reference recipes (`*See Wednesday — ...*`), still include all three lines — values reflect the variant on that day (e.g. Friday's "Big oats bowl" has higher kcal than Wednesday's oats).

Optional fourth line — **only add it if auto-detection picks the wrong category** (which it almost never does; skip it by default):

```markdown
**Image:** chicken
```

This controls the category-themed preview banner at the top of the recipe page (gradient colour + central food emoji). Categories: `eggs`, `oats`, `pasta`, `chicken`, `fish`, `salad`, `chickpea`, `yogurt`, `bread`, `rice`, `default`. The renderer auto-picks from the dish title using keyword priority (eggs → oats → pasta → chicken → fish → chickpea → salad → yogurt → bread → rice → default), so e.g. "Tuna pasta salad" lands on `pasta`, "Sardines + boiled potatoes + tomato salad" on `fish`. You can also pass a custom emoji: `**Image:** 🥑 default`.

---

*{Closing note on where to shop, e.g. "Pingo Doce, Continente, and Lidl all cover this. Lidl tends to be cheapest for nuts, oats, and frozen fish."}*
```

#### Domain rules — follow when filling in the plan

- **Carb load tracks training load.** Use planned TSS first to rank the days (highest TSS = biggest fuel day); fall back to session type/duration only when TSS isn't available. Hard days get bigger carb portions, in-session fuel (bananas, dates, energy bars, isotonic), and post-session recovery (chocolate milk). Easy / recovery days are lighter — fewer carbs, no sports drinks, no recovery shake.
- **Reuse fridge items.** Where a meal uses something already in the fridge, append `*(use what's in fridge)*` to the bullet.
- **Bilingual shopping list.** Each item: English name + Portuguese name in parentheses, e.g. `Chicken breasts (peito de frango) — 1 kg`. Quantities should scale with the week's training load (more bananas/dates/energy bars/chocolate milk on big aerobic weeks).
- **Reference supermarkets.** Pingo Doce, Continente, Lidl. The closing note typically flags which is cheapest for specific categories.
- **Athlete is a triathlete** (swim/bike/run + core/plyometrics). Don't suggest meals that conflict with that (e.g. very heavy/fatty pre-session meals).

#### Recipes section — per-day organization

- Generate a short recipe for **every distinct dish** named in the Meal Plan (breakfast/lunch/dinner; fueling snacks like "banana + honey toast" don't need a recipe).
- Group by day. If the user flips to "Wednesday" in the PDF they should find every Wednesday dish on that page or the next.
- Each recipe: 4–8 ingredients with quantities (1 serving unless the dish is built for leftovers — bolognese, etc.), then 3–7 numbered steps. Keep it tight; this is a working kitchen reference, not a cookbook.
- If a dish appears on multiple days (e.g. "Spaghetti with bolognese (second batch)"), write the full recipe on the first day and on later days write only `*See {Day} — {Dish}*`.
- Also check `favorite-recipes.md` first — if the user has saved a version of a dish there, prefer that version (it's their preferred way).

### A5. Final consistency pass

Before declaring the plan done, walk every dish across all seven days and confirm every ingredient is either in **Already in the Fridge** or on the **Shopping List**. Add anything missing — named herbs, spices, condiments — including training-load-scaled quantities (bananas, dates, energy bars, chocolate milk).

### A6. Write the file

Save to `~/.claude/skills/weekly-meal-plan/plans/meal-plan-week-{month}-{day}-{year}.md` (lowercase month name, no leading zero on day).

### A6.5. Generate recipe preview images (Composio Gemini MCP)

Each recipe page in the PDF shows a 12 × 8 cm food photo above the title. Generate one per recipe via the Composio **GEMINI_GENERATE_IMAGE** tool (`gemini-2.5-flash-image`, aspect_ratio `3:2`). The connection is already active on Composio (toolkit `gemini`); just call the tool.

**Prompt template** (keep them neutral and concrete — Gemini blocks recitation if you copy a brand name; stick to ingredients + plating):

```
Food photography, top-down view: {plainspoken dish description with key ingredients}.
Rustic ceramic plate/bowl, natural daylight, clean wooden table, minimal styling,
soft shadows, magazine quality, no text, no logos.
```

**Batching.** Composio's pitfall note recommends ≤3 concurrent calls to avoid 429s, but in practice batches of 5–9 via `COMPOSIO_MULTI_EXECUTE_TOOL` succeed. For ~20 recipes, two batches is enough.

**Download + resize + cache.** Each Gemini result has a presigned `data.image.s3url` that expires in ~1 hour — download immediately. The originals are ~1.7 MB PNGs at 1248×832, which would bloat the PDF; resize and re-encode as JPEG q85 at 800×533 (3:2) — keeps each image ~80–110 KB and adds ~1.8 MB to the PDF total. Final PDF lands around 2.5–3 MB.

```bash
# After downloading {dish-slug}.png from the presigned s3url:
mkdir -p ~/.claude/skills/weekly-meal-plan/plans/images/week-{month}-{day}-{year}
magick {dish-slug}.png -resize '800x533!' -quality 85 -interlace JPEG \
    -sampling-factor 4:2:0 -strip \
    ~/.claude/skills/weekly-meal-plan/plans/images/week-{month}-{day}-{year}/{dish-slug}.jpg
```

**Filename convention.** Images live at `plans/images/week-{month}-{day}-{year}/{slug(dish_title)}.jpg` (or .png/.webp). The slug uses the same `slugify` logic the renderer uses: NFKD-normalise → strip combining accents → lowercase → non-alphanumerics replaced with `-` → trim. The renderer derives the directory from the markdown filename and looks each one up automatically.

**Graceful degradation.** If the images dir doesn't exist (Gemini quota exhausted, offline run, the user wants to skip), the renderer silently falls back to the emoji banner per recipe — no error. Skipping image generation is acceptable; the rest of the PDF still ships.

### A7. Render the PDF

```bash
python3 ~/.claude/skills/weekly-meal-plan/scripts/md-to-pdf.py \
    ~/.claude/skills/weekly-meal-plan/plans/meal-plan-week-{month}-{day}-{year}.md \
    /tmp/meal-plan-week-{month}-{day}-{year}.pdf
```

The script prints the absolute output path on success. Required tools: `chromium` and the `markdown` Python module — both already present. If the script fails, surface the stderr to the user; do not silently fall back.

The renderer is **not** a plain markdown-to-HTML dump — it parses the schema in A4 directly and lays it out as a styled PDF (blue/orange palette, Playfair Display titles, cover page, day cards, multi-column shopping list, one-recipe-per-page with numbered steps). The look is modeled on the "2023-01 Meal Template.pdf" the user has on Drive. **Don't change the section headings or bullet shapes in A4** — the parser depends on them; changing them will silently drop content from the PDF. Google Fonts is fetched at render time for best typography; if offline, the layout still works using local serif/sans fallbacks.

### A8. Upload to Google Drive (via rclone)

Use the **rclone** CLI — the `gdrive:` remote is already configured against the user's Google Drive (bushevdv@gmail.com). This bypasses the Drive MCP's inline-base64 path, which doesn't fit a typical 0.9–1.2 MB PDF in a single tool call.

```bash
rclone copy -v --stats=0 \
    ~/.claude/skills/weekly-meal-plan/plans/meal-plan-week-{month}-{day}-{year}.pdf \
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
2. Find the current week's plan: list `~/.claude/skills/weekly-meal-plan/plans/`, parse the Monday-date out of each filename, pick the most recent file whose Monday ≤ today ≤ Monday+6.
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
3. Also check `favorite-recipes.md` — if the dish exists there, prefer that version (it's the saved/preferred one) and mention briefly: *"Using your saved version."*
4. If the dish is in the meal plan but not in the Recipes section (older file from before this skill, or a fueling snack), generate the recipe on the fly using the same per-recipe format (4–8 ingredients, 3–7 steps), then **append it to the Recipes section of that week's file** so it's there for next time.
5. If the dish is nowhere — the user is asking about something not on the plan — generate a recipe but do NOT write it into the weekly plan (it's not part of that week). Offer to save it as a favorite if they want.

---

## E. Save favorite recipe

Trigger phrases: "save this", "I liked the X, save it", "add to favorites", "remember this recipe".

1. Identify which dish the user means. Usually it's the one just discussed in this conversation — quote the dish name back briefly to confirm if there's any ambiguity (more than one dish in recent turns).
2. Locate the recipe — current week's plan first, then `favorite-recipes.md` (already saved → tell the user and stop), then generate fresh if needed.
3. Append to `~/.claude/skills/weekly-meal-plan/favorite-recipes.md` using the format shown at the top of that file. Today's date for `*Saved {YYYY-MM-DD}*`. Reference the week of origin if known.
4. One-line confirmation: *"Saved 'Bolognese with pasta' to favorites."*

---

## F. Fridge contents

Return the `## Already in the Fridge` section of the current week's plan verbatim. If the user wants to update it ("add chorizo to the fridge"), edit that section in the file in-place. Don't regenerate the plan unless they ask.

---

## Notes & gotchas

- **Date format.** The TrainingPeaks MCP wants `YYYY-MM-DD` for calendar days. The plan filename and `**Week of ...**` header use lowercase month names, no leading zero on day (matches existing files).
- **Don't ask before reading TP.** Reads (`tp_get_workouts`, `tp_get_fitness`, etc.) are safe and cached for the conversation — call them freely. Only confirm before mutating TP (this skill never mutates TP, but still).
- **Don't refetch profile basics** (FTP, zones, A-race) within one conversation unless the user just changed them.
- **Don't generate the PDF speculatively** — only as part of action A (creating a week). Querying actions read the cached `.md` and never touch chromium.
- **If chromium / markdown ever go missing**, ask the user to reinstall (`pacman -S chromium` and `pip install --user markdown` on Arch). Do not fall back to a different renderer silently; the layout is tuned for this pipeline.
- **The repo at `~/projects/4e6/meal-plans/` was the origin of this skill** and is being deleted. The current week (May 11–17, 2026) was migrated to `plans/` so action B works immediately. After the repo is gone, the skill is fully self-contained.
