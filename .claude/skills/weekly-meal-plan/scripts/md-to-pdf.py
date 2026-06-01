#!/usr/bin/env python3
"""Render a weekly meal plan markdown file to a styled PDF via headless Chromium.

Visual design is inspired by the "Kinetic" recipe-pack template the user has on
Drive (2023-01 Meal Template.pdf): blue top stripe on content pages, Playfair
Display serif titles, orange section labels, day cards for the meal plan,
multi-column shopping list, and one-recipe-per-page layout with a two-column
ingredients + method body.

The input markdown schema is the one documented in SKILL.md and stays the
source of truth; this script only changes how that markdown is rendered.

Usage: python3 md-to-pdf.py <input.md> <output.pdf>
"""
import argparse
import html as html_lib
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import markdown


# ============================================================ Parsing ======


def parse_plan(md_text: str) -> dict:
    plan = {
        "title": "",
        "week": "",
        "training_bullets": [],
        "training_summary": "",
        "days": [],
        "fridge": [],
        "shopping": [],
        "recipes": [],
        "closing_note": "",
    }

    section = None
    current_day = None
    current_category = None
    current_recipe_day = None
    current_dish = None

    for raw in md_text.split("\n"):
        line = raw.rstrip()

        if line.startswith("# "):
            plan["title"] = line[2:].strip()
            continue
        if line.startswith("**Week of "):
            plan["week"] = line.strip("*").replace("Week of ", "").strip()
            continue
        if line.strip() == "---":
            current_day = current_category = current_recipe_day = current_dish = None
            continue
        if line.startswith("## "):
            head = line[3:].strip()
            section = {
                "Training Overview": "training",
                "Meal Plan": "meal_plan",
                "Already in the Fridge": "fridge",
                "Shopping List": "shopping",
                "Recipes": "recipes",
            }.get(head)
            current_day = current_category = current_recipe_day = current_dish = None
            continue

        if section == "training":
            if line.startswith("- "):
                plan["training_bullets"].append(line[2:].strip())
            elif line.strip() and not line.startswith("#"):
                if plan["training_summary"]:
                    plan["training_summary"] += " " + line.strip()
                else:
                    plan["training_summary"] = line.strip()

        elif section == "meal_plan":
            if line.startswith("### "):
                head = line[4:].strip()
                m = re.match(r"^([A-Za-z]+)\s*[—–-]\s*(.+)$", head)
                if m:
                    current_day = {
                        "name": m.group(1),
                        "session": m.group(2),
                        "meals": [],
                    }
                else:
                    current_day = {"name": head, "session": "", "meals": []}
                plan["days"].append(current_day)
            elif current_day is not None and line.startswith("- "):
                bullet = line[2:].strip()
                m = re.match(r"^\*\*([^:*]+):\*\*\s*(.*)$", bullet)
                if m:
                    current_day["meals"].append(
                        {"label": m.group(1).strip(), "body": m.group(2).strip()}
                    )
                else:
                    current_day["meals"].append({"label": "", "body": bullet})

        elif section == "fridge":
            if line.startswith("- "):
                plan["fridge"].append(line[2:].strip())

        elif section == "shopping":
            if line.startswith("### "):
                current_category = {"category": line[4:].strip(), "items": []}
                plan["shopping"].append(current_category)
            elif current_category is not None and line.lstrip().startswith("-"):
                item = re.sub(
                    r"^-\s*\[\s*[xX ]?\s*\]\s*",
                    "",
                    line.strip(),
                )
                item = item.lstrip("-").strip()
                if item:
                    current_category["items"].append(item)

        elif section == "recipes":
            if line.startswith("### "):
                current_recipe_day = {"day": line[4:].strip(), "dishes": []}
                plan["recipes"].append(current_recipe_day)
                current_dish = None
            elif line.startswith("#### "):
                if current_recipe_day is None:
                    current_recipe_day = {"day": "", "dishes": []}
                    plan["recipes"].append(current_recipe_day)
                current_dish = {"title": line[5:].strip(), "lines": []}
                current_recipe_day["dishes"].append(current_dish)
            elif current_dish is not None:
                current_dish["lines"].append(line)
            elif (
                current_recipe_day is None
                and line.strip().startswith("*")
                and line.strip().endswith("*")
            ):
                plan["closing_note"] = line.strip().strip("*").strip()

        elif section is None and line.strip().startswith("*") and line.strip().endswith("*"):
            plan["closing_note"] = line.strip().strip("*").strip()

    for day in plan["recipes"]:
        for dish in day["dishes"]:
            dish["structured"] = parse_recipe_body(dish["lines"])
            del dish["lines"]

    return plan


