/**
 * DRIVER D8 — the Gallery (D6 §11). What these pin:
 *
 * - Colleagues past render DESATURATED (the twin's material — the past
 *   is not currently true), with the tenure the termination stamped.
 * - `not_measurable` renders as words with its missing list, never zero.
 * - The empty KPI series and the ledger's missing read surface are said,
 *   not drawn as empty charts.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { TenantRecordOut } from "../src/api/tenant";
import {
  GallerySurface,
  type GalleryLoaders,
  type PastColleague,
} from "../src/app/GallerySurface";

afterEach(cleanup);

const RESOLUTION: TenantRecordOut = {
  id: "res-1",
  entity_def_id: "d",
  data: { title: "Raise chase cadence", adopted_on: "2026-07-01" },
  version: 1,
  def_version: 1,
  deleted_at: null,
  created_at: "2026-07-01T00:00:00",
  sor: null,
  synced: false,
};

const MANDATE: TenantRecordOut = {
  ...RESOLUTION,
  id: "man-1",
  data: { title: "Cadence at 4 days" },
};

const PAST: PastColleague = {
  entity_id: "e-1",
  name: "Meera",
  art_name: "agt-046-meera",
  terminated_at: "2026-07-29T10:00:00",
  runs_total: 40,
  runs_completed: 36,
  memo_artifact_id: "memo-1",
};

function harness(overrides: Partial<GalleryLoaders> = {}): GalleryLoaders {
  return {
    records: async (def) =>
      def === "Resolution" ? [RESOLUTION] : def === "Mandate" ? [MANDATE] : [],
    past: async () => [PAST],
    realized: async () => ({
      kpi_key: "dso",
      predicted_value: null,
      realized_value: null,
      measurable: false,
      missing: ["kpi history before the mandate"],
      verdict: null,
      honesty_grade: null,
    }),
    echo: async () => undefined,
    ...overrides,
  };
}

describe("the gallery", () => {
  it("colleagues past are desaturated and carry their stamped tenure", async () => {
    render(<GallerySurface loaders={harness()} />);
    await waitFor(() => {
      expect(document.querySelector("[data-part='past-colleague']")).not.toBeNull();
    });
    expect(document.querySelector(".vh-desaturated")).not.toBeNull();
    expect(screen.getByText(/36 pieces of work stand/)).toBeDefined();
    expect(screen.getByText(/memo in the Library/)).toBeDefined();
  });

  it("not-measurable is words with the missing list, never a zero", async () => {
    render(<GallerySurface loaders={harness()} />);
    await waitFor(() => {
      expect(screen.getByText("predicted vs realized")).toBeDefined();
    });
    const flip = document.querySelector(
      "[data-part='monument'] details",
    ) as HTMLDetailsElement;
    flip.open = true;
    fireEvent(flip, new Event("toggle"));
    await waitFor(() => {
      expect(document.querySelector("[data-part='not-measurable']")).not.toBeNull();
    });
    expect(
      screen.getByText(/missing: kpi history before the mandate/),
    ).toBeDefined();
    expect(flip.textContent).not.toContain("0 ·");
  });

  it("honest absences are sentences, not empty charts", async () => {
    render(<GallerySurface loaders={harness()} />);
    await waitFor(() => {
      expect(document.querySelector("[data-part='kpi-honesty']")).not.toBeNull();
    });
    expect(document.querySelector("[data-part='ledger-absent']")).not.toBeNull();
  });

  it("an estate with no history says where history starts", async () => {
    render(
      <GallerySurface
        loaders={harness({ records: async () => [], past: async () => [] })}
      />,
    );
    await waitFor(() => {
      expect(document.querySelector("[data-part='seasons-empty']")).not.toBeNull();
    });
    expect(screen.getByText("Nobody has left.")).toBeDefined();
  });
});
