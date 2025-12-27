import React, { useState, useEffect } from 'react';
import { GlassCard, JellyButton } from '@/components/ui';
import { CheckCircle, XCircle, Clock, Shield, AlertTriangle } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { HumanApproval } from '@/types';
import './HITLPanel.css';

export const HITLPanel: React.FC = () => {
    const [approvals, setApprovals] = useState<HumanApproval[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchPendingApprovals();
        const interval = setInterval(fetchPendingApprovals, 10000);
        return () => clearInterval(interval);
    }, []);

    const fetchPendingApprovals = async () => {
        try {
            const { data } = await apiClient.get<HumanApproval[]>('/ai/approvals/pending');
            setApprovals(data);
        } catch (error) {
            console.error('Failed to fetch approvals:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleRespond = async (approvalId: string, status: 'APPROVED' | 'REJECTED') => {
        try {
            await apiClient.post(`/ai/approvals/${approvalId}/respond`, {
                status,
                notes: `Responded via HITL Dashboard`
            });
            setApprovals(prev => prev.filter(a => a.id !== approvalId));
        } catch (error) {
            console.error('Failed to respond to approval:', error);
        }
    };

    if (loading) return <div className="loading">Authorized Personnel Required...</div>;

    return (
        <div className="hitl-panel">
            <div className="panel-header">
                <div className="title-area">
                    <Shield size={24} color="var(--color-secondary)" />
                    <h1>Guardian Oversight</h1>
                    <p>Human-in-the-Loop Decision Center</p>
                </div>
                <div className="approval-count">
                    {approvals.length} Pending
                </div>
            </div>

            <div className="approvals-list">
                {approvals.length === 0 ? (
                    <GlassCard className="empty-hitl">
                        <CheckCircle size={48} color="var(--color-success)" />
                        <h3>All Systems Nominal</h3>
                        <p>No pending human intervention requests at this time.</p>
                    </GlassCard>
                ) : (
                    approvals.map(approval => (
                        <GlassCard key={approval.id} className="approval-card">
                            <div className="approval-info">
                                <div className="trigger-source">
                                    <AlertTriangle size={16} />
                                    <span>Checkpoint: {approval.checkpoint_trigger}</span>
                                </div>
                                <div className="run-reference">
                                    Execution: {approval.run_id.slice(0, 8)}
                                </div>
                                <div className="timestamp">
                                    <Clock size={14} />
                                    {new Date(approval.requested_at).toLocaleString()}
                                </div>
                            </div>

                            <div className="approval-actions">
                                <JellyButton
                                    className="approve-btn"
                                    onClick={() => handleRespond(approval.id, 'APPROVED')}
                                >
                                    <CheckCircle size={18} />
                                    Authorize
                                </JellyButton>
                                <JellyButton
                                    variant="ghost"
                                    className="reject-btn"
                                    onClick={() => handleRespond(approval.id, 'REJECTED')}
                                >
                                    <XCircle size={18} />
                                    Reject
                                </JellyButton>
                            </div>
                        </GlassCard>
                    ))
                )}
            </div>
        </div>
    );
};
