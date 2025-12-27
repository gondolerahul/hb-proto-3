import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { GlassCard, JellyButton } from '@/components/ui';
import { ArrowLeft, ChevronDown, ChevronRight, Zap, Cpu, MessageSquare, Wrench, Clock, DollarSign, Database, Brain, Layers } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { ExecutionRun, RunStatus, EntityType, LLMInteractionLog, ToolInteractionLog } from '@/types';
import './ExecutionDetail.css';

const TraceNode: React.FC<{ run: ExecutionRun; depth: number }> = ({ run, depth }) => {
    const [expanded, setExpanded] = useState(depth < 2);
    const [showLLMLogs, setShowLLMLogs] = useState(false);
    const [showToolLogs, setShowToolLogs] = useState(false);

    const hasChildren = run.child_runs && run.child_runs.length > 0;
    const hasLLMLogs = run.llm_logs && run.llm_logs.length > 0;
    const hasToolLogs = run.tool_logs && run.tool_logs.length > 0;

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
                    <div className="stat-group">
                        {run.total_cost_usd > 0 && (
                            <span className="stat-item mini" title="Cost">
                                <DollarSign size={10} /> ${run.total_cost_usd.toFixed(4)}
                            </span>
                        )}
                        {run.total_tokens > 0 && (
                            <span className="stat-item mini" title="Tokens">
                                <Database size={10} /> {run.total_tokens.toLocaleString()}
                            </span>
                        )}
                    </div>
                    <span className="node-status" style={{ color: getStatusColor(run.status) }}>
                        {run.status}
                    </span>
                    {run.execution_time_ms ? (
                        <span className="node-duration">{(run.execution_time_ms / 1000).toFixed(2)}s</span>
                    ) : run.completed_at && run.started_at && (
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
                            <div className="thought-header"><MessageSquare size={12} /> AI Workspace / Reasoning</div>
                            <div className="thought-content">{run.context_state.reasoning}</div>
                        </div>
                    )}

                    {/* LLM Logs */}
                    {hasLLMLogs && (
                        <div className="node-logs">
                            <button className="text-btn" onClick={() => setShowLLMLogs(!showLLMLogs)}>
                                {showLLMLogs ? 'Hide' : 'Show'} LLM Interactions ({run.llm_logs?.length})
                            </button>
                            {showLLMLogs && run.llm_logs?.map((log: LLMInteractionLog) => (
                                <div key={log.id} className="log-entry">
                                    <div className="log-meta">
                                        <div className="stat-group">
                                            <span>{log.model_name} ({log.model_provider})</span>
                                            {log.reasoning_mode && <span className="badge">{log.reasoning_mode}</span>}
                                        </div>
                                        <div className="stat-group">
                                            <span>{log.prompt_tokens + log.completion_tokens} tokens</span>
                                            <span>${log.cost_usd.toFixed(4)}</span>
                                            <span>{log.latency_ms}ms</span>
                                        </div>
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

                    {/* Tool Logs */}
                    {hasToolLogs && (
                        <div className="node-tools">
                            <button className="text-btn" onClick={() => setShowToolLogs(!showToolLogs)}>
                                {showToolLogs ? 'Hide' : 'Show'} Tool Interactions ({run.tool_logs?.length})
                            </button>
                            {showToolLogs && run.tool_logs?.map((log: ToolInteractionLog) => (
                                <div key={log.id} className="tool-entry">
                                    <div className="tool-meta">
                                        <span><Wrench size={10} /> {log.tool_name}</span>
                                        <span>{log.latency_ms}ms</span>
                                        <span style={{ color: log.success ? 'var(--color-success)' : 'var(--color-error)' }}>
                                            {log.success ? 'SUCCESS' : 'FAILED'}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Result */}
                    {run.result_data && (
                        <div className="node-result">
                            <label>Structured Output</label>
                            <pre>{JSON.stringify(run.result_data, null, 2)}</pre>
                        </div>
                    )}

                    {/* Error */}
                    {run.error_message && (
                        <div className="node-error">
                            <label>Execution Error</label>
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

    if (loading) return (
        <div className="loading-container">
            <Brain size={48} className="pulse" color="var(--color-secondary)" />
            <div className="loading-text">Retracing Neuronal Path...</div>
        </div>
    );
    if (!run) return <div className="error-message">Execution not found.</div>;

    return (
        <div className="execution-detail-page">
            <div className="detail-header">
                <JellyButton variant="ghost" onClick={() => navigate('/ai/executions')}>
                    <ArrowLeft size={18} />
                    History
                </JellyButton>
                <div className="header-title">
                    <h1>Trace Archive</h1>
                    <p>{run.entity?.name} • ID: {run.id.slice(0, 8)}</p>
                </div>
                <div className={`status-pill ${run.status.toLowerCase()}`}>{run.status}</div>
            </div>

            <div className="detail-grid">
                <div className="trace-section">
                    <GlassCard>
                        <div className="card-header-with-icon">
                            <Layers size={18} />
                            <h2>Hierarchical Invocation Tree</h2>
                        </div>
                        <div className="trace-container">
                            <TraceNode run={run} depth={0} />
                        </div>
                    </GlassCard>
                </div>

                <div className="stats-section">
                    <GlassCard className="execution-summary-card">
                        <h2>Operational Context</h2>
                        <div className="stats-list">
                            <div className="stat-item">
                                <label><Clock size={12} /> Timeline</label>
                                <span>{new Date(run.created_at).toLocaleString()}</span>
                            </div>
                            <div className="stat-item">
                                <label><DollarSign size={12} /> Total Accrued Cost</label>
                                <span className="highlight-texted">${run.total_cost_usd.toFixed(4)}</span>
                            </div>
                            <div className="stat-item">
                                <label><Database size={12} /> Token Consumption</label>
                                <span>{run.total_tokens.toLocaleString()} tokens</span>
                            </div>
                            <div className="stat-item">
                                <label>Input Parameters</label>
                                <pre className="mini-pre">{JSON.stringify(run.input_data, null, 2)}</pre>
                            </div>
                        </div>
                    </GlassCard>
                </div>
            </div>
        </div>
    );
};
