/**
 * components/agent/P11IterationCard — One row per iteration on the
 * AgentLoop timeline.
 *
 * Shows the executor, decision, the four critic verdicts (Track 3),
 * any retry the Strategist queued (Track 3), and a resume marker
 * when the worker picked up from a snapshot (Track 2).
 */
import React from 'react';

import type {
    IterationSlice,
} from '@/hooks/useExecutionEvents';
import type { SpanNode } from '@/types/phase11';

import {
    P11CriticVerdictChip,
    P11ExecutorBadge,
    P11FailureTagChip,
    P11ResumeIndicator,
    P11RetryStrategyBadge,
} from './P11AgentKernel';
import { P11SpanTree } from './P11SpanTree';

import './P11IterationCard.css';

interface Props {
    slice: IterationSlice;
    /** Resolved span-tree roots for this iteration (steps/tools/LLM calls). */
    spans?: SpanNode[];
}

export const P11IterationCard: React.FC<Props> = ({ slice, spans }) => {
    const cost = Number(slice.cost_iter_usd ?? 0);
    return (
        <div className={`p11-iter-card p11-iter-card--${slice.outcome ?? 'pending'}`}>
            <div className="p11-iter-card__header">
                <span className="p11-iter-card__num">iter #{slice.iteration}</span>
                <P11ExecutorBadge executor={slice.executor as never} />
                {typeof slice.resumed_from === 'number' && (
                    <P11ResumeIndicator fromIteration={slice.resumed_from} />
                )}
                <span className="p11-iter-card__decision">
                    {slice.decision ?? (slice.outcome ? slice.outcome : 'running…')}
                </span>
                {cost > 0 && (
                    <span className="p11-iter-card__cost" title="iteration cost">
                        ${cost.toFixed(4)}
                    </span>
                )}
            </div>

            <div className="p11-iter-card__verdicts">
                {slice.pre_critic && (
                    <P11CriticVerdictChip
                        label="pre"
                        verdict={slice.pre_critic.verdict}
                        title={
                            slice.pre_critic.concerns_count
                                ? `${slice.pre_critic.concerns_count} concerns`
                                : undefined
                        }
                    />
                )}
                {slice.post_critic && (
                    <P11CriticVerdictChip
                        label="post"
                        verdict={slice.post_critic.verdict}
                    />
                )}
                {slice.alignment && (
                    <P11CriticVerdictChip
                        label="align"
                        verdict={slice.alignment.aligned ? 'PASS' : 'REVISE'}
                        title={`drift ${(slice.alignment.drift * 100).toFixed(0)}%`}
                    />
                )}
                {slice.supervisor && (
                    <P11CriticVerdictChip
                        label="super"
                        verdict={slice.supervisor.recommendation}
                        title={`conf ${(slice.supervisor.confidence * 100).toFixed(0)}%`}
                    />
                )}
                {slice.retry && (
                    <P11RetryStrategyBadge strategy={slice.retry.strategy} />
                )}
            </div>

            {slice.post_critic?.tags?.length ? (
                <div className="p11-iter-card__tags">
                    {slice.post_critic.tags.map((t) => (
                        <P11FailureTagChip key={t} tag={t} />
                    ))}
                </div>
            ) : null}

            {spans && spans.length > 0 && <P11SpanTree roots={spans} />}
        </div>
    );
};
