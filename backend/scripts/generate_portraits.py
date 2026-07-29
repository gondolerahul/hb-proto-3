"""The A-direction portrait pipeline (Inc-7, charter decision 8; R1 + the
2026-07-29 brainstorm round).

Owner decisions this implements, verbatim:

* **Fully model-generated** finals — Vertex Imagen (ADC) renders the whole
  look from one locked style block + a reviewed one-line persona each.
* **Roster:** Pragya + the nine Wave-0 workforce agents. Everything else
  keeps the procedural seal.
* **Personas owner-reviewed** — the lines below were approved 2026-07-29
  ("approved as drafted"); editing one is a reviewed act.
* **SVG dot geometry by trace** — `--trace` resamples each bitmap's light
  onto a fixed dot lattice in the gold ramp. The trace has no style
  opinion; when a portrait's dots do not survive it, that colleague ships
  as PNG and the delta is recorded (format yields, the art never does).
* **Two style rounds** — `--round1` renders four treatment candidates of
  Pragya for the owner's pick; `--agents --treatment TN` mass-produces the
  nine with the locked treatment. **Frozen once published**: regenerating
  a promoted portrait is a reviewed act, like a certified version bump.

This is a dev-time ops script: no tenant, no wallet, no runtime path.

Usage (from backend/):
    poetry run python scripts/generate_portraits.py --round1
    poetry run python scripts/generate_portraits.py --agents --treatment T1
    poetry run python scripts/generate_portraits.py --trace
    poetry run python scripts/generate_portraits.py --promote --treatment T1
"""
from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
STAGING = BACKEND_ROOT.parent / "vihara" / "portraits-staging"
PUBLIC = BACKEND_ROOT.parent / "vihara" / "public" / "portraits"
MANIFEST = (
    BACKEND_ROOT.parent / "vihara" / "src" / "components" / "portraits"
    / "manifest.json")

PROJECT = "hirebuddha-production"
REGION = "us-central1"
#: Tried in order until one answers — model availability is a deploy fact,
#: not a code fact.
MODEL_CANDIDATES = (
    "imagen-4.0-generate-001",
    "imagen-3.0-generate-002",
    "imagen-3.0-generate-001",
    "imagegeneration@006",
)

#: The locked style block (art bible §7.1's medium, made into prompt
#: language). Every generation starts from this, byte-identical.
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

TREATMENTS: dict[str, str] = {
    "T1": ("Fine-grain halftone: very small dots in a dense even field, "
           "soft gradual falloff from light to dark, delicate and quiet."),
    "T2": ("Bold print halftone: larger dots on a visible regular lattice, "
           "high contrast, confident screen-print feel."),
    "T3": ("Hand-stippled: irregular organically placed dots like a "
           "master engraver's stipple, varied dot sizes, textured and warm."),
    "T4": ("Luminous halftone: fine dots with a gentle glow bloom on the "
           "lit side of the figure, as if the portrait were made of "
           "embers, still calm and dark overall."),
}

#: The reviewed personas — approved by the owner 2026-07-29, as drafted.
PERSONAS: dict[str, tuple[str, str]] = {
    "pragya": (
        "Pragya",
        "An elegant upright figure, hair gathered in a low bun, a long "
        "shawl-collar drape over one shoulder; the stillest posture."),
    "agt-013": (
        "Inbound Deal Closer",
        "Energetic short-cropped silhouette, open collar, a slight "
        "forward lean, mid-conversation."),
    "agt-015": (
        "Proposal & Quote",
        "Neat side-parted hair, high buttoned collar, square shoulders, "
        "the precision of a drafted document."),
    "agt-030": (
        "Omnichannel Care Orchestrator",
        "Soft rounded silhouette, shoulder-length hair tucked behind one "
        "ear, a slim headset arc implied at the temple."),
    "agt-035": (
        "Appointment Concierge",
        "Slim upright figure, short curls, a mandarin-collar jacket, a "
        "maitre d's poise."),
    "agt-092": (
        "Scheduling Agent",
        "Compact practical silhouette, hair in a short tail, a "
        "rolled-sleeves impression at the shoulder line."),
    "agt-038": (
        "Accounts Receivable",
        "Steady broad-shouldered figure, close-cropped hair, a waistcoat "
        "line."),
    "agt-046": (
        "Bookkeeping & Reconciliation",
        "A slighter figure, round spectacles implied by two brighter dot "
        "rings, cardigan collar."),
    "agt-068": (
        "Regulatory Watchdog",
        "The most formal silhouette: swept-back hair, high sharp lapels, "
        "chin slightly raised."),
    "agt-051": (
        "Cashflow Forecaster",
        "A thoughtful head-tilt, loose wavy hair, a scarf loop, gaze "
        "toward the horizon implied by posture alone."),
}

AGENT_KEYS = tuple(k for k in PERSONAS if k != "pragya")


def _token() -> str:
    import google.auth
    import google.auth.transport.requests

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(google.auth.transport.requests.Request())
    return str(credentials.token)


def _generate(prompt: str, model: str, token: str) -> bytes | None:
    url = (
        f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{PROJECT}"
        f"/locations/{REGION}/publishers/google/models/{model}:predict")
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "aspectRatio": "1:1"},
        },
        timeout=120,
    )
    if response.status_code == 404:
        return None  # model not available on this project — try the next
    response.raise_for_status()
    predictions = response.json().get("predictions", [])
    if not predictions:
        raise RuntimeError(
            f"{model} returned no image (safety filter?) for: {prompt[:80]}…")
    return base64.b64decode(predictions[0]["bytesBase64Encoded"])


