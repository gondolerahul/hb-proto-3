/**
 * POLISH P7 (amended by the 2026-07-30 screenshot round) — onboarding
 * staged in the world. Two rules, both learned the hard way:
 *
 * 1. Depth 0 is the reward at stage 9 — while the estate is genuinely
 *    unbuilt.
 * 2. **An activated estate is an estate.** A long-active tenant whose
 *    owner never touched the engagement sits at stage 1 forever, and the
 *    first version of this gate locked such a tenant's front door
 *    permanently — found the moment a screenshot was taken with a real
 *    seeded tenant. Activation outranks the stage.
 *
 * Plus the standing rule: the gate FAILS OPEN on anything unreadable.
 */
import { describe, expect, it, vi, type Mock } from "vitest";

vi.mock("../src/api/client", () => ({ api: { get: vi.fn() } }));

import { api } from "../src/api/client";
import { fetchEstateStanding, gateFromStanding } from "../src/app/onboarding";

describe("the stage-9 gate (P7, amended)", () => {
  it("locks the still surface at every stage before 9 while unactivated", () => {
    for (let stage = 1; stage <= 8; stage++) {
      expect(gateFromStanding({ activated: false, stage })).toEqual({
        stillLocked: true,
        stage,
      });
    }
  });

  it("stage 9 earns the silence", () => {
    expect(gateFromStanding({ activated: false, stage: 9 })).toEqual({
      stillLocked: false,
      stage: 9,
    });
  });

  it("an ACTIVATED estate is never locked, whatever its engagement row says", () => {
    for (const stage of [1, 4, 8, null]) {
      expect(gateFromStanding({ activated: true, stage }).stillLocked).toBe(
        false,
      );
    }
  });

  it("fails OPEN on an unreadable standing — a sequencing rule must never lock the front door", () => {
    expect(gateFromStanding({ activated: null, stage: null })).toEqual({
      stillLocked: false,
      stage: null,
    });
    expect(
      gateFromStanding({ activated: false, stage: null }).stillLocked,
    ).toBe(false);
  });
});

describe("reading the standing", () => {
  it("returns activation and stage together", async () => {
    (api.get as Mock).mockImplementation(async (path: string) =>
      path.includes("onboarding")
        ? { data: { activated: true } }
        : { data: { stage: 4 } },
    );
    expect(await fetchEstateStanding()).toEqual({ activated: true, stage: 4 });
  });

  it("each leg degrades to null independently", async () => {
    (api.get as Mock).mockImplementation(async (path: string) => {
      if (path.includes("onboarding")) throw new Error("down");
      return { data: {} };
    });
    expect(await fetchEstateStanding()).toEqual({
      activated: null,
      stage: null,
    });
  });
});
