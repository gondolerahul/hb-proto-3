/**
 * pages/admin/LoopOpsPage — the Inc-2 ONBOARD admin surfaces
 * (04_onboard_wizard.md §2) over the Inc-1 signal/loop APIs:
 *
 *   1. Signals  — coverage KPI tiles + the parked/escalated/dead queues + replay.
 *   2. Triggers — the trigger registry: enable/disable + priority.
 *   3. Envelope — Sheel's budget envelope: utilization, reserve, downshift/cap.
 */
import React, { useCallback, useEffect, useState } from 'react';

import {
    aiAdminService,
    EnvelopeRow,
    SignalCoverage,
    SignalRow,
    SignalStatus,
    TriggerRow,
} from '@/services/aiAdmin.service';

import './LoopOpsPage.css';

type Tab = 'signals' | 'triggers' | 'envelope';

const QUEUE_FILTERS: (SignalStatus | 'all')[] = ['all', 'pending', 'parked', 'escalated', 'dead', 'consumed'];

export const LoopOpsPage: React.FC = () => {
    const [tab, setTab] = useState<Tab>('signals');

    return (
        <div className="page-container loop-ops">
            <header className="page-header">
                <h1>Loop Operations</h1>
                <p>
                    Signal bus, trigger registry and the budget envelope — the operator
                    view of the one-loop substrate.
                </p>
            </header>

            <nav className="loop-ops__tabs">
                <button className={tab === 'signals' ? 'active' : ''} onClick={() => setTab('signals')}>Signals</button>
                <button className={tab === 'triggers' ? 'active' : ''} onClick={() => setTab('triggers')}>Triggers</button>
                <button className={tab === 'envelope' ? 'active' : ''} onClick={() => setTab('envelope')}>Envelope</button>
            </nav>

            {tab === 'signals' && <SignalsTab />}
            {tab === 'triggers' && <TriggersTab />}
            {tab === 'envelope' && <EnvelopeTab />}
        </div>
    );
};

// ── Tab 1: signals inspector ────────────────────────────────────────────────

const SignalsTab: React.FC = () => {
    const [coverage, setCoverage] = useState<SignalCoverage | null>(null);
    const [signals, setSignals] = useState<SignalRow[] | null>(null);
    const [filter, setFilter] = useState<SignalStatus | 'all'>('all');
    const [expanded, setExpanded] = useState<string | null>(null);
    const [replaying, setReplaying] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);

    const refresh = useCallback(() => {
        aiAdminService.getCoverage().then(setCoverage).catch(() => setCoverage(null));
        aiAdminService.listSignals(filter === 'all' ? undefined : filter)
            .then(setSignals)
            .catch(() => setSignals([]));
    }, [filter]);

    useEffect(() => { refresh(); }, [refresh]);

    const handleReplay = async (id: string) => {
        setReplaying(id);
        setNotice(null);
        try {
            const res = await aiAdminService.replaySignal(id);
            setNotice(`Replayed as ${res.id}`);
            refresh();
        } catch {
            setNotice('Replay failed');
        } finally {
            setReplaying(null);
        }
    };

    return (
        <section>
            {coverage && (
                <div className="loop-ops__tiles">
                    <div className="loop-ops__tile">
                        <span className="tile-value">{coverage.coverage_pct}%</span>
                        <span className="tile-label">coverage</span>
                    </div>
                    {(['pending', 'consumed', 'parked', 'escalated', 'dead'] as SignalStatus[]).map(s => (
                        <div key={s} className={`loop-ops__tile ${['parked', 'escalated', 'dead'].includes(s) && (coverage.counts[s] || 0) > 0 ? 'warn' : ''}`}>
                            <span className="tile-value">{coverage.counts[s] || 0}</span>
                            <span className="tile-label">{s}</span>
                        </div>
                    ))}
                </div>
            )}

            <div className="loop-ops__filterbar">
                {QUEUE_FILTERS.map(f => (
                    <button
                        key={f}
                        className={`chip ${filter === f ? 'active' : ''}`}
                        onClick={() => setFilter(f)}
                    >{f}</button>
                ))}
                <button className="chip refresh" onClick={refresh}>↻ refresh</button>
                {notice && <span className="loop-ops__notice">{notice}</span>}
            </div>

            {signals === null ? <p>loading…</p> : signals.length === 0 ? (
                <p className="loop-ops__empty">No signals{filter !== 'all' ? ` in '${filter}'` : ''}.</p>
            ) : (
                <table className="loop-ops__table">
                    <thead>
                        <tr>
                            <th>type</th><th>source</th><th>status</th><th>urgency</th>
                            <th>attempts</th><th>created</th><th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {signals.map(s => (
                            <React.Fragment key={s.id}>
                                <tr className="signal-row" onClick={() => setExpanded(expanded === s.id ? null : s.id)}>
                                    <td className="mono">{s.type}</td>
                                    <td>{s.source}</td>
                                    <td><span className={`status status--${s.status}`}>{s.status}</span></td>
                                    <td>{s.urgency}</td>
                                    <td>{s.attempts}</td>
                                    <td>{new Date(s.created_at).toLocaleString()}</td>
                                    <td>
                                        {['parked', 'escalated', 'dead'].includes(s.status) && (
                                            <button
                                                className="chip"
                                                disabled={replaying === s.id}
                                                onClick={(e) => { e.stopPropagation(); handleReplay(s.id); }}
                                            >
                                                {replaying === s.id ? '…' : 'replay'}
                                            </button>
                                        )}
                                    </td>
                                </tr>
                                {expanded === s.id && (
                                    <tr className="signal-detail">
                                        <td colSpan={7}>
                                            {s.last_error && <div className="signal-error">last_error: {s.last_error}</div>}
                                            <pre>{JSON.stringify({ payload: s.payload, object_refs: s.object_refs, dedupe_key: s.dedupe_key, replayed_from: s.replayed_from }, null, 2)}</pre>
                                        </td>
                                    </tr>
                                )}
                            </React.Fragment>
                        ))}
                    </tbody>
                </table>
            )}
        </section>
    );
};

