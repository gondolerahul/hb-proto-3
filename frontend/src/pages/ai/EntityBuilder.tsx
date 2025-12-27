import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { GlassCard, GlassInput, JellyButton } from '@/components/ui';
import { Save, X, Plus, Trash2, Zap, Activity, Brain, Workflow } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { HierarchicalEntity, EntityType } from '@/types';
import './EntityBuilder.css';

interface Model {
    model_key: string;
    model_name: string;
    provider: string;
    model_type: string;
    is_active: boolean;
}

interface Step {
    id: string;
    entity_id: string;
    entity_name?: string;
}

const AVAILABLE_TOOLS = [
    { id: 'web_search', name: 'Web Search', description: 'Search the internet for information' },
    { id: 'calculator', name: 'Calculator', description: 'Perform mathematical calculations' },
    { id: 'code_interpreter', name: 'Code Interpreter', description: 'Execute Python code' },
    { id: 'knowledge_base', name: 'Knowledge Base', description: 'Search uploaded documents' },
];

export const EntityBuilder: React.FC = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);
    const [models, setModels] = useState<Model[]>([]);
    const [allEntities, setAllEntities] = useState<HierarchicalEntity[]>([]);

    // Shared state
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [type, setType] = useState<EntityType>(EntityType.ACTION);
    const [error, setError] = useState('');

    // Action specific state
    const [promptTemplate, setPromptTemplate] = useState('');
    const [selectedModel, setSelectedModel] = useState('');
    const [temperature, setTemperature] = useState(0.7);
    const [selectedTools, setSelectedTools] = useState<string[]>([]);

    // Composite specific state (Skill, Agent, Process)
    const [steps, setSteps] = useState<Step[]>([]);

    useEffect(() => {
        fetchModels();
        fetchEntities();
        if (id) {
            fetchEntity();
        }
    }, [id]);

    const fetchModels = async () => {
        try {
            const { data } = await apiClient.get('/config/models');
            setModels(data.filter((m: Model) => m.is_active && m.model_type === 'text'));
            if (data.length > 0 && !selectedModel) {
                setSelectedModel(data[0].model_key);
            }
        } catch (error) {
            console.error('Failed to fetch models:', error);
        }
    };

    const fetchEntities = async () => {
        try {
            const { data } = await apiClient.get('/ai/entities');
            setAllEntities(data);
        } catch (error) {
            console.error('Failed to fetch entities:', error);
        }
    };

    const fetchEntity = async () => {
        try {
            const { data } = await apiClient.get<HierarchicalEntity>(`/ai/entities/${id}`);
            setName(data.name);
            setDescription(data.description || '');
            setType(data.type);

            if (data.type === EntityType.ACTION) {
                setPromptTemplate(data.static_plan?.prompt_template || '');
                setSelectedModel(data.llm_config?.model || '');
                setTemperature(data.llm_config?.temperature || 0.7);
                setSelectedTools(data.llm_config?.tools || []);
            } else {
                setSteps(data.static_plan?.steps || []);
            }
        } catch (error) {
            console.error('Failed to fetch entity:', error);
            setError('Failed to load entity');
        }
    };

    const handleToolToggle = (toolId: string) => {
        setSelectedTools(prev =>
            prev.includes(toolId)
                ? prev.filter(t => t !== toolId)
                : [...prev, toolId]
        );
    };

    const addStep = () => {
        const newStep: Step = {
            id: `step_${Date.now()}`,
            entity_id: '',
        };
        setSteps([...steps, newStep]);
    };

    const removeStep = (stepId: string) => {
        setSteps(steps.filter(s => s.id !== stepId));
    };

    const updateStep = (stepId: string, entityId: string) => {
        const entity = allEntities.find(e => e.id === entityId);
        setSteps(steps.map(s => s.id === stepId ? { ...s, entity_id: entityId, entity_name: entity?.name } : s));
    };

    const moveStep = (index: number, direction: 'up' | 'down') => {
        if ((direction === 'up' && index === 0) || (direction === 'down' && index === steps.length - 1)) return;
        const newSteps = [...steps];
        const swapIndex = direction === 'up' ? index - 1 : index + 1;
        [newSteps[index], newSteps[swapIndex]] = [newSteps[swapIndex], newSteps[index]];
        setSteps(newSteps);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        const modelInfo = models.find(m => m.model_key === selectedModel);

        const payload: any = {
            name,
            description,
            type,
            is_active: true
        };

        if (type === EntityType.ACTION) {
            payload.static_plan = { prompt_template: promptTemplate };
            payload.llm_config = {
                provider: modelInfo?.provider || 'openai',
                model: selectedModel,
                temperature,
                tools: selectedTools
            };
        } else {
            payload.static_plan = { steps };
        }

        try {
            if (id) {
                await apiClient.put(`/ai/entities/${id}`, payload);
            } else {
                await apiClient.post('/ai/entities', payload);
            }
            navigate('/ai/entities');
        } catch (err: any) {
            console.error(err);
            setError(err.response?.data?.detail || 'Failed to save entity');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="entity-builder">
            <div className="builder-header">
                <div>
                    <h1>{id ? 'Edit' : 'Create'} {type.charAt(0) + type.slice(1).toLowerCase()}</h1>
                    <p>Configure your intelligent unit</p>
                </div>
                <JellyButton variant="ghost" onClick={() => navigate('/ai/entities')}>
                    <X size={20} />
                </JellyButton>
            </div>

            <form onSubmit={handleSubmit}>
                <div className="builder-grid">
                    {/* common info */}
                    <GlassCard className="builder-section">
                        <h2>General</h2>
                        <div className="form-group">
                            <label>Type</label>
                            <div className="type-selector">
                                {Object.values(EntityType).map(t => (
                                    <button
                                        key={t}
                                        type="button"
                                        className={`type-btn ${type === t ? 'active' : ''}`}
                                        onClick={() => setType(t)}
                                        disabled={!!id} // Type cannot be changed after creation
                                    >
                                        {t === EntityType.ACTION && <Zap size={14} />}
                                        {t === EntityType.SKILL && <Activity size={14} />}
                                        {t === EntityType.AGENT && <Brain size={14} />}
                                        {t === EntityType.PROCESS && <Workflow size={14} />}
                                        {t}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <GlassInput
                            label="Entity Name"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            required
                            placeholder="e.g. Resume Parser"
                        />

                        <div className="form-group">
                            <label>Description</label>
                            <textarea
                                className="glass-textarea"
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                rows={3}
                                placeholder="What does this entity do?"
                            />
                        </div>
                    </GlassCard>

                    {type === EntityType.ACTION ? (
                        <>
                            <GlassCard className="builder-section">
                                <h2>Intelligence</h2>
                                <div className="form-group">
                                    <label>Model</label>
                                    <select
                                        className="glass-select"
                                        value={selectedModel}
                                        onChange={(e) => setSelectedModel(e.target.value)}
                                        required
                                    >
                                        <option value="">Select a model</option>
                                        {models.map(m => (
                                            <option key={m.model_key} value={m.model_key}>{m.model_name}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Temperature: {temperature}</label>
                                    <input
                                        type="range"
                                        min="0"
                                        max="1.5"
                                        step="0.1"
                                        value={temperature}
                                        onChange={(e) => setTemperature(parseFloat(e.target.value))}
                                        className="glass-slider"
                                    />
                                </div>
                            </GlassCard>

                            <GlassCard className="builder-section full-width">
                                <h2>Static Blueprint (Prompt)</h2>
                                <p className="help-text">Define the core logic using variables like {'{{input}}'}</p>
                                <textarea
                                    className="glass-textarea prompt-editor"
                                    value={promptTemplate}
                                    onChange={(e) => setPromptTemplate(e.target.value)}
                                    rows={8}
                                    placeholder="You are an AI that..."
                                    required
                                />
                            </GlassCard>

                            <GlassCard className="builder-section full-width">
                                <h2>Capabilities (Tools)</h2>
                                <div className="tools-grid">
                                    {AVAILABLE_TOOLS.map(tool => (
                                        <div
                                            key={tool.id}
                                            className={`tool-card ${selectedTools.includes(tool.id) ? 'active' : ''}`}
                                            onClick={() => handleToolToggle(tool.id)}
                                        >
                                            <h4>{tool.name}</h4>
                                            <p>{tool.description}</p>
                                        </div>
                                    ))}
                                </div>
                            </GlassCard>
                        </>
                    ) : (
                        <GlassCard className="builder-section full-width">
                            <div className="section-header">
                                <h2>Composition Plan</h2>
                                <JellyButton type="button" variant="secondary" onClick={addStep}>
                                    <Plus size={16} />
                                    Add Step
                                </JellyButton>
                            </div>

                            <div className="steps-list">
                                {steps.length === 0 && <p className="empty-msg">No units added to the plan.</p>}
                                {steps.map((step, index) => (
                                    <div key={step.id} className="step-row">
                                        <div className="step-idx">{index + 1}</div>
                                        <div className="step-config">
                                            <select
                                                className="glass-select"
                                                value={step.entity_id}
                                                onChange={(e) => updateStep(step.id, e.target.value)}
                                                required
                                            >
                                                <option value="">Select an Entity...</option>
                                                {allEntities
                                                    .filter(e => e.id !== id) // Prevent self-recursion
                                                    .map(e => (
                                                        <option key={e.id} value={e.id}>[{e.type}] {e.name}</option>
                                                    ))}
                                            </select>
                                        </div>
                                        <div className="step-actions">
                                            <button type="button" onClick={() => moveStep(index, 'up')} disabled={index === 0}>↑</button>
                                            <button type="button" onClick={() => moveStep(index, 'down')} disabled={index === steps.length - 1}>↓</button>
                                            <button type="button" className="delete" onClick={() => removeStep(step.id)}><Trash2 size={16} /></button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </GlassCard>
                    )}
                </div>

                {error && <div className="error-banner">{error}</div>}

                <div className="form-submit">
                    <JellyButton type="submit" roseGold disabled={loading}>
                        <Save size={20} />
                        {loading ? 'Processing...' : (id ? 'Update Entity' : 'Finalize Entity')}
                    </JellyButton>
                </div>
            </form>
        </div>
    );
};
