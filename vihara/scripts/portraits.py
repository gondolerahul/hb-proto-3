#!/usr/bin/env python3
"""Generate Vihara's colleague portraits — art bible §7 direction A.

Owner review, 2026-07-30: the procedural halftone bust was not personified
enough. It read as a *figure*; it did not read as a *person*. So the portraits go
back to being **generated**, which is what §7.1 direction A always specified and
what charter decision 8 listed as a pre-G1 obligation blocked on an image
pipeline.

The pipeline is not new. `backend/scripts/generate_portraits.py` built it before
the redesign, the owner reviewed four treatments and picked **T4 luminous**, and
that STYLE block is reproduced here byte-identical. What changed is only the cast:
the old personas were written per *role* (`agt-046` was "Bookkeeping &
Reconciliation, round spectacles"), while the redesign's colleagues are named
people whose ids mean something else entirely. Reusing those assets would have put
a bespectacled bookkeeper's face on Meera in Collections.

Three properties worth keeping when this is next touched:

* **One locked style block.** Every figure starts from the same bytes, so the cast
  reads as one house and not as twelve prompts. Personas add only silhouette.
* **The trace has no style opinion.** Dot presence, size and shade all come from
  the model's own luminance (`trace_png`). If a portrait looks wrong, the fix is
  the prompt, never the tracer — otherwise the medium drifts per portrait.
* **A frozen manifest.** `public/portraits/manifest.json` lists what exists.
  Regenerating a promoted portrait is a reviewed act, not a side effect of running
  this script: `promote` refuses to overwrite unless `--force` is passed.

Credentials come from the VM's attached service account via the metadata server
(`hirebuddha-vertex-ai`, cloud-platform scope). The user ADC in
~/.config/gcloud is expired and cannot be refreshed non-interactively; the
metadata path needs no login and is what the backend already uses.

    python scripts/portraits.py generate      # rasters into portraits-staging/
    python scripts/portraits.py trace         # rasters -> SVG dot lattices
    python scripts/portraits.py promote       # into public/portraits/ + manifest
    python scripts/portraits.py all
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGING = ROOT / "portraits-staging"
PROMOTED = ROOT / "public" / "portraits"
MANIFEST = PROMOTED / "manifest.json"

PROJECT = "hirebuddha-production"
REGION = "us-central1"
METADATA_TOKEN = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)

#: Model availability is a deploy fact, not a code fact — tried in order.
MODEL_CANDIDATES = (
    "imagen-4.0-generate-001",
    "imagen-3.0-generate-002",
    "imagen-3.0-generate-001",
)

#: The locked style block, reproduced byte-identical from the reviewed pipeline.
#: Do not edit to fix one portrait. Edit that portrait's persona.
STYLE = (
    "A portrait made ONLY of small round dots of warm gold, a halftone "
    "stipple illustration. Shoulder-up bust of a single figure on a pure "
    "near-black background (very dark warm black, #0a0908). The figure is "
    "formed entirely by the density and size of golden dots (#edab48): "
    "dense dots where light falls, sparse dots in shadow, no outlines, no "
    "solid fills, no lines. Features are implied by dot spacing only — "
    "absolutely no drawn eyes, no mouth, no facial features, no "
    "photorealism, no skin texture, no text, no watermark. Calm, "
    "dignified, slightly luminous. Centered, facing slightly off-axis. "
)

#: T4 — the treatment the owner picked from four, 2026-07-29.
TREATMENT = (
    "Luminous halftone: fine dots with a gentle glow bloom on the "
    "lit side of the figure, as if the portrait were made of "
    "embers, still calm and dark overall."
)

#: The cast. One line each, silhouette only — the style block does the rest.
#:
#: Written against the redesign's actual fixtures so an id means the same person
#: everywhere: `estate.ts` COLLEAGUES, `people.ts` DOSSIERS, `decisions.ts`
#: STANDUP, `talent.ts` CANDIDATES, `gallery.ts` colleagues past.
#:
#: Each line names build, hair and one garment detail, because those are what a
#: dot lattice can actually carry at 40px. Anything finer is lost in the trace and
#: only makes the prompt harder for the model to hold.
PERSONAS: dict[str, tuple[str, str]] = {
    "pragya": (
        "Pragya · the account manager",
        "An elegant upright figure, hair gathered in a low bun, a long "
        "shawl-collar drape over one shoulder; the stillest posture of the set.",
    ),
    # ---- serving colleagues -------------------------------------------------
    "agt-046": (
        "Meera · Collections",
        "A composed woman in her thirties, dark hair drawn back smoothly, level "
        "square shoulders in a plain high-necked kurta; direct and unhurried.",
    ),
    "agt-038": (
        "Ravi · Reconciliation",
        "A younger man, short neat side-parted hair, a plain buttoned collar, a "
        "slight attentive forward lean, as though checking a figure twice.",
    ),
    "agt-041": (
        "Anjali · Dunning",
        "A woman with shoulder-length hair tucked behind one ear, a high "
        "mandarin collar, chin level; firm without hardness.",
    ),
    "agt-013": (
        "Devika · Quoting",
        "A senior woman, hair in a sleek low knot, crisp notched lapels over a "
        "collarless blouse, the precision of a drafted document.",
    ),
    "agt-092": (
        "Farhan · Bookkeeping",
        "A slighter man, close-cropped hair, round spectacles implied by two "
        "brighter dot rings, a cardigan collar.",
    ),
    # ---- colleagues past (Gallery renders these drained) --------------------
    "agt-021": (
        "Kavya · Quoting, retired",
        "A woman with loose wavy hair falling past the shoulder, a soft scarf "
        "loop at the neck, a thoughtful head-tilt.",
    ),
    "agt-055": (
        "Ishan · Outreach, left in probation",
        "A young man with short curls, an open unbuttoned collar, shoulders "
        "slightly raised, eager and unfinished.",
    ),
    # ---- Talent Office candidates ------------------------------------------
    "cand-8801": (
        "Kabir · Negotiator",
        "A man with swept-back hair, high sharp lapels, chin a little raised; "
        "the most formal silhouette in the set.",
    ),
    "cand-8814": (
        "Anaya · Collector",
        "A woman with short practical hair, a rolled-sleeve impression at the "
        "shoulder line, quick upright posture.",
    ),
    "cand-8822": (
        "Priya · Auditor",
        "A woman with hair in a tight centre-parted bun, a narrow-collared "
        "jacket buttoned to the throat, very still.",
    ),
    "cand-8830": (
        "Devraj · Negotiator",
        "A broad-shouldered older man, greying close-cropped hair, a waistcoat "
        "line under a heavy jacket collar.",
    ),
}

# --------------------------------------------------------------------- trace

GRID = 112
DOT_FLOOR = 0.045
#: Lifts mid-tones so the trace keeps the artwork's luminosity — the raw mean
#: under-reads a dotted source (dots on black average dark even where the print
#: reads bright).
GAMMA = 0.62
#: The brand's gold ramp, darkest first. Shade follows luminance so a portrait is
#: lit by the same key as everything else in the product.
GOLD_RAMP = (
    ("#4f3614", 0.16),
    ("#7d551f", 0.30),
    ("#a8722a", 0.46),
    ("#d2923a", 0.63),
    ("#edab48", 0.80),
    ("#fdc871", 1.01),
)


def _token() -> str:
    request = urllib.request.Request(
        METADATA_TOKEN, headers={"Metadata-Flavor": "Google"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)["access_token"]


def _generate(prompt: str, model: str, token: str) -> bytes | None:
    url = (
        f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{PROJECT}"
        f"/locations/{REGION}/publishers/google/models/{model}:predict"
    )
    body = json.dumps(
        {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": "1:1",
                # People are the entire point of this pipeline; without this the
                # model returns nothing and it reads as a transport failure.
                "personGeneration": "allow_adult",
            },
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode()[:300]
        print(f"  {model}: HTTP {error.code} {detail}")
        return None
    predictions = payload.get("predictions") or []
    if not predictions:
        print(f"  {model}: no image returned (safety filter?)")
        return None
    return base64.b64decode(predictions[0]["bytesBase64Encoded"])


def pick_model(token: str) -> str:
    probe = STYLE + TREATMENT + " The figure: " + PERSONAS["pragya"][1]
    for model in MODEL_CANDIDATES:
        image = _generate(probe, model, token)
        if image:
            STAGING.mkdir(parents=True, exist_ok=True)
            (STAGING / "_probe.png").write_bytes(image)
            print(f"model: {model}")
            return model
    raise SystemExit("no Imagen model answered on this project/region")


def generate(force: bool = False) -> None:
    STAGING.mkdir(parents=True, exist_ok=True)
    token = _token()
    model = pick_model(token)
    for key, (label, persona) in PERSONAS.items():
        out = STAGING / f"{key}.png"
        if out.exists() and not force:
            print(f"kept    {key}  ({label})")
            continue
        prompt = STYLE + TREATMENT + " The figure: " + persona
        image = _generate(prompt, model, token)
        if not image:
            print(f"FAILED  {key}  ({label})")
            continue
        out.write_bytes(image)
        print(f"drew    {key}  ({label})  {len(image) // 1024} KB")


def trace_png(png_path: Path) -> str:
    """Resample the artwork's light onto a fixed dot lattice.

    No style opinion: dot presence, size and shade all come from the model's own
    luminance. That is deliberate — if the tracer had taste, twelve portraits
    would drift into twelve mediums.
    """
    import numpy as np
    from PIL import Image

    image = Image.open(png_path).convert("L")

    # Crop to the artwork, not to the canvas.
    #
    # Imagen centres the bust with a wide black margin, so tracing the raw square
    # spends a third of the lattice on empty ground and the face lands small — a
    # real problem at 34px in the dossier roster, where the head is then ~12px.
    # Find the lit content, square it up around its own centre, and pad by 6%.
    array = np.asarray(image, dtype=np.float64) / 255.0
    lit = np.argwhere(array > 0.06)
    if lit.size:
        top, left = lit.min(axis=0)
        bottom, right = lit.max(axis=0)
        cx = (left + right) / 2
        cy = (top + bottom) / 2
        half = max(right - left, bottom - top) / 2 * 1.06
        # Clamp to the canvas rather than letting the box run off it, which would
        # otherwise shift the figure off-centre on an already-tight source.
        half = min(half, cx, cy, image.width - cx, image.height - cy)
        image = image.crop(
            (int(cx - half), int(cy - half), int(cx + half), int(cy + half))
        )
    else:
        side = min(image.size)
        image = image.crop((0, 0, side, side))

    image = image.resize((GRID * 4, GRID * 4))
    pixels = np.asarray(image, dtype=np.float64) / 255.0

    cell = 4
    circles: list[str] = []
    unit = 1000 / GRID
    for row in range(GRID):
        for col in range(GRID):
            block = pixels[row * cell : (row + 1) * cell, col * cell : (col + 1) * cell]
            lum = float(block.mean())
            if lum < DOT_FLOOR:
                continue
            lum = min(1.0, lum**GAMMA)
            radius = (unit * 0.5) * lum
            shade = next(hex_ for hex_, ceiling in GOLD_RAMP if lum < ceiling)
            cx = round(col * unit + unit / 2, 1)
            cy = round(row * unit + unit / 2, 1)
            circles.append(
                f'<circle cx="{cx}" cy="{cy}" r="{round(radius, 2)}" fill="{shade}"/>'
            )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" '
        'role="img" aria-hidden="true">\n'
        '<rect width="1000" height="1000" fill="#0a0908"/>\n'
        + "\n".join(circles)
        + "\n</svg>\n"
    )


def trace() -> None:
    for png_path in sorted(STAGING.glob("*.png")):
        if png_path.name.startswith("_"):
            continue
        svg = trace_png(png_path)
        out = png_path.with_suffix(".svg")
        out.write_text(svg, encoding="utf-8")
        print(f"traced  {png_path.stem}  ({len(svg) // 1024} KB)")


def promote(force: bool = False) -> None:
    """Move traced SVGs into public/ and write the manifest.

    Refuses to overwrite an existing promoted portrait without `--force`: a
    colleague's face changing under them is a reviewed act, not a build step.
    """
    PROMOTED.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text())

    for svg_path in sorted(STAGING.glob("*.svg")):
        key = svg_path.stem
        if key not in PERSONAS:
            continue
        target = PROMOTED / f"{key}.svg"
        if target.exists() and not force:
            print(f"kept    {key}  (already promoted)")
            manifest[key] = PERSONAS[key][0]
            continue
        target.write_text(svg_path.read_text(), encoding="utf-8")
        manifest[key] = PERSONAS[key][0]
        print(f"promoted {key}  ({PERSONAS[key][0]})")

    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"manifest: {len(manifest)} portraits")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("generate", "trace", "promote", "all"))
    parser.add_argument(
        "--force",
        action="store_true",
        help="redraw rasters / overwrite promoted portraits (a reviewed act)",
    )
    args = parser.parse_args()

    if args.step in ("generate", "all"):
        generate(force=args.force)
    if args.step in ("trace", "all"):
        trace()
    if args.step in ("promote", "all"):
        promote(force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
