/**
 * POLISH P5 — the motion language. The §9 table is pinned over the CSS
 * text (jsdom runs no animations), and the one piece of motion that is
 * LOGIC — the ribbon's 400ms leave — is driven through its hook with
 * fake timers.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  announce,
  RIBBON_DWELL_MS,
  RIBBON_EXIT_MS,
  useRibbon,
} from "../src/app/ribbon";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const appCss = readFileSync(
  path.join(
    path.dirname(new URL(import.meta.url).pathname),
    "..", "src", "app", "app.css",
  ),
  "utf-8",
);

describe("the §9 motion table, pinned", () => {
  it.each([
    ["depth change", /vh-depth-arrive 320ms var\(--ease-out\)/],
    ["tray arrival", /vh-tray-arrive 240ms var\(--ease-out\)/],
    ["sheet open", /vh-sheet-open 200ms var\(--ease-out\)/],
    ["beacon raise", /vh-beacon-raise 640ms var\(--ease-out\)/],
    ["beacon breath", /vh-beacon-breath 4s var\(--ease-in-out\)/],
    ["ribbon leave", /vh-ribbon-out 400ms var\(--ease-out\)/],
  ])("%s runs at the art bible's duration", (_name, pattern) => {
    expect(appCss).toMatch(pattern);
  });

  it("reduced motion stops the breath but keeps the beacon at full glow", () => {
    const block = appCss.match(
      /@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\n\}/,
    );
    expect(block?.[0]).toContain(".vh-beacon-count");
    expect(block?.[0]).toContain("animation: none");
    expect(block?.[0]).toContain("box-shadow");
  });

  it("the breath is the only repeating attention animation", () => {
    // `infinite` may appear exactly once in the app's CSS — on the beacon.
    const repeats = appCss.match(/\binfinite\b/g) ?? [];
    expect(repeats).toHaveLength(1);
    const beaconRule = appCss.match(/^\.vh-beacon-count \{[\s\S]*?\}/m);
    expect(beaconRule?.[0]).toContain("infinite");
  });
});

describe("the ribbon's leave (the one motion that is logic)", () => {
  it("murmurs in, dwells, leaves over 400ms, then unmounts", () => {
    vi.useFakeTimers();
    const view = renderHook(() => useRibbon());
    act(() => announce("filed the quote"));
    expect(view.result.current).toEqual({
      sentence: "filed the quote",
      leaving: false,
    });
    act(() => {
      vi.advanceTimersByTime(RIBBON_DWELL_MS);
    });
    expect(view.result.current).toEqual({
      sentence: "filed the quote",
      leaving: true,
    });
    act(() => {
      vi.advanceTimersByTime(RIBBON_EXIT_MS);
    });
    expect(view.result.current).toEqual({ sentence: null, leaving: false });
  });

  it("a new sentence during the leave cancels it — last write wins", () => {
    vi.useFakeTimers();
    const view = renderHook(() => useRibbon());
    act(() => announce("one"));
    act(() => {
      vi.advanceTimersByTime(RIBBON_DWELL_MS);
    });
    expect(view.result.current.leaving).toBe(true);
    act(() => announce("two"));
    expect(view.result.current).toEqual({ sentence: "two", leaving: false });
    act(() => {
      vi.advanceTimersByTime(RIBBON_EXIT_MS);
    });
    // The cancelled exit must not clear the new sentence.
    expect(view.result.current).toEqual({ sentence: "two", leaving: false });
  });
});
