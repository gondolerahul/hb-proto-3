import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { GlassCard, JellyButton } from '@/components/ui';
import { Clock, CheckCircle, XCircle, Loader, Eye, RotateCcw } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { Execution } from '@/types';
import './ExecutionHistory.css';

export const ExecutionHistory: React.FC = () => {
    const [executions, setExecutions] = useState<Execution[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState<'all' | 'completed' | 'failed' | 'running'>('all');

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

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'completed':
                return <CheckCircle size={20} color="var(--color-success)" />;
            case 'failed':
                return <XCircle size={20} color="var(--color-error)" />;
            case 'running':
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
        if (filter === 'all') return true;
        return exec.status === filter;
    });

    if (loading) {
        return <div className="loading">Loading execution history...</div>;
    }

    return (
        <div className="execution-history">
            <div className="page-header">
                <div>
                    <h1>Execution History</h1>
                    <p>View past agent and workflow executions</p>
                </div>
            </div>

            <div className="filter-bar">
                <button
                    className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
                    onClick={() => setFilter('all')}
                >
                    All ({executions.length})
                </button>
                <button
                    className={`filter-btn ${filter === 'completed' ? 'active' : ''}`}
                    onClick={() => setFilter('completed')}
                >
                    Completed ({executions.filter(e => e.status === 'completed').length})
                </button>
                <button
                    className={`filter-btn ${filter === 'running' ? 'active' : ''}`}
                    onClick={() => setFilter('running')}
                >
                    Running ({executions.filter(e => e.status === 'running').length})
                </button>
                <button
                    className={`filter-btn ${filter === 'failed' ? 'active' : ''}`}
                    onClick={() => setFilter('failed')}
                >
                    Failed ({executions.filter(e => e.status === 'failed').length})
                </button>
            </div>

            <div className="executions-list">
                {filteredExecutions.length === 0 ? (
                    <GlassCard className="empty-state">
                        <Clock size={64} color="var(--color-text-tertiary)" />
                        <h3>No executions found</h3>
                        <p>
                            {filter === 'all'
                                ? 'Execute an agent or workflow to see it here'
                                : `No ${filter} executions`}
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
                                        {execution.agent_id ? 'Agent' : 'Workflow'} Execution
                                    </h3>
                                    <span className={`status-badge ${execution.status}`}>
                                        {execution.status}
                                    </span>
                                </div>

                                <div className="execution-meta">
                                    <span className="execution-time">
                                        {formatDate(execution.created_at)}
                                    </span>
                                    {execution.completed_at && (
                                        <>
                                            <span>•</span>
                                            <span className="execution-duration">
                                                Duration: {Math.round(
                                                    (new Date(execution.completed_at).getTime() -
                                                        new Date(execution.created_at).getTime()) / 1000
                                                )}s
                                            </span>
                                        </>
                                    )}
                                </div>

                                {execution.error && (
                                    <div className="execution-error">
                                        <strong>Error:</strong> {execution.error}
                                    </div>
                                )}
                            </div>

                            <div className="execution-actions">
                                {execution.output && (
                                    <Link to={`/executions/${execution.id}`}>
                                        <JellyButton variant="secondary">
                                            <Eye size={16} />
                                            View
                                        </JellyButton>
                                    </Link>
                                )}
                                {execution.status === 'completed' && execution.agent_id && (
                                    <Link to={`/execute/agent/${execution.agent_id}`}>
                                        <JellyButton variant="ghost">
                                            <RotateCcw size={16} />
                                            Re-run
                                        </JellyButton>
                                    </Link>
                                )}
                            </div>
                        </GlassCard>
                    ))
                )}
            </div>
        </div>
    );
};
