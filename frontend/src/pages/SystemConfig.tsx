import React, { useState, useEffect } from 'react';
import { GlassCard, GlassInput, JellyButton } from '@/components/ui';
import { Plus, Save, Trash2 } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import './SystemConfig.css';

interface Model {
    id: string;
    model_key: string;
    model_name: string;
    provider: string;
    model_type: string;
    is_active: boolean;
}

export const SystemConfig: React.FC = () => {
    const [models, setModels] = useState<Model[]>([]);
    const [showAddModel, setShowAddModel] = useState(false);
    const [newModel, setNewModel] = useState({
        model_name: '',
        model_key: '',
        provider: '',
        model_type: 'text',
        is_active: true,
    });

    useEffect(() => {
        fetchModels();
    }, []);

    const fetchModels = async () => {
        try {
            const { data } = await apiClient.get('/config/models');
            setModels(data);
        } catch (error) {
            console.error('Failed to fetch models:', error);
        }
    };

    const handleAddModel = async () => {
        try {
            const { data } = await apiClient.post('/config/models', newModel);
            setModels([...models, data]);
            setNewModel({ model_name: '', model_key: '', provider: '', model_type: 'text', is_active: true });
            setShowAddModel(false);
        } catch (error) {
            console.error('Failed to add model:', error);
        }
    };

    const toggleModelActive = async (id: string) => {
        try {
            const model = models.find(m => m.id === id);
            if (!model) return;

            await apiClient.put(`/config/models/${id}`, {
                ...model,
                is_active: !model.is_active,
            });
            setModels(models.map(m => m.id === id ? { ...m, is_active: !m.is_active } : m));
        } catch (error) {
            console.error('Failed to update model:', error);
        }
    };

    const handleDeleteModel = async (id: string) => {
        if (window.confirm('Are you sure you want to delete this model?')) {
            try {
                await apiClient.delete(`/config/models/${id}`);
                setModels(models.filter(m => m.id !== id));
            } catch (error) {
                console.error('Failed to delete model:', error);
            }
        }
    };

    return (
        <div className="system-config">
            <div className="page-header">
                <h1>System Configuration</h1>
                <p>Manage AI models and system settings</p>
            </div>

            <GlassCard>
                <div className="section-header">
                    <h2>AI Model Registry</h2>
                    <JellyButton
                        variant="secondary"
                        onClick={() => setShowAddModel(!showAddModel)}
                    >
                        <Plus size={20} />
                        Add Model
                    </JellyButton>
                </div>

                {showAddModel && (
                    <div className="add-model-form">
                        <GlassInput
                            label="Model Name"
                            value={newModel.model_name}
                            onChange={(e) => setNewModel({ ...newModel, model_name: e.target.value })}
                            placeholder="e.g., GPT-4 Turbo"
                        />
                        <GlassInput
                            label="Model Key"
                            value={newModel.model_key}
                            onChange={(e) => setNewModel({ ...newModel, model_key: e.target.value })}
                            placeholder="e.g., gpt-4"
                        />
                        <GlassInput
                            label="Provider"
                            value={newModel.provider}
                            onChange={(e) => setNewModel({ ...newModel, provider: e.target.value })}
                            placeholder="e.g., openai"
                        />
                        <div className="form-group">
                            <label>Type</label>
                            <select
                                className="glass-select"
                                value={newModel.model_type}
                                onChange={(e) => setNewModel({ ...newModel, model_type: e.target.value })}
                            >
                                <option value="text">Text</option>
                                <option value="image">Image</option>
                                <option value="audio">Audio</option>
                                <option value="video">Video</option>
                            </select>
                        </div>
                        <div className="form-actions">
                            <JellyButton
                                variant="ghost"
                                onClick={() => setShowAddModel(false)}
                            >
                                Cancel
                            </JellyButton>
                            <JellyButton
                                roseGold
                                onClick={handleAddModel}
                                disabled={!newModel.model_key || !newModel.provider || !newModel.model_name}
                            >
                                <Save size={20} />
                                Save Model
                            </JellyButton>
                        </div>
                    </div>
                )}

                <div className="models-table">
                    <table>
                        <thead>
                            <tr>
                                <th>Model Name</th>
                                <th>Model Key</th>
                                <th>Provider</th>
                                <th>Type</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {models.map((model) => (
                                <tr key={model.id}>
                                    <td className="model-name">{model.model_name}</td>
                                    <td className="model-key">{model.model_key}</td>
                                    <td>{model.provider}</td>
                                    <td>
                                        <span className="type-badge">{model.model_type}</span>
                                    </td>
                                    <td>
                                        <button
                                            className={`status-toggle ${model.is_active ? 'active' : 'inactive'}`}
                                            onClick={() => toggleModelActive(model.id)}
                                        >
                                            {model.is_active ? 'Active' : 'Inactive'}
                                        </button>
                                    </td>
                                    <td>
                                        <JellyButton
                                            variant="ghost"
                                            onClick={() => handleDeleteModel(model.id)}
                                        >
                                            <Trash2 size={16} />
                                        </JellyButton>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </GlassCard>

            <GlassCard>
                <h2>API Keys</h2>
                <p className="help-text">
                    API keys are encrypted and write-only. You cannot view existing keys.
                </p>

                <div className="api-keys-form">
                    <GlassInput
                        type="password"
                        label="OpenAI API Key"
                        placeholder="sk-..."
                    />
                    <GlassInput
                        type="password"
                        label="Anthropic API Key"
                        placeholder="sk-ant-..."
                    />
                    <GlassInput
                        type="password"
                        label="Twilio Account SID"
                        placeholder="AC..."
                    />
                    <JellyButton roseGold>
                        <Save size={20} />
                        Update API Keys
                    </JellyButton>
                </div>
            </GlassCard>
        </div>
    );
};