PER_SERVING_KEYS = {
    "kcal": "kcal",
    "cal": "kcal",
    "calories": "kcal",
    "protein": "protein",
    "fat": "fat",
    "fats": "fat",
    "carb": "carbs",
    "carbs": "carbs",
    "fibre": "fibre",
    "fiber": "fibre",
}


def parse_per_serving(text: str) -> dict:
    """Parse '825 kcal · 41 g protein · 43 g fat · 61 g carbs · 3 g fibre'."""
    out = {}
    for part in re.split(r"\s*[·•|]\s*", text):
        m = re.match(
            r"^\s*(\d+(?:\.\d+)?)\s*g?\s*([A-Za-z]+)\s*$",
            part,
        )
        if not m:
            continue
        value = m.group(1)
        key = PER_SERVING_KEYS.get(m.group(2).lower())
        if key:
            out[key] = value
    return out


def parse_time(text: str) -> dict:
    """Parse '5 min prep · 10 min cook' (any order, either field optional)."""
    out = {}
    for part in re.split(r"\s*[·•|]\s*", text):
        m = re.match(r"^\s*(\d+)\s*min(?:s|utes)?\s*(prep|cook)\s*$", part, re.I)
        if m:
            out[m.group(2).lower()] = m.group(1)
    return out


def parse_recipe_body(lines):
    serves = ""
    ingredients = []
    steps = []
    note_chunks = []
    nutrition = {}
    times = {}
    image_override = {}
    meal = ""
    state = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if re.match(r"^\*\*Tags:\*\*", line):
            continue
        m_meal = re.match(r"^\*\*Meal:\*\*\s*(.+)$", line)
        if m_meal:
            meal = m_meal.group(1).strip()
            continue
        m_nutr = re.match(r"^\*\*Per serving:\*\*\s*(.+)$", line)
        if m_nutr:
            nutrition = parse_per_serving(m_nutr.group(1))
            continue
        m_time = re.match(r"^\*\*Time:\*\*\s*(.+)$", line)
        if m_time:
            times = parse_time(m_time.group(1))
            continue
        m_img = re.match(r"^\*\*Image:\*\*\s*(.+)$", line)
        if m_img:
            # Format: "category" or "🍗 category" — emoji optional.
            raw_img = m_img.group(1).strip()
            parts = raw_img.split(None, 1)
            if len(parts) == 2 and not parts[0].isascii():
                image_override = {"emoji": parts[0], "category": parts[1].strip().lower()}
            else:
                image_override = {"category": raw_img.lower()}
            continue

        m_ing = re.match(r"^\*\*Ingredients(\s*\(([^)]+)\))?\*\*\s*$", line)
        if m_ing:
            state = "ingredients"
            if m_ing.group(2):
                serves = m_ing.group(2).strip()
            continue
        if re.match(r"^\*\*Steps\*\*\s*$", line):
            state = "steps"
            continue

        if state == "ingredients" and line.startswith("- "):
            ingredients.append(line[2:].strip())
            continue
        if state == "steps" and re.match(r"^\d+\.", line):
            steps.append(re.sub(r"^\d+\.\s*", "", line).strip())
            continue

        if state is None and line.startswith("*") and line.endswith("*"):
            note_chunks.append(line.strip("*").strip())

    return {
        "serves": serves,
        "ingredients": ingredients,
        "steps": steps,
        "note": " ".join(note_chunks),
        "nutrition": nutrition,
        "times": times,
        "image_override": image_override,
        "meal": meal,
    }


# ============================================================== Helpers ====


def md_inline(text: str) -> str:
    """Convert inline markdown (em, strong) to HTML, stripping wrapping <p>."""
    if not text:
        return ""
    out = markdown.markdown(text).strip()
    if out.startswith("<p>") and out.endswith("</p>"):
        out = out[3:-4]
    return out


def slugify(text: str) -> str:
    """Lowercase, accents stripped, non-alphanumerics → '-', collapsed and trimmed."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    out = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return out.strip("-")


_DAY_REF_RE = re.compile(
    r"(See|Same method as|Same as|Refer to)\s+"
    r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*"
    r"[—–-]\s*([^.]+)",
    re.IGNORECASE,
)


def linkify_day_refs(note: str, anchor_index) -> str:
    """Wrap the day word in '(See|Same method as) {Day} — {Dish}' with a markdown
    link pointing to the matching recipe's anchor (resolved via anchor_index)."""
    if not note:
        return note

    def replace(match):
        prefix = match.group(1)
        day = match.group(2)
        ref_dish = match.group(3).strip()
        target = None
        for day_lower, dish_lower, anchor in anchor_index:
            if day_lower == day.lower() and ref_dish.lower() in dish_lower:
                target = anchor
                break
        if not target:
            return match.group(0)
        return f"{prefix} [{day}](#{target}) — {ref_dish}"

    return _DAY_REF_RE.sub(replace, note)


