# Recipe preview images — provider chain

Mechanics for action A6.5 in [SKILL.md](../SKILL.md). Read this only when
actually generating images; the rest of the skill never needs it.

Each recipe page in the PDF shows a 12 × 8 cm food photo above the title. The renderer looks each one up at `plans/images/week-{month}-{day}-{year}/{slug(dish_title)}.{jpg|jpeg|png|webp}`. The slug uses the same `slugify` logic the renderer uses: NFKD-normalise → strip combining accents → lowercase → non-alphanumerics replaced with `-` → trim. If the images dir doesn't exist or a specific dish is missing, the renderer silently falls back to the emoji banner — skipping is always acceptable; the rest of the PDF still ships.

**Provider fallback chain.** Try in order; stop at the first one that returns images:

1. **Local Z-Image Turbo on the Mac's GPU** (default — offline, unlimited, no API key)
2. **Composio Gemini MCP** (first hosted fallback)
3. **Hugging Face FLUX.1-schnell via `dynamic_space`** (free, authenticated)
4. **Pollinations.ai** (zero-auth last-resort fallback)

**Shared prompt template** (works for every provider — keep neutral and concrete; brand names trigger recitation blocks on Gemini):

```
Food photography, top-down view: {plainspoken dish description with key ingredients}.
Rustic ceramic plate/bowl, natural daylight, clean wooden table, minimal styling,
soft shadows, magazine quality, no text, no logos.
```

Option 1 owns this template in code (`PROMPT_TEMPLATE` in [scripts/gen-recipe-images.py](../scripts/gen-recipe-images.py)) and fills it in for you, so on the local path you supply only the `{description}` half. The hosted options need the whole string built by hand.

---

## Option 1: Local Z-Image Turbo (default)

Generates every image on the Mac's own GPU via [mflux](https://github.com/filipstrand/mflux) — a native MLX port of several diffusion models. **No API key, no quota, no network** (after the one-time model download), and no per-image cost, which makes it strictly better than the hosted options for a weekly 20-image batch.

**Model:** `mflux-community/z-image-turbo-mflux-q8` — Z-Image Turbo (6B, Apache-2.0), pre-quantized to 8-bit by the mflux community. ~11 GB, downloaded once to `~/.cache/huggingface` and reused forever. The repo is public and ungated: **no Hugging Face token is required.** Prefer this pre-quantized repo over the upstream `Tongyi-MAI/Z-Image-Turbo`, which is a 33 GB fp32 download that mflux would then have to quantize at load.

**Requirements:** Apple Silicon (MLX is Metal-only — there is no x86 build). If the host isn't an Apple-Silicon Mac, skip straight to Option 2.

### One-time setup (idempotent — the snippet below re-creates it if missing)

```bash
SKILL_DIR=<base directory from skill launch>

if [ ! -x "$SKILL_DIR/scripts/.venv-imagegen/bin/python" ]; then
    # Explicit >=3.10 interpreter: macOS's system python3 is 3.9.6, which mflux
    # rejects (requires-python >=3.10). Bare `python3` picks the wrong one.
    /opt/homebrew/bin/python3.14 -m venv "$SKILL_DIR/scripts/.venv-imagegen"
    "$SKILL_DIR/scripts/.venv-imagegen/bin/pip" install -q \
        -r "$SKILL_DIR/scripts/requirements-imagegen.txt"
fi
```

This is a **separate venv from the renderer's** `scripts/.venv/`: mflux pulls mlx + torch + transformers (~1.2 GB installed), and rendering a PDF must not have to carry that.

### Generating

Write a job file — one entry per dish, `title` for the slug and `description` for the prompt — then run the batch script once. It loads the model a single time for the whole week; twenty one-shot CLI calls would instead re-load weights twenty times.

