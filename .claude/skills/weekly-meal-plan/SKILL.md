---
name: weekly-meal-plan
description: Plan, render, and serve weekly triathlon meal plans. Use when the user asks to "make next week's plan", "create a meal plan", "what's today's menu", "show the shopping list", "what's in the fridge", "how do I cook X", or "save this recipe / I liked X". Pulls planned workouts from the TrainingPeaks MCP, generates a Mon→Sun meal plan tailored to training load, renders it (plus per-day recipes) to PDF via headless Chromium, uploads the PDF to the "Meal Plans" folder in Google Drive, and answers follow-up questions during the week from the cached markdown.
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
├── favorite-recipes.md                         # recipes the user explicitly asked to save
└── scripts/
    ├── md-to-pdf.py                            # Markdown → PDF (headless Chromium)
    ├── requirements.txt                        # Python deps for the renderer (just `markdown`)
    └── .venv/                                  # local virtualenv (gitignored; created on first render)
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

**Race weeks — get the race distance.** If the week contains a workout titled `RACE` / `PRE-RACE` / `WARM-UP | …` on the final day, treat it as race week. The race itself is normally on the TrainingPeaks calendar as an event — call `tp_get_next_event` (and `tp_get_focus_event` if relevant) to pull the race name + distance directly. **Don't infer distance from the workout description** — the coach's notes typically list multiple distance options (e.g. *"In case its a 10K Race … Half Marathon … Marathon …"*) and don't tell you which one applies. If the event lookup doesn't return a clear distance, ask the user once: *"What's the distance for Sunday's race?"* before building the plan. Distance drives Saturday carb-load target (~5–7 g/kg for 10K, ~7–10 g/kg for HM+), in-race fueling (10K rarely needs gels; HM = 2–3 gels + isotonic; Marathon = continuous fueling), and post-race recovery depth.

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
- [ ] Item (Portuguese name) — qty (Day[, Day…])

### Carbs
### Fruit
### Vegetables
### Legumes & Pantry
### Nuts & Extras
### Training-specific

---

## Recipes

### Monday
#### {Monday's breakfast dish}
**Meal:** Breakfast
**Per serving:** ...
**Time:** ...

**Ingredients (1 serving)**
- ...

**Steps**
1. ...

#### {Monday's lunch dish}
**Meal:** Lunch
... (full recipe — metadata + Ingredients + Steps)

#### {Monday's dinner dish}
**Meal:** Dinner
... (full recipe)

