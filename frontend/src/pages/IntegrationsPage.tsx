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
        <div className="integrations-page p-8">
            <header className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-white mb-2">Service Integrations</h1>
                    <p className="text-gray-400">Manage your AI provider keys and SKU-based costing mappings.</p>
                </div>
                <div className="flex gap-4">
                    <button
                        onClick={openCreateModal}
                        className="flex items-center gap-2 px-4 py-2 bg-rose-500 text-white rounded-lg font-semibold hover:bg-rose-600 transition-all"
                    >
                        <Plus size={18} />
                        Add Integration
                    </button>
                    <button
                        onClick={fetchData}
                        className="p-2 rounded-full hover:bg-white/10 transition-colors"
                    >
                        <RefreshCw className="text-rose-300" size={20} />
                    </button>
                </div>
            </header>

            {error && (
                <div className="bg-red-500/20 border border-red-500/50 p-4 rounded-lg text-red-200 flex items-center gap-2 mb-6">
                    <AlertTriangle size={20} />
                    {error}
                </div>
            )}

            <div className="grid grid-cols-1 gap-6">
                <div className="integrations-list glass overflow-hidden">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-white/5">
                                <th className="p-4 border-b border-white/10 text-white">Provider</th>
                                <th className="p-4 border-b border-white/10 text-white">SKU / Model</th>
                                <th className="p-4 border-b border-white/10 text-white">Type</th>
                                <th className="p-4 border-b border-white/10 text-white">Internal Cost</th>
                                <th className="p-4 border-b border-white/10 text-white">Status</th>
                                <th className="p-4 border-b border-white/10 text-white">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {integrations.map((item) => (
                                <tr key={item.id} className="hover:bg-white/5 transition-colors">
                                    <td className="p-4 border-b border-white/5">
                                        <div className="flex items-center gap-3">
                                            <div className="w-8 h-8 rounded bg-blue-500/20 flex items-center justify-center text-blue-400">
                                                <Cpu size={16} />
                                            </div>
                                            <span className="font-medium text-white">{item.provider_name}</span>
                                        </div>
                                    </td>
                                    <td className="p-4 border-b border-white/5 text-gray-300">
                                        <div className="flex flex-col">
                                            <span className="text-rose-400 text-sm font-mono">{item.service_sku}</span>
                                            <span className="text-xs">{item.model_name || 'N/A'}</span>
                                        </div>
                                    </td>
                                    <td className="p-4 border-b border-white/5">
                                        <span className="px-2 py-1 bg-white/10 rounded text-xs text-gray-400 uppercase tracking-wider">
                                            {item.component_type.replace('_', ' ')}
                                        </span>
                                    </td>
                                    <td className="p-4 border-b border-white/5 text-green-400 font-mono">
                                        ${Number(item.internal_cost).toFixed(6)} / {item.cost_unit}
                                    </td>
                                    <td className="p-4 border-b border-white/5">
                                        <div className="flex items-center gap-1.5 text-green-500 text-sm">
                                            <CheckCircle2 size={14} />
                                            {item.status.toUpperCase()}
                                        </div>
                                    </td>
                                    <td className="p-4 border-b border-white/5">
                                        <div className="flex items-center gap-2">
                                            <button
                                                onClick={() => openEditModal(item)}
                                                className="p-2 hover:bg-white/10 rounded-lg text-gray-400 hover:text-white transition-all"
                                            >
                                                <Settings size={18} />
                                            </button>
                                            <button
                                                onClick={() => handleDelete(item.id)}
                                                className="p-2 hover:bg-red-500/20 rounded-lg text-gray-400 hover:text-red-500 transition-all"
                                            >
                                                <Trash2 size={18} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                            {integrations.length === 0 && !loading && (
                                <tr>
                                    <td colSpan={6} className="p-8 text-center text-gray-500">
                                        No integrations found. Add your first AI provider key.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
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