def format_serves(text: str) -> str:
    if not text:
        return "Serves 1"
    return re.sub(r"^(\d+)\s+servings?", r"Serves \1", text)


# Each rule: (keyword list, category slug, emoji). Order matters — first match
# wins, so put the primary protein/identifier ahead of generic side keywords.
CATEGORY_RULES = [
    (["scrambled", "omelette", "eggs on", "soft egg", "fried egg"], "eggs", "🍳"),
    (["oats", "oatmeal", "porridge", "oat bowl"], "oats", "🥣"),
    (["pasta", "spaghetti", "penne", "bolognese", "lasagna"], "pasta", "🍝"),
    (["chicken"], "chicken", "🍗"),
    (["fish", "salmon", "sardines", "cod", "tuna", "pescada", "dourada"], "fish", "🐟"),
    (["chickpea"], "chickpea", "🥗"),
    (["salad"], "salad", "🥗"),
    (["yogurt", "yoghurt"], "yogurt", "🥛"),
    (["bread", "toast", "sandwich"], "bread", "🥪"),
    (["rice"], "rice", "🍚"),
]


def detect_category(title: str) -> tuple:
    t = title.lower()
    for keywords, slug, emoji in CATEGORY_RULES:
        if any(k in t for k in keywords):
            return slug, emoji
    return "default", "🍽️"


# ================================================================= CSS =====


CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=Source+Sans+3:wght@300;400;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Noto+Color+Emoji&display=swap');

* { box-sizing: border-box; }

@page {
    size: A4;
    margin: 1.8cm 1.4cm 1.6cm;
}
@page :first {
    margin: 0;
}

html, body {
    margin: 0;
    padding: 0;
    color: #1d1d1d;
    font-family: 'Source Sans 3', 'Liberation Sans', 'DejaVu Sans', sans-serif;
    line-height: 1.5;
    font-size: 10.5pt;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}

h1, h2, h3, h4 { margin: 0; font-weight: 700; }
ul, ol { padding: 0; margin: 0; list-style: none; }

/* Top blue stripe — fixed; the cover element sits on top via z-index. */
.page-stripe {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 0.45cm;
    background: #0091d9;
    z-index: 10;
}

/* ============================== COVER ============================== */

/* Cover: solid + single linear gradient only. NO radial gradients, NO rgba
   translucent fills — those force PDF readers to rasterize Type-2/3 shading
   patterns and alpha-composite layers on every paint, which makes scrolling
   the cover heavy in Chrome's PDF viewer. */

.cover {
    position: relative;
    width: 21cm;
    height: 29.7cm;
    margin: 0;
    padding: 0;
    page-break-after: always;
    background: linear-gradient(180deg, #0095db 0%, #00669c 100%);
    color: #fff;
    z-index: 9999;          /* visually cover the fixed stripe on page 1 */
    overflow: hidden;
}

.cover-content {
    position: relative;
    z-index: 1;
    padding: 4.5cm 2.5cm 0;
    text-align: center;
}

.cover-eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.4em;
    font-size: 10pt;
    font-weight: 600;
    color: #c8e6f5;
    margin-bottom: 1.2cm;
}

.cover-mark {
    width: 2.6cm;
    height: 2.6cm;
    border-radius: 50%;
    background: #003352;
    border: 2px solid #ffffff;
    margin: 0 auto 1cm;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Playfair Display', 'Liberation Serif', 'DejaVu Serif', serif;
    font-size: 22pt;
    font-style: italic;
    font-weight: 700;
}

.cover-title {
    font-family: 'Playfair Display', 'Liberation Serif', 'DejaVu Serif', serif;
    font-size: 56pt;
    line-height: 1.05;
    font-weight: 700;
    margin: 0.2cm 0 0.5cm;
}

.cover-week {
    font-size: 14pt;
    letter-spacing: 0.05em;
    font-weight: 300;
    color: #e8f4fb;
    margin-bottom: 1.4cm;
}

.cover-divider {
    width: 2.2cm;
    height: 3px;
    background: #ffffff;
    margin: 0 auto 1.2cm;
}

.cover-stats {
    display: flex;
    justify-content: space-between;
    gap: 0.6cm;
    margin-top: 0.5cm;
}

.cover-stat {
    flex: 1;
    background: #0a7fb8;
    border: 1px solid #79c2e8;
    padding: 0.55cm 0.4cm;
    border-radius: 2px;
    text-align: center;
}

.cover-stat .label {
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 8.5pt;
    font-weight: 600;
    color: #c8e6f5;
    margin-bottom: 0.2cm;
}

