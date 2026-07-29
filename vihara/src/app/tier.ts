/**
 * The device tier (D7 §2) — probed, never sniffed. User-agent strings are
 * wrong about capability on both ends, so the probe asks the platform:
 * WebGL2 availability, deviceMemory, hardwareConcurrency, saveData, and
 * the two media queries. The result is stored in LEARN's `surface.*`
 * namespace so the user can override it in either direction — a tenant on
 * tier C who wants the map gets the map with a warning; a tenant on tier A
 * who prefers sheets keeps sheets forever (§6.3's rule: never gate
 * capability).
 */
import { api } from "../api/client";

export type DeviceTier = "A" | "B" | "C" | "D";

export interface ProbedCapabilities {
  webgl2: boolean;
  deviceMemoryGb: number | null;
  cores: number | null;
  saveData: boolean;
  reducedMotion: boolean;
  reducedTransparency: boolean;
}

/** Pure — the probe's facts in, the tier out (D7 §2's table). */
export function classifyTier(probed: ProbedCapabilities): DeviceTier {
  if (probed.reducedMotion || probed.reducedTransparency) {
    // Tier D is not degraded tier A: the sheet is the designed product for
    // this user, and it loses information only if we built it wrong.
    return "D";
  }
  if (
    !probed.webgl2 ||
    probed.saveData ||
    (probed.deviceMemoryGb !== null && probed.deviceMemoryGb < 4)
  ) {
    return "C";
  }
  const bigMemory = probed.deviceMemoryGb !== null && probed.deviceMemoryGb >= 8;
  const manyCores = probed.cores !== null && probed.cores >= 8;
  if (probed.deviceMemoryGb === null ? manyCores : bigMemory && manyCores) {
    return "A";
  }
  return "B";
}

/** Ask the platform, not the user-agent string. */
export function probeCapabilities(): ProbedCapabilities {
  let webgl2 = false;
  try {
    const canvas = document.createElement("canvas");
    webgl2 = canvas.getContext("webgl2") !== null;
  } catch {
    webgl2 = false;
  }
  const nav = navigator as Navigator & {
    deviceMemory?: number;
    connection?: { saveData?: boolean };
  };
  return {
    webgl2,
    deviceMemoryGb: typeof nav.deviceMemory === "number" ? nav.deviceMemory : null,
    cores:
      typeof nav.hardwareConcurrency === "number"
        ? nav.hardwareConcurrency
        : null,
    saveData: nav.connection?.saveData === true,
    reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    reducedTransparency: window.matchMedia(
      "(prefers-reduced-transparency: reduce)",
    ).matches,
  };
}

export interface TierDecision {
  probed: DeviceTier;
  effective: DeviceTier;
  overridden: boolean;
}

/** The override lives in LEARN's surface.* namespace (D5 §8, VG-21) — no
 * new table, no new endpoint, and unknown namespaces are refused there so
 * this cannot quietly grow keys. */
export async function decideTier(): Promise<TierDecision> {
  const probed = classifyTier(probeCapabilities());
  try {
    const response = await api.get<{
      preferences?: Record<string, { value?: unknown }>;
    }>("/ai/learning/preferences", { params: { prefix: "surface" } });
    const stored = response.data.preferences?.["surface.tier"]?.value;
    if (stored === "A" || stored === "B" || stored === "C" || stored === "D") {
      return { probed, effective: stored, overridden: stored !== probed };
    }
  } catch {
    // The probe stands on its own; a preference read must never block entry.
  }
  return { probed, effective: probed, overridden: false };
}

export async function storeTierOverride(tier: DeviceTier): Promise<void> {
  try {
    await api.put("/ai/learning/preferences", {
      key: "surface.tier",
      value: tier,
    });
  } catch {
    // Losing the override costs a re-probe next session, never entry.
  }
}
