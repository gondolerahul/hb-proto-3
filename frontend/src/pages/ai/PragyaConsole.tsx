import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Send, ShieldCheck, ExternalLink, Check } from 'lucide-react';
import { GlassCard, GlassInput, JellyButton } from '@/components/ui';
import { StepUpModal } from '@/components/StepUpModal';
import {
    pragyaService,
    type Engagement,
    type HistoryTurn,
    type TurnResponse,
} from '@/services/pragya.service';
import './PragyaConsole.css';

/**
 * The Pragya console (Inc-3 PRAGYA T7) — chat, the nine-stage rail, and the
 * step-up ceremony when a command needs more proof than the session holds.
 *
 * The page never decides what a command needs. It sends the turn, and if the
 * server says `needs_step_up`, it opens the modal and re-sends afterwards.
 * That keeps one authorisation path: the frontend cannot accidentally permit
 * something by disagreeing with the classifier.
 */

export const PragyaConsole: React.FC = () => {
    const [engagement, setEngagement] = useState<Engagement | null>(null);
    const [turns, setTurns] = useState<HistoryTurn[]>([]);
    const [draft, setDraft] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Stages 2 and 5 wait on the owner. Without this the engagement
    // dead-ends: the server will not advance them and nothing else can.
    const [awaitingConfirmation, setAwaitingConfirmation] = useState(false);
    const [confirming, setConfirming] = useState(false);

    const [stepUpOpen, setStepUpOpen] = useState(false);
    const [pendingTurn, setPendingTurn] = useState<TurnResponse | null>(null);
    const [pendingMessage, setPendingMessage] = useState<string>('');

    const endRef = useRef<HTMLDivElement>(null);

    const refresh = useCallback(async () => {
        try {
            const [next, history] = await Promise.all([
                pragyaService.getEngagement(),
                pragyaService.getHistory(),
            ]);
            setEngagement(next);
            setTurns(history);
        } catch {
            setError('Could not load your conversation.');
        }
    }, []);

    useEffect(() => { void refresh(); }, [refresh]);
    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [turns]);

    const deliver = async (message: string) => {
        setBusy(true);
        setError(null);
        try {
            const result = await pragyaService.send(message);
            await refresh();

            // The server decides when a confirmation is due — the console
            // never infers it from the stage number.
            setAwaitingConfirmation(result.awaiting_confirmation);

            // The server decides a ceremony is needed; we just open it and
            // hold the message so it can be re-sent once elevated.
            if (result.needs_step_up || result.needs_oob) {
                setPendingTurn(result);
                setPendingMessage(message);
                setStepUpOpen(true);
            }
            return result;
        } catch (err: any) {
            setError(err?.response?.data?.detail ?? 'That message did not go through.');
            return null;
        } finally {
            setBusy(false);
        }
    };

    const handleSend = async (e: React.FormEvent) => {
        e.preventDefault();
        const message = draft.trim();
        if (!message || busy) return;
        setDraft('');
        await deliver(message);
    };

    const handleConfirmStage = async () => {
        setConfirming(true);
        setError(null);
        try {
            await pragyaService.advance();
            setAwaitingConfirmation(false);
            await refresh();
        } catch (err: any) {
            // A 409 means the stage is not actually finished yet — the server
            // refuses to carry a half-formed hypothesis into the build.
            setError(err?.response?.data?.detail
                ?? 'That stage is not ready to close yet.');
        } finally {
            setConfirming(false);
        }
    };

    const currentStage = engagement?.stage ?? 1;

    return (
        <div className="pragya-console">
            <GlassCard className="pragya-rail">
                <h2>Engagement</h2>
                <ol className="stage-rail">
                    {(engagement?.stages ?? []).map((s) => (
                        <li
                            key={s.stage}
                            className={
                                s.stage === currentStage ? 'current'
                                    : s.stage < currentStage ? 'done' : ''
                            }
                            title={s.summary}
                        >
                            <span className="stage-num">{s.stage}</span>
                            <span className="stage-name">{s.name}</span>
                        </li>
                    ))}
                </ol>
                {engagement && (
                    <p className="stage-summary">{engagement.stage_summary}</p>
                )}
                <a className="desk-link" href="/ai/approvals">
                    Judgment Desk <ExternalLink size={14} />
                </a>
                <p className="desk-note">
                    Approvals always happen here, never in chat — so there's a
                    record of a human making the call.
                </p>
            </GlassCard>

            <GlassCard className="pragya-chat">
                <div className="chat-scroll">
                    {turns.length === 0 && (
                        <p className="chat-empty">
                            Pragya is your account manager. Ask her how the week
                            went, or tell her what to change.
                        </p>
                    )}
                    {turns.map((t, i) => (
                        <div key={i} className={`bubble ${t.role}`}>
                            <p>{t.content}</p>
                            {t.tier && t.tier !== 'T0' && t.tier !== 'T1' && (
                                <span className="tier-chip" title="Needed verification">
                                    <ShieldCheck size={12} /> {t.tier}
                                </span>
                            )}
                        </div>
                    ))}
                    <div ref={endRef} />
                </div>

                {error && <div className="alert alert-error">{error}</div>}

                {awaitingConfirmation && (
                    <div className="stage-confirm">
                        <span>
                            Happy with this? I'll only move on when you say so.
                        </span>
                        <JellyButton onClick={handleConfirmStage} disabled={confirming}>
                            <Check size={16} /> Yes, continue
                        </JellyButton>
                    </div>
                )}

                <form className="chat-input" onSubmit={handleSend}>
                    <GlassInput
                        value={draft}
                        placeholder="Ask Pragya anything about your business…"
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                            setDraft(e.target.value)}
                        disabled={busy}
                    />
                    <JellyButton type="submit" disabled={busy || !draft.trim()}>
                        <Send size={16} />
                    </JellyButton>
                </form>
            </GlassCard>

            <StepUpModal
                isOpen={stepUpOpen}
                needsOob={pendingTurn?.needs_oob}
                commandRef={pendingTurn?.command_ref ?? undefined}
                commandSummary={pendingTurn?.command_summary ?? undefined}
                onClose={() => {
                    setStepUpOpen(false);
                    setPendingTurn(null);
                    setPendingMessage('');
                }}
                onElevated={async () => {
                    setStepUpOpen(false);
                    const message = pendingMessage;
                    setPendingTurn(null);
                    setPendingMessage('');
                    if (message) await deliver(message);
                }}
            />
        </div>
    );
};

export default PragyaConsole;