.cover-stat .value {
    font-family: 'Playfair Display', 'Liberation Serif', 'DejaVu Serif', serif;
    font-size: 17pt;
    line-height: 1.15;
    font-weight: 700;
}

.cover-stat .value-sm {
    font-size: 10pt;
    line-height: 1.35;
    font-weight: 400;
}

.cover-band {
    position: absolute;
    bottom: 0; left: 0; right: 0;
    z-index: 1;
    background: #003352;
    padding: 0.9cm 2.5cm;
    text-align: center;
    font-style: italic;
    font-size: 11.5pt;
    line-height: 1.5;
}

/* ============================== Section frame ============================== */

.section {
    page-break-before: always;
    padding-top: 0.4cm;
}

.section-eyebrow {
    text-align: center;
    text-transform: uppercase;
    letter-spacing: 0.35em;
    font-size: 9pt;
    font-weight: 700;
    color: #c1632c;
    margin-bottom: 0.25cm;
}

.section-title {
    text-align: center;
    font-family: 'Playfair Display', 'Liberation Serif', 'DejaVu Serif', serif;
    font-size: 34pt;
    line-height: 1.05;
    font-weight: 700;
    color: #111;
    margin-bottom: 0.9cm;
}

.section-blurb {
    text-align: center;
    color: #555;
    max-width: 14cm;
    margin: -0.4cm auto 0.9cm;
    font-size: 11pt;
    font-style: italic;
}

/* ============================== Meal Plan ============================== */

.day {
    page-break-inside: avoid;
    margin-bottom: 0.45cm;
    border: 1px solid #e3e6e8;
    background: #fff;
}

.day-header {
    background: #0091d9;
    color: #fff;
    padding: 0.22cm 0.5cm;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
}

.day-name {
    font-family: 'Playfair Display', 'Liberation Serif', 'DejaVu Serif', serif;
    font-size: 14pt;
    font-weight: 700;
    letter-spacing: 0.02em;
}

.day-session {
    font-size: 9.5pt;
    font-style: italic;
    opacity: 0.95;
    text-align: right;
    max-width: 12cm;
}

.day-body {
    padding: 0.25cm 0.5cm 0.3cm;
}

.meal {
    padding: 0.07cm 0;
    font-size: 10.5pt;
    line-height: 1.5;
}

.meal-label {
    color: #c1632c;
    font-weight: 700;
    margin-right: 0.18em;
}

