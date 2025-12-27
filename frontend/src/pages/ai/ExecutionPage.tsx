import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { GlassCard, GlassInput, JellyButton } from '@/components/ui';
import { Play, ArrowLeft, Loader, Cpu, Zap, Activity, Info } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { HierarchicalEntity } from '@/types';
import './ExecutionPage.css';

export const ExecutionPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();

    const [entity, setEntity] = useState<HierarchicalEntity | null>(null);
    const [variables, setVariables] = useState<Record<string, string>>({});
    const [requiredVars, setRequiredVars] = useState<string[]>([]);

    const [executing, setExecuting] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        fetchDetails();
    }, [id]);

    const fetchDetails = async () => {
        try {
            const { data } = await apiClient.get<HierarchicalEntity>(`/ai/entities/${id}`);
            setEntity(data);

            // Extract variables from all prompt templates in the plan
            const allVars = new Set<string>();
            const steps = data.planning?.static_plan?.steps || [];

            steps.forEach(step => {
                const promptTemplate = step.target?.prompt_template;
                if (promptTemplate) {
                    const regex = /\{\{(\w+)\}\}/g;
                    const matches = promptTemplate.matchAll(regex);
                    for (const match of matches) {
                        allVars.add(match[1]);
                    }
                }
            });

            const varsArray = Array.from(allVars);
            setRequiredVars(varsArray);

            // Initialize variable state
            const initialVars: Record<string, string> = {};
            varsArray.forEach(v => initialVars[v] = '');
            setVariables(initialVars);
        } catch (error) {
            console.error('Failed to fetch details:', error);
            setError('Failed to load execution target');
        }
    };

    const handleExecute = async () => {
        setError('');
        setExecuting(true);

        try {
            const payload = {
                entity_id: id,
                input_data: variables,
            };

            const { data } = await apiClient.post('/ai/execute', payload);

            // Redirect to detail page with trace
            setTimeout(() => {
                navigate(`/executions/${data.id}`);
            }, 1000);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Execution failed');
            setExecuting(false);
        }
    };

    const canExecute = requiredVars.every(v => variables[v]?.trim());

    if (!entity && !error) return (
        <div className="loading-container">
            <Cpu size={48} className="pulse" color="var(--color-primary)" />
            <div className="loading">Calibrating Synapses...</div>
        </div>
    );

    return (
        <div className="execution-page">
            <div className="execution-header">
                <JellyButton variant="ghost" onClick={() => navigate(-1)}>
                    <ArrowLeft size={18} />
                    Back
                </JellyButton>
                <div className="header-info">
                    <h1>Execute: {entity?.name}</h1>
                    <div className="entity-path">
                        <span className="type-tag">{entity?.type}</span>
                        <span className="version-tag">v{entity?.version}</span>
                    </div>
                </div>
            </div>

            <div className="execution-grid">
                {/* Input Panel */}
                <GlassCard className="execution-input">
                    <div className="card-header-icon">
                        <Activity size={20} color="var(--color-secondary)" />
                        <h2>Deployment Parameters</h2>
                    </div>

                    {requiredVars.length > 0 ? (
                        <div className="variables-list">
                            <p className="help-text">Input required context for the AI entity:</p>
                            {requiredVars.map((varName) => (
                                <GlassInput
                                    key={varName}
                                    label={varName.replace(/_/g, ' ').toUpperCase()}
                                    placeholder={`Enter ${varName}...`}
                                    value={variables[varName] || ''}
                                    onChange={(e) => setVariables({ ...variables, [varName]: e.target.value })}
                                    required
                                />
                            ))}
                        </div>
                    ) : (
                        <div className="no-vars">
                            <Zap size={32} color="var(--color-text-tertiary)" />
                            <p>This entity is configured for autonomous execution without external parameters.</p>
                        </div>
                    )}

                    <div className="action-area">
                        <JellyButton
                            roseGold
                            onClick={handleExecute}
                            disabled={executing || !canExecute}
                            className="execute-btn"
                        >
                            {executing ? (
                                <>
                                    <Loader className="spin" size={20} />
                                    Initialising...
                                </>
                            ) : (
                                <>
                                    <Play size={20} />
                                    Launch Execution
                                </>
                            )}
                        </JellyButton>
                        {error && <div className="error-message">{error}</div>}
                    </div>
                </GlassCard>

                {/* Info Panel */}
                <GlassCard className="execution-info-card">
                    <div className="card-header-icon">
                        <Info size={20} color="var(--color-primary)" />
                        <h2>Execution Context</h2>
                    </div>
                    <div className="info-content">
                        <div className="info-item">
                            <label>Reasoning Mode</label>
                            <span>{entity?.logic_gate?.reasoning_config?.reasoning_mode || 'STANDARD'}</span>
                        </div>
                        <div className="info-item">
                            <label>Model Configuration</label>
                            <span>{entity?.logic_gate?.reasoning_config?.model_name} ({entity?.logic_gate?.reasoning_config?.model_provider})</span>
                        </div>
                        {entity?.governance?.hitl_checkpoints && entity.governance.hitl_checkpoints.length > 0 && (
                            <div className="info-item">
                                <label>Guardrails</label>
                                <span className="warning-text">Human-in-the-loop enabled ({entity.governance.hitl_checkpoints.length} checkpoints)</span>
                            </div>
                        )}
                    </div>
                </GlassCard>
            </div>
        </div>
    );
};
