import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { GlassCard, GlassInput, JellyButton } from '@/components/ui';
import { Save, X, Plus, Trash2, ArrowDown } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { Agent } from '@/types';
import './WorkflowBuilder.css';

interface WorkflowStep {
    id: string;
    agent_id: string;
    order: number;
    input_mapping: Record<string, string>;
}

export const WorkflowBuilder: React.FC = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);
    const [agents, setAgents] = useState<Agent[]>([]);

    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [steps, setSteps] = useState<WorkflowStep[]>([]);
    const [error, setError] = useState('');

    useEffect(() => {
        fetchAgents();
        if (id) {
            fetchWorkflow();
        }
    }, [id]);

    const fetchAgents = async () => {
        try {
            const { data } = await apiClient.get('/ai/agents');
            setAgents(data);
        } catch (error) {
            console.error('Failed to fetch agents:', error);
        }
    };

    const fetchWorkflow = async () => {
        try {
            const { data } = await apiClient.get(`/ai/workflows/${id}`);
            setName(data.name);
            setDescription(data.description || '');

            // Parse DAG structure to steps
            // API returns: { dag_structure: { nodes: [...], edges: [...] } }
            if (data.dag_structure && data.dag_structure.nodes) {
                // Convert nodes back to steps format
                const loadedSteps = data.dag_structure.nodes.map((node: any, index: number) => ({
                    id: node.id,
                    agent_id: node.config.agent_id,
                    order: index,
                    input_mapping: node.config.input_mapping || {}
                }));

                // Sort by edges to maintain correct order
                // If there are edges, sort by dependency order
                if (data.dag_structure.edges && data.dag_structure.edges.length > 0) {
                    const sortedSteps: WorkflowStep[] = [];
                    const nodeMap = new Map(loadedSteps.map((step: WorkflowStep) => [step.id, step]));
                    const edgeMap = new Map(data.dag_structure.edges.map((edge: any) => [edge.source, edge.target]));

                    // Find the first node (one without incoming edge)
                    let currentId = loadedSteps.find((step: WorkflowStep) =>
                        !data.dag_structure.edges.some((edge: any) => edge.target === step.id)
                    )?.id;

                    while (currentId && nodeMap.has(currentId)) {
                        const step = nodeMap.get(currentId)!;
                        sortedSteps.push({ ...step, order: sortedSteps.length });
                        currentId = edgeMap.get(currentId);
                    }

                    setSteps(sortedSteps.length > 0 ? sortedSteps : loadedSteps);
                } else {
                    setSteps(loadedSteps);
                }
            }
        } catch (error) {
            console.error('Failed to fetch workflow:', error);
            setError('Failed to load workflow');
        }
    };

    const addStep = () => {
        const newStep: WorkflowStep = {
            id: `step_${Date.now()}`,
            agent_id: agents[0]?.id || '',
            order: steps.length,
            input_mapping: {},
        };
        setSteps([...steps, newStep]);
    };

    const removeStep = (stepId: string) => {
        setSteps(steps.filter(s => s.id !== stepId).map((s, idx) => ({ ...s, order: idx })));
    };

    const updateStep = (stepId: string, field: keyof WorkflowStep, value: any) => {
        setSteps(steps.map(s => s.id === stepId ? { ...s, [field]: value } : s));
    };

    const moveStep = (stepId: string, direction: 'up' | 'down') => {
        const index = steps.findIndex(s => s.id === stepId);
        if (
            (direction === 'up' && index === 0) ||
            (direction === 'down' && index === steps.length - 1)
        ) {
            return;
        }

        const newSteps = [...steps];
        const swapIndex = direction === 'up' ? index - 1 : index + 1;
        [newSteps[index], newSteps[swapIndex]] = [newSteps[swapIndex], newSteps[index]];
        setSteps(newSteps.map((s, idx) => ({ ...s, order: idx })));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        // Convert sequential steps to DAG structure (Nodes & Edges)
        const nodes = steps.map(step => ({
            id: step.id,
            type: 'agent',
            config: {
                agent_id: step.agent_id,
                input_mapping: step.input_mapping
            }
        }));

        const edges = [];
        for (let i = 0; i < steps.length - 1; i++) {
            edges.push({
                source: steps[i].id,
                target: steps[i + 1].id
            });
        }

        const payload = {
            name,
            dag_structure: {
                nodes,
                edges
            },
            is_active: true
        };

        try {
            if (id) {
                await apiClient.put(`/ai/workflows/${id}`, payload);
            } else {
                await apiClient.post('/ai/workflows', payload);
            }
            navigate('/workflows');
        } catch (err: any) {
            console.error(err);
            const detail = err.response?.data?.detail;
            if (Array.isArray(detail)) {
                setError(detail.map(e => `${e.loc.join('.')}: ${e.msg}`).join(', '));
            } else if (typeof detail === 'object') {
                setError(JSON.stringify(detail));
            } else {
                setError(detail || 'Failed to save workflow');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="workflow-builder">
            <div className="builder-header">
                <h1>{id ? 'Edit Workflow' : 'Create New Workflow'}</h1>
                <JellyButton variant="ghost" onClick={() => navigate('/workflows')}>
                    <X size={20} />
                    Cancel
                </JellyButton>
            </div>

            <form onSubmit={handleSubmit}>
                <GlassCard className="workflow-info">
                    <h2>Workflow Information</h2>

                    <GlassInput
                        label="Workflow Name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        required
                        placeholder="e.g., Content Generation Pipeline"
                    />

                    <div className="form-group">
                        <label>Description (optional)</label>
                        <textarea
                            className="glass-textarea"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="Describe what this workflow does..."
                            rows={3}
                        />
                    </div>
                </GlassCard>

                <GlassCard className="workflow-steps">
                    <div className="steps-header">
                        <h2>Workflow Steps</h2>
                        <JellyButton type="button" variant="secondary" onClick={addStep}>
                            <Plus size={20} />
                            Add Step
                        </JellyButton>
                    </div>

                    <p className="help-text">
                        Define a sequence of agents. Each agent will process the output from the previous step.
                    </p>

                    {steps.length === 0 ? (
                        <div className="empty-steps">
                            <p>No steps yet. Add your first agent to begin building the workflow.</p>
                            <JellyButton type="button" roseGold onClick={addStep}>
                                <Plus size={20} />
                                Add First Step
                            </JellyButton>
                        </div>
                    ) : (
                        <div className="steps-list">
                            {steps.map((step, index) => (
                                <React.Fragment key={step.id}>
                                    <div className="step-card">
                                        <div className="step-number">Step {index + 1}</div>

                                        <div className="step-content">
                                            <div className="form-group">
                                                <label>Select Agent</label>
                                                <select
                                                    className="glass-select"
                                                    value={step.agent_id}
                                                    onChange={(e) => updateStep(step.id, 'agent_id', e.target.value)}
                                                    required
                                                >
                                                    <option value="">Choose an agent...</option>
                                                    {agents.map((agent) => (
                                                        <option key={agent.id} value={agent.id}>
                                                            {agent.name}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>

                                            {index > 0 && (
                                                <div className="input-mapping">
                                                    <small>Input from: Previous step output</small>
                                                </div>
                                            )}
                                        </div>

                                        <div className="step-actions">
                                            <button
                                                type="button"
                                                className="step-action-btn"
                                                onClick={() => moveStep(step.id, 'up')}
                                                disabled={index === 0}
                                            >
                                                ↑
                                            </button>
                                            <button
                                                type="button"
                                                className="step-action-btn"
                                                onClick={() => moveStep(step.id, 'down')}
                                                disabled={index === steps.length - 1}
                                            >
                                                ↓
                                            </button>
                                            <button
                                                type="button"
                                                className="step-action-btn delete"
                                                onClick={() => removeStep(step.id)}
                                            >
                                                <Trash2 size={16} />
                                            </button>
                                        </div>
                                    </div>

                                    {index < steps.length - 1 && (
                                        <div className="step-connector">
                                            <ArrowDown size={24} color="var(--color-accent-primary)" />
                                        </div>
                                    )}
                                </React.Fragment>
                            ))}
                        </div>
                    )}
                </GlassCard>

                {error && <div className="error-message">{error}</div>}

                <div className="builder-actions">
                    <JellyButton type="button" variant="ghost" onClick={() => navigate('/workflows')}>
                        Cancel
                    </JellyButton>
                    <JellyButton type="submit" roseGold disabled={loading || steps.length === 0}>
                        <Save size={20} />
                        {loading ? 'Saving...' : (id ? 'Update Workflow' : 'Create Workflow')}
                    </JellyButton>
                </div>
            </form>
        </div>
    );
};
