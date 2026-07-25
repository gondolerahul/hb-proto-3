import { apiClient } from './api.client';

/**
 * Inward-channel authentication (Inc-3 AUTH, register finding D1).
 *
 * The browser is the primary authenticator surface (decision 2, console-first):
 * passkey ceremonies run natively here, and other channels step up by opening
 * a link back into this console. The server owns every policy decision — this
 * module only moves ceremony payloads and never decides what a command needs.
 */

export type AuthLevel = 'none' | 'bound' | 'elevated' | 'oob_confirmed';
export type ChannelKind = 'console' | 'email' | 'whatsapp' | 'voice';

export interface ChannelBinding {
    id: string;
    channel_kind: ChannelKind;
    address: string;
    label: string | null;
    verified: boolean;
    last_seen_at?: string | null;
}

export interface AuthnStatus {
    auth_level: AuthLevel;
    elevated_until: string | null;
    elevated_by: string | null;
    locked: boolean;
    locked_until: string | null;
    failed_stepups: number;
    has_passkey: boolean;
    has_totp: boolean;
    bindings: ChannelBinding[];
}

export interface StepUpOutcome {
    ok: boolean;
    reason?: string;
    locked?: boolean;
    failed_attempts?: number;
    auth_level?: AuthLevel;
    elevated_until?: string | null;
}

/**
 * The 403 body every certified endpoint returns (`inward_auth/guard.py`).
 *
 * It is an *instruction*, not a message: it says which ceremony is missing, so
 * the console opens the right one instead of showing a dead-end error. The
 * tier itself is never re-derived here — a second copy of the §20 rules in the
 * browser is a second thing to keep correct, and the one that would drift.
 */
export interface StepUpRefusal {
    tier: 'T0' | 'T1' | 'T2' | 'T3';
    why: string;
    reason: string;
    current_level: AuthLevel;
    required_level: AuthLevel;
    needs_step_up: boolean;
    needs_oob: boolean;
    locked: boolean;
    /** Binds the T3 out-of-band nonce to this command; server-supplied. */
    command_ref: string | null;
    command_summary: string | null;
}

/**
 * Recognise a step-up refusal in an axios error, or return null.
 *
 * Null means "not mine" — the caller's own error handling should run. Only a
 * 403 carrying the `step_up_required` marker is claimed, so an ordinary
 * permission denial still reads as one.
 */
export const parseStepUpRefusal = (error: any): StepUpRefusal | null => {
    if (error?.response?.status !== 403) return null;
    const detail = error.response?.data?.detail;
    if (!detail || typeof detail !== 'object' || detail.error !== 'step_up_required') {
        return null;
    }
    return detail as StepUpRefusal;
};

export interface PasskeyCredential {
    id: string;
    label: string | null;
    created_at: string;
    last_used_at: string | null;
}

/** WebAuthn speaks ArrayBuffers; the wire speaks base64url. */
const b64urlToBuffer = (value: string): ArrayBuffer => {
    const padded = value.replace(/-/g, '+').replace(/_/g, '/');
    const binary = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4));
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
};

const bufferToB64url = (buffer: ArrayBuffer): string => {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    bytes.forEach((b) => { binary += String.fromCharCode(b); });
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};

export const isPasskeySupported = (): boolean =>
    typeof window !== 'undefined' && !!window.PublicKeyCredential;

