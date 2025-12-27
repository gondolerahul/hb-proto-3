import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { GlassCard } from './ui/GlassCard';
import { GlassInput } from './ui/GlassInput';
import { integrationService, Model, Integration } from '../services/integration.service';
import { User } from '../types';

interface CreateIntegrationModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (data: any) => Promise<void>;
    currentUser: User | null;
    editingIntegration?: Integration | null;
}

const COMPONENT_TYPES = [
    { id: 'input_token', name: 'Input Token' },
    { id: 'output_token', name: 'Output Token' },
    { id: 'analysis', name: 'Analysis' },
    { id: 'minute', name: 'Minute' },
    { id: 'character', name: 'Character' },
    { id: 'flat_fee', name: 'Flat Fee' }
];

export const CreateIntegrationModal: React.FC<CreateIntegrationModalProps> = ({
    isOpen,
    onClose,
    onSubmit,
    currentUser,
    editingIntegration
}) => {
    const [models, setModels] = useState<Model[]>([]);
    const [formData, setFormData] = useState({
        provider_name: '',
        model_name: '',
        service_sku: '',
        component_type: 'input_token',
        internal_cost: 0,
        cost_unit: '1M Tokens',
        api_key: '',
        status: 'active'
    });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchModels = async () => {
            try {
                const data = await integrationService.getModels();
                setModels(data);
            } catch (err) {
                console.error('Failed to fetch models', err);
            }
        };
        if (isOpen) {
            fetchModels();
        }
    }, [isOpen]);

    useEffect(() => {
        if (editingIntegration) {
            setFormData({
                provider_name: editingIntegration.provider_name,
                model_name: editingIntegration.model_name || '',
                service_sku: editingIntegration.service_sku,
                component_type: editingIntegration.component_type,
                internal_cost: editingIntegration.internal_cost,
                cost_unit: editingIntegration.cost_unit,
                api_key: '', // Don't show existing key
                status: editingIntegration.status
            });
        } else {
            setFormData({
                provider_name: '',
                model_name: '',
                service_sku: '',
                component_type: 'input_token',
                internal_cost: 0,
                cost_unit: '1M Tokens',
                api_key: '',
                status: 'active'
            });
        }
    }, [editingIntegration, isOpen]);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setLoading(true);

        try {
            const payload = {
                ...formData,
                company_id: currentUser?.company_id,
                internal_cost: Number(formData.internal_cost)
            };

            // If editing and api_key is empty, remove it from payload so it's not updated to empty
            if (editingIntegration && !formData.api_key) {
                delete (payload as any).api_key;
            }

            await onSubmit(payload);
            onClose();
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to save integration');
        } finally {
            setLoading(false);
        }
    };

    const handleModelChange = (modelKey: string) => {
        const model = models.find(m => m.model_key === modelKey);
        if (model) {
            setFormData({
                ...formData,
                model_name: model.model_key,
                provider_name: model.provider,
                service_sku: `${model.model_key}-${formData.component_type === 'input_token' ? 'in' : 'out'}`
            });
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <GlassCard className="w-full max-w-2xl p-8 relative max-h-[90vh] overflow-y-auto">
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 p-2 text-gray-400 hover:text-white transition-colors"
                >
                    <X size={20} />
                </button>

                <h2 className="text-2xl font-bold text-white mb-6">
                    {editingIntegration ? 'Edit Integration' : 'Add New Integration'}
                </h2>

                <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-6">
                    <div className="col-span-1">
                        <label className="block text-sm font-medium text-gray-300 mb-2">Model Template</label>
                        <select
                            onChange={(e) => handleModelChange(e.target.value)}
                            value={formData.model_name}
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-rose-500/50 transition-all"
                        >
                            <option value="" className="bg-gray-900">Select Model...</option>
                            {models.map(m => (
                                <option key={m.model_key} value={m.model_key} className="bg-gray-900">
                                    {m.model_name} ({m.provider})
                                </option>
                            ))}
                        </select>
                    </div>

                    <GlassInput
                        label="Provider Name"
                        value={formData.provider_name}
                        onChange={(e) => setFormData({ ...formData, provider_name: e.target.value })}
                        required
                    />

                    <GlassInput
                        label="Service SKU (Unique)"
                        value={formData.service_sku}
                        onChange={(e) => setFormData({ ...formData, service_sku: e.target.value })}
                        required
                        placeholder="e.g. gpt-4o-in"
                    />

                    <div className="col-span-1">
                        <label className="block text-sm font-medium text-gray-300 mb-2">Component Type</label>
                        <select
                            value={formData.component_type}
                            onChange={(e) => setFormData({ ...formData, component_type: e.target.value })}
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-rose-500/50 transition-all"
                            required
                        >
                            {COMPONENT_TYPES.map(t => (
                                <option key={t.id} value={t.id} className="bg-gray-900">{t.name}</option>
                            ))}
                        </select>
                    </div>

                    <GlassInput
                        label="Internal Cost"
                        type="number"
                        step="0.000001"
                        value={formData.internal_cost.toString()}
                        onChange={(e) => setFormData({ ...formData, internal_cost: parseFloat(e.target.value) })}
                        required
                    />

                    <GlassInput
                        label="Cost Unit"
                        value={formData.cost_unit}
                        onChange={(e) => setFormData({ ...formData, cost_unit: e.target.value })}
                        required
                        placeholder="e.g. 1M Tokens"
                    />

                    <div className="col-span-2">
                        <GlassInput
                            label={editingIntegration ? "API Key (Leave blank to keep current)" : "API Key"}
                            type="password"
                            value={formData.api_key}
                            onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                            required={!editingIntegration}
                        />
                    </div>

                    {error && (
                        <p className="col-span-2 text-red-400 text-sm bg-red-400/10 p-3 rounded-lg border border-red-400/20">
                            {error}
                        </p>
                    )}

                    <div className="col-span-2 flex justify-end gap-4 pt-4">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-6 py-2 text-gray-300 hover:text-white transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={loading}
                            className="px-6 py-2 bg-rose-500 hover:bg-rose-600 disabled:opacity-50 text-white rounded-lg transition-all"
                        >
                            {loading ? 'Saving...' : (editingIntegration ? 'Update' : 'Create')}
                        </button>
                    </div>
                </form>
            </GlassCard>
        </div>
    );
};
