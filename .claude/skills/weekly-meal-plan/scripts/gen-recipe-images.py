#!/usr/bin/env python
"""Generate recipe preview images locally on Apple Silicon (MLX / Z-Image Turbo).

Loads the diffusion model **once** and generates every dish in a job file, which is
the whole point of batching here: model load costs ~20-30 s, so twenty one-shot CLI
invocations would waste ~10 min doing nothing but reloading weights.

Output is written straight into the week's images dir as 800x533 JPEG q85, named by
the same `slugify` the PDF renderer uses to look images up (md-to-pdf.py:281). A dish
whose image is missing falls back to an emoji banner, so partial failure is fine.

Usage:
    gen-recipe-images.py --out-dir plans/images/week-may-18-2026 --jobs jobs.json

Job file is a JSON list; each entry needs a `title` (slug source) and either a
`description` (wrapped in the shared food-photography template) or a verbatim
`prompt`. An explicit `slug` overrides the one derived from `title`.

    [
      {"title": "Grilled Salmon Bowl", "description": "grilled salmon fillet with
       roasted sweet potato wedges and steamed broccoli"},
      {"title": "Overnight Oats", "prompt": "Food photography, top-down view: ..."}
    ]

Exit status is 0 when at least one image was produced or everything was already
cached, and 1 when the model could not load or every job failed -- that is the
signal for the caller to fall through to a remote provider.
"""

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

# Keep in lockstep with the shared template in reference/image-providers.md. Neutral
# and concrete on purpose: brand names make some hosted providers refuse the prompt.
PROMPT_TEMPLATE = (
    "Food photography, top-down view: {description}. "
    "Rustic ceramic plate/bowl, natural daylight, clean wooden table, minimal styling, "
    "soft shadows, magazine quality, no text, no logos."
)

DEFAULT_MODEL = "mflux-community/z-image-turbo-mflux-q8"
GEN_SIZE = (1248, 832)   # 3:2, both multiples of 16 as the VAE requires
OUT_SIZE = (800, 533)    # what the renderer embeds; keeps each JPEG ~80-110 KB


def slugify(text: str) -> str:
    """Byte-for-byte the renderer's slugify (md-to-pdf.py:281). Must not drift."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    out = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return out.strip("-")


def load_jobs(path: Path) -> list[dict]:
    jobs = json.loads(path.read_text())
    if not isinstance(jobs, list):
        sys.exit(f"error: {path} must contain a JSON list, got {type(jobs).__name__}")

    out = []
    for i, job in enumerate(jobs):
        title = (job.get("title") or "").strip()
        slug = (job.get("slug") or slugify(title)).strip()
        if not slug:
            sys.exit(f"error: job {i} has neither a usable 'title' nor a 'slug'")

        prompt = job.get("prompt")
        if not prompt:
            description = (job.get("description") or title).strip().rstrip(".")
            if not description:
                sys.exit(f"error: job {i} ({slug}) has no 'prompt' or 'description'")
            prompt = PROMPT_TEMPLATE.format(description=description)
        out.append({"slug": slug, "prompt": prompt})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", type=Path, required=True, help="JSON list of dishes to render")
    ap.add_argument("--out-dir", type=Path, required=True, help="plans/images/week-{month}-{day}-{year}")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"HF repo or local path (default: {DEFAULT_MODEL})")
    ap.add_argument("--steps", type=int, default=9, help="denoising steps (default: 9, the turbo sweet spot)")
    ap.add_argument("--seed", type=int, default=42, help="base seed; each dish gets seed + its index")
    ap.add_argument("--force", action="store_true", help="regenerate images that already exist")
    ap.add_argument("--dry-run", action="store_true", help="list what would be generated, then exit")
    args = ap.parse_args()

    jobs = load_jobs(args.jobs)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Any extension the renderer accepts counts as already-cached, so a hand-dropped
    # PNG or a leftover from a remote provider is never silently overwritten.
    pending = []
    skipped = 0
    for i, job in enumerate(jobs):
        existing = [e for e in (".jpg", ".jpeg", ".png", ".webp") if (args.out_dir / (job["slug"] + e)).exists()]
        if existing and not args.force:
            skipped += 1
            continue
        pending.append((i, job))

    print(f"[gen] {len(jobs)} dishes: {len(pending)} to generate, {skipped} already cached", flush=True)
    if args.dry_run:
        for i, job in pending:
            print(f"  {job['slug']}: {job['prompt'][:100]}...")
        return 0
    if not pending:
        return 0

    # Imported here so --dry-run and argument errors stay instant; pulling in mlx and
    # the mflux model tree costs several seconds.
    from PIL import Image
    import mlx.core as mx
    from mflux.models.common.config.model_config import ModelConfig
    from mflux.models.z_image import ZImage

    t0 = time.monotonic()
    try:
        # A non-builtin --model is a weights path, not a config: mflux keeps the
        # z-image-turbo config and loads the (pre-quantized) weights from the repo.
        model = ZImage(model_path=args.model, model_config=ModelConfig.z_image_turbo())
    except Exception as exc:
        print(f"[gen] FATAL: could not load {args.model}: {exc}", file=sys.stderr)
        return 1
    print(f"[gen] model loaded in {time.monotonic() - t0:.1f}s", flush=True)

    done = failed = 0
    for n, (i, job) in enumerate(pending, 1):
        out_path = args.out_dir / (job["slug"] + ".jpg")
        t = time.monotonic()
        try:
            generated = model.generate_image(
                seed=args.seed + i,
                prompt=job["prompt"],
                num_inference_steps=args.steps,
                width=GEN_SIZE[0],
                height=GEN_SIZE[1],
            )
            generated.image.convert("RGB").resize(OUT_SIZE, Image.LANCZOS).save(
                out_path, "JPEG", quality=85, optimize=True, progressive=True
            )
            done += 1
            kb = out_path.stat().st_size / 1024
            print(f"[gen] {n}/{len(pending)} {job['slug']} -> {kb:.0f} KB ({time.monotonic() - t:.1f}s)", flush=True)
        except KeyboardInterrupt:
            print("[gen] interrupted", file=sys.stderr)
            break
        except Exception as exc:
            failed += 1
            print(f"[gen] {n}/{len(pending)} {job['slug']} FAILED: {exc}", file=sys.stderr, flush=True)
        # Peak memory otherwise creeps up across a 20-dish batch.
        mx.clear_cache()

    print(f"[gen] {done} generated, {skipped} cached, {failed} failed in {time.monotonic() - t0:.1f}s", flush=True)
    return 1 if done == 0 and failed else 0


if __name__ == "__main__":
    sys.exit(main())
