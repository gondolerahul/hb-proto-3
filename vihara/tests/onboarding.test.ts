/**
 * POLISH P7 — onboarding staged in the world: the one sequencing rule
 * the wireframes call un-get-wrongable (depth 0 is the reward at stage
 * 9), and the gate's deliberate fail-open on an unreadable engagement.
 */
import { describe, expect, it, vi, type Mock } from "vitest";

vi.mock("../src/api/client", () => ({ api: { get: vi.fn() } }));

import { api } from "../src/api/client";
import { fetchEngagementStage, gateFromStage } from "../src/app/onboarding";

describe("the stage-9 gate (P7)", () => {
  it("locks the still surface at every stage before 9", () => {
    for (let stage = 1; stage <= 8; stage++) {
      expect(gateFromStage(stage)).toEqual({ stillLocked: true, stage });
    }
  });

  it("stage 9 earns the silence", () => {
    expect(gateFromStage(9)).toEqual({ stillLocked: false, stage: 9 });
  });

  it("fails OPEN on an unreadable engagement — a sequencing rule must never lock the front door", () => {
    expect(gateFromStage(null)).toEqual({ stillLocked: false, stage: null });
  });
});

describe("reading the stage", () => {
  it("returns the engagement's stage", async () => {
    (api.get as Mock).mockResolvedValueOnce({ data: { stage: 4 } });
    expect(await fetchEngagementStage()).toBe(4);
  });

  it("returns null on a malformed body and on a failed request", async () => {
    (api.get as Mock).mockResolvedValueOnce({ data: {} });
    expect(await fetchEngagementStage()).toBeNull();
    (api.get as Mock).mockRejectedValueOnce(new Error("down"));
    expect(await fetchEngagementStage()).toBeNull();
  });
});
