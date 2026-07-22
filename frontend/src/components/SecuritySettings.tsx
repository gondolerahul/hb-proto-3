import React, { useCallback, useEffect, useState } from 'react';
import { GlassCard, GlassInput, JellyButton } from './ui';
import { KeyRound, Smartphone, Trash2, Plus, ShieldCheck } from 'lucide-react';
import {
    authnService,
    isPasskeySupported,
    type AuthnStatus,
    type ChannelKind,
    type PasskeyCredential,
} from '../services/authn.service';
import { StepUpModal } from './StepUpModal';

/**
 * Settings → Security (Inc-3 AUTH T4/T5).
 *
 * Where the owner enrolls the factors and channels that the tier gate later
 * consumes: passkeys, a TOTP fallback, and the channel bindings Pragya uses to
 * recognise them off-console.
 *
 * Two of these operations are themselves T2 — adding and revoking a binding —
 * so the server rejects them without a live elevation and this panel opens the
 * step-up modal in response. The check is not duplicated here; a 403 is the
 * signal.
 */

const CHANNEL_OPTIONS: { value: ChannelKind; label: string; hint: string }[] = [
    { value: 'whatsapp', label: 'WhatsApp', hint: '+919876543210' },
    { value: 'voice', label: 'Phone', hint: '+919876543210' },
    { value: 'email', label: 'Email', hint: 'you@company.com' },
];