def _pick_model(token: str) -> str:
    probe = STYLE + TREATMENTS["T1"] + " " + PERSONAS["pragya"][1]
    for model in MODEL_CANDIDATES:
        try:
            image = _generate(probe, model, token)
        except Exception as error:  # noqa: BLE001 — probing is the point
            print(f"  {model}: {error}")
            continue
        if image is not None:
            (STAGING / "_probe.png").write_bytes(image)
            print(f"model: {model}")
            return model
    raise SystemExit("no Imagen model answered on this project/region")


def generate_round1(model: str, token: str) -> None:
    name, persona = PERSONAS["pragya"]
    for key, treatment in TREATMENTS.items():
        prompt = STYLE + treatment + " The figure: " + persona
        image = _generate(prompt, model, token)
        if image is None:
            raise SystemExit(f"{model} vanished mid-run")
        out = STAGING / f"pragya.{key}.png"
        out.write_bytes(image)
        print(f"round 1: {name} {key} -> {out.name}")


def generate_agents(model: str, token: str, treatment: str) -> None:
    for key in AGENT_KEYS:
        name, persona = PERSONAS[key]
        prompt = STYLE + TREATMENTS[treatment] + " The figure: " + persona
        image = _generate(prompt, model, token)
        if image is None:
            raise SystemExit(f"{model} vanished mid-run")
        out = STAGING / f"{key}.{treatment}.png"
        out.write_bytes(image)
        print(f"round 2: {name} -> {out.name}")


# ── the trace: bitmap light → gold dot geometry ─────────────────────────────

GOLD_RAMP = (("#a8722a", 0.18), ("#edab48", 0.42), ("#fdc871", 1.01))
GRID = 96
DOT_FLOOR = 0.045
#: Lifts mid-tones so the trace keeps the artwork's luminosity — the raw
#: mean under-reads a dotted source (dots on black average dark even where
#: the print reads bright).
GAMMA = 0.62


def trace_png(png_path: Path) -> str:
    """Resample the artwork's light onto a fixed dot lattice. No style
    opinion: dot presence, size and ramp shade all come from the model's
    own luminance."""
    import numpy as np
    from PIL import Image

    image = Image.open(png_path).convert("L")
    side = min(image.size)
    image = image.crop((0, 0, side, side)).resize((GRID * 4, GRID * 4))
    pixels = np.asarray(image, dtype=np.float64) / 255.0

    cell = 4
    circles: list[str] = []
    unit = 1000 / GRID
    for row in range(GRID):
        for col in range(GRID):
            block = pixels[row * cell:(row + 1) * cell,
                           col * cell:(col + 1) * cell]
            lum = float(block.mean())
            if lum < DOT_FLOOR:
                continue
            lum = min(1.0, lum**GAMMA)
            radius = (unit * 0.5) * lum
            shade = next(hex_ for hex_, ceiling in GOLD_RAMP if lum < ceiling)
            cx = round(col * unit + unit / 2, 1)
            cy = round(row * unit + unit / 2, 1)
            circles.append(
                f'<circle cx="{cx}" cy="{cy}" r="{round(radius, 2)}" '
                f'fill="{shade}"/>')

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" '
        'role="img">\n'
        '<rect width="1000" height="1000" fill="#0a0908"/>\n'
        + "\n".join(circles)
        + "\n</svg>\n")


def trace_all() -> None:
    for png_path in sorted(STAGING.glob("*.png")):
        if png_path.name.startswith("_"):
            continue
        svg = trace_png(png_path)
        out = png_path.with_suffix(".svg")
        out.write_text(svg, encoding="utf-8")
        print(f"traced {png_path.name} -> {out.name} "
              f"({len(svg) // 1024} KB)")


def promote(treatment: str) -> None:
    """Owner-picked treatment → public/. The manifest is what the Portrait
    component consults; a key absent there falls back to the seal."""
    PUBLIC.mkdir(parents=True, exist_ok=True)
    published: dict[str, str] = {}
    for key in PERSONAS:
        source = STAGING / f"{key}.{treatment}.svg"
        if not source.exists():
            print(f"  ! {source.name} missing — {key} keeps the seal")
            continue
        target = PUBLIC / f"{key}.svg"
        shutil.copyfile(source, target)
        published[key] = PERSONAS[key][0]
        print(f"promoted {key} ({PERSONAS[key][0]})")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps({"treatment": treatment, "portraits": published},
                   indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"manifest -> {MANIFEST}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round1", action="store_true")
    parser.add_argument("--agents", action="store_true")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--treatment", choices=sorted(TREATMENTS), default="T1")
    parser.add_argument("--model", default=None)
    arguments = parser.parse_args()

    STAGING.mkdir(parents=True, exist_ok=True)
    if arguments.round1 or arguments.agents:
        token = _token()
        model = arguments.model or _pick_model(token)
        if arguments.round1:
            generate_round1(model, token)
        if arguments.agents:
            generate_agents(model, token, arguments.treatment)
    if arguments.trace:
        trace_all()
    if arguments.promote:
        promote(arguments.treatment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