export const authnService = {
    getStatus: async (): Promise<AuthnStatus> => {
        const response = await apiClient.get<AuthnStatus>('/ai/authn/status');
        return response.data;
    },

    listBindings: async (): Promise<ChannelBinding[]> => {
        const response = await apiClient.get<ChannelBinding[]>('/ai/authn/bindings');
        return response.data;
    },

    /**
     * Start enrolling a channel. The OTP is delivered to the address being
     * claimed and is deliberately not returned here — holding the console
     * session and holding the device are two separate proofs, and the
     * handshake only means something while they stay separate.
     */
    beginBindingEnrollment: async (
        channelKind: ChannelKind, address: string, label?: string,
    ): Promise<{ binding_id: string }> => {
        const response = await apiClient.post<{ binding_id: string }>(
            '/ai/authn/bindings',
            { channel_kind: channelKind, address, label: label ?? null },
        );
        return response.data;
    },

    confirmBinding: async (bindingId: string, code: string): Promise<void> => {
        await apiClient.post('/ai/authn/bindings/confirm', {
            binding_id: bindingId, code,
        });
    },

    revokeBinding: async (bindingId: string): Promise<void> => {
        await apiClient.delete(`/ai/authn/bindings/${bindingId}`);
    },

    listPasskeys: async (): Promise<PasskeyCredential[]> => {
        const response = await apiClient.get<PasskeyCredential[]>(
            '/ai/authn/webauthn/credentials');
        return response.data;
    },

    deletePasskey: async (credentialRowId: string): Promise<void> => {
        await apiClient.delete(`/ai/authn/webauthn/credentials/${credentialRowId}`);
    },

    /** Full registration ceremony: options → authenticator → attestation. */
    registerPasskey: async (label?: string): Promise<void> => {
        const { data: options } = await apiClient.post<any>(
            '/ai/authn/webauthn/register/begin');

        const created = (await navigator.credentials.create({
            publicKey: {
                ...options,
                challenge: b64urlToBuffer(options.challenge),
                user: { ...options.user, id: b64urlToBuffer(options.user.id) },
                excludeCredentials: (options.excludeCredentials ?? []).map((c: any) => ({
                    ...c, id: b64urlToBuffer(c.id),
                })),
            },
        })) as PublicKeyCredential | null;

        if (!created) throw new Error('Passkey registration was cancelled');
        const attestation = created.response as AuthenticatorAttestationResponse;

        await apiClient.post('/ai/authn/webauthn/register/finish', {
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
    },

    /**
     * Step up with a passkey. Returns the server's outcome rather than
     * throwing on a rejected assertion, because a failure is counted toward
     * the lockout and the caller needs to show that back to the user.
     */
    stepUpWithPasskey: async (): Promise<StepUpOutcome> => {
        const { data: options } = await apiClient.post<any>(
            '/ai/authn/webauthn/authenticate/begin');

        const assertion = (await navigator.credentials.get({
            publicKey: {
                ...options,
                challenge: b64urlToBuffer(options.challenge),
                allowCredentials: (options.allowCredentials ?? []).map((c: any) => ({
                    ...c, id: b64urlToBuffer(c.id),
                })),
            },
        })) as PublicKeyCredential | null;

        if (!assertion) throw new Error('Passkey step-up was cancelled');
        const response = assertion.response as AuthenticatorAssertionResponse;

        const { data } = await apiClient.post<StepUpOutcome>('/ai/authn/step-up', {
            method: 'passkey',
            credential: {
                id: assertion.id,
                rawId: bufferToB64url(assertion.rawId),
                type: assertion.type,
                response: {
                    clientDataJSON: bufferToB64url(response.clientDataJSON),
                    authenticatorData: bufferToB64url(response.authenticatorData),
                    signature: bufferToB64url(response.signature),
                    userHandle: response.userHandle
                        ? bufferToB64url(response.userHandle) : null,
                },
                clientExtensionResults: assertion.getClientExtensionResults(),
            },
        });
        return data;
    },

    enrollTotp: async (): Promise<{ secret: string; provisioning_uri: string }> => {
        const response = await apiClient.post<{ secret: string; provisioning_uri: string }>(
            '/ai/authn/totp/enroll');
        return response.data;
    },

    confirmTotp: async (code: string): Promise<void> => {
        await apiClient.post('/ai/authn/totp/confirm', { code });
    },

    stepUpWithTotp: async (code: string): Promise<StepUpOutcome> => {
        const { data } = await apiClient.post<StepUpOutcome>('/ai/authn/step-up', {
            method: 'totp', code,
        });
        return data;
    },

    /** Ask the server what a command needs — never re-derive tiers here. */
    classify: async (intent: {
        kind: string;
        category?: string | null;
        amount?: number | null;
        band?: number | null;
        touches_tenant_data?: boolean;
    }) => {
        const { data } = await apiClient.post('/ai/authn/classify', intent);
        return data as {
            tier: 'T0' | 'T1' | 'T2' | 'T3';
            why: string;
            allowed: boolean;
            needs_step_up: boolean;
            needs_oob: boolean;
            locked: boolean;
            reason: string;
        };
    },

    issueOob: async (commandRef: string): Promise<{ challenge_id: string; sent_to_channel: ChannelKind }> => {
        const { data } = await apiClient.post('/ai/authn/oob/issue', {
            command_ref: commandRef,
        });
        return data;
    },

    confirmOob: async (
        challengeId: string, commandRef: string, nonce: string,
    ): Promise<StepUpOutcome> => {
        const { data } = await apiClient.post<StepUpOutcome>('/ai/authn/oob/confirm', {
            challenge_id: challengeId, command_ref: commandRef, nonce,
        });
        return data;
    },
};
