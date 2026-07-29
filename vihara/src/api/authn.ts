/**
 * The step-up half a certified act needs (DRIVER D1; VG-05's console
 * lesson carried into the new app). Storage-pinned like everything under
 * src/ — the ceremony proves the human, the server holds the state.
 *
 * The refusal parser claims ONLY a 403 carrying the `step_up_required`
 * marker, so an ordinary permission denial still reaches the caller's own
 * error path — the legacy console's rule, kept exactly.
 */
import { api } from "./client";

export interface StepUpRefusal {
  error: "step_up_required";
  tier: string;
  why: string;
  reason: string;
  needs_step_up: boolean;
  needs_oob: boolean;
  locked: boolean;
  /** Server-supplied — a client-invented ref would let one command's
   * confirmation authorise another (the T3 nonce binds to this). */
  command_ref: string | null;
  command_summary: string | null;
}

interface RefusalCarrier {
  response?: { status?: number; data?: { detail?: unknown } };
}

export function parseStepUpRefusal(error: unknown): StepUpRefusal | null {
  const response = (error as RefusalCarrier).response;
  if (response?.status !== 403) return null;
  const detail = response.data?.detail;
  if (detail === null || detail === undefined || typeof detail !== "object") {
    return null;
  }
  if ((detail as { error?: unknown }).error !== "step_up_required") return null;
  return detail as StepUpRefusal;
}

export interface StepUpOutcome {
  ok: boolean;
  reason?: string;
  locked?: boolean;
  failed_attempts?: number;
}

/** WebAuthn speaks ArrayBuffers; the wire speaks base64url. */
export function b64urlToBuffer(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

export function bufferToB64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  bytes.forEach((b) => {
    binary += String.fromCharCode(b);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function isPasskeySupported(): boolean {
  return typeof window !== "undefined" && Boolean(window.PublicKeyCredential);
}

/**
 * The passkey ceremony: options → authenticator → `/ai/authn/step-up`.
 * Returns the server's outcome rather than throwing on a rejected
 * assertion — a failure counts toward the lockout and the caller must be
 * able to show that back (never elevate inside a verify function; the
 * router elevates, this only reports).
 */
export async function stepUpWithPasskey(): Promise<StepUpOutcome> {
  const { data: options } = await api.post<{
    challenge: string;
    allowCredentials?: { id: string; type: string }[];
    [key: string]: unknown;
  }>("/ai/authn/webauthn/authenticate/begin");

  const assertion = (await navigator.credentials.get({
    publicKey: {
      ...options,
      challenge: b64urlToBuffer(options.challenge),
      allowCredentials: (options.allowCredentials ?? []).map((c) => ({
        ...c,
        id: b64urlToBuffer(c.id),
      })),
    } as PublicKeyCredentialRequestOptions,
  })) as PublicKeyCredential | null;

  if (assertion === null) throw new Error("Passkey step-up was cancelled");
  const response = assertion.response as AuthenticatorAssertionResponse;

  const { data } = await api.post<StepUpOutcome>("/ai/authn/step-up", {
    method: "passkey",
    credential: {
      id: assertion.id,
      rawId: bufferToB64url(assertion.rawId),
      type: assertion.type,
      response: {
        clientDataJSON: bufferToB64url(response.clientDataJSON),
        authenticatorData: bufferToB64url(response.authenticatorData),
        signature: bufferToB64url(response.signature),
        userHandle:
          response.userHandle !== null
            ? bufferToB64url(response.userHandle)
            : null,
      },
      clientExtensionResults: assertion.getClientExtensionResults(),
    },
  });
  return data;
}

export async function stepUpWithTotp(code: string): Promise<StepUpOutcome> {
  const { data } = await api.post<StepUpOutcome>("/ai/authn/step-up", {
    method: "totp",
    code,
  });
  return data;
}

// ── passkey management (the Study, DRIVER D12) ─────────────────────────

export interface PasskeyCredential {
  id: string;
  label: string | null;
  created_at: string;
  last_used_at: string | null;
}

export async function listPasskeys(): Promise<PasskeyCredential[]> {
  return (
    await api.get<PasskeyCredential[]>("/ai/authn/webauthn/credentials")
  ).data;
}

/** Plain, deliberately — removing a factor is the safe direction. */
export async function deletePasskey(credentialRowId: string): Promise<void> {
  await api.delete(`/ai/authn/webauthn/credentials/${credentialRowId}`);
}

/** Full registration ceremony: options → authenticator → attestation. */
export async function registerPasskey(label?: string): Promise<void> {
  const { data: options } = await api.post<{
    challenge: string;
    user: { id: string; [key: string]: unknown };
    excludeCredentials?: { id: string; type: string }[];
    [key: string]: unknown;
  }>("/ai/authn/webauthn/register/begin");

  const created = (await navigator.credentials.create({
    publicKey: {
      ...options,
      challenge: b64urlToBuffer(options.challenge),
      user: { ...options.user, id: b64urlToBuffer(options.user.id) },
      excludeCredentials: (options.excludeCredentials ?? []).map((c) => ({
        ...c,
        id: b64urlToBuffer(c.id),
      })),
    } as PublicKeyCredentialCreationOptions,
  })) as PublicKeyCredential | null;

  if (created === null) throw new Error("Passkey registration was cancelled");
  const attestation = created.response as AuthenticatorAttestationResponse;

  await api.post("/ai/authn/webauthn/register/finish", {
    label: label ?? null,
    credential: {
      id: created.id,
      rawId: bufferToB64url(created.rawId),
      type: created.type,
      response: {
        clientDataJSON: bufferToB64url(attestation.clientDataJSON),
        attestationObject: bufferToB64url(attestation.attestationObject),
      },
      clientExtensionResults: created.getClientExtensionResults(),
    },
  });
}
