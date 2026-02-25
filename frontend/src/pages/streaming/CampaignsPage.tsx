import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { GlassCard, JellyButton } from '@/components/ui';
import { Plus, Play, Pause, Square, Info, RefreshCw, PhoneForwarded, X } from 'lucide-react';
import { CampaignCreateModal } from './CampaignCreateModal';
import './CampaignsPage.css';

interface Campaign {
    id: string;
    name: string;
    description: string;
    status: string;
    total_contacts: number;
    calls_initiated: number;
    calls_completed: number;
    calls_failed: number;
    created_at: string;
}

export const CampaignsPage: React.FC = () => {
    const { token } = useAuth();
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedCampaign, setSelectedCampaign] = useState<any>(null);
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [actionLoading, setActionLoading] = useState<string | null>(null);

    const campaignsRef = useRef<Campaign[]>([]);

    useEffect(() => {
        fetchCampaigns();
    }, []);

    // Update ref whenever campaigns change
    useEffect(() => {
        campaignsRef.current = campaigns;
    }, [campaigns]);

    // Set up polling interval only once
    useEffect(() => {
        const interval = setInterval(() => {
            const hasRunning = campaignsRef.current.some(c => c.status === 'running');
            if (hasRunning) {
                fetchCampaigns(false);
            }
        }, 5000);

        return () => clearInterval(interval);
    }, []); // Empty dependency array - only set up once

    const fetchCampaigns = async (showLoading = true) => {
        if (showLoading) setLoading(true);
        try {
            const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/campaigns`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await response.json();
            setCampaigns(data.campaigns || []);
        } catch (error) {
            console.error('Error fetching campaigns:', error);
        } finally {
            if (showLoading) setLoading(false);
        }
    };

    const viewCampaignDetails = async (campaignId: string) => {
        try {
            const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/campaigns/${campaignId}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await response.json();
            setSelectedCampaign(data);
        } catch (error) {
            console.error('Error fetching campaign details:', error);
        }
    };

    const updateStatus = async (campaignId: string, status: string) => {
        setActionLoading(campaignId);
        try {
            const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/campaigns/${campaignId}/status?status=${status}`, {
                method: 'PATCH',
                headers: { 'Authorization': `Bearer ${token}` }
            });

            if (!response.ok) throw new Error('Failed to update status');

            await fetchCampaigns(false);
        } catch (error) {
            console.error('Error updating campaign status:', error);
            alert('Failed to update campaign status');
        } finally {
            setActionLoading(null);
        }
    };

    const getStatusColor = (status: string) => {
        const colors: Record<string, string> = {
            'draft': 'gray',
            'scheduled': 'blue',
            'running': 'green',
            'paused': 'yellow',
            'completed': 'purple',
            'failed': 'red',
            'stopped': 'red'
        };
        return colors[status] || 'gray';
    };

    const calculateProgress = (campaign: Campaign) => {
        if (campaign.total_contacts === 0) return 0;
        return Math.round((campaign.calls_completed / campaign.total_contacts) * 100);
    };

    if (loading) {
        return (
            <div className="loading-container">
                <RefreshCw size={48} className="pulse" color="var(--color-rose-gold)" />
                <div className="loading">Syncing voice campaigns...</div>
            </div>
        );
    }

    return (
        <div className="campaigns-page">
            <div className="page-header">
                <div>
                    <h1>Voice Campaigns</h1>
                    <p className="subtitle">Orchestrate and monitor high-volume outbound AI calling</p>
                </div>
                <div className="header-actions">
                    <JellyButton roseGold onClick={() => setIsCreateModalOpen(true)}>
                        <Plus size={20} />
                        Launch Campaign
                    </JellyButton>
                </div>
            </div>

            <GlassCard>
                <div className="campaigns-grid">
                    {campaigns.length === 0 ? (
                        <div className="empty-state">
                            <PhoneForwarded size={64} color="var(--text-tertiary)" style={{ marginBottom: '1.5rem' }} />
                            <h3>No Active Pipelines</h3>
                            <p>Configure a neural agent and contact list to initiate outreach.</p>
                            <JellyButton
                                variant="secondary"
                                style={{ marginTop: '1.5rem' }}
                                onClick={() => setIsCreateModalOpen(true)}
                            >
                                <Plus size={16} /> Create First Campaign
                            </JellyButton>
                        </div>
                    ) : (
                        <div className="campaign-cards">
                            {campaigns.map(campaign => (
                                <div key={campaign.id} className="campaign-card">
                                    <div className="campaign-header">
                                        <h3>{campaign.name}</h3>
                                        <span className={`status-badge ${getStatusColor(campaign.status)}`}>
                                            {campaign.status}
                                        </span>
                                    </div>

                                    {campaign.description && (
                                        <p className="campaign-description">{campaign.description}</p>
                                    )}

                                    <div className="campaign-stats">
                                        <div className="stat">
                                            <span className="stat-label">Total</span>
                                            <span className="stat-value">{campaign.total_contacts}</span>
                                        </div>
                                        <div className="stat">
                                            <span className="stat-label">Completed</span>
                                            <span className="stat-value success">{campaign.calls_completed}</span>
                                        </div>
                                        <div className="stat">
                                            <span className="stat-label">Pending</span>
                                            <span className="stat-value">{campaign.total_contacts - (campaign.calls_completed + campaign.calls_failed)}</span>
                                        </div>
                                    </div>

                                    <div className="progress-bar">
                                        <div
                                            className={`progress-fill ${campaign.status === 'running' ? 'progress-animated' : ''}`}
                                            style={{ width: `${calculateProgress(campaign)}%` }}
                                        />
                                    </div>
                                    <div className="progress-label-row">
                                        <span className="progress-percent">{calculateProgress(campaign)}%</span>
                                        <span className="progress-detail">{campaign.calls_completed} of {campaign.total_contacts} contacts</span>
                                    </div>

                                    <div className="campaign-actions">
                                        {campaign.status === 'draft' || campaign.status === 'paused' || campaign.status === 'failed' || campaign.status === 'stopped' ? (
                                            <button
                                                className="action-btn start"
                                                onClick={() => updateStatus(campaign.id, 'running')}
                                                disabled={actionLoading === campaign.id}
                                                title="Start Campaign"
                                            >
                                                <Play size={18} fill="currentColor" />
                                            </button>
                                        ) : campaign.status === 'running' ? (
                                            <button
                                                className="action-btn pause"
                                                onClick={() => updateStatus(campaign.id, 'paused')}
                                                disabled={actionLoading === campaign.id}
                                                title="Pause Campaign"
                                            >
                                                <Pause size={18} fill="currentColor" />
                                            </button>
                                        ) : null}

                                        {campaign.status === 'running' || campaign.status === 'paused' ? (
                                            <button
                                                className="action-btn stop"
                                                onClick={() => updateStatus(campaign.id, 'stopped')}
                                                disabled={actionLoading === campaign.id}
                                                title="Hard Stop"
                                            >
                                                <Square size={18} fill="currentColor" />
                                            </button>
                                        ) : null}

                                        <div className="spacer" />

                                        <button
                                            className="btn-view"
                                            onClick={() => viewCampaignDetails(campaign.id)}
                                        >
                                            <Info size={16} /> Details
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </GlassCard>

            <CampaignCreateModal
                isOpen={isCreateModalOpen}
                onClose={() => setIsCreateModalOpen(false)}
                onSuccess={() => fetchCampaigns()}
            />

            {selectedCampaign && (
                <div className="modal-overlay" onClick={() => setSelectedCampaign(null)}>
                    <div className="modal-content campaign-details glass" onClick={e => e.stopPropagation()}>
                        <div className="modal-header">
                            <h2>{selectedCampaign.name}</h2>
                            <button className="close-btn" onClick={() => setSelectedCampaign(null)}><X size={20} /></button>
                        </div>

                        <div className="detail-section">
                            <h3>Campaign Metrics</h3>
                            <div className="detail-grid">
                                <div className="detail-item">
                                    <span className="label">Current Status</span>
                                    <span className={`status-badge ${getStatusColor(selectedCampaign.status)}`}>
                                        {selectedCampaign.status}
                                    </span>
                                </div>
                                <div className="detail-item">
                                    <span className="label">Outreach Engine</span>
                                    <strong>{selectedCampaign.provider === 'tata_tele' ? 'Tata Tele' : 'Twilio'}</strong>
                                </div>
                                <div className="detail-item">
                                    <span className="label">Total Contacts</span>
                                    <strong>{selectedCampaign.total_contacts}</strong>
                                </div>
                                <div className="detail-item">
                                    <span className="label">Initiated</span>
                                    <strong>{selectedCampaign.calls_initiated}</strong>
                                </div>
                                <div className="detail-item">
                                    <span className="label">Success</span>
                                    <strong className="success">{selectedCampaign.calls_completed}</strong>
                                </div>
                                <div className="detail-item">
                                    <span className="label">Anomalies</span>
                                    <strong className="danger">{selectedCampaign.calls_failed}</strong>
                                </div>
                            </div>
                        </div>

                        <div className="detail-section">
                            <h3>Configuration</h3>
                            <div className="detail-grid">
                                <div className="detail-item">
                                    <span className="label">Concurrency</span>
                                    <strong>{selectedCampaign.max_concurrent_calls || 5} streams</strong>
                                </div>
                                <div className="detail-item">
                                    <span className="label">Target Zone</span>
                                    <strong>{selectedCampaign.provider === 'tata_tele' ? 'India' : 'International'}</strong>
                                </div>
                                {selectedCampaign.scheduled_start && (
                                    <div className="detail-item">
                                        <span className="label">Scheduled Window</span>
                                        <strong>{new Date(selectedCampaign.scheduled_start).toLocaleString()}</strong>
                                    </div>
                                )}
                            </div>
                        </div>

                        {selectedCampaign.description && (
                            <div className="detail-section">
                                <h3>Operational Objective</h3>
                                <p className="description-text">{selectedCampaign.description}</p>
                            </div>
                        )}

                        <div className="modal-footer">
                            <JellyButton variant="primary" onClick={() => setSelectedCampaign(null)}>
                                Close Monitor
                            </JellyButton>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

