/**
 * The one portrait door (art bible §7.1, R1 + the 2026-07-29 rounds):
 * a colleague with a promoted A-direction bust renders it; every other
 * entity renders the procedural seal. Nothing is ever portrait-less, and
 * nothing waits on an art pipeline.
 *
 * The manifest is written only by the promote step of
 * `backend/scripts/generate_portraits.py` — portraits are FROZEN once
 * published; regenerating one is a reviewed act. The key is the agent
 * code (or "pragya"), lower-case; an unknown key is not an error, it is
 * a seal.
 *
 * Rules that hold here (§7.2): never gold-glowing at rest — the bust gets
 * no halo, no filter; a raised hand's beacon lives ABOVE the portrait in
 * the surface that shows it. Gallery/twin desaturation is the PLANE's
 * job (the renderer applies --twin-desaturate at the boundary), never
 * this component's.
 */
import manifest from "./manifest.json";
import { Seal } from "./Seal";

const PORTRAITS: Record<string, string> = manifest.portraits;

export function hasBust(key: string): boolean {
  return Object.prototype.hasOwnProperty.call(PORTRAITS, key.toLowerCase());
}

export function Portrait({
  entityKey,
  entityId,
  name,
  size = 48,
}: {
  /** The stable art key: an agent code like "agt-046", or "pragya". */
  entityKey: string;
  /** Fallback seed for the seal — a tenant-custom colleague's entity id. */
  entityId?: string;
  name?: string;
  size?: number;
}): JSX.Element {
  const key = entityKey.toLowerCase();
  if (hasBust(key)) {
    return (
      <img
        src={`/portraits/${key}.svg`}
        width={size}
        height={size}
        alt={name !== undefined ? `${name} — portrait` : "portrait"}
        data-part="bust"
        data-portrait-key={key}
      />
    );
  }
  return <Seal id={entityId ?? key} size={size} label={name} />;
}
