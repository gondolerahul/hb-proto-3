import { parseServerDate } from '@/utils/datetime';
import React, { useState, useEffect } from 'react';
import { GlassCard, JellyButton } from '@/components/ui';
import { CheckCircle, XCircle, Clock, Shield } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { StepUpModal } from '@/components/StepUpModal';
import { useCertifiedAction } from '@/hooks/useCertifiedAction';
import { HumanApproval } from '@/types';
import './HITLPanel.css';

export const HITLPanel: React.FC = () => {
    const [approvals, setApprovals] = useState<HumanApproval[]>([]);
    const [loading, setLoading] = useState(true);
    // Responding to a categorised approval is a certified act (VG-05): the same
    // ceremony Pragya asks for when the request arrives as conversation.
    const stepUp = useCertifiedAction();

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
            await stepUp.run(async () => {
                await apiClient.post(`/ai/approvals/${approvalId}/respond`, {
                    status,
                    notes: `Responded via HITL Dashboard`
                });
                setApprovals(prev => prev.filter(a => a.id !== approvalId));
            });
        } catch (error) {
            console.error('Failed to respond to approval:', error);
        }
    };

    /** C3: time left against the per-category SLA — "3h 12m left" / "overdue". */
    const slaState = (approval: HumanApproval): { label: string; overdue: boolean } | null => {
        if (!approval.sla_seconds) return null;
        const deadline = parseServerDate(approval.requested_at).getTime() + approval.sla_seconds * 1000;
        const remainingMs = deadline - Date.now();
        if (remainingMs <= 0) {
            return { label: `overdue → ${approval.on_timeout || 'escalate'}`, overdue: true };
        }
        const h = Math.floor(remainingMs / 3600000);
        const m = Math.floor((remainingMs % 3600000) / 60000);
        return { label: h > 0 ? `${h}h ${m}m left` : `${m}m left`, overdue: false };
    };

    if (loading) return <div className="loading">Authorized Personnel Required...</div>;

    return (
        <div className="page-container hitl-panel">
            <header className="page-header">
                <div>
                    <h1>Guardian Oversight</h1>
                    <p>Decision center for Human-in-the-Loop interventions</p>
                </div>
                <div className="badge badge-purple px-6 py-2 text-sm font-bold tracking-widest">
                    {approvals.length} PENDING BLOCKS
                </div>
            </header>

            {stepUp.error && (
                <div className="alert alert-error">{stepUp.error}</div>
            )}

            <div className="standard-grid">
                {approvals.length === 0 ? (
                    <GlassCard className="col-span-full py-20 opacity-30 flex flex-col items-center">
                        <CheckCircle size={64} className="mb-4 text-green-400" />
                        <p>All neural systems are operating within nominal autonomous boundaries.</p>
                    </GlassCard>
                ) : (
                    approvals.map(approval => (
                        <GlassCard key={approval.id} className="flex flex-col h-full" hover>
                            <div className="p-6 flex-1">
                                <div className="flex items-start gap-4 mb-6">
                                    <div className="bg-red-500/10 p-3 rounded-lg text-red-400">
                                        <Shield size={24} />
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <h3 className="mb-1 truncate text-lg">
                                            {approval.context_snapshot?.category
                                                ? `${approval.context_snapshot.category} approval`
                                                : 'Checkpoint Required'}
                                        </h3>
                                        <div className="text-xs text-tertiary font-mono truncate">
                                            {approval.checkpoint_key || approval.checkpoint_trigger}
                                        </div>
                                    </div>
                                </div>

                                {approval.context_snapshot?.reason && (
                                    <div className="hitl-reason">
                                        {approval.context_snapshot.reason}
                                        {approval.context_snapshot.band && (
                                            <span className="hitl-band">band: {approval.context_snapshot.band}</span>
                                        )}
                                    </div>
                                )}

                                <div className="space-y-4 mb-8">
                                    <div className="flex items-center justify-between text-xs text-tertiary">
                                        <span>EXECUTION REF</span>
                                        <span className="text-secondary font-mono bg-white/5 px-2 py-1 rounded">{approval.run_id.slice(0, 12)}</span>
                                    </div>
                                    <div className="flex items-center justify-between text-xs text-tertiary">
                                        <span>REQUESTED AT</span>
                                        <div className="flex items-center gap-1.5 text-secondary">
                                            <Clock size={12} />
                                            {parseServerDate(approval.requested_at).toLocaleTimeString()}
                                        </div>
                                    </div>
                                    {(() => {
                                        const sla = slaState(approval);
                                        return sla ? (
                                            <div className="flex items-center justify-between text-xs text-tertiary">
                                                <span>SLA</span>
                                                <span className={sla.overdue ? 'hitl-sla-overdue' : 'text-secondary'}>
                                                    {sla.label}
                                                </span>
                                            </div>
                                        ) : null;
                                    })()}
                                </div>
                            </div>

                            <div className="p-4 pt-0 border-t border-white/5 mt-auto grid grid-cols-2 gap-3">
                                <JellyButton
                                    roseGold
                                    onClick={() => handleRespond(approval.id, 'APPROVED')}
                                    className="w-full"
                                >
                                    <CheckCircle size={16} /> Authorize
                                </JellyButton>
                                <JellyButton
                                    variant="ghost"
                                    onClick={() => handleRespond(approval.id, 'REJECTED')}
                                    className="w-full text-red-500 hover:text-red-400"
                                >
                                    <XCircle size={16} /> Block Cycle
                                </JellyButton>
                            </div>
                        </GlassCard>
                    ))
                )}
            </div>

            <StepUpModal {...stepUp.modalProps} />
        </div>
    );
};