### Tuesday
... (every day lists Breakfast, Lunch and Dinner — one #### entry per main meal, in that order, through Sunday)

#### {Tuesday's lunch — same dish as an earlier day, or a leftover from a batch}
**Meal:** Lunch
**Per serving:** ...
**Time:** ...

*Leftover from Monday's lentil-soup batch — reheat. See Monday — Lentil soup.*

#### Per-recipe metadata (required)

Every `#### {Dish}` heading must be followed by three metadata lines, before the `**Ingredients**` block (or before the pointer line, for a repeat/leftover). They drive the meal label in the per-day table of contents and recipe eyebrow, plus the Prep/Cook/Kcal/Fats/Carbs/Protein/Fibre table at the bottom of each recipe page:

```markdown
#### Spaghetti bolognese
**Meal:** Dinner
**Per serving:** 680 kcal · 38 g protein · 22 g fat · 84 g carbs · 7 g fibre
**Time:** 15 min prep · 35 min cook

**Ingredients (3 servings — 1 Thu dinner, 1 Sat dinner, 1 Sun lunch)**
- ...
```

When a recipe is batch-cooked, the serving line must name where every serving goes (see the portion-conservation rule below) — not just "reserve half".

Field rules:
- **Meal** — `Breakfast`, `Lunch`, or `Dinner`. Required on **every** entry so the reader can scan a day's meals. Keep the `####` title the plain dish name (no "Breakfast — " prefix) — the renderer reads the slot from this line, and the title's slug is what the recipe image and anchor link are keyed on.
- **Per serving** — kcal first, then protein/fat/carbs/fibre. Units `g` are optional but recommended. Separators can be `·`, `•`, or `|`. Values are estimates — fine to round to 5 kcal / 1 g. For multi-serving recipes (bolognese, etc.), values are **per serving**, not for the whole pot.
- **Time** — `N min prep · N min cook`. Either field can be omitted; `0 min cook` is valid for no-cook dishes. For a leftover, `0 min prep · 3 min reheat` is fine.
- **Repeat / leftover pointer** — when an entry reuses a dish cooked on an earlier day, give the three metadata lines (values reflect *this* day's portion — e.g. Friday's "Big oats bowl" has higher kcal than Wednesday's oats), then **one italic pointer line in place of Ingredients/Steps**. Use one of these phrasings so the renderer can hyperlink the day to the origin recipe:
  - Same dish cooked fresh again: `*Same as Wednesday — Eggs on toast.*`
  - Eating a batch leftover: `*Leftover from Thursday's bolognese batch — reheat. See Thursday — Spaghetti bolognese.*`
  - The linkable phrase must read `See {Day} — {Dish}` or `Same as {Day} — {Dish}`, end with a period, and the `{Dish}` must match the origin entry's `####` title (substring, case-insensitive). The origin entry — the one with the full recipe — lives on the day the dish is first cooked.

An optional `**Image:**` line (alongside the metadata lines) — **only add it if auto-detection picks the wrong category** (which it almost never does; skip it by default):

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
  - Derive these from the same dish-by-day walk you do in the A5 ingredient-coverage check — record, per item, which days consume it, then write that set as the tag.
- **Reference supermarkets.** Pingo Doce, Continente, Lidl. The closing note typically flags which is cheapest for specific categories.
- **Athlete is a triathlete** (swim/bike/run + core/plyometrics). Don't suggest meals that conflict with that (e.g. very heavy/fatty pre-session meals).

#### Recipes section — per-day organization

The Recipes section is a **day-by-day overview**: the reader flips to a day and sees that whole day's eating. So it lists *every* main meal of *every* day — never silently dropping a meal because the dish appeared earlier.

- **One `#### {Dish}` entry per main meal, every day.** For each `### {Day}`, emit Breakfast, then Lunch, then Dinner (whichever the Meal Plan lists for that day — usually all three), in that order. Each entry carries its `**Meal:**` line. This is what makes the per-day table of contents at the top of the section show the full day at a glance.
- **Scope: the three main meals only.** Pre-/during-/post-session fuel (bananas, dates, energy bars, chocolate milk, isotonic) stays in the Meal Plan section and does *not* get a recipe entry — it needs no recipe and would clutter the day overview.
- **Origin entry = full recipe.** The day a dish is first cooked gets the full recipe: 4–8 ingredients with quantities (1 serving unless the dish is built for leftovers — bolognese, etc.), then 3–7 numbered steps. Keep it tight; this is a working kitchen reference, not a cookbook.
- **Repeat / leftover entry = pointer, not a re-print.** If a day's meal reuses a dish cooked earlier, still give it its own `#### {Dish}` entry with the `**Meal:**`/`**Per serving:**`/`**Time:**` lines, but replace Ingredients/Steps with a single italic pointer line (`*Same as … — …*` or `*Leftover from … — reheat. See … — ….*`) per the metadata rules above. The renderer links it back to the origin recipe, so the reader still gets one tap to the method.
- **Keep dish titles stable.** Use the same `#### {Dish}` title on the repeat/leftover day as on the origin day (the link resolves by matching that title). Don't encode the meal slot into the title — that's the `**Meal:**` line's job.
- Also check `favorite-recipes.md` first — if the user has saved a version of a dish there, prefer that version (it's their preferred way).

### A5. Final consistency pass

Three checks before declaring the plan done:

**1. Ingredient coverage + usage-day tags.** Walk every dish across all seven days and confirm every ingredient is either in **Already in the Fridge** or on the **Shopping List**. Add anything missing — named herbs, spices, condiments — including training-load-scaled quantities (bananas, dates, energy bars, chocolate milk). As you walk, record for each shopping item the set of days that consume it, and confirm every purchased item ends with its usage-day tag (per the bilingual-shopping-list rule). The tag's day set must match where the item is actually used — if you add or move a meal, update the tag.

**1b. Recipe-section day×meal completeness.** For each day, confirm the Recipes section has a `#### {Dish}` entry for every main meal that day's Meal Plan lists (Breakfast/Lunch/Dinner), each with a `**Meal:**` line. The dish must match the Meal Plan bullet. Every repeat/leftover meal must still appear as its own entry with a working pointer line (`See/Same as {Day} — {Dish}`) whose `{Dish}` matches an origin entry's title on that day. No main meal may be missing from the Recipes section.

**2. Portion balance (leftover ledger).** Walk every recipe that yields more than one serving and confirm `portions cooked == portions eaten` across the week. For each multi-serving dish, list the meal slots that consume it and check the count matches the serving line. If a portion has no slot, either (a) add a meal slot that eats it within the week (respecting the ~2–3 day perishability window), or (b) reduce the batch size so nothing is left over. Do not ship a plan where any cooked portion is unaccounted for — that's the exact failure this guards against (e.g. a 2-portion Tuesday soup with only one portion scheduled).

### A6. Write the file

Save to `$SKILL_DIR/plans/meal-plan-week-{month}-{day}-{year}.md` (lowercase month name, no leading zero on day). For the Write tool, expand `$SKILL_DIR` to the launch base directory.

### A6.5. Generate recipe preview images

Each recipe page in the PDF shows a 12 × 8 cm food photo above the title. The renderer looks each one up at `plans/images/week-{month}-{day}-{year}/{slug(dish_title)}.{jpg|jpeg|png|webp}`. The slug uses the same `slugify` logic the renderer uses: NFKD-normalise → strip combining accents → lowercase → non-alphanumerics replaced with `-` → trim. If the images dir doesn't exist or a specific dish is missing, the renderer silently falls back to the emoji banner — skipping is always acceptable; the rest of the PDF still ships.

**Provider fallback chain.** Try in order; stop at the first one that returns images:

1. **Composio Gemini MCP** (primary, best quality) — see below
2. **Hugging Face Z-Image Turbo MCP** (free, authenticated) — see below
3. **Pollinations.ai** (zero-auth last-resort fallback) — see below

**Shared prompt template** (works for both providers — keep neutral and concrete; brand names trigger recitation blocks on Gemini):

```
Food photography, top-down view: {plainspoken dish description with key ingredients}.
Rustic ceramic plate/bowl, natural daylight, clean wooden table, minimal styling,
soft shadows, magazine quality, no text, no logos.
```

#### Option 1: Composio Gemini MCP

Call the Composio **GEMINI_GENERATE_IMAGE** tool (`gemini-2.5-flash-image`, aspect_ratio `3:2`). The connection is already active on Composio (toolkit `gemini`).

**Batching.** Composio's pitfall note recommends ≤3 concurrent calls to avoid 429s, but in practice batches of 5–9 via `COMPOSIO_MULTI_EXECUTE_TOOL` succeed. For ~20 recipes, two batches is enough.

**Download + resize + cache.** Each Gemini result has a presigned `data.image.s3url` that expires in ~1 hour — download immediately. The originals are ~1.7 MB PNGs at 1248×832, which would bloat the PDF; resize and re-encode as JPEG q85 at 800×533 (3:2) — keeps each image ~80–110 KB and adds ~1.8 MB to the PDF total.

```bash
# After downloading {dish-slug}.png from the presigned s3url:
SKILL_DIR=<base directory from skill launch>
WEEK_DIR="$SKILL_DIR/plans/images/week-{month}-{day}-{year}"
mkdir -p "$WEEK_DIR"
magick {dish-slug}.png -resize '800x533!' -quality 85 -interlace JPEG \
    -sampling-factor 4:2:0 -strip \
    "$WEEK_DIR/{dish-slug}.jpg"
```

#### Option 2: Hugging Face FLUX.1-schnell via dynamic_space (fallback)

Free image generation via the `hf-mcp-server` MCP. Uses Black Forest Labs' `FLUX.1-schnell` (4-step turbo diffusion), reached through `mcp__hf-mcp-server__dynamic_space` (the generic Space-invocation tool) targeting the curated `evalstate/flux1_schnell` Space. Login is already wired up (authenticated as user `4e6`).

Why this specific Space and not a typed tool: HF's MCP server exposes one typed tool per pre-registered Space, and the only typed image-gen tool currently registered is Z-Image Turbo (`mcp__hf-mcp-server__gr1_z_image_turbo_generate`). Z-Image Turbo reserves **~60 s of ZeroGPU time per call**, which only fits 2–3 images into the free 5-min daily ZeroGPU budget. `evalstate/flux1_schnell` reserves **~10 s per call**, fits ~30 images in the same budget — enough for a full 20-recipe week. Quality at 4 inference steps is comparable for food photography.

```text
mcp__hf-mcp-server__dynamic_space(
    operation="invoke",
    space_name="evalstate/flux1_schnell",
    parameters='{"prompt": "<shared prompt template, filled in>", "width": 1248, "height": 832, "num_inference_steps": 4, "randomize_seed": true}',
)
```

Parameter rules:
- `parameters` is a **JSON-encoded string**, not an object. Pass `'{"prompt": "..."}'` literally.
- `prompt` should be ≲60–70 words (Space-level limit; the shared template fits comfortably).
- `width`/`height` accept any multiples of 8 — `1248×832` matches the 3:2 banner crop the renderer wants.
- Keep `num_inference_steps=4` (the schnell sweet spot; 8 doubles GPU cost without visible quality gain).

The tool result contains an inline preview and an `Image URL:` line pointing at a Gradio temp file (typically `https://evalstate-flux1-schnell.hf.space/.../image.webp` or similar). Download immediately and resize to 800×533 — same magick invocation as the Gemini branch, just starting from a `.webp`:

```bash
SKILL_DIR=<base directory from skill launch>
WEEK_DIR="$SKILL_DIR/plans/images/week-{month}-{day}-{year}"
mkdir -p "$WEEK_DIR"

curl -sS --fail --max-time 90 -o /tmp/{dish-slug}.webp "<image-url-from-tool-output>"

magick /tmp/{dish-slug}.webp -resize '800x533!' -quality 85 -interlace JPEG \
    -sampling-factor 4:2:0 -strip \
    "$WEEK_DIR/{dish-slug}.jpg"
```

**Pitfalls.**
- Tool output is a tuple — the inline preview image in the conversation is *not* what gets saved; always parse the `Image URL:` line and `curl` it. Skipping the curl step leaves you with no on-disk file.
- The Space returns `.webp`. ImageMagick reads it transparently.
- **ZeroGPU quota is per-user, shared across all ZeroGPU Spaces** (it's not per-Space). Free authenticated quota is **5 min/day**, PRO is 40 min/day. At ~10 s per `flux1_schnell` call, free covers ~30 images/day — a full week in one sitting, with margin. But: if you burn the budget on Z-Image Turbo earlier in the same UTC day (60 s/call), there's no separate budget for FLUX. Treat it as one wallet.
- Quota errors look like `ZeroGPU quota exceeded (10s requested vs. 0s left)`. The "Try again in 0:00:00" hint is bogus — actual reset is 24 h after the day's first GPU use. When this fires, fall through to Pollinations for the remaining dishes; don't loop-retry.
- **Don't fire in parallel.** ZeroGPU runs each call sequentially under a queue — parallel tool calls in one assistant turn don't generate in parallel and can race the quota check. Issue them one at a time (or with low concurrency, 2–3 max).
- Quality at 4 steps is good for plated-food banners; slightly below Gemini for hero/cover shots. If a specific dish comes out poorly, retry once with a tweaked prompt before falling through to Pollinations.

#### Option 3: Pollinations.ai (last-resort fallback)

Zero-auth HTTP endpoint backed by FLUX. Returns a 800×533 JPEG directly — **no resize / no ImageMagick step needed**, just save the response body.

```bash
SKILL_DIR=<base directory from skill launch>
WEEK_DIR="$SKILL_DIR/plans/images/week-{month}-{day}-{year}"
mkdir -p "$WEEK_DIR"

# URL-encode the prompt (python3 one-liner — bash doesn't have a builtin):
PROMPT="Food photography, top-down view: {dish description}. Rustic ceramic plate/bowl, natural daylight, clean wooden table, minimal styling, soft shadows, magazine quality, no text, no logos."
ENCODED=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$PROMPT")

curl -sS --fail --max-time 120 \
    -o "$WEEK_DIR/{dish-slug}.jpg" \
    "https://image.pollinations.ai/prompt/${ENCODED}?width=800&height=533&nologo=true"
```

**Pitfalls.**
- Latency is ~30–90 s per image (synchronous generation). Run ≥4 in parallel with `&` + `wait` to keep total time under ~2 min for 20 recipes.
- Occasional 502 / empty response / HTTP 402 — retry once before falling back to the emoji banner for that one dish.
- **Do not pass `model=flux`** — as of 2026 it returns HTTP 402 (paid tier). The default model is free and produces good food photography. If Pollinations adds another free model identifier later, test it before switching.
- `nologo=true` strips the Pollinations watermark. Required for a clean PDF.

**Final PDF size** with images from either provider: ~2.5–3 MB.

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

Once the new PDF exists locally, remove old PDFs and image directories from `plans/` — but keep every `.md` (those are the historical record and the cache that actions B–F read).

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

Use the **rclone** CLI — the `gdrive:` remote is already configured against the user's Google Drive (bushevdv@gmail.com). This bypasses the Drive MCP's inline-base64 path, which doesn't fit a typical 0.9–1.2 MB PDF in a single tool call.

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
3. Also check `favorite-recipes.md` — if the dish exists there, prefer that version (it's the saved/preferred one) and mention briefly: *"Using your saved version."*
4. If the dish is in the meal plan but not in the Recipes section (older file from before this skill, or a fueling snack), generate the recipe on the fly using the same per-recipe format (4–8 ingredients, 3–7 steps), then **append it to the Recipes section of that week's file** so it's there for next time.
5. If the dish is nowhere — the user is asking about something not on the plan — generate a recipe but do NOT write it into the weekly plan (it's not part of that week). Offer to save it as a favorite if they want.

---

## E. Save favorite recipe

Trigger phrases: "save this", "I liked the X, save it", "add to favorites", "remember this recipe".

1. Identify which dish the user means. Usually it's the one just discussed in this conversation — quote the dish name back briefly to confirm if there's any ambiguity (more than one dish in recent turns).
2. Locate the recipe — current week's plan first, then `favorite-recipes.md` (already saved → tell the user and stop), then generate fresh if needed.
3. Append to `$SKILL_DIR/favorite-recipes.md` (resolved per Path resolution) using the format shown at the top of that file. Today's date for `*Saved {YYYY-MM-DD}*`. Reference the week of origin if known.
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
- **If the renderer's venv is missing/broken**, recreate it from the pinned requirements: `python3 -m venv "$SKILL_DIR/scripts/.venv" && "$SKILL_DIR/scripts/.venv/bin/pip" install -r "$SKILL_DIR/scripts/requirements.txt"` (the A7 snippet does this automatically on first run). **If `chromium` is missing**, ask the user to reinstall it (`pacman -S chromium` on Arch) — it's a system binary, not a Python package, so it can't go in the venv. Do not fall back to a different renderer silently; the layout is tuned for this pipeline.
- **The repo at `~/projects/4e6/meal-plans/` was the origin of this skill** and is being deleted. The current week (May 11–17, 2026) was migrated to `plans/` so action B works immediately. After the repo is gone, the skill is fully self-contained.
