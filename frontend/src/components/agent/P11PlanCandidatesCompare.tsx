/**
 * components/agent/P11PlanCandidatesCompare — modal-style side-by-side
 * compare of the plan candidates the PlanGenerator generated.
 *
 * The "chosen" candidate is highlighted; "alternates" are shown with
 * their invariant violations + the judge's score (when present).
 */
import React, { useEffect, useState } from 'react';

import { agentService } from '@/services/agent.service';
import type { PlanCandidate, PlanCandidatesResponse } from '@/types/phase11';

import './P11PlanCandidatesCompare.css';

interface Props {
    runId: string;
    open: boolean;
    onClose: () => void;
}

export const P11PlanCandidatesCompare: React.FC<Props> = ({
    runId,
    open,
    onClose,
}) => {
    const [data, setData] = useState<PlanCandidatesResponse | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!open) return;
        setLoading(true);
        agentService
            .getPlanCandidates(runId)
            .then(setData)
            .finally(() => setLoading(false));
    }, [open, runId]);

    if (!open) return null;

    return (
        <div className="p11-plancmp-overlay" onClick={onClose}>
            <div
                className="p11-plancmp-modal"
                onClick={(e) => e.stopPropagation()}
            >
                <header className="p11-plancmp-modal__header">
                    <h3>Plan candidates</h3>
                    <button onClick={onClose} aria-label="close">
                        ✕
                    </button>
                </header>
                <div className="p11-plancmp-modal__body">
                    {loading && <p>loading…</p>}
                    {!loading && (!data?.chosen && data?.alternates.length === 0) && (
                        <p className="p11-plancmp-modal__empty">
                            No plan candidates persisted for this run.
                        </p>
                    )}
                    {!loading && data?.chosen && (
                        <div className="p11-plancmp-modal__grid">
                            <CandidateCard
                                candidate={data.chosen}
                                title="Chosen"
                                emphasis
                            />
                            {data.alternates.map((c, i) => (
                                <CandidateCard
                                    key={i}
                                    candidate={c}
                                    title={`Alternate ${i + 1}`}
                                />
                            ))}
                        </div>
                    )}
                    {!loading && data?.judge_reasoning && (
                        <p className="p11-plancmp-modal__judge">
                            <strong>Judge:</strong> {data.judge_reasoning}
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
};

const CandidateCard: React.FC<{
    candidate: PlanCandidate;
    title: string;
    emphasis?: boolean;
}> = ({ candidate, title, emphasis }) => {
    const steps = candidate.steps ?? [];
    return (
        <article
            className={`p11-plancmp-card ${emphasis ? 'p11-plancmp-card--chosen' : ''}`}
        >
            <header>
                <strong>{title}</strong>
                <span className="p11-plancmp-card__style">{candidate.style}</span>
                <span className="p11-plancmp-card__cost">
                    ${candidate.estimated_cost_usd}
                </span>
            </header>
            {candidate.invariant_violations &&
                candidate.invariant_violations.length > 0 && (
                    <div className="p11-plancmp-card__violations">
                        {candidate.invariant_violations.map((v) => (
                            <span key={v}>⚠ {v}</span>
                        ))}
                    </div>
                )}
            {typeof candidate.judge_score === 'number' && (
                <div className="p11-plancmp-card__judge">
                    judge score: {candidate.judge_score.toFixed(2)}
                </div>
            )}
            <ol className="p11-plancmp-card__steps">
                {steps.slice(0, 12).map((s: any, i: number) => (
                    <li key={s?.step_id ?? i}>
                        <code>{s?.type ?? '?'}</code>{' '}
                        {s?.name ?? s?.step_id ?? `step ${i + 1}`}
                    </li>
                ))}
                {steps.length > 12 && (
                    <li className="p11-plancmp-card__more">
                        …({steps.length - 12} more)
                    </li>
                )}
            </ol>
        </article>
    );
};
