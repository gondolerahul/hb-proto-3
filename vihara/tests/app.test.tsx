/**
 * SUB T7 — the shell and the G0 round trip, driven with injected loaders.
 * What these pin: the still surface renders a REAL manifest end to end
 * (loader → ladder → renderer → bindings), a failure is visible (a blank
 * still surface would read as "all is well"), and the first manual act
 * emits its echo sentence (L10).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { EchoInput } from "../src/api/genui";
import { assessManifest } from "../src/manifest/refusals";
import type { WireScaffold } from "../src/manifest/schema";
import { StillSurface, type StillLoaders } from "../src/app/StillSurface";

afterEach(cleanup);

const STILL: WireScaffold = {
  part: "scaffold",
  manifest_version: 1,
  surface_id: "still",
  renderer: "S",
  plane: "live",
  depth: 0,
  density: "novice",
  layout: { kind: "stack", regions: ["line", "pulse"] },
  components: [
    {
      id: "c1",
      type: "narrative.still-line@1",
      region: "line",
      props: { template: "All is well. {raised} hands raised." },
      bindings: [{ source: "estate.beacon", params: {} }],
    },
    {
      id: "c2",
      type: "primitive.pulse@1",
      region: "pulse",
      props: { label: "The pulse" },
      bindings: [{ source: "estate.pulse", params: {} }],
    },
  ],
  issued_at: "t",
  ttl_seconds: 120,
};

function loaders(overrides: Partial<StillLoaders> = {}): {
  loaders: StillLoaders;
  echoes: EchoInput[];
} {
  const echoes: EchoInput[] = [];
  return {
    echoes,
    loaders: {
      manifest: async () => ({
        manifest: STILL,
        assessment: assessManifest(STILL),
      }),
      estate: async () => ({
        estate: { pulse: { beat_at: "t", healthy: true } },
        beacons: [{ approval_id: "a1" }],
      }),
      echo: async (echo) => {
        echoes.push(echo);
      },
      ...overrides,
    },
  };
}

describe("the G0 round trip", () => {
  it("a SEAM-shaped manifest renders with estate data in its slots", async () => {
    render(<StillSurface loaders={loaders().loaders} />);
    await waitFor(() =>
      expect(screen.getByText("All is well. 1 hands raised.")).toBeTruthy(),
    );
    expect(screen.getByText("Steady")).toBeTruthy();
  });

  it("the first manual act emits its echo sentence (L10)", async () => {
    const { loaders: injected, echoes } = loaders();
    render(<StillSurface loaders={injected} />);
    await waitFor(() => screen.getByText("1 waiting"));
    fireEvent.click(screen.getByText("1 waiting"));
    expect(echoes).toHaveLength(1);
    expect(echoes[0]?.sentence).toContain("opened the tray list");
    expect(echoes[0]?.action_ref.kind).toBe("still.open_trays");
  });

  it("an unreachable estate fails visible — never a blank calm", async () => {
    const { loaders: injected } = loaders({
      estate: async () => {
        throw new Error("down");
      },
    });
    render(<StillSurface loaders={injected} />);
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "could not be reached",
      ),
    );
  });

  it("a rejected manifest surfaces its reason", async () => {
    const { loaders: injected } = loaders({
      manifest: async () => ({ kind: "rejected", reason: "bad wire data" }),
    });
    render(<StillSurface loaders={injected} />);
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("bad wire data"),
    );
  });
});
