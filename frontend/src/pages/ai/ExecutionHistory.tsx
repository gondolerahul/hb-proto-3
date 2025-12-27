import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { GlassCard, JellyButton } from '@/components/ui';
import { Clock, CheckCircle, XCircle, Loader, Eye, RotateCcw } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { ExecutionRun, RunStatus } from '@/types';
import './ExecutionHistory.css';

export const ExecutionHistory: React.FC = () => {
    const [executions, setExecutions] = useState<ExecutionRun[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState<RunStatus | 'ALL'>('ALL');

    useEffect(() => {
        fetchExecutions();
    }, []);

    const fetchExecutions = async () => {
        try {
            const { data } = await apiClient.get('/ai/executions');
            setExecutions(data);
        } catch (error) {
            console.error('Failed to fetch executions:', error);
        } finally {
            setLoading(false);
        }
    };

    const getStatusIcon = (status: RunStatus) => {
        switch (status) {
            case RunStatus.COMPLETED:
                return <CheckCircle size={20} color="var(--color-success)" />;
            case RunStatus.FAILED:
                return <XCircle size={20} color="var(--color-error)" />;
            case RunStatus.RUNNING:
                return <Loader className="spin" size={20} color="var(--color-info)" />;
            default:
                return <Clock size={20} color="var(--color-warning)" />;
        }
    };

    const formatDate = (dateString: string) => {
        const date = new Date(dateString);
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    };

    const filteredExecutions = executions.filter(exec => {
        if (filter === 'ALL') return true;
        return exec.status === filter;
    });

    if (loading) {
        return <div className="loading">Consulting Historical Records...</div>;
    }

    return (
        <div className="execution-history">
            <div className="page-header">
                <div>
                    <h1>Execution Records</h1>
                    <p>Audit trail of all hierarchical intelligence units</p>
                </div>
            </div>

            <div className="filter-bar">
                {(['ALL', ...Object.values(RunStatus)] as const).map(s => (
                    <button
                        key={s}
                        className={`filter-btn ${filter === s ? 'active' : ''}`}
                        onClick={() => setFilter(s)}
                    >
                        {s} ({s === 'ALL' ? executions.length : executions.filter(e => e.status === s).length})
                    </button>
                ))}
            </div>

            <div className="executions-list">
                {filteredExecutions.length === 0 ? (
                    <GlassCard className="empty-state">
                        <Clock size={64} color="var(--color-text-tertiary)" />
                        <h3>Quiet in the archives</h3>
                        <p>
                            {filter === 'ALL'
                                ? 'Deploy a unit to see its trail here'
                                : `No executions found with status: ${filter}`}
                        </p>
                    </GlassCard>
                ) : (
                    filteredExecutions.map((execution) => (
                        <GlassCard key={execution.id} hover className="execution-card">
                            <div className="execution-status-icon">
                                {getStatusIcon(execution.status)}
                            </div>

                            <div className="execution-info">
                                <div className="execution-header">
                                    <h3>
                                        {execution.entity?.name || 'Anonymous Unit'}
                                    </h3>
                                    <span className={`status-badge ${execution.status.toLowerCase()}`}>
                                        {execution.status}
                                    </span>
                                </div>

                                <div className="execution-meta">
                                    <span className="execution-time">
                                        {formatDate(execution.created_at)}
                                    </span>
                                    {execution.completed_at && execution.started_at && (
                                        <>
                                            <span>•</span>
                                            <span className="execution-duration">
                                                Duration: {((new Date(execution.completed_at).getTime() -
                                                    new Date(execution.started_at).getTime()) / 1000).toFixed(1)}s
                                            </span>
                                        </>
                                    )}
                                </div>

                                {execution.error_message && (
                                    <div className="execution-error">
                                        <strong>Error:</strong> {execution.error_message}
                                    </div>
                                )}
                            </div>

                            <div className="execution-actions">
                                <Link to={`/executions/${execution.id}`}>
                                    <JellyButton variant="secondary">
                                        <Eye size={16} />
                                        Trace
                                    </JellyButton>
                                </Link>
                                <Link to={`/ai/execute/${execution.entity_id}`}>
                                    <JellyButton variant="ghost">
                                        <RotateCcw size={16} />
                                        Re-run
                                    </JellyButton>
                                </Link>
                            </div>
                        </GlassCard>
                    ))
                )}
            </div>
        </div>
    );
};
