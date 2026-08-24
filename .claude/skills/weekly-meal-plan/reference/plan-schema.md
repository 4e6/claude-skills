# Plan file schema

The shape of a weekly plan `.md`. Read this while building a plan (action A4 in
[SKILL.md](../SKILL.md)); the querying actions (B–E) don't need it.

`parse_plan()` in [../scripts/md-to-pdf.py](../scripts/md-to-pdf.py) parses these
headings and bullet shapes **directly** — it is not a generic markdown converter.
Change a heading or a bullet shape here without changing the parser and the
content silently disappears from the PDF.

## Document skeleton

Preserve section order and headings exactly.

````markdown
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

---

*{Closing note on where to shop, e.g. "Pingo Doce, Continente, and Lidl all cover this. Lidl tends to be cheapest for nuts, oats, and frozen fish."}*
````

## Per-recipe metadata (required)

Every `#### {Dish}` heading must be followed by three metadata lines, before the `**Ingredients**` block (or before the pointer line, for a repeat/leftover). They drive the meal label in the per-day table of contents and recipe eyebrow, plus the Prep/Cook/Kcal/Fats/Carbs/Protein/Fibre table at the bottom of each recipe page:

```markdown
#### Spaghetti bolognese
**Meal:** Dinner
**Per serving:** 680 kcal · 38 g protein · 22 g fat · 84 g carbs · 7 g fibre
**Time:** 15 min prep · 35 min cook

**Ingredients (3 servings — 1 Thu dinner, 1 Sat dinner, 1 Sun lunch)**
- ...
```

When a recipe is batch-cooked, the serving line must name where every serving goes (see the portion-conservation domain rule in [SKILL.md](../SKILL.md) A4) — not just "reserve half".

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

## Recipes section — per-day organization

The Recipes section is a **day-by-day overview**: the reader flips to a day and sees that whole day's eating. So it lists *every* main meal of *every* day — never silently dropping a meal because the dish appeared earlier.

- **One `#### {Dish}` entry per main meal, every day.** For each `### {Day}`, emit Breakfast, then Lunch, then Dinner (whichever the Meal Plan lists for that day — usually all three), in that order. Each entry carries its `**Meal:**` line. This is what makes the per-day table of contents at the top of the section show the full day at a glance.
- **Scope: the three main meals only.** Pre-/during-/post-session fuel (bananas, dates, energy bars, chocolate milk, isotonic) stays in the Meal Plan section and does *not* get a recipe entry — it needs no recipe and would clutter the day overview.
- **Origin entry = full recipe.** The day a dish is first cooked gets the full recipe: 4–8 ingredients with quantities (1 serving unless the dish is built for leftovers — bolognese, etc.), then 3–7 numbered steps. Keep it tight; this is a working kitchen reference, not a cookbook.
- **Repeat / leftover entry = pointer, not a re-print.** If a day's meal reuses a dish cooked earlier, still give it its own `#### {Dish}` entry with the `**Meal:**`/`**Per serving:**`/`**Time:**` lines, but replace Ingredients/Steps with a single italic pointer line (`*Same as … — …*` or `*Leftover from … — reheat. See … — ….*`) per the metadata rules above. The renderer links it back to the origin recipe, so the reader still gets one tap to the method.
- **Keep dish titles stable.** Use the same `#### {Dish}` title on the repeat/leftover day as on the origin day (the link resolves by matching that title). Don't encode the meal slot into the title — that's the `**Meal:**` line's job.
