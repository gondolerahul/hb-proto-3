import React, { useEffect, useState } from 'react';
import { ShieldCheck, X, KeyRound, Smartphone, AlertTriangle } from 'lucide-react';
import { GlassCard, GlassInput, JellyButton } from './ui';
import {
    authnService,
    isPasskeySupported,
    type AuthnStatus,
    type ChannelKind,
} from '../services/authn.service';

/**
 * The step-up ceremony modal (Inc-3 AUTH T4).
 *
 * Pragya's console opens this when a command needs more proof than the session
 * holds. It renders what the *server* said was missing — it never classifies a
 * command itself, because a second copy of the tier rules in the frontend is a
 * second thing to keep correct.
 *
 * For a T3 command the modal runs both legs in order: the passkey/TOTP
 * ceremony, then a nonce sent to a different registered channel. The second
 * leg deliberately cannot be completed on the channel that asked.
 */

interface StepUpModalProps {
    isOpen: boolean;
    onClose: () => void;
    /** Set by the server's classify/require response. */
    needsOob?: boolean;
    /** Identifies the command the T3 nonce is bound to. */
    commandRef?: string;
    /** Human-readable statement of what is being authorised. */
    commandSummary?: string;
    onElevated: () => void;
}

export const StepUpModal: React.FC<StepUpModalProps> = ({
    isOpen,
    onClose,
    needsOob = false,
    commandRef,
    commandSummary,
    onElevated,
}) => {
    const [status, setStatus] = useState<AuthnStatus | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [totpCode, setTotpCode] = useState('');

    // Second-leg state, only reached after the first leg succeeds.
    const [challengeId, setChallengeId] = useState<string | null>(null);
    const [oobChannel, setOobChannel] = useState<ChannelKind | null>(null);
    const [nonce, setNonce] = useState('');

    useEffect(() => {
        if (!isOpen) return;
        setError(null);
        setTotpCode('');
        setNonce('');
        setChallengeId(null);
        authnService.getStatus().then(setStatus).catch(() => setStatus(null));
    }, [isOpen]);

    if (!isOpen) return null;

    const finishFirstLeg = async () => {
        if (!needsOob) {
            onElevated();
            onClose();
            return;
        }
        if (!commandRef) {
            setError('This command cannot be confirmed out of band: no command reference.');
            return;
        }
        // Fail closed and say why: with no second channel there is no way to
        // authorise a T3 command at all, and the fix is enrolling one.
        try {
            const issued = await authnService.issueOob(commandRef);
            setChallengeId(issued.challenge_id);
            setOobChannel(issued.sent_to_channel);
        } catch (err: any) {
            setError(err?.response?.data?.detail
                ?? 'Could not send the confirmation to a second channel.');
        }
    };

    const handlePasskey = async () => {
        setBusy(true);
        setError(null);
        try {
            const outcome = await authnService.stepUpWithPasskey();
            if (!outcome.ok) {
                setError(outcome.locked
                    ? 'Too many failed attempts — sensitive commands are locked for now. '
                      + 'We alerted every channel registered to your account.'
                    : outcome.reason ?? 'Passkey verification failed.');
                return;
            }
            await finishFirstLeg();
        } catch (err: any) {
            setError(err?.message ?? 'The passkey ceremony did not complete.');
        } finally {
            setBusy(false);
        }
    };

    const handleTotp = async () => {
        setBusy(true);
        setError(null);
        try {
            const outcome = await authnService.stepUpWithTotp(totpCode.trim());
            if (!outcome.ok) {
                setError(outcome.locked
                    ? 'Too many failed attempts — sensitive commands are locked for now. '
                      + 'We alerted every channel registered to your account.'
                    : outcome.reason ?? 'That code did not match.');
                return;
            }
            await finishFirstLeg();
        } catch (err: any) {
            setError(err?.response?.data?.detail ?? 'Verification failed.');
        } finally {
            setBusy(false);
        }
    };

    const handleOobConfirm = async () => {
        if (!challengeId || !commandRef) return;
        setBusy(true);
        setError(null);
        try {
            const outcome = await authnService.confirmOob(
                challengeId, commandRef, nonce.trim());
            if (!outcome.ok) {
                setError(outcome.reason ?? 'That confirmation code did not match.');
                return;
            }
            onElevated();
            onClose();
        } catch (err: any) {
            setError(err?.response?.data?.detail ?? 'Confirmation failed.');
        } finally {
            setBusy(false);
        }
    };

    const locked = status?.locked ?? false;
    const inSecondLeg = challengeId !== null;

    return (
        <div className="modal-overlay">
            <GlassCard className="modal-content" style={{ maxWidth: 460 }}>
                <div className="modal-header">
                    <h2><ShieldCheck size={20} /> Confirm it's you</h2>
                    <button className="icon-button" onClick={onClose} aria-label="Close">
                        <X size={18} />
                    </button>
                </div>

                {commandSummary && (
                    <p className="step-up-command">
                        You're authorising: <strong>{commandSummary}</strong>
                    </p>
                )}

                {locked && (
                    <div className="alert alert-error">
                        <AlertTriangle size={16} />
                        <span>
                            Sensitive commands are locked after repeated failed attempts.
                            {status?.locked_until
                                && ` Try again after ${new Date(status.locked_until).toLocaleTimeString()}.`}
                        </span>
                    </div>
                )}

                {error && <div className="alert alert-error">{error}</div>}

                {!locked && !inSecondLeg && (
                    <div className="step-up-methods">
                        {status?.has_passkey && isPasskeySupported() && (
                            <JellyButton onClick={handlePasskey} disabled={busy}>
                                <KeyRound size={16} /> Use a passkey
                            </JellyButton>
                        )}

                        {status?.has_totp && (
                            <div className="step-up-totp">
                                <label htmlFor="totp-code">
                                    <Smartphone size={16} /> Authenticator code
                                </label>
                                <GlassInput
                                    id="totp-code"
                                    value={totpCode}
                                    inputMode="numeric"
                                    autoComplete="one-time-code"
                                    placeholder="123456"
                                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                        setTotpCode(e.target.value)}
                                />
                                <JellyButton
                                    onClick={handleTotp}
                                    disabled={busy || totpCode.trim().length < 6}
                                >
                                    Verify
                                </JellyButton>
                            </div>
                        )}

                        {!status?.has_passkey && !status?.has_totp && (
                            <p className="step-up-empty">
                                You haven't set up a passkey or an authenticator app yet.
                                Add one in Settings → Security before running sensitive
                                commands.
                            </p>
                        )}
                    </div>
                )}

                {inSecondLeg && (
                    <div className="step-up-oob">
                        <p>
                            This action can't be undone, so it needs a second confirmation.
                            We sent a code to your registered <strong>{oobChannel}</strong>{' '}
                            channel — not to this one, on purpose.
                        </p>
                        <GlassInput
                            id="oob-nonce"
                            value={nonce}
                            inputMode="numeric"
                            placeholder="123456"
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                setNonce(e.target.value)}
                        />
                        <JellyButton
                            onClick={handleOobConfirm}
                            disabled={busy || nonce.trim().length < 6}
                        >
                            Confirm
                        </JellyButton>
                    </div>
                )}
            </GlassCard>
        </div>
    );
};