// ── Tab 2: trigger registry ─────────────────────────────────────────────────

const TriggersTab: React.FC = () => {
    const [triggers, setTriggers] = useState<TriggerRow[] | null>(null);
    const [busy, setBusy] = useState<string | null>(null);

    const refresh = useCallback(() => {
        aiAdminService.listTriggers().then(setTriggers).catch(() => setTriggers([]));
    }, []);

    useEffect(() => { refresh(); }, [refresh]);

    const toggle = async (t: TriggerRow) => {
        setBusy(t.id);
        try {
            await aiAdminService.updateTrigger(t.id, { enabled: !t.enabled });
            refresh();
        } finally {
            setBusy(null);
        }
    };

    const setPriority = async (t: TriggerRow, raw: string) => {
        const priority = parseInt(raw, 10);
        if (Number.isNaN(priority) || priority === t.priority) return;
        setBusy(t.id);
        try {
            await aiAdminService.updateTrigger(t.id, { priority });
            refresh();
        } finally {
            setBusy(null);
        }
    };

    if (triggers === null) return <p>loading…</p>;
    return (
        <section>
            {triggers.length === 0 ? (
                <p className="loop-ops__empty">No trigger registrations — activate a bundle first.</p>
            ) : (
                <table className="loop-ops__table">
                    <thead>
                        <tr><th>pattern</th><th>process entity</th><th>priority</th><th>enabled</th></tr>
                    </thead>
                    <tbody>
                        {triggers.map(t => (
                            <tr key={t.id}>
                                <td className="mono">{t.type_pattern}</td>
                                <td className="mono dim">{t.process_entity_id}</td>
                                <td>
                                    <input
                                        className="loop-ops__priority"
                                        type="number"
                                        defaultValue={t.priority}
                                        disabled={busy === t.id}
                                        onBlur={(e) => setPriority(t, e.target.value)}
                                    />
                                </td>
                                <td>
                                    <button
                                        className={`chip ${t.enabled ? 'active' : ''}`}
                                        disabled={busy === t.id}
                                        onClick={() => toggle(t)}
                                    >
                                        {t.enabled ? 'enabled' : 'disabled'}
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </section>
    );
};

// ── Tab 3: budget envelope ──────────────────────────────────────────────────

const EnvelopeTab: React.FC = () => {
    const [envelopes, setEnvelopes] = useState<EnvelopeRow[] | null>(null);

    useEffect(() => {
        aiAdminService.getEnvelopes().then(setEnvelopes).catch(() => setEnvelopes([]));
    }, []);

    if (envelopes === null) return <p>loading…</p>;
    if (envelopes.length === 0) {
        return <p className="loop-ops__empty">No budget envelope yet — it is seeded with the Loop runtime.</p>;
    }
    return (
        <section className="loop-ops__envelopes">
            {envelopes.map(env => (
                <div key={env.id} className={`envelope-card ${env.capped ? 'capped' : env.downshift ? 'downshift' : ''}`}>
                    <div className="envelope-cycle">
                        {env.cycle}
                        {env.capped ? <span className="status status--dead">capped</span>
                            : env.downshift ? <span className="status status--parked">downshift</span>
                            : <span className="status status--consumed">healthy</span>}
                    </div>
                    <div className="envelope-bar">
                        <div
                            className="envelope-bar__fill"
                            style={{ width: `${Math.min(env.utilization_pct, 100)}%` }}
                        />
                        <div
                            className="envelope-bar__downshift"
                            style={{ left: `${env.downshift_at_pct}%` }}
                            title={`downshift at ${env.downshift_at_pct}%`}
                        />
                    </div>
                    <div className="envelope-meta">
                        <span>{env.utilization_pct}% used</span>
                        <span>${env.spent_usd.toFixed(2)} spent</span>
                        <span>${env.reserved_usd.toFixed(2)} reserved</span>
                        <span>${env.envelope_usd.toFixed(2)} envelope</span>
                    </div>
                    {env.refreshed_at && (
                        <div className="envelope-refresh">refreshed {new Date(env.refreshed_at).toLocaleString()}</div>
                    )}
                </div>
            ))}
        </section>
    );
};

export default LoopOpsPage;