export const SecuritySettings: React.FC = () => {
    const [status, setStatus] = useState<AuthnStatus | null>(null);
    const [passkeys, setPasskeys] = useState<PasskeyCredential[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const [stepUpOpen, setStepUpOpen] = useState(false);
    const [pendingAction, setPendingAction] = useState<(() => Promise<void>) | null>(null);

    const [totpUri, setTotpUri] = useState<string | null>(null);
    const [totpSecret, setTotpSecret] = useState<string | null>(null);
    const [totpCode, setTotpCode] = useState('');

    const [newKind, setNewKind] = useState<ChannelKind>('whatsapp');
    const [newAddress, setNewAddress] = useState('');
    const [pendingBindingId, setPendingBindingId] = useState<string | null>(null);
    const [bindingCode, setBindingCode] = useState('');

    const refresh = useCallback(async () => {
        try {
            const [nextStatus, nextPasskeys] = await Promise.all([
                authnService.getStatus(),
                authnService.listPasskeys(),
            ]);
            setStatus(nextStatus);
            setPasskeys(nextPasskeys);
        } catch {
            setError('Could not load your security settings.');
        }
    }, []);

    useEffect(() => { void refresh(); }, [refresh]);

    /** Run a T2 action, opening the step-up modal if the server demands one. */
    const withStepUp = async (action: () => Promise<void>) => {
        setError(null);
        setNotice(null);
        try {
            await action();
            await refresh();
        } catch (err: any) {
            if (err?.response?.status === 403) {
                setPendingAction(() => action);
                setStepUpOpen(true);
                return;
            }
            setError(err?.response?.data?.detail ?? 'That did not work.');
        }
    };

    const handleAddPasskey = async () => {
        setBusy(true);
        try {
            await authnService.registerPasskey(
                `Passkey added ${new Date().toLocaleDateString()}`);
            setNotice('Passkey registered.');
            await refresh();
        } catch (err: any) {
            setError(err?.message ?? 'Passkey registration did not complete.');
        } finally {
            setBusy(false);
        }
    };

    const handleEnrollTotp = async () => {
        setBusy(true);
        try {
            const enrollment = await authnService.enrollTotp();
            setTotpUri(enrollment.provisioning_uri);
            setTotpSecret(enrollment.secret);
        } catch {
            setError('Could not start authenticator setup.');
        } finally {
            setBusy(false);
        }
    };

    const handleConfirmTotp = async () => {
        setBusy(true);
        try {
            await authnService.confirmTotp(totpCode.trim());
            setTotpUri(null);
            setTotpSecret(null);
            setTotpCode('');
            setNotice('Authenticator app confirmed.');
            await refresh();
        } catch (err: any) {
            setError(err?.response?.data?.detail ?? 'That code did not match.');
        } finally {
            setBusy(false);
        }
    };

    const handleAddBinding = () => withStepUp(async () => {
        const result = await authnService.beginBindingEnrollment(newKind, newAddress);
        setPendingBindingId(result.binding_id);
        setNotice(`We sent a code to ${newAddress}. Enter it below to finish.`);
    });

    const handleConfirmBinding = async () => {
        if (!pendingBindingId) return;
        setBusy(true);
        try {
            await authnService.confirmBinding(pendingBindingId, bindingCode.trim());
            setPendingBindingId(null);
            setBindingCode('');
            setNewAddress('');
            setNotice('Channel verified.');
            await refresh();
        } catch (err: any) {
            setError(err?.response?.data?.detail ?? 'That code did not match.');
        } finally {
            setBusy(false);
        }
    };

    const handleRevokeBinding = (id: string) =>
        withStepUp(() => authnService.revokeBinding(id));

    const handleDeletePasskey = (id: string) =>
        withStepUp(() => authnService.deletePasskey(id));

    const bindings = status?.bindings ?? [];
    const hasSecondChannel = bindings.filter((b) => b.verified).length >= 2;

    return (
        <GlassCard className="settings-section">
            <h2><ShieldCheck size={20} /> Security</h2>
            <p className="settings-hint">
                These factors are what let your account manager act on sensitive
                instructions. Without one, she can answer questions and report — but
                she'll decline anything that moves money or changes how your
                processes run.
            </p>

            {error && <div className="alert alert-error">{error}</div>}
            {notice && <div className="alert alert-success">{notice}</div>}

            {/* ── Passkeys ─────────────────────────────────────────────── */}
            <section className="security-block">
                <h3><KeyRound size={16} /> Passkeys</h3>
                {passkeys.length === 0 && <p>No passkey registered yet.</p>}
                <ul className="security-list">
                    {passkeys.map((key) => (
                        <li key={key.id}>
                            <span>{key.label ?? 'Passkey'}</span>
                            <span className="muted">
                                {key.last_used_at
                                    ? `last used ${new Date(key.last_used_at).toLocaleDateString()}`
                                    : 'never used'}
                            </span>
                            <button
                                className="icon-button"
                                aria-label="Remove passkey"
                                onClick={() => handleDeletePasskey(key.id)}
                            >
                                <Trash2 size={16} />
                            </button>
                        </li>
                    ))}
                </ul>
                {isPasskeySupported() ? (
                    <JellyButton onClick={handleAddPasskey} disabled={busy}>
                        <Plus size={16} /> Add a passkey
                    </JellyButton>
                ) : (
                    <p className="muted">
                        This browser doesn't support passkeys — use an authenticator app.
                    </p>
                )}
            </section>

            {/* ── TOTP fallback ────────────────────────────────────────── */}
            <section className="security-block">
                <h3><Smartphone size={16} /> Authenticator app</h3>
                {status?.has_totp && !totpUri && <p>An authenticator app is set up.</p>}

                {!totpUri && (
                    <JellyButton onClick={handleEnrollTotp} disabled={busy}>
                        {status?.has_totp ? 'Replace authenticator' : 'Set up authenticator'}
                    </JellyButton>
                )}

                {totpUri && (
                    <div className="totp-enroll">
                        <p>
                            Add this to your authenticator app, then enter the code it
                            shows to confirm.
                        </p>
                        <code className="totp-secret">{totpSecret}</code>
                        <GlassInput
                            label="Code from your app"
                            value={totpCode}
                            inputMode="numeric"
                            autoComplete="one-time-code"
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                setTotpCode(e.target.value)}
                        />
                        <JellyButton
                            onClick={handleConfirmTotp}
                            disabled={busy || totpCode.trim().length < 6}
                        >
                            Confirm
                        </JellyButton>
                    </div>
                )}
            </section>

            {/* ── Channel bindings ─────────────────────────────────────── */}
            <section className="security-block">
                <h3>Registered channels</h3>
                <p className="settings-hint">
                    Messages from an unregistered number reach your account manager as a
                    stranger's — she'll help, but she won't discuss your business or take
                    instructions. Registering a second channel is also what makes
                    irreversible actions possible to confirm.
                </p>

                <ul className="security-list">
                    {bindings.map((binding) => (
                        <li key={binding.id}>
                            <span>{binding.channel_kind}</span>
                            <span>{binding.address}</span>
                            <span className="muted">
                                {binding.verified ? 'verified' : 'awaiting code'}
                            </span>
                            <button
                                className="icon-button"
                                aria-label="Remove channel"
                                onClick={() => handleRevokeBinding(binding.id)}
                            >
                                <Trash2 size={16} />
                            </button>
                        </li>
                    ))}
                </ul>

                {!hasSecondChannel && (
                    <p className="muted">
                        Register at least two channels so irreversible actions can be
                        confirmed somewhere other than where they were requested.
                    </p>
                )}

                {!pendingBindingId ? (
                    <div className="binding-add">
                        <select
                            value={newKind}
                            onChange={(e) => setNewKind(e.target.value as ChannelKind)}
                            aria-label="Channel type"
                        >
                            {CHANNEL_OPTIONS.map((opt) => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                            ))}
                        </select>
                        <GlassInput
                            value={newAddress}
                            placeholder={
                                CHANNEL_OPTIONS.find((o) => o.value === newKind)?.hint}
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                setNewAddress(e.target.value)}
                        />
                        <JellyButton onClick={handleAddBinding} disabled={busy || !newAddress}>
                            <Plus size={16} /> Add channel
                        </JellyButton>
                    </div>
                ) : (
                    <div className="binding-confirm">
                        <GlassInput
                            label="Code we sent to that channel"
                            value={bindingCode}
                            inputMode="numeric"
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                setBindingCode(e.target.value)}
                        />
                        <JellyButton
                            onClick={handleConfirmBinding}
                            disabled={busy || bindingCode.trim().length < 6}
                        >
                            Verify channel
                        </JellyButton>
                    </div>
                )}
            </section>

            <StepUpModal
                isOpen={stepUpOpen}
                onClose={() => { setStepUpOpen(false); setPendingAction(null); }}
                onElevated={async () => {
                    setStepUpOpen(false);
                    const action = pendingAction;
                    setPendingAction(null);
                    if (action) await withStepUp(action);
                }}
            />
        </GlassCard>
    );
};
