/**
 * POLISH P2 — the atmosphere layer: the scene description both renderers
 * share, the world-canvas pause rule, and the mount's contract. Structural
 * like every other golden here: data-parts and attributes, never pixels.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { cleanup, render, act } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Atmosphere } from "../src/atmosphere/Atmosphere";
import { DEPTH_DIM, luminanceAt, seededBlobs } from "../src/atmosphere/scene";
import {
  setWorldCanvasActive,
  subscribeWorldCanvas,
} from "../src/atmosphere/worldActive";

afterEach(() => {
  cleanup();
  setWorldCanvasActive(false);
});

const at = (hours: number, minutes: number): Date =>
  new Date(2026, 6, 29, hours, minutes, 0);

describe("the scene description", () => {
  it("night and day carry the estate-visual multipliers; beacon gold is not painted here", () => {
    expect(luminanceAt(at(3, 0))).toEqual({ phase: "night", face: 1, glow: 1 });
    expect(luminanceAt(at(12, 0))).toEqual({ phase: "day", face: 2.3, glow: 0.5 });
  });

  it("sunrise interpolates over the art bible's 20-minute window, monotonically", () => {
    const before = luminanceAt(at(6, 9));
    const mid = luminanceAt(at(6, 30));
    const after = luminanceAt(at(6, 51));
    expect(before.phase).toBe("night");
    expect(mid.phase).toBe("dawn");
    expect(after.phase).toBe("day");
    // Midpoint of the window is the midpoint of the ramp.
    expect(mid.face).toBeCloseTo((1 + 2.3) / 2, 5);
    expect(mid.glow).toBeCloseTo((1 + 0.5) / 2, 5);
    // Dusk runs the same ramp downward.
    expect(luminanceAt(at(18, 30)).phase).toBe("dusk");
    expect(luminanceAt(at(19, 0)).phase).toBe("night");
  });

  it("the blob field is deterministic — an estate does not rearrange its light", () => {
    expect(seededBlobs()).toEqual(seededBlobs());
    expect(seededBlobs(7)).not.toEqual(seededBlobs(11));
    const blobs = seededBlobs();
    expect(blobs.filter((blob) => blob.bright)).toHaveLength(1);
  });

  it("the floor recedes as surfaces grow dense, and never vanishes", () => {
    expect(DEPTH_DIM["0"]).toBeGreaterThan(DEPTH_DIM["1"]);
    expect(DEPTH_DIM["1"]).toBeGreaterThan(DEPTH_DIM["2"]);
    expect(DEPTH_DIM["2"]).toBeGreaterThan(DEPTH_DIM["3"]);
    expect(DEPTH_DIM["3"]).toBeGreaterThan(0);
  });
});

describe("the world-canvas pause (the one-GL-context rule)", () => {
  it("notifies subscribers once per change, replaying current state on subscribe", () => {
    const seen: boolean[] = [];
    const unsubscribe = subscribeWorldCanvas((active) => seen.push(active));
    setWorldCanvasActive(true);
    setWorldCanvasActive(true);
    setWorldCanvasActive(false);
    unsubscribe();
    setWorldCanvasActive(true);
    expect(seen).toEqual([false, true, false]);
  });
});

describe("the atmosphere mount", () => {
  it("renders vignette, floor canvas and the synced brand-mark watermark", () => {
    const { container } = render(<Atmosphere context="shell" depthLevel={0} />);
    const layer = container.querySelector('[data-part="atmosphere"]');
    expect(layer).not.toBeNull();
    expect(layer?.getAttribute("aria-hidden")).toBe("true");
    expect(
      container.querySelector('canvas[data-part="atmosphere-floor"]'),
    ).not.toBeNull();
    const mark = container.querySelector(".vh-watermark img");
    expect(mark?.getAttribute("src")).toBe("/brand-mark.svg");
    expect(mark?.getAttribute("alt")).toBe("");
  });

  it("dims by depth from the one scene table", () => {
    const { container: still } = render(
      <Atmosphere context="shell" depthLevel={0} />,
    );
    const { container: undercroft } = render(
      <Atmosphere context="shell" depthLevel={3} />,
    );
    const opacity = (root: HTMLElement): string =>
      (root.querySelector(".vh-floorwrap") as HTMLElement).style.opacity;
    expect(opacity(still as HTMLElement)).toBe(String(DEPTH_DIM["0"]));
    expect(opacity(undercroft as HTMLElement)).toBe(String(DEPTH_DIM["3"]));
  });

  it("hides while the world canvas is live, returns when it is not", () => {
    const { container } = render(<Atmosphere context="shell" depthLevel={1} />);
    const layer = (): string | null =>
      container
        .querySelector('[data-part="atmosphere"]')
        ?.getAttribute("data-hidden") ?? null;
    expect(layer()).toBe("false");
    act(() => setWorldCanvasActive(true));
    expect(layer()).toBe("true");
    act(() => setWorldCanvasActive(false));
    expect(layer()).toBe("false");
  });

  it("reduced motion pins the static frame", () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) =>
      ({
        matches: query.includes("prefers-reduced-motion"),
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        addListener: () => undefined,
        removeListener: () => undefined,
        onchange: null,
        dispatchEvent: () => false,
      }) as MediaQueryList) as typeof window.matchMedia;
    try {
      const { container } = render(<Atmosphere context="presession" />);
      expect(
        container
          .querySelector('[data-part="atmosphere"]')
          ?.getAttribute("data-static"),
      ).toBe("true");
    } finally {
      window.matchMedia = original;
    }
  });

  it("the public watermark is the design system's mark, byte for byte", () => {
    const appRoot = path.resolve(
      path.dirname(new URL(import.meta.url).pathname), "..");
    const repoRoot = path.resolve(appRoot, "..");
    const source = path.join(
      repoRoot, "docs", "product-road-map", "increment-7",
      "buddha-cognitive-lab-design-system", "project", "assets",
      "logo-mark-gold.svg");
    const copy = path.join(appRoot, "public", "brand-mark.svg");
    expect(readFileSync(copy)).toEqual(readFileSync(source));
  });
});
