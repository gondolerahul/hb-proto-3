import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { GlassCard, GlassInput, JellyButton } from '@/components/ui';
import { Save, X } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import './AgentBuilder.css';

interface Model {
    model_key: string;
    model_name: string;
    provider: string;
    model_type: string;
    is_active: boolean;
}

const AVAILABLE_TOOLS = [
    { id: 'web_search', name: 'Web Search', description: 'Search the internet for information' },
    { id: 'calculator', name: 'Calculator', description: 'Perform mathematical calculations' },
    { id: 'code_interpreter', name: 'Code Interpreter', description: 'Execute Python code' },
    { id: 'knowledge_base', name: 'Knowledge Base', description: 'Search uploaded documents' },
];

export const AgentBuilder: React.FC = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);
    const [models, setModels] = useState<Model[]>([]);

    // Form state
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [systemPrompt, setSystemPrompt] = useState('');
    const [selectedModel, setSelectedModel] = useState('');
    const [temperature, setTemperature] = useState(0.7);
    const [topP, setTopP] = useState(1.0);
    const [selectedTools, setSelectedTools] = useState<string[]>([]);
    const [error, setError] = useState('');

    useEffect(() => {
        fetchModels();
        if (id) {
            fetchAgent();
        }
    }, [id]);

    const fetchModels = async () => {
        try {
            const { data } = await apiClient.get('/config/models');
            setModels(data.filter((m: Model) => m.is_active && m.model_type === 'text'));
            if (data.length > 0) {
                setSelectedModel(data[0].model_key);
            }
        } catch (error) {
            console.error('Failed to fetch models:', error);
        }
    };

    const fetchAgent = async () => {
        try {
            const { data } = await apiClient.get(`/ai/agents/${id}`);
            setName(data.name);
            setDescription(data.description || '');
            setSystemPrompt(data.role);
            setSelectedModel(data.llm_config?.model);
            setTemperature(data.llm_config?.temperature || 0.7);
            // top_p is not in the current backend schema, keeping state but not setting from DB
            setSelectedTools(data.llm_config?.tools || []);
        } catch (error) {
            console.error('Failed to fetch agent:', error);
            setError('Failed to load agent');
        }
    };

    const handleToolToggle = (toolId: string) => {
        setSelectedTools(prev =>
            prev.includes(toolId)
                ? prev.filter(t => t !== toolId)
                : [...prev, toolId]
        );
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        // Find the provider for the selected model
        const modelInfo = models.find(m => m.model_key === selectedModel);

        const payload = {
            name,
            role: systemPrompt, // Mapping system_prompt to 'role' as per schema
            llm_config: {
                provider: modelInfo?.provider || 'openai',
                model: selectedModel,
                temperature,
                max_tokens: 4000,
                tools: selectedTools
            },
            is_active: true
        };

        try {
            if (id) {
                await apiClient.put(`/ai/agents/${id}`, payload);
            } else {
                await apiClient.post('/ai/agents', payload);
            }
            navigate('/agents');
        } catch (err: any) {
            console.error(err);
            const detail = err.response?.data?.detail;
            if (Array.isArray(detail)) {
                // Handle array of errors (Video of Pydantic validation errors)
                setError(detail.map(e => `${e.loc.join('.')}: ${e.msg}`).join(', '));
            } else if (typeof detail === 'object') {
                setError(JSON.stringify(detail));
            } else {
                setError(detail || 'Failed to save agent');
            }
        } finally {
            setLoading(false);
        }
    };

    const extractVariables = (text: string): string[] => {
        const regex = /\{\{(\w+)\}\}/g;
        const matches = text.matchAll(regex);
        return Array.from(new Set(Array.from(matches, m => m[1])));
    };

    const variables = extractVariables(systemPrompt);

    return (
        <div className="agent-builder">
            <div className="builder-header">
                <h1>{id ? 'Edit Agent' : 'Create New Agent'}</h1>
                <JellyButton variant="ghost" onClick={() => navigate('/agents')}>
                    <X size={20} />
                    Cancel
                </JellyButton>
            </div>

            <form onSubmit={handleSubmit}>
                <div className="builder-grid">
                    {/* Basic Info */}
                    <GlassCard className="builder-section">
                        <h2>Basic Information</h2>

                        <GlassInput
                            label="Agent Name"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            required
                            placeholder="e.g., Customer Support Agent"
                        />

                        <div className="form-group">
                            <label>Description (optional)</label>
                            <textarea
                                className="glass-textarea"
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                placeholder="Describe what this agent does..."
                                rows={3}
                            />
                        </div>
                    </GlassCard>

                    {/* Model Configuration */}
                    <GlassCard className="builder-section">
                        <h2>Model Configuration</h2>

                        <div className="form-group">
                            <label>Model</label>
                            <select
                                className="glass-select"
                                value={selectedModel}
                                onChange={(e) => setSelectedModel(e.target.value)}
                                required
                            >
                                <option value="">Select a model</option>
                                {models.map((model) => (
                                    <option key={model.model_key} value={model.model_key}>
                                        {model.model_name} ({model.provider})
                                    </option>
                                ))}
                            </select>
                        </div>

                        <div className="form-group">
                            <label>Temperature: {temperature.toFixed(2)}</label>
                            <input
                                type="range"
                                className="glass-slider"
                                min="0"
                                max="2"
                                step="0.1"
                                value={temperature}
                                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                            />
                            <p className="help-text">Controls randomness (0 = deterministic, 2 = creative)</p>
                        </div>

                        <div className="form-group">
                            <label>Top P: {topP.toFixed(2)}</label>
                            <input
                                type="range"
                                className="glass-slider"
                                min="0"
                                max="1"
                                step="0.05"
                                value={topP}
                                onChange={(e) => setTopP(parseFloat(e.target.value))}
                            />
                            <p className="help-text">Nucleus sampling (0.1 = focused, 1.0 = diverse)</p>
                        </div>
                    </GlassCard>

                    {/* System Prompt */}
                    <GlassCard className="builder-section full-width">
                        <h2>System Prompt</h2>
                        <p className="help-text">
                            Define the agent's role and behavior. Use {'{{variable}}'} syntax for dynamic inputs.
                        </p>

                        <textarea
                            className="glass-textarea prompt-editor"
                            value={systemPrompt}
                            onChange={(e) => setSystemPrompt(e.target.value)}
                            required
                            placeholder="You are a helpful assistant that..."
                            rows={10}
                        />

                        {variables.length > 0 && (
                            <div className="variables-detected">
                                <strong>Variables detected:</strong>
                                <div className="variable-chips">
                                    {variables.map((v) => (
                                        <span key={v} className="variable-chip">{`{{${v}}}`}</span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </GlassCard>

                    {/* Tools */}
                    <GlassCard className="builder-section full-width">
                        <h2>Tools & Capabilities</h2>
                        <p className="help-text">Select which tools this agent can use</p>

                        <div className="tools-grid">
                            {AVAILABLE_TOOLS.map((tool) => (
                                <div
                                    key={tool.id}
                                    className={`tool-card ${selectedTools.includes(tool.id) ? 'selected' : ''}`}
                                    onClick={() => handleToolToggle(tool.id)}
                                >
                                    <div className="tool-checkbox">
                                        <input
                                            type="checkbox"
                                            checked={selectedTools.includes(tool.id)}
                                            onChange={() => { }}
                                        />
                                    </div>
                                    <div className="tool-info">
                                        <h4>{tool.name}</h4>
                                        <p>{tool.description}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </GlassCard>
                </div>

                {error && <div className="error-message">{error}</div>}

                <div className="builder-actions">
                    <JellyButton type="button" variant="ghost" onClick={() => navigate('/agents')}>
                        Cancel
                    </JellyButton>
                    <JellyButton type="submit" roseGold disabled={loading}>
                        <Save size={20} />
                        {loading ? 'Saving...' : (id ? 'Update Agent' : 'Create Agent')}
                    </JellyButton>
                </div>
            </form>
        </div>
    );
};
