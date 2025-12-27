import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { GlassCard, JellyButton } from '@/components/ui';
import { ArrowLeft, ChevronDown, ChevronRight, Zap, Cpu, MessageSquare } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { ExecutionRun, RunStatus, EntityType, LLMInteractionLog } from '@/types';
import './ExecutionDetail.css';

const TraceNode: React.FC<{ run: ExecutionRun; depth: number }> = ({ run, depth }) => {
    const [expanded, setExpanded] = useState(depth < 2);
    const [showLogs, setShowLogs] = useState(false);

    const hasChildren = run.child_runs && run.child_runs.length > 0;
    const hasLogs = run.llm_logs && run.llm_logs.length > 0;

    const getStatusColor = (status: RunStatus) => {
        switch (status) {
            case RunStatus.COMPLETED: return 'var(--color-success)';
            case RunStatus.FAILED: return 'var(--color-error)';
            case RunStatus.RUNNING: return 'var(--color-warning)';
            default: return 'var(--color-text-tertiary)';
        }
    };

    return (
        <div className="trace-node" style={{ marginLeft: depth > 0 ? '20px' : '0' }}>
            <div className={`node-header ${run.status.toLowerCase()}`} onClick={() => hasChildren && setExpanded(!expanded)}>
                <div className="node-icon">
                    {hasChildren ? (expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : <div style={{ width: 14 }} />}
                    {run.entity?.type === EntityType.ACTION ? <Zap size={14} /> : <Cpu size={14} />}
                </div>

                <div className="node-info">
                    <span className="node-name">{run.entity?.name || 'Anonymous Unit'}</span>
                    <span className="node-type">[{run.entity?.type || 'UNKNOWN'}]</span>
                </div>

                <div className="node-meta">
                    <span className="node-status" style={{ color: getStatusColor(run.status) }}>
                        {run.status}
                    </span>
                    {run.completed_at && run.started_at && (
                        <span className="node-duration">
                            {((new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000).toFixed(2)}s
                        </span>
                    )}
                </div>
            </div>

            {expanded && (
                <div className="node-body">
                    {/* Reasoning / Thoughts */}
                    {run.context_state?.reasoning && (
                        <div className="node-thought">
                            <div className="thought-header"><MessageSquare size={12} /> Reasoning</div>
                            <div className="thought-content">{run.context_state.reasoning}</div>
                        </div>
                    )}

                    {/* LLM Logs */}
                    {hasLogs && (
                        <div className="node-logs">
                            <button className="text-btn" onClick={() => setShowLogs(!showLogs)}>
                                {showLogs ? 'Hide' : 'Show'} LLM Interactions ({run.llm_logs?.length})
                            </button>
                            {showLogs && run.llm_logs?.map((log: LLMInteractionLog) => (
                                <div key={log.id} className="log-entry">
                                    <div className="log-meta">
                                        <span>{log.model_name}</span>
                                        <span>{log.prompt_tokens + log.completion_tokens} tokens</span>
                                        <span>{log.latency_ms}ms</span>
                                    </div>
                                    <div className="log-io">
                                        <div className="io-box">
                                            <label>Prompt</label>
                                            <pre>{log.input_prompt}</pre>
                                        </div>
                                        <div className="io-box">
                                            <label>Response</label>
                                            <pre>{log.output_response}</pre>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Result */}
                    {run.result_data && (
                        <div className="node-result">
                            <label>Result</label>
                            <pre>{JSON.stringify(run.result_data, null, 2)}</pre>
                        </div>
                    )}

                    {/* Error */}
                    {run.error_message && (
                        <div className="node-error">
                            <label>Error</label>
                            <div className="error-text">{run.error_message}</div>
                        </div>
                    )}

                    {/* Recursive Children */}
                    {hasChildren && (
                        <div className="node-children">
                            {run.child_runs?.map(child => (
                                <TraceNode key={child.id} run={child} depth={depth + 1} />
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export const ExecutionDetail: React.FC = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [run, setRun] = useState<ExecutionRun | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchRun();
        const interval = setInterval(() => {
            if (run?.status === RunStatus.RUNNING || run?.status === RunStatus.PENDING) {
                fetchRun();
            }
        }, 3000);
        return () => clearInterval(interval);
    }, [id, run?.status]);

    const fetchRun = async () => {
        try {
            const { data } = await apiClient.get<ExecutionRun>(`/ai/executions/${id}`);
            setRun(data);
        } catch (error) {
            console.error('Failed to fetch execution:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) return <div className="loading">Retracing Neuronal Path...</div>;
    if (!run) return <div className="error-message">Execution not found.</div>;

    return (
        <div className="execution-detail-page">
            <div className="detail-header">
                <JellyButton variant="ghost" onClick={() => navigate('/executions')}>
                    <ArrowLeft size={18} />
                    History
                </JellyButton>
                <div className="header-title">
                    <h1>Trace: {run.entity?.name}</h1>
                    <span className={`status-pill ${run.status.toLowerCase()}`}>{run.status}</span>
                </div>
            </div>

            <div className="detail-grid">
                <div className="trace-section">
                    <GlassCard>
                        <h2>Hierarchical Trace</h2>
                        <div className="trace-container">
                            <TraceNode run={run} depth={0} />
                        </div>
                    </GlassCard>
                </div>

                <div className="stats-section">
                    <GlassCard>
                        <h2>Run Context</h2>
                        <div className="stats-list">
                            <div className="stat-item">
                                <label>Started</label>
                                <span>{new Date(run.created_at).toLocaleString()}</span>
                            </div>
                            <div className="stat-item">
                                <label>Input</label>
                                <pre className="mini-pre">{JSON.stringify(run.input_data, null, 2)}</pre>
                            </div>
                            {run.result_data && (
                                <div className="stat-item">
                                    <label>Final Output</label>
                                    <pre className="mini-pre">{JSON.stringify(run.result_data, null, 2)}</pre>
                                </div>
                            )}
                        </div>
                    </GlassCard>
                </div>
            </div>
        </div>
    );
};
