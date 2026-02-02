import React, { useState, useEffect } from 'react';
import {
    Settings,
    Plus,
    Trash2,
    CheckCircle2,
    Cpu,
    RefreshCw,
    AlertTriangle
} from 'lucide-react';
import { integrationService, Integration } from '../services/integration.service';
import { authService } from '../services/auth.service';
import { User } from '../types';
import { CreateIntegrationModal } from '../components/CreateIntegrationModal';
import { JellyButton, GlassCard } from '@/components/ui';
import './IntegrationsPage.css';

export const IntegrationsPage: React.FC = () => {
    const [integrations, setIntegrations] = useState<Integration[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [currentUser, setCurrentUser] = useState<User | null>(null);
    const [editingIntegration, setEditingIntegration] = useState<Integration | null>(null);

    const fetchData = async () => {
        try {
            setLoading(true);
            const data = await integrationService.getIntegrations();
            setIntegrations(data);
            setError(null);
        } catch (err) {
            setError('Failed to load integrations');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const fetchUser = async () => {
        try {
            const user = await authService.getCurrentUser();
            setCurrentUser(user);
        } catch (err) {
            console.error('Failed to fetch user', err);
        }
    };

    useEffect(() => {
        fetchData();
        fetchUser();
    }, []);

    const handleDelete = async (id: string) => {
        if (!window.confirm('Are you sure you want to delete this integration?')) return;
        try {
            await integrationService.deleteIntegration(id);
            setIntegrations(integrations.filter(i => i.id !== id));
        } catch (err) {
            alert('Failed to delete integration');
        }
    };

    const handleSubmit = async (data: any) => {
        if (editingIntegration) {
            await integrationService.updateIntegration(editingIntegration.id, data);
        } else {
            await integrationService.createIntegration(data);
        }
        fetchData();
    };

    const openEditModal = (integration: Integration) => {
        setEditingIntegration(integration);
        setIsModalOpen(true);
    };

    const openCreateModal = () => {
        setEditingIntegration(null);
        setIsModalOpen(true);
    };

    if (loading && integrations.length === 0) {
        return (
            <div className="p-8 flex justify-center">
                <RefreshCw className="animate-spin text-rose-500" />
            </div>
        );
    }

    return (
        <div className="page-container integrations-page">
            <header className="page-header">
                <div>
                    <h1>Service Integrations</h1>
                    <p>Manage your AI provider keys and SKU-based costing mappings.</p>
                </div>
                <div className="flex gap-4">
                    <JellyButton
                        variant="ghost"
                        onClick={fetchData}
                        className="p-2"
                    >
                        <RefreshCw className="text-rose-300" size={20} />
                    </JellyButton>
                    <JellyButton
                        roseGold
                        onClick={openCreateModal}
                    >
                        <Plus size={18} /> Add Integration
                    </JellyButton>
                </div>
            </header>

            {error && (
                <div className="error-banner mb-6 p-4 flex items-center gap-2">
                    <AlertTriangle size={20} />
                    {error}
                </div>
            )}

            <div className="standard-grid">
                {integrations.map((item) => (
                    <GlassCard key={item.id} className="glass-card-item" hover>
                        <div className="card-header">
                            <div className="card-icon-wrapper card-icon" style={{ color: 'var(--color-rose-gold)' }}>
                                <Cpu size={24} />
                            </div>
                            <div className="card-info">
                                <div className="card-title-row">
                                    <h3 title={item.provider_name}>{item.provider_name}</h3>
                                </div>
                                <div className="card-badge-row">
                                    <span className="type-badge" style={{ background: 'rgba(124, 58, 237, 0.2)', color: '#c4b5fd' }}>
                                        {item.component_type.replace('_', ' ')}
                                    </span>
                                    <span className="status-badge" style={{ color: 'var(--color-success)' }}>
                                        <CheckCircle2 size={10} /> {item.status}
                                    </span>
                                </div>
                            </div>
                        </div>

                        <div className="card-description">
                            Model: {item.model_name || 'Generic'}
                            <br />
                            SKU: <span style={{ fontFamily: 'monospace', fontSize: '0.8em' }}>{item.service_sku}</span>
                        </div>

                        <div className="card-meta">
                            <span className="meta-item">
                                <span style={{ color: 'var(--color-success)', fontWeight: 'bold' }}>${Number(item.internal_cost).toFixed(6)}</span>
                            </span>
                            <span className="meta-item">
                                {item.cost_unit}
                            </span>
                        </div>

                        <div className="card-actions">
                            <JellyButton
                                variant="secondary"
                                size="sm"
                                onClick={() => openEditModal(item)}
                            >
                                <Settings size={14} /> Configure
                            </JellyButton>
                            <JellyButton
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDelete(item.id)}
                                className="text-red-500 hover:text-red-400"
                            >
                                <Trash2 size={14} /> Remove
                            </JellyButton>
                        </div>
                    </GlassCard>
                ))}

                {integrations.length === 0 && !loading && (
                    <GlassCard className="empty-state">
                        <Cpu size={64} className="mb-4" color="var(--color-text-tertiary)" />
                        <h3>No integrations found</h3>
                        <p>Add your first AI provider key to get started.</p>
                    </GlassCard>
                )}
            </div>

            <CreateIntegrationModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                onSubmit={handleSubmit}
                currentUser={currentUser}
                editingIntegration={editingIntegration}
            />
        </div>
    );
};
