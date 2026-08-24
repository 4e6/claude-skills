# Recipe preview images — provider chain

Mechanics for action A6.5 in [SKILL.md](../SKILL.md). Read this only when
actually generating images; the rest of the skill never needs it.

Each recipe page in the PDF shows a 12 × 8 cm food photo above the title. The renderer looks each one up at `plans/images/week-{month}-{day}-{year}/{slug(dish_title)}.{jpg|jpeg|png|webp}`. The slug uses the same `slugify` logic the renderer uses: NFKD-normalise → strip combining accents → lowercase → non-alphanumerics replaced with `-` → trim. If the images dir doesn't exist or a specific dish is missing, the renderer silently falls back to the emoji banner — skipping is always acceptable; the rest of the PDF still ships.

**Provider fallback chain.** Try in order; stop at the first one that returns images:

1. **Composio Gemini MCP** (primary, best quality)
2. **Hugging Face FLUX.1-schnell via `dynamic_space`** (free, authenticated)
3. **Pollinations.ai** (zero-auth last-resort fallback)

**Shared prompt template** (works for every provider — keep neutral and concrete; brand names trigger recitation blocks on Gemini):

```
Food photography, top-down view: {plainspoken dish description with key ingredients}.
Rustic ceramic plate/bowl, natural daylight, clean wooden table, minimal styling,
soft shadows, magazine quality, no text, no logos.
```

## Option 1: Composio Gemini MCP

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

## Option 2: Hugging Face FLUX.1-schnell via dynamic_space (fallback)

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

## Option 3: Pollinations.ai (last-resort fallback)

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

**Final PDF size** with images from any provider: ~2.5–3 MB.