```bash
SKILL_DIR=<base directory from skill launch>
WEEK_DIR="$SKILL_DIR/plans/images/week-{month}-{day}-{year}"

cat > /tmp/recipe-jobs.json <<'EOF'
[
  {"title": "Overnight Oats with Berries",
   "description": "overnight oats in a glass jar topped with fresh blueberries, raspberries and sliced banana, drizzled with honey"},
  {"title": "Bacalhau à Brás",
   "description": "Portuguese shredded salt cod with thin crispy potato straws, scrambled egg, black olives and chopped parsley"}
]
EOF

"$SKILL_DIR/scripts/.venv-imagegen/bin/python" \
    "$SKILL_DIR/scripts/gen-recipe-images.py" \
    --jobs /tmp/recipe-jobs.json --out-dir "$WEEK_DIR"
```

`title` must be the dish title **exactly as it appears in the plan markdown** — the script derives the filename with the renderer's own `slugify`, so any drift silently produces an unused image and an emoji banner in the PDF. A job may instead carry an explicit `slug`, or a verbatim `prompt` that bypasses the shared template.

The script writes 800 × 533 JPEG q85 straight into `--out-dir`, resizing in-process with Pillow — **the local path needs no `magick`**, unlike the hosted options below.

Useful flags: `--dry-run` (print the resolved slugs and prompts, generate nothing — worth doing once to eyeball the slugs), `--force` (regenerate images that already exist), `--steps` (default 9), `--seed` (default 42; each dish gets `seed + index`, so runs are reproducible).

**Measured on an M5 Pro / 48 GB** (1248 × 832, 9 steps): ~40 s per image including the folded-in lazy weight load on the first one, so a 20-recipe week is ~13 min unattended. Output lands at ~50–80 KB per JPEG, ~1.4 MB for a full week.

**Pitfalls.**
- **Re-runs are free and resumable.** Any dish that already has an image in `--out-dir` (any of the four extensions the renderer accepts) is skipped, so re-running after an interruption only generates what's missing, and a hand-picked image dropped in by the user is never clobbered. A fully-cached run exits in ~0.05 s.
- **Exit status is the fall-through signal.** `0` means at least one image was produced or everything was already cached; `1` means the model could not load or every dish failed — that's when to move to Option 2. Individual dish failures are logged to stderr and do not abort the batch; those dishes just get emoji banners.
- **First run downloads ~11 GB** and looks like a long hang — mflux prints no progress until the download completes. Run it in the background and watch `du -sh ~/.cache/huggingface`. Every later run is fully offline.
- **On battery, 20 images is a real power draw.** mflux stops generating when the battery hits 5% (`--battery-percentage-stop-limit`, which the batch script leaves at its default); a partial batch is safe — re-run on power and it resumes.
- Peak memory is ~12–14 GB of unified memory. Comfortable on 48 GB; on a 16 GB Mac add `--low-ram` to the mflux call.
- Z-Image Turbo is guidance-distilled, so `--guidance` and negative prompts do nothing. Steer with the prompt text alone; if a dish comes out poorly, reword the `description` and re-run that one dish with `--force`.

---

## Option 2: Composio Gemini MCP (first hosted fallback)

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

## Option 3: Hugging Face FLUX.1-schnell via dynamic_space (fallback)

Free image generation via the `hf-mcp-server` MCP. Uses Black Forest Labs' `FLUX.1-schnell` (4-step turbo diffusion), reached through `mcp__hf-mcp-server__dynamic_space` (the generic Space-invocation tool) targeting the curated `evalstate/flux1_schnell` Space. Login is already wired up (authenticated as user `4e6`).

Why this specific Space and not a typed tool: HF's MCP server exposes one typed tool per pre-registered Space, and the only typed image-gen tool currently registered is Z-Image Turbo (`mcp__hf-mcp-server__gr1_z_image_turbo_generate`). Z-Image Turbo reserves **~60 s of ZeroGPU time per call**, which only fits 2–3 images into the free 5-min daily ZeroGPU budget. `evalstate/flux1_schnell` reserves **~10 s per call**, fits ~30 images in the same budget — enough for a full 20-recipe week. Quality at 4 inference steps is comparable for food photography. (Note that Option 1 runs *that same Z-Image Turbo model* locally, where the ZeroGPU budget that made it impractical here doesn't apply at all.)

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

## Option 4: Pollinations.ai (last-resort fallback)

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

**Final PDF size** with images from any provider: ~2–3 MB.