.meal em { color: #5a5a5a; font-style: italic; }

/* Fridge card */

.fridge {
    margin-top: 0.65cm;
    background: #f6f4ef;
    border-left: 4px solid #c1632c;
    padding: 0.4cm 0.55cm 0.45cm;
    page-break-inside: avoid;
}

.fridge h3 {
    font-family: 'Playfair Display', 'Liberation Serif', 'DejaVu Serif', serif;
    font-size: 13pt;
    color: #c1632c;
    margin-bottom: 0.2cm;
}

.fridge ul {
    columns: 2;
    column-gap: 0.6cm;
}

.fridge li {
    padding: 0.03cm 0 0.03cm 0.4cm;
    text-indent: -0.4cm;
    font-size: 10pt;
}

.fridge li::before {
    content: '•';
    color: #c1632c;
    margin-right: 0.2em;
}

/* ============================== Shopping List ============================== */

.shopping {
    column-count: 3;
    column-gap: 0.7cm;
    column-fill: balance;
}

.shopping .category {
    break-inside: avoid;
    margin: 0 0 0.5cm;
    padding: 0;
}

.shopping .category h3 {
    font-family: 'Source Sans 3', 'Liberation Sans', sans-serif;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 9.5pt;
    font-weight: 700;
    color: #0a3d62;
    padding-bottom: 0.1cm;
    border-bottom: 2px solid #0091d9;
    margin-bottom: 0.25cm;
}

.shopping li {
    padding: 0.05cm 0 0.05cm 0.55cm;
    text-indent: -0.55cm;
    font-size: 9.5pt;
    line-height: 1.4;
}

.shopping li::before {
    content: '◻';
    color: #999;
    margin-right: 0.25em;
    font-size: 10pt;
}

/* ============================== Recipes ============================== */

.recipes-intro {
    text-align: center;
}

.recipes-toc {
    column-count: 2;
    column-gap: 1.2cm;
    text-align: left;
    margin: 0.5cm 0.5cm 0;
}

.recipes-toc .toc-day {
    break-inside: avoid;
    margin-bottom: 0.45cm;
}

.recipes-toc .toc-day-name {
    font-family: 'Playfair Display', 'Liberation Serif', 'DejaVu Serif', serif;
    font-size: 13pt;
    font-weight: 700;
    color: #0091d9;
    padding-bottom: 0.08cm;
    border-bottom: 1px solid #d6dade;
    margin-bottom: 0.15cm;
}

.recipes-toc ul li {
    font-size: 10pt;
    padding: 0.04cm 0;
    color: #333;
}

.recipes-toc .toc-meal {
    color: #c1632c;
    font-weight: 600;
}

.recipe {
    page-break-before: always;
    padding: 0.4cm 0 0;
    display: flex;
    flex-direction: column;
    min-height: 25.2cm;
}

.recipe-main {
    flex: 0 0 auto;
}

/* Real food-photo preview (preferred). 12 × 8 cm centered = 3:2 ratio,
   matches the aspect we ask Gemini for. Stays under the body-budget on
   the longest recipe page (bolognese). */

.recipe-image-wrap {
    width: 100%;
    text-align: center;
    margin-bottom: 0.5cm;
}

.recipe-image {
    display: block;
    width: 12cm;
    height: 8cm;
    object-fit: cover;
    margin: 0 auto;
    border-radius: 2px;
}

/* Emoji fallback banner (when no real food photo is cached). */

.recipe-banner {
    width: 100%;
    height: 3.6cm;
    margin-bottom: 0.7cm;
    position: relative;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
}

/* Radial overlay removed: each banner used to stack two radial gradients on
   top of the linear base. That's 2-3 PDF shading patterns per banner × 20
   banners = ~60 objects, which inflated the rendered PDF significantly.
   The linear gradient on .banner-* alone is enough visual depth. */

.recipe-banner .banner-emoji {
    font-family: 'Noto Color Emoji', 'Apple Color Emoji', 'Segoe UI Emoji', sans-serif;
    font-size: 70pt;
    line-height: 1;
    position: relative;
    z-index: 1;
}

.recipe-banner .banner-side {
    font-family: 'Noto Color Emoji', 'Apple Color Emoji', 'Segoe UI Emoji', sans-serif;
    font-size: 30pt;
    line-height: 1;
    opacity: 0.35;
    position: relative;
    z-index: 1;
    margin: 0 0.8cm;
}

.banner-eggs     { background: linear-gradient(135deg, #fcc55a 0%, #e3962a 100%); }
.banner-oats     { background: linear-gradient(135deg, #d8be95 0%, #a48562 100%); }
.banner-yogurt   { background: linear-gradient(135deg, #f6e3c6 0%, #d6bd92 100%); }
.banner-pasta    { background: linear-gradient(135deg, #e58c44 0%, #b85518 100%); }
.banner-fish     { background: linear-gradient(135deg, #6fa4c8 0%, #3d6e93 100%); }
.banner-chicken  { background: linear-gradient(135deg, #d99e58 0%, #aa7034 100%); }
.banner-salad    { background: linear-gradient(135deg, #98c46c 0%, #5c8836 100%); }
.banner-chickpea { background: linear-gradient(135deg, #d8bb78 0%, #a08144 100%); }
.banner-bread    { background: linear-gradient(135deg, #d1a075 0%, #966c41 100%); }
.banner-rice     { background: linear-gradient(135deg, #ecdda7 0%, #c3aa66 100%); }
.banner-default  { background: linear-gradient(135deg, #95a0a8 0%, #5e6c75 100%); }

.recipe-eyebrow {
    text-align: center;
    text-transform: uppercase;
    letter-spacing: 0.32em;
    font-size: 11.5pt;
    font-weight: 700;
    color: #c1632c;
    margin-bottom: 0.3cm;
}

.recipe-title {
    text-align: center;
    font-family: 'Playfair Display', 'Liberation Serif', 'DejaVu Serif', serif;
    font-size: 26pt;
    line-height: 1.1;
    font-weight: 700;
    color: #111;
    margin: 0 auto 0.9cm;
    max-width: 16cm;
}

.recipe-body {
    display: grid;
    grid-template-columns: 5.8cm 1fr;
    gap: 1cm;
    margin-top: 0.4cm;
}

.recipe-body h3 {
    font-family: 'Source Sans 3', 'Liberation Sans', sans-serif;
    font-size: 12pt;
    font-weight: 700;
    color: #c1632c;
    margin-bottom: 0.3cm;
}

.recipe-ingredients ul li {
    padding: 0.06cm 0;
    font-size: 10pt;
    line-height: 1.45;
}

.recipe-ingredients ul li + li {
    border-top: 1px dotted #e3e3e3;
}

.recipe-steps ol {
    counter-reset: step;
}

.recipe-steps ol li {
    counter-increment: step;
    position: relative;
    padding: 0 0 0.35cm 0.95cm;
    font-size: 10.5pt;
    line-height: 1.5;
}

.recipe-steps ol li::before {
    content: counter(step);
    position: absolute;
    left: 0;
    top: 0.05cm;
    width: 0.65cm;
    height: 0.65cm;
    background: #0091d9;
    color: #fff;
    border-radius: 50%;
    text-align: center;
    line-height: 0.65cm;
    font-size: 9pt;
    font-weight: 700;
    font-family: 'Source Sans 3', 'Liberation Sans', sans-serif;
}

.recipe-note-only {
    margin-top: 0.6cm;
    padding: 0.5cm 0.6cm;
    background: #f6f4ef;
    border-left: 4px solid #c1632c;
    font-style: italic;
    color: #444;
    font-size: 11pt;
    line-height: 1.55;
}

.recipe-note-only a,
.recipes-toc a {
    color: #0091d9;
    text-decoration: underline;
    font-weight: 600;
}

.recipes-toc a {
    text-decoration: none;
    font-weight: 400;
    color: #333;
}

.recipes-toc a:hover { text-decoration: underline; }

/* Recipe nutrition table (matches the Kinetic template). */

.recipe-footer {
    margin-top: auto;
    padding-top: 1.2cm;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25cm;
}

.nutrition {
    border-collapse: collapse;
    font-size: 9pt;
    font-family: 'Source Sans 3', 'Liberation Sans', sans-serif;
    margin-top: 0.1cm;
}

.nutrition th, .nutrition td {
    padding: 0.16cm 0.32cm;
    text-align: center;
    border-bottom: 1px solid #d8d8d8;
}

.nutrition th {
    background: #ebebeb;
    font-weight: 700;
    color: #222;
    border-bottom: 1px solid #c8c8c8;
}

.nutrition td {
    color: #333;
}

.nutrition-caption {
    font-size: 8.5pt;
    color: #888;
    margin-top: 0.1cm;
    font-style: italic;
}

/* ============================== Closing ============================== */

.closing-note {
    margin-top: 0.9cm;
    text-align: center;
    font-style: italic;
    color: #666;
    font-size: 10pt;
}

/* ============================== Page numbers ============================== */

@page {
    @bottom-left {
        content: counter(page);
        font-family: 'Source Sans 3', 'Liberation Sans', sans-serif;
        font-size: 9pt;
        color: #888;
        margin-left: 1.4cm;
        margin-bottom: 1cm;
    }
}
@page :first {
    @bottom-left { content: none; }
}
"""


# =========================================================== Renderers =====


def render_cover(plan):
    total = hard = easy = ""
    for b in plan["training_bullets"]:
        m = re.match(r"^\*\*(Total|Hard days|Easy days):\*\*\s*(.*)$", b)
        if not m:
            continue
        v = m.group(2).strip()
        if m.group(1) == "Total":
            total = v
        elif m.group(1) == "Hard days":
            hard = v
        elif m.group(1) == "Easy days":
            easy = v

    title_html = html_lib.escape(plan["title"])

    return f"""
<section class="cover">
  <div class="cover-content">
    <div class="cover-eyebrow">For the Triathlete</div>
    <div class="cover-mark">TP</div>
    <h1 class="cover-title">{title_html}</h1>
    <div class="cover-week">{html_lib.escape(plan['week'])}</div>
    <div class="cover-divider"></div>
    <div class="cover-stats">
      <div class="cover-stat">
        <div class="label">Total Load</div>
        <div class="value">{md_inline(total)}</div>
      </div>
      <div class="cover-stat">
        <div class="label">Hard Days</div>
        <div class="value-sm">{md_inline(hard)}</div>
      </div>
      <div class="cover-stat">
        <div class="label">Easy Days</div>
        <div class="value-sm">{md_inline(easy)}</div>
      </div>
    </div>
  </div>
  <div class="cover-band">{md_inline(plan['training_summary'])}</div>
</section>
"""


def render_meal_plan(plan):
    parts = [
        '<section class="section">',
        '  <div class="section-eyebrow">Mon → Sun</div>',
        '  <h2 class="section-title">Weekly Meal Plan</h2>',
    ]
    for day in plan["days"]:
        meals_html = "\n".join(
            (
                '<div class="meal">'
                f'<span class="meal-label">{html_lib.escape(m["label"])}'
                f'{":" if m["label"] else ""}</span> {md_inline(m["body"])}'
                "</div>"
            )
            for m in day["meals"]
        )
        parts.append(
            f"""
<div class="day">
  <div class="day-header">
    <span class="day-name">{html_lib.escape(day['name'])}</span>
    <span class="day-session">{md_inline(day['session'])}</span>
  </div>
  <div class="day-body">{meals_html}</div>
</div>
"""
        )

    if plan["fridge"]:
        items_html = "\n".join(
            f"<li>{md_inline(item)}</li>" for item in plan["fridge"]
        )
        parts.append(
            f"""
<div class="fridge">
  <h3>Already in the Fridge</h3>
  <ul>{items_html}</ul>
</div>
"""
        )

    parts.append("</section>")
    return "\n".join(parts)


def render_shopping_list(plan):
    parts = [
        '<section class="section">',
        '  <div class="section-eyebrow">For the Week</div>',
        '  <h2 class="section-title">Shopping List</h2>',
        '  <div class="shopping">',
    ]
    for cat in plan["shopping"]:
        items_html = "\n".join(
            f"<li>{md_inline(item)}</li>" for item in cat["items"]
        )
        parts.append(
            f"""
<div class="category">
  <h3>{html_lib.escape(cat['category'])}</h3>
  <ul>{items_html}</ul>
</div>
"""
        )
    parts.append("  </div>")
    if plan["closing_note"]:
        parts.append(
            f'<p class="closing-note">{md_inline(plan["closing_note"])}</p>'
        )
    parts.append("</section>")
    return "\n".join(parts)


def render_recipes(plan, images_dir):
    # Pre-pass: give each dish a stable anchor ID and build a flat lookup so
    # "(See|Same method as) <Day> — <Dish>" references in note callouts can
    # link to the right page.
    anchor_index = []
    for d in plan["recipes"]:
        for dish in d["dishes"]:
            slug = slugify(d["day"]) + "-" + slugify(dish["title"])
            dish["anchor_id"] = "recipe-" + slug
            anchor_index.append(
                (d["day"].lower(), dish["title"].lower(), dish["anchor_id"])
            )

    parts = [
        '<section class="section recipes-intro">',
        '  <div class="section-eyebrow">Mon → Sun</div>',
        '  <h2 class="section-title">Recipes</h2>',
        '  <p class="section-blurb">A quick kitchen reference for every dish on the plan — flip to your day.</p>',
        '  <div class="recipes-toc">',
    ]
    for d in plan["recipes"]:
        if not d["dishes"]:
            continue
        parts.append('    <div class="toc-day">')
        parts.append(
            f'      <div class="toc-day-name">{html_lib.escape(d["day"])}</div>'
        )
        parts.append("      <ul>")
        for dish in d["dishes"]:
            aid = dish.get("anchor_id", "")
            meal = (dish.get("structured") or {}).get("meal", "")
            meal_html = (
                f'<span class="toc-meal">{html_lib.escape(meal)}</span> — '
                if meal
                else ""
            )
            parts.append(
                f'        <li><a href="#{aid}">{meal_html}{html_lib.escape(dish["title"])}</a></li>'
            )
        parts.append("      </ul>")
        parts.append("    </div>")
    parts.append("  </div>")
    parts.append("</section>")

    for d in plan["recipes"]:
        for dish in d["dishes"]:
            parts.append(render_recipe(d["day"], dish, anchor_index, images_dir))

    return "\n".join(parts)


def render_recipe_footer(s):
    """Render the nutrition table for a recipe. Returns '' if no data."""
    nutrition = s.get("nutrition") or {}
    times = s.get("times") or {}
    has_table = bool(nutrition) or bool(times)

    if not has_table:
        return ""

    parts = ['<div class="recipe-footer">']

    if has_table:
        def cell(v):
            return html_lib.escape(v) if v else "—"

        prep = f"{times['prep']} mins" if times.get("prep") else ""
        cook = f"{times['cook']} mins" if times.get("cook") else ""

        parts.append(
            '<table class="nutrition"><thead><tr>'
            "<th>Prep</th><th>Cook</th><th>Kcal</th>"
            "<th>Fats(g)</th><th>Carbs(g)</th><th>Protein(g)</th><th>Fibre(g)</th>"
            "</tr></thead><tbody><tr>"
            f"<td>{cell(prep)}</td>"
            f"<td>{cell(cook)}</td>"
            f"<td>{cell(nutrition.get('kcal', ''))}</td>"
            f"<td>{cell(nutrition.get('fat', ''))}</td>"
            f"<td>{cell(nutrition.get('carbs', ''))}</td>"
            f"<td>{cell(nutrition.get('protein', ''))}</td>"
            f"<td>{cell(nutrition.get('fibre', ''))}</td>"
            "</tr></tbody></table>"
            '<div class="nutrition-caption">*Nutrition per serve (estimate)</div>'
        )

    parts.append("</div>")
    return "\n".join(parts)


CATEGORY_DEFAULT_EMOJI = {slug: emoji for _, slug, emoji in CATEGORY_RULES}
CATEGORY_DEFAULT_EMOJI["default"] = "🍽️"


def render_recipe_banner(dish_title: str, image_override: dict, images_dir) -> str:
    """Render the visual preview above a recipe.

    Priority:
      1. A real food photo at `{images_dir}/{slugify(dish_title)}.jpg|.png`
         (typically generated via Composio's Gemini MCP, see SKILL.md A6.5).
      2. An emoji banner with the auto-detected (or overridden) category color.
    """
    if images_dir is not None:
        slug = slugify(dish_title)
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            candidate = images_dir / (slug + ext)
            if candidate.exists():
                return (
                    f'<div class="recipe-image-wrap">'
                    f'<img class="recipe-image" src="file://{candidate}" alt="" />'
                    f'</div>'
                )

    auto_slug, auto_emoji = detect_category(dish_title)
    slug = (image_override.get("category") or auto_slug).lower() if image_override else auto_slug
    if slug not in CATEGORY_DEFAULT_EMOJI:
        slug = "default"
    emoji = (image_override.get("emoji") if image_override else None) or CATEGORY_DEFAULT_EMOJI[slug] or auto_emoji
    return (
        f'<div class="recipe-banner banner-{html_lib.escape(slug)}">'
        f'<span class="banner-side">{html_lib.escape(emoji)}</span>'
        f'<span class="banner-emoji">{html_lib.escape(emoji)}</span>'
        f'<span class="banner-side">{html_lib.escape(emoji)}</span>'
        "</div>"
    )


def render_recipe(day_name, dish, anchor_index, images_dir):
    s = dish["structured"]
    title = html_lib.escape(dish["title"])
    meal = s.get("meal") or ""
    eyebrow = html_lib.escape(f"{day_name} · {meal}" if meal else day_name)
    footer = render_recipe_footer(s)
    banner = render_recipe_banner(dish["title"], s.get("image_override") or {}, images_dir)
    aid = html_lib.escape(dish.get("anchor_id", ""))

    if s["ingredients"] or s["steps"]:
        serves = format_serves(s["serves"])
        ings = "\n".join(f"<li>{md_inline(i)}</li>" for i in s["ingredients"])
        steps = "\n".join(f"<li>{md_inline(st)}</li>" for st in s["steps"])
        return f"""
<section class="recipe" id="{aid}">
  <div class="recipe-main">
    {banner}
    <div class="recipe-eyebrow">{eyebrow}</div>
    <h2 class="recipe-title">{title}</h2>
    <div class="recipe-body">
      <div class="recipe-ingredients">
        <h3>{html_lib.escape(serves)}</h3>
        <ul>{ings}</ul>
      </div>
      <div class="recipe-steps">
        <h3>What you need to do</h3>
        <ol>{steps}</ol>
      </div>
    </div>
  </div>
  {footer}
</section>
"""

    if s["note"]:
        linked = linkify_day_refs(s["note"], anchor_index)
        return f"""
<section class="recipe" id="{aid}">
  <div class="recipe-main">
    {banner}
    <div class="recipe-eyebrow">{eyebrow}</div>
    <h2 class="recipe-title">{title}</h2>
    <div class="recipe-note-only">{md_inline(linked)}</div>
  </div>
  {footer}
</section>
"""

    return ""


def render_html(plan, images_dir):
    body = [
        '<div class="page-stripe"></div>',
        render_cover(plan),
        render_meal_plan(plan),
        render_shopping_list(plan),
        render_recipes(plan, images_dir),
    ]
    return (
        "<!DOCTYPE html>\n"
        '<html><head><meta charset="utf-8">\n'
        f"<style>{CSS}</style>\n"
        "</head><body>\n"
        + "\n".join(body)
        + "\n</body></html>"
    )


# ================================================================== Main ===


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Path to input markdown file")
    parser.add_argument("output", help="Path to output PDF file")
    args = parser.parse_args()

    md_path = Path(args.input)
    md_text = md_path.read_text(encoding="utf-8")
    plan = parse_plan(md_text)

    # Image cache lives at `{markdown_dir}/images/{week-key}/`, where week-key
    # is the markdown filename's stem with the "meal-plan-" prefix stripped
    # (e.g. plans/meal-plan-week-may-11-2026.md → plans/images/week-may-11-2026/).
    images_dir = md_path.parent / "images" / md_path.stem.replace("meal-plan-", "")
    if not images_dir.is_dir():
        images_dir = None  # graceful fallback to emoji banners

    html = render_html(plan, images_dir)

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, encoding="utf-8"
    ) as f:
        f.write(html)
        html_path = f.name

    try:
        result = subprocess.run(
            [
                "chromium",
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--no-pdf-header-footer",
                "--virtual-time-budget=10000",
                f"--print-to-pdf={output_path}",
                f"file://{html_path}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not output_path.exists():
            sys.stderr.write(result.stderr)
            return result.returncode or 1
    finally:
        Path(html_path).unlink(missing_ok=True)

    print(str(output_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
