import React, { useState, useEffect } from 'react';
import {
    Settings,
    Plus,
    Trash2,
    Save,
    Shield,
    AlertCircle,
    CheckCircle2,
    Cpu
} from 'lucide-react';
import './IntegrationsPage.css';

interface Integration {
    id: string;
    provider_name: string;
    model_name: string | null;
    service_sku: string;
    component_type: string;
    internal_cost: number;
    cost_unit: string;
    status: string;
    created_at: string;
}

export const IntegrationsPage: React.FC = () => {
    const [integrations, setIntegrations] = useState<Integration[]>([]);
    const [loading, setLoading] = useState(true);

    // Mock data for initial UI design
    useEffect(() => {
        setTimeout(() => {
            setIntegrations([
                {
                    id: '1',
                    provider_name: 'OpenAI',
                    model_name: 'gpt-4o',
                    service_sku: 'gpt-4o-in',
                    component_type: 'input_token',
                    internal_cost: 0.000005,
                    cost_unit: 'Token',
                    status: 'active',
                    created_at: new Date().toISOString()
                },
                {
                    id: '2',
                    provider_name: 'OpenAI',
                    model_name: 'gpt-4o',
                    service_sku: 'gpt-4o-out',
                    component_type: 'output_token',
                    internal_cost: 0.000015,
                    cost_unit: 'Token',
                    status: 'active',
                    created_at: new Date().toISOString()
                }
            ]);
            setLoading(false);
        }, 1000);
    }, []);

    if (loading) return <div className="p-8 text-center">Loading integrations...</div>;

    return (
        <div className="integrations-page p-8">
            <header className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-white mb-2">Service Integrations</h1>
                    <p className="text-gray-400">Manage your AI provider keys and SKU-based costing mappings.</p>
                </div>
                <button className="flex items-center gap-2 px-4 py-2 bg-rose-gold text-black rounded-lg font-semibold hover:opacity-90 transition-all">
                    <Plus size={18} />
                    Add Integration
                </button>
            </header>

            <div className="grid grid-cols-1 gap-6">
                <div className="integrations-list glass overflow-hidden">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-white/5">
                                <th className="p-4 border-b border-white/10">Provider</th>
                                <th className="p-4 border-b border-white/10">SKU / Model</th>
                                <th className="p-4 border-b border-white/10">Type</th>
                                <th className="p-4 border-b border-white/10">Internal Cost</th>
                                <th className="p-4 border-b border-white/10">Status</th>
                                <th className="p-4 border-b border-white/10">Actions</th>
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
                                            <span className="font-medium">{item.provider_name}</span>
                                        </div>
                                    </td>
                                    <td className="p-4 border-b border-white/5 text-gray-300">
                                        <div className="flex flex-col">
                                            <span className="text-rose-gold text-sm font-mono">{item.service_sku}</span>
                                            <span className="text-xs">{item.model_name || 'N/A'}</span>
                                        </div>
                                    </td>
                                    <td className="p-4 border-b border-white/5">
                                        <span className="px-2 py-1 bg-white/10 rounded text-xs text-gray-400 uppercase tracking-wider">
                                            {item.component_type.replace('_', ' ')}
                                        </span>
                                    </td>
                                    <td className="p-4 border-b border-white/5 text-green-400 font-mono">
                                        ${item.internal_cost.toFixed(6)} / {item.cost_unit}
                                    </td>
                                    <td className="p-4 border-b border-white/5">
                                        <div className="flex items-center gap-1.5 text-green-500 text-sm">
                                            <CheckCircle2 size={14} />
                                            Active
                                        </div>
                                    </td>
                                    <td className="p-4 border-b border-white/5">
                                        <div className="flex items-center gap-2">
                                            <button className="p-2 hover:bg-white/10 rounded-lg text-gray-400 hover:text-white transition-all">
                                                <Settings size={18} />
                                            </button>
                                            <button className="p-2 hover:bg-rose-500/20 rounded-lg text-gray-400 hover:text-rose-500 transition-all">
                                                <Trash2 size={18} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                <div className="security-note glass p-6 border-l-4 border-amber-500/50 flex gap-4">
                    <div className="text-amber-500 mt-1">
                        <Shield size={24} />
                    </div>
                    <div>
                        <h3 className="font-bold text-white mb-1">Security & Encryption</h3>
                        <p className="text-sm text-gray-400">
                            All API keys are encrypted using <span className="text-rose-gold font-mono">AES-256-GCM</span> before storage.
                            Keys are only decrypted in the secure AI worker environment during execution.
                            Master keys are stored in environment variables, separate from the database.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};
