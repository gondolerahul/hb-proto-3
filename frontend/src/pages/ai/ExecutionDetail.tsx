import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { GlassCard, JellyButton } from '@/components/ui';
import { ArrowLeft, Copy, CheckCircle, XCircle, Clock } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { Execution } from '@/types';
import './ExecutionDetail.css';

export const ExecutionDetail: React.FC = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [execution, setExecution] = useState<Execution | null>(null);
    const [loading, setLoading] = useState(true);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        fetchExecution();
    }, [id]);

    const fetchExecution = async () => {
        try {
            const { data } = await apiClient.get(`/ai/executions/${id}`);
            setExecution(data);
        } catch (error) {
            console.error('Failed to fetch execution:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleCopy = () => {
        if (execution?.output) {
            navigator.clipboard.writeText(execution.output);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
    };

    const getDuration = () => {
        if (!execution?.created_at || !execution?.completed_at) return 'N/A';
        const start = new Date(execution.created_at).getTime();
        const end = new Date(execution.completed_at).getTime();
        return `${((end - start) / 1000).toFixed(2)}s`;
    };

    const getStatusIcon = () => {
        switch (execution?.status) {
            case 'completed':
                return <CheckCircle size={32} color="var(--color-success)" />;
            case 'failed':
                return <XCircle size={32} color="var(--color-error)" />;
            default:
                return <Clock size={32} color="var(--color-warning)" />;
        }
    };

    if (loading) {
        return <div className="loading">Loading execution details...</div>;
    }

    if (!execution) {
        return (
            <div className="execution-detail">
                <div className="error-message">Execution not found</div>
            </div>
        );
    }

    return (
        <div className="execution-detail">
            <div className="detail-header">
                <JellyButton variant="ghost" onClick={() => navigate('/executions')}>
                    <ArrowLeft size={20} />
                    Back to History
                </JellyButton>
            </div>

            <GlassCard className="execution-info-card">
                <div className="info-header">
                    <div className="status-icon">{getStatusIcon()}</div>
                    <div className="info-title">
                        <h1>Execution Details</h1>
                        <span className={`status-badge ${execution.status}`}>
                            {execution.status}
                        </span>
                    </div>
                </div>

                <div className="info-grid">
                    <div className="info-item">
                        <label>Type</label>
                        <span>{execution.agent_id ? 'Agent' : 'Workflow'}</span>
                    </div>
                    <div className="info-item">
                        <label>Started</label>
                        <span>{formatDate(execution.created_at)}</span>
                    </div>
                    {execution.completed_at && (
                        <div className="info-item">
                            <label>Completed</label>
                            <span>{formatDate(execution.completed_at)}</span>
                        </div>
                    )}
                    <div className="info-item">
                        <label>Duration</label>
                        <span>{getDuration()}</span>
                    </div>
                </div>
            </GlassCard>

            {execution.input && Object.keys(execution.input).length > 0 && (
                <GlassCard className="execution-section">
                    <h2>Input</h2>
                    <pre className="code-block">
                        {JSON.stringify(execution.input, null, 2)}
                    </pre>
                </GlassCard>
            )}

            {execution.output && (
                <GlassCard className="execution-section">
                    <div className="section-header">
                        <h2>Output</h2>
                        <JellyButton variant="secondary" onClick={handleCopy}>
                            {copied ? <CheckCircle size={16} /> : <Copy size={16} />}
                            {copied ? 'Copied!' : 'Copy'}
                        </JellyButton>
                    </div>
                    <pre className="code-block output-block">{execution.output}</pre>
                </GlassCard>
            )}

            {execution.error && (
                <GlassCard className="execution-section">
                    <h2>Error</h2>
                    <div className="error-block">
                        <pre>{execution.error}</pre>
                    </div>
                </GlassCard>
            )}
        </div>
    );
};
