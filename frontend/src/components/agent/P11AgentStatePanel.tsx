/**
 * components/agent/P11AgentStatePanel — Sticky right-rail of
 * ExecutionDetail. Renders live AgentState: budget, subgoals,
 * blockers, last action / observation, recent reflections.
 */
import React from 'react';

import type { AgentStateSnapshot } from '@/types/phase11';

import { P11BudgetBar, P11ExecutorBadge } from './P11AgentKernel';

import './P11AgentStatePanel.css';

interface Props {
    state: AgentStateSnapshot | null;
    loading?: boolean;
}

export const P11AgentStatePanel: React.FC<Props> = ({ state, loading }) => {
    if (loading && !state) {
        return (
            <aside className="p11-state-panel">
                <h3>Agent State</h3>
                <p className="p11-state-panel__loading">loading…</p>
            </aside>
        );
    }
    if (!state) {
        return (
            <aside className="p11-state-panel">
                <h3>Agent State</h3>
                <p className="p11-state-panel__empty">No snapshot yet.</p>
            </aside>
        );
    }
    // Defensive: a snapshot may be partial (older runs / mid-write); never
    // crash on a missing array field.
    const openSubgoals = state.open_subgoals ?? [];
    const achieved = state.achieved ?? [];
    const blockers = state.blockers ?? [];

    return (
        <aside className="p11-state-panel">
            <h3>Agent State</h3>

            <section className="p11-state-panel__section">
                <h4>Budget · iter #{state.iteration}</h4>
                <P11BudgetBar budget={state.budget} />
                {state.task_class && (
                    <div className="p11-state-panel__taskclass">
                        task class: <code>{state.task_class}</code>
                    </div>
                )}
            </section>

            <section className="p11-state-panel__section">
                <h4>Open subgoals ({openSubgoals.length})</h4>
                {openSubgoals.length === 0 ? (
                    <p className="p11-state-panel__empty">none</p>
                ) : (
                    <ul className="p11-state-panel__list">
                        {openSubgoals.map((sg) => (
                            <li key={sg.id}>
                                <strong>{sg.description}</strong>
                                {sg.blocked_on ? (
                                    <span className="p11-state-panel__blocked">
                                        blocked: {sg.blocked_on}
                                    </span>
                                ) : null}
                            </li>
                        ))}
                    </ul>
                )}
            </section>

            {achieved.length > 0 && (
                <section className="p11-state-panel__section">
                    <h4>Achieved ({achieved.length})</h4>
                    <ul className="p11-state-panel__list p11-state-panel__list--muted">
                        {achieved.map((sg) => (
                            <li key={sg.id}>✓ {sg.description}</li>
                        ))}
                    </ul>
                </section>
            )}

            {blockers.length > 0 && (
                <section className="p11-state-panel__section">
                    <h4>Blockers</h4>
                    <ul className="p11-state-panel__list">
                        {blockers.map((b, i) => (
                            <li key={i} className="p11-state-panel__blocker">
                                <span className="p11-state-panel__blocker-kind">{b.kind}</span>{' '}
                                {b.detail}
                            </li>
                        ))}
                    </ul>
                </section>
            )}

            {(state.last_action || state.last_observation) && (
                <section className="p11-state-panel__section">
                    <h4>Last activity</h4>
                    {state.last_action && (
                        <div>
                            <P11ExecutorBadge executor={state.last_action.executor} />{' '}
                            <span className="p11-state-panel__muted">
                                iter {state.last_action.iteration}
                            </span>
                        </div>
                    )}
                    {state.last_observation && (
                        <p className="p11-state-panel__obs">
                            <span className={`p11-state-panel__outcome p11-state-panel__outcome--${state.last_observation.outcome}`}>
                                {state.last_observation.outcome}
                            </span>{' '}
                            {state.last_observation.summary?.slice(0, 200) || ''}
                        </p>
                    )}
                </section>
            )}

            <P11ReflectionsList state={state} />
        </aside>
    );
};

const P11ReflectionsList: React.FC<{ state: AgentStateSnapshot }> = ({ state }) => {
    const recent = (state.reflections ?? []).slice(-5).reverse();
    if (!recent.length) return null;
    return (
        <section className="p11-state-panel__section">
            <h4>Reflections (last {recent.length})</h4>
            <ul className="p11-state-panel__list">
                {recent.map((r, i) => (
                    <li key={i} className="p11-state-panel__refl">
                        <span className={`p11-state-panel__refl-scope p11-state-panel__refl-scope--${r.scope}`}>
                            {r.scope}
                        </span>
                        {r.proposed_change ? (
                            <strong>{r.proposed_change}</strong>
                        ) : (
                            <em>{r.what_worked || r.what_didnt || '—'}</em>
                        )}
                    </li>
                ))}
            </ul>
        </section>
    );
};
