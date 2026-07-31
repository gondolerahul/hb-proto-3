/**
 * Reading the server's three refusals — R-4 part C, C3.
 *
 * §6's instruction is to treat a `step_up_required` 403 as the ceremony's
 * *entry point* rather than as an error, and to match the shape the backend
 * actually raises instead of assuming one. `backend/src/ai/inward_auth/` raises
 * three distinct things at the certified boundary, and only the first of them
 * is what `api/authn.ts` claims:
 *
 * | raised by | status | `detail` |
 * |---|---|---|
 * | `guard.tier_refusal` — every `enforce_tier`/`enforce_kind` site | 403 | an object marked `error: "step_up_required"` |
 * | `api.post_step_up`, `api.post_webauthn_authenticate_begin` | 403 | the plain string `"step-up is locked after repeated failures"` |
 * | `api.post_webauthn_authenticate_begin` | 400 | the plain string `"no passkey registered"` |
 *
 * The last two are raised *inside* the ceremony, so a ceremony that treats
 * every non-200 as "that did not verify" tells a locked-out owner their passkey
 * was wrong and tells an owner with no passkey to try again. Each gets its own
 * reading here, and the ceremony renders each differently.
 *
 * The marker check itself is **not** duplicated: `parseStepUpRefusal` owns the
 * rule that only a marked 403 is claimed (an ordinary permission denial must
 * still reach the caller's own error path), and this module widens its result
 * rather than re-deciding it. What it widens by is `current_level` /
 * `required_level` — `guard.tier_refusal` sends both and the shipped
 * `StepUpRefusal` interface omits them, which is why the ceremony could not
 * previously say *what* the session holds and what the act wants.
 */
import { parseStepUpRefusal, type StepUpRefusal } from "../../api/authn";

export interface CertifiedRefusal extends StepUpRefusal {
  /** `AuthDecision.current_level` — what the console session holds right now. */
  current_level: string | null;
  /** `AuthDecision.required_level` — what this act needs it to hold. */
  required_level: string | null;
}

interface Carrier {
  response?: { status?: number; data?: { detail?: unknown } };
}

function detailOf(error: unknown): unknown {
  return (error as Carrier).response?.data?.detail;
}

function statusOf(error: unknown): number | undefined {
  return (error as Carrier).response?.status;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * The refusal, widened — or null when this error is not one, in which case it
 * belongs to the caller and must not be swallowed.
 */
export function readStepUpRefusal(error: unknown): CertifiedRefusal | null {
  const claimed = parseStepUpRefusal(error);
  if (claimed === null) return null;
  const detail = detailOf(error);
  const extra = (detail ?? {}) as Record<string, unknown>;
  return {
    ...claimed,
    current_level: text(extra["current_level"]),
    required_level: text(extra["required_level"]),
  };
}

/**
 * The lockout raised *by the ceremony's own endpoints*. Distinct from
 * `refusal.locked`, which is the lockout reported by the act's gate before the
 * ceremony opens — this one bites between opening it and completing it, and
 * offering the passkey button again afterwards would spend a lockout the owner
 * cannot see.
 */
export function stepUpLockoutReason(error: unknown): string | null {
  if (statusOf(error) !== 403) return null;
  const detail = text(detailOf(error));
  if (detail === null || !detail.startsWith("step-up is locked")) return null;
  // The server's own sentence, carried through rather than restated — the
  // ceremony never paraphrases a security answer.
  return detail;
}

export function isStepUpLockout(error: unknown): boolean {
  return stepUpLockoutReason(error) !== null;
}

/**
 * `/ai/authn/webauthn/authenticate/begin` answers 400 `"no passkey registered"`
 * when the account has none. It is not a failure of this attempt and must not
 * count as one in the copy: the correct response is to hand the owner the TOTP
 * leg, which is what §11.3 put it there for.
 */
export function isNoPasskeyEnrolled(error: unknown): boolean {
  if (statusOf(error) !== 400) return false;
  const detail = text(detailOf(error));
  return detail !== null && detail.startsWith("no passkey registered");
}
