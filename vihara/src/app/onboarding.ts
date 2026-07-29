/**
 * Onboarding staged in the world (POLISH P7, spec §15.1, wireframes §19).
 *
 * No new surfaces and no new backend: the nine-stage engagement (Pragya's
 * Inc-3 stage contract over the unchanged Inc-2 step APIs) drives what
 * the estate shows, and the shell enforces the one sequencing rule the
 * wireframes call un-get-wrongable: **depth 0 is the reward at stage 9,
 * not the start screen at stage 1.** Before stage 9 a session opens onto
 * the Terrace — the ghost estate, `world.ghost` doing the work — and the
 * steward carries the stage conversationally.
 *
 * The gate FAILS OPEN. It is a sequencing rule, not a security control:
 * an unreadable engagement must never lock a working estate out of its
 * own home screen. (The reverse failure — a finished estate briefly
 * showing its terrace — costs a click; the other failure mode costs the
 * product's front door.)
 */
import { api } from "../api/client";

export interface OnboardingGate {
  /** True while the estate is still being raised (stage < 9). */
  stillLocked: boolean;
  stage: number | null;
}

export const STILL_LOCKED_SENTENCE =
  "The still surface arrives with stage 9 — the estate is still being raised.";

/** Pure — the sequencing rule, fail-open. */
export function gateFromStage(stage: number | null): OnboardingGate {
  if (stage === null) return { stillLocked: false, stage: null };
  return { stillLocked: stage < 9, stage };
}

/** Reads the engagement's stage; null on any failure (the gate fails open). */
export async function fetchEngagementStage(): Promise<number | null> {
  try {
    const response = await api.get<{ stage?: unknown }>("/ai/pragya/engagement");
    const stage = response.data.stage;
    return typeof stage === "number" ? stage : null;
  } catch {
    return null;
  }
}
