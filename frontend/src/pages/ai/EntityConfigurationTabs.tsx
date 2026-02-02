import React, { useState, useEffect } from 'react';
import { ToolSelectionPanel } from '@/components/ToolSelectionPanel';
import { integrationService } from '../../services/integration.service';
import { JellyButton } from '@/components/ui';
import { Info, Brain, Settings, Route, Wrench, Shield, Layers, Plus, Trash2 } from 'lucide-react';
import { EntityType, EntityStatus, HierarchicalEntity } from '@/types';
import { EntityFlow } from './EntityFlow';
import { Node, Edge } from 'reactflow';
import './EntityConfigurationTabs.css';

interface EntityConfigurationTabsProps {
    entity?: HierarchicalEntity;
    onSave: (entityData: any) => void;
    onCancel: () => void;
}

export const EntityConfigurationTabs: React.FC<EntityConfigurationTabsProps> = ({ entity, onSave, onCancel }) => {
    const [activeTab, setActiveTab] = useState('overview');

    // Overview State
    const [name, setName] = useState(entity?.name || '');
    const [displayName, setDisplayName] = useState(entity?.display_name || '');
    const [type, setType] = useState<EntityType>(entity?.type || EntityType.AGENT);
    const [description, setDescription] = useState(entity?.description || '');
    const [version, setVersion] = useState(entity?.version || '1.0.0');
    const [status, setStatus] = useState<EntityStatus>(entity?.status || EntityStatus.DRAFT);
    const [tags, setTags] = useState<string[]>(entity?.tags || []);
    const [tagInput, setTagInput] = useState('');

    // Identity State
    const [systemPrompt, setSystemPrompt] = useState(entity?.identity?.system_prompt || '');
    const [examples, setExamples] = useState(entity?.identity?.examples || []);
    // NEW Few Shot State
    const [fewShotExamples, setFewShotExamples] = useState<{ [key: string]: string }[]>(entity?.identity?.few_shot_examples || []);

    const [behavioralConstraints, setBehavioralConstraints] = useState(entity?.identity?.behavioral_constraints || []);
    const [constraintInput, setConstraintInput] = useState('');



    // Few Shot Handlers
    const addFewShot = () => {
        setFewShotExamples([...fewShotExamples, { input: '', output: '' }]);
    };

    const updateFewShot = (index: number, key: string, value: string) => {
        const updated = [...fewShotExamples];
        updated[index] = { ...updated[index], [key]: value };
        setFewShotExamples(updated);
    };

    const removeFewShot = (index: number) => {
        setFewShotExamples(fewShotExamples.filter((_, i) => i !== index));
    };

    // Logic Gate State
    const [modelProvider, setModelProvider] = useState(entity?.logic_gate?.reasoning_config?.model_provider || 'google');
    const [modelName, setModelName] = useState(entity?.logic_gate?.reasoning_config?.model_name || 'gemini-3-flash-preview');
    const [temperature, setTemperature] = useState(entity?.logic_gate?.reasoning_config?.temperature || 0.7);
    const [topP, setTopP] = useState(entity?.logic_gate?.reasoning_config?.top_p || 1.0);
    const [maxTokens, setMaxTokens] = useState<number | undefined>(entity?.logic_gate?.reasoning_config?.max_tokens);
    const [reasoningMode, setReasoningMode] = useState(entity?.logic_gate?.reasoning_config?.reasoning_mode || 'REACT');
    const [maxRetries, setMaxRetries] = useState(entity?.logic_gate?.retry_policy?.max_retries || 3);
    const [backoffStrategy, setBackoffStrategy] = useState(entity?.logic_gate?.retry_policy?.backoff_strategy || 'EXPONENTIAL');
    const [reviewEnabled, setReviewEnabled] = useState(entity?.logic_gate?.review_mechanism?.enabled || false);
    const [reviewPrompt, setReviewPrompt] = useState(entity?.logic_gate?.review_mechanism?.review_prompt || '');

    // NEW Context Policy State
    const [contextPolicyType, setContextPolicyType] = useState<'FULL' | 'LAST_N' | 'SLIDING_WINDOW' | 'EXPLICIT'>(entity?.logic_gate?.context_policy?.type || 'FULL');
    const [contextPolicyN, setContextPolicyN] = useState<number | undefined>(entity?.logic_gate?.context_policy?.n);
    const [contextPolicyMaxChars, setContextPolicyMaxChars] = useState<number | undefined>(entity?.logic_gate?.context_policy?.max_chars);
    const [contextPolicySummarizeThreshold, setContextPolicySummarizeThreshold] = useState<number | undefined>(entity?.logic_gate?.context_policy?.summarize_threshold);

    // Planning State
    const [staticPlanEnabled, setStaticPlanEnabled] = useState(entity?.planning?.static_plan?.enabled ?? true);
    const [dynamicPlanningEnabled, setDynamicPlanningEnabled] = useState(entity?.planning?.dynamic_planning?.enabled ?? false);
    const [planningPrompt, setPlanningPrompt] = useState(entity?.planning?.dynamic_planning?.planning_prompt || '');
    const [maxIterations, setMaxIterations] = useState(entity?.planning?.loop_control?.max_iterations || 10);

    // Capabilities State
    const [selectedTools, setSelectedTools] = useState<string[]>(
        entity?.capabilities?.tools?.map((t: any) => t.tool_id || t) || []
    );
    const [memoryEnabled, setMemoryEnabled] = useState(entity?.capabilities?.memory?.enabled || false);
    const [memoryScope, setMemoryScope] = useState(entity?.capabilities?.memory?.scope || 'SESSION');
    const [maxContextTokens, setMaxContextTokens] = useState(entity?.capabilities?.context_engineering?.max_context_tokens || 8000);

    // Governance State
    const [maxCostUsd, setMaxCostUsd] = useState<number | undefined>(entity?.governance?.max_cost_usd);
    const [timeoutMs, setTimeoutMs] = useState(entity?.governance?.timeout_ms || 300000);
    const [maxRecursionDepth, setMaxRecursionDepth] = useState(5);
    const [maxToolCalls, setMaxToolCalls] = useState<number | undefined>(undefined);
    const [hitlCheckpoints, setHitlCheckpoints] = useState(entity?.governance?.hitl_checkpoints || []);

    // NEW Logic Gate Additional State
    const [backoffMultiplier, setBackoffMultiplier] = useState(entity?.logic_gate?.retry_policy?.backoff_multiplier || 2.0);
    const [retryOn, setRetryOn] = useState<string[]>(entity?.logic_gate?.retry_policy?.retry_on || ["TOOL_FAILURE", "LLM_ERROR", "TIMEOUT"]);
    const [reviewOnFailure, setReviewOnFailure] = useState(entity?.logic_gate?.review_mechanism?.on_failure || "RETRY");
    const [successCriteria, setSuccessCriteria] = useState<any[]>(entity?.logic_gate?.review_mechanism?.success_criteria || []);

    // NEW Planning Additional State
    const [fallbackBehavior, setFallbackBehavior] = useState(entity?.planning?.static_plan?.fallback_behavior || 'ADAPTIVE');
    const [dynamicConstraints, setDynamicConstraints] = useState<string[]>(entity?.planning?.dynamic_planning?.constraints || []);
    const [reconciliationStrategy, setReconciliationStrategy] = useState(entity?.planning?.dynamic_planning?.reconciliation_strategy || 'HYBRID');
    const [allowedDeviations, setAllowedDeviations] = useState(entity?.planning?.dynamic_planning?.allowed_deviations || {
        can_add_steps: true,
        can_skip_optional_steps: true,
        can_reorder_steps: false,
        can_change_tools: false
    });
    const [iterationContextMode, setIterationContextMode] = useState(entity?.planning?.loop_control?.iteration_context_mode || 'FULL_HISTORY');

    // NEW Capabilities Additional State
    const [memoryStorageBackend, setMemoryStorageBackend] = useState(entity?.capabilities?.memory?.storage_backend || 'POSTGRES_JSONB');
    const [contextPriority, setContextPriority] = useState<string[]>(entity?.capabilities?.context_engineering?.context_priority || ["SYSTEM_PROMPT", "STATIC_PLAN", "USER_INPUT"]);
    const [artifactHandlingMode, setArtifactHandlingMode] = useState(entity?.capabilities?.context_engineering?.artifact_handling?.artifact_reference_mode || 'REFERENCE');

    // NEW IO Contract State
    const [inputSchema, setInputSchema] = useState(JSON.stringify(entity?.io_contract?.input_schema || { type: "object", properties: {} }, null, 2));
    const [outputSchema, setOutputSchema] = useState(JSON.stringify(entity?.io_contract?.output_schema || { type: "object", properties: {} }, null, 2));

    // NEW Observability State
    const [logLevel, setLogLevel] = useState(entity?.observability?.log_level || 'INFO');
    const [logThoughts, setLogThoughts] = useState(entity?.observability?.log_thoughts ?? true);
    const [trackCost, setTrackCost] = useState(entity?.observability?.track_cost ?? true);

    const [availableModels, setAvailableModels] = useState<any[]>([]);

    const [hierarchyNodes, setHierarchyNodes] = useState<Node[]>([]);
    const [hierarchyEdges, setHierarchyEdges] = useState<Edge[]>([]);

    useEffect(() => {
        const fetchModels = async () => {
            try {
                const models = await integrationService.getModels();
                setAvailableModels(models);

                const providers = Array.from(new Set(models.map(m => m.provider))).filter(p => p !== 'openai');
                const currentProviderValid = providers.includes(modelProvider);

                if ((!currentProviderValid || !modelName) && models.length > 0) {
                    const geminiModel = models.find(m => m.model_key.includes('gemini'));
                    const defaultModel = geminiModel || models[0];
                    setModelProvider(defaultModel.provider);
                    setModelName(defaultModel.model_key);
                } else if (currentProviderValid && models.length > 0) {
                    const modelsForProvider = models.filter(m => m.provider === modelProvider);
                    const currentModelValid = modelsForProvider.some(m => m.model_key === modelName);
                    if (!currentModelValid && modelsForProvider.length > 0) {
                        setModelName(modelsForProvider[0].model_key);
                    }
                }
            } catch (error) {
                console.error('Failed to fetch models:', error);
            }
        };
        fetchModels();
    }, []);

    // Initialize Hierarchy Nodes from Entity Steps
    useEffect(() => {
        if (entity?.planning?.static_plan?.steps && entity.planning.static_plan.steps.length > 0) {
            const steps = entity.planning.static_plan.steps;
            const nodes: Node[] = steps.map((step: any, idx: number) => {
                const isEntity = step.type === 'CHILD_ENTITY_INVOCATION';
                const isTool = step.type === 'TOOL_CALL';

                return {
                    id: step.step_id || crypto.randomUUID(),
                    type: isEntity ? 'entityNode' : isTool ? 'toolNode' : 'defaultNode',
                    position: { x: 400, y: 100 + idx * 150 },
                    data: {
                        label: step.name,
                        description: step.description,
                        required: step.required,
                        entityRef: step.target?.entity_id ? { id: step.target.entity_id } : undefined,
                        toolRef: step.target?.tool_id ? { tool_id: step.target.tool_id } : undefined,
                    }
                };
            });

            setHierarchyNodes(nodes);

            // Create default sequential edges if no edge logic is stored
            const edges: Edge[] = [];
            for (let i = 0; i < nodes.length - 1; i++) {
                edges.push({
                    id: `e${nodes[i].id}-${nodes[i + 1].id}`,
                    source: nodes[i].id,
                    target: nodes[i + 1].id,
                    animated: true,
                });
            }
            setHierarchyEdges(edges);
        }
    }, [entity?.id]); // Only re-run when actual entity ID changes (loaded)

    const addTag = () => {
        if (tagInput.trim() && !tags.includes(tagInput.trim())) {
            setTags([...tags, tagInput.trim()]);
            setTagInput('');
        }
    };

    const removeTag = (tag: string) => {
        setTags(tags.filter(t => t !== tag));
    };

    const addConstraint = () => {
        if (constraintInput.trim()) {
            setBehavioralConstraints([...behavioralConstraints, constraintInput.trim()]);
            setConstraintInput('');
        }
    };

    const removeConstraint = (index: number) => {
        setBehavioralConstraints(behavioralConstraints.filter((_, i) => i !== index));
    };

    const addExample = () => {
        setExamples([...examples, { scenario: '', ideal_response: '' }]);
    };

    const updateExample = (index: number, field: 'scenario' | 'ideal_response', value: string) => {
        const updated = [...examples];
        updated[index][field] = value;
        setExamples(updated);
    };

    const removeExample = (index: number) => {
        setExamples(examples.filter((_, i) => i !== index));
    };

    const handleSave = () => {
        const entityData = {
            name,
            display_name: displayName,
            type,
            description,
            version,
            status,
            tags,

            identity: {
                persona: {
                    system_prompt: systemPrompt,
                    examples,
                    behavioral_constraints: behavioralConstraints,
                    few_shot_examples: fewShotExamples,
                }
            },

            logic_gate: {
                reasoning_config: {
                    model_provider: modelProvider,
                    model_name: modelName,
                    temperature,
                    top_p: topP,
                    max_tokens: maxTokens,
                    reasoning_mode: reasoningMode,
                },
                retry_policy: {
                    max_retries: maxRetries,
                    backoff_strategy: backoffStrategy,
                    backoff_multiplier: backoffMultiplier,
                    retry_on: retryOn,
                },
                review_mechanism: {
                    enabled: reviewEnabled,
                    review_prompt: reviewPrompt,
                    on_failure: reviewOnFailure,
                    success_criteria: successCriteria,
                },
                context_policy: {
                    type: contextPolicyType,
                    n: contextPolicyN,
                    max_chars: contextPolicyMaxChars,
                    summarize_threshold: contextPolicySummarizeThreshold,
                }
            },

            planning: {
                static_plan: {
                    enabled: staticPlanEnabled,
                    steps: convertNodesToSteps(hierarchyNodes, hierarchyEdges),
                    fallback_behavior: fallbackBehavior,
                },
                dynamic_planning: {
                    enabled: dynamicPlanningEnabled,
                    planning_prompt: planningPrompt,
                    constraints: dynamicConstraints,
                    reconciliation_strategy: reconciliationStrategy,
                    allowed_deviations: allowedDeviations,
                },
                loop_control: {
                    max_iterations: maxIterations,
                    iteration_context_mode: iterationContextMode,
                }
            },

            capabilities: {
                tools: selectedTools.map(toolName => ({ tool_id: toolName })),
                memory: {
                    enabled: memoryEnabled,
                    scope: memoryScope,
                    storage_backend: memoryStorageBackend,
                },
                context_engineering: {
                    max_context_tokens: maxContextTokens,
                    context_priority: contextPriority,
                    artifact_handling: {
                        artifact_reference_mode: artifactHandlingMode,
                        store_large_objects: true,
                    }
                }
            },

            governance: {
                max_cost_usd: maxCostUsd,
                timeout_ms: timeoutMs,
                execution_limits: {
                    max_recursion_depth: maxRecursionDepth,
                    max_tool_calls: maxToolCalls,
                },
                hitl_checkpoints: hitlCheckpoints,
            },

            io_contract: {
                input_schema: JSON.parse(inputSchema),
                output_schema: JSON.parse(outputSchema),
            },

            observability: {
                log_level: logLevel,
                log_thoughts: logThoughts,
                track_cost: trackCost,
            },

            hierarchy: {
                children: extractChildrenFromGraph(hierarchyNodes, hierarchyEdges),
                is_atomic: hierarchyNodes.length === 0,
            },
        };

        onSave(entityData);
    };

    const convertNodesToSteps = (nodes: Node[], edges: Edge[]) => {
        // Convert ReactFlow nodes/edges to static plan steps
        return nodes
            .filter(n => n.id !== 'root')
            .map((node, idx) => {
                // Find incoming edges to determine dependencies
                const dependencies = edges
                    .filter(e => e.target === node.id)
                    .map(e => e.source);

                return {
                    step_id: node.id,
                    order: idx + 1, // Visual order, but dependencies dictate execution
                    name: node.data.label,
                    description: node.data.description || '',
                    type: node.data.entityRef ? 'CHILD_ENTITY_INVOCATION' : node.data.toolRef ? 'TOOL_CALL' : 'ACTION',
                    target: {
                        entity_id: node.data.entityRef?.id,
                        tool_id: node.data.toolRef?.tool_id,
                        prompt_template: !node.data.entityRef && !node.data.toolRef ? node.data.description : undefined,
                        input_dependencies: dependencies.length > 0 ? dependencies : undefined,
                    },
                    required: node.data.required ?? true,
                };
            });
    };

    const extractChildrenFromGraph = (nodes: Node[], edges: Edge[]) => {
        // Extract unique child entities from the graph
        return nodes
            .filter(n => n.data.entityRef)
            .map(n => ({
                child_id: n.data.entityRef.id,
                child_type: n.data.entityRef.type,
                relationship: 'SEQUENTIAL', // Default, can be enhanced
            }));
    };

    // Group available models by provider
    const providers = Array.from(new Set(availableModels.map(m => m.provider)));
    const modelsByProvider: Record<string, string[]> = {};
    providers.forEach(p => {
        modelsByProvider[p] = availableModels.filter(m => m.provider === p).map(m => m.model_key);
    });

    const tabs = [
        { id: 'overview', label: 'Overview', icon: Info },
        { id: 'identity', label: 'Identity', icon: Brain },
        { id: 'logic', label: 'Logic Gate', icon: Settings },
        { id: 'planning', label: 'Planning', icon: Route },
        { id: 'capabilities', label: 'Capabilities', icon: Wrench },
        { id: 'governance', label: 'Governance', icon: Shield },
        { id: 'contract', label: 'IO Contract', icon: Layers },
        { id: 'observability', label: 'Observability', icon: Settings },
        { id: 'hierarchy', label: 'Hierarchy', icon: Layers },
    ];

    return (
        <div className="entity-configuration-tabs">
            <div className="tabs-header">
                {tabs.map(tab => (
                    <button
                        key={tab.id}
                        className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
                        onClick={() => setActiveTab(tab.id)}
                    >
                        <tab.icon size={16} />
                        {tab.label}
                    </button>
                ))}
            </div>

            <div className="tabs-content">
                {activeTab === 'overview' && (
                    <div className="tab-panel">
                        <div className="form-section">
                            <h3>Basic Information</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Name (ID) *</label>
                                    <input
                                        type="text"
                                        value={name}
                                        onChange={(e) => setName(e.target.value)}
                                        placeholder="unique_entity_name"
                                    />
                                    <small>Unique identifier, lowercase with underscores</small>
                                </div>
                                <div className="form-group">
                                    <label>Display Name</label>
                                    <input
                                        type="text"
                                        value={displayName}
                                        onChange={(e) => setDisplayName(e.target.value)}
                                        placeholder="Human-friendly Name"
                                    />
                                </div>
                            </div>

                            <div className="form-row">
                                <div className="form-group">
                                    <label>Entity Type *</label>
                                    <select value={type} onChange={(e) => setType(e.target.value as EntityType)}>
                                        {Object.values(EntityType).map(t => (
                                            <option key={t} value={t}>{t}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Status</label>
                                    <select value={status} onChange={(e) => setStatus(e.target.value as EntityStatus)}>
                                        {Object.values(EntityStatus).map(s => (
                                            <option key={s} value={s}>{s}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Version</label>
                                    <input
                                        type="text"
                                        value={version}
                                        onChange={(e) => setVersion(e.target.value)}
                                        placeholder="1.0.0"
                                    />
                                </div>
                            </div>

                            <div className="form-group">
                                <label>Description</label>
                                <textarea
                                    value={description}
                                    onChange={(e) => setDescription(e.target.value)}
                                    placeholder="Describe what this entity does..."
                                    rows={4}
                                />
                            </div>

                            <div className="form-group">
                                <label>Tags</label>
                                <div className="tag-input-wrapper">
                                    <input
                                        type="text"
                                        value={tagInput}
                                        onChange={(e) => setTagInput(e.target.value)}
                                        onKeyPress={(e) => e.key === 'Enter' && addTag()}
                                        placeholder="Add tag..."
                                    />
                                    <JellyButton size="sm" onClick={addTag}>
                                        <Plus size={16} />
                                    </JellyButton>
                                </div>
                                <div className="tag-list">
                                    {tags.map(tag => (
                                        <span key={tag} className="tag">
                                            {tag}
                                            <button onClick={() => removeTag(tag)}>&times;</button>
                                        </span>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'identity' && (
                    <div className="tab-panel">
                        <div className="form-section">
                            <h3>Persona & System Instructions</h3>
                            <div className="form-group">
                                <label>System Prompt</label>
                                <textarea
                                    value={systemPrompt}
                                    onChange={(e) => setSystemPrompt(e.target.value)}
                                    placeholder="Define the role, constraints, tone, and behavior..."
                                    rows={10}
                                    className="code-textarea"
                                />
                                <small>This prompt defines the entity's role and behavior. Used in all LLM calls.</small>
                            </div>

                            <h3>Examples (Few-Shot Learning)</h3>
                            {examples.map((example, idx) => (
                                <div key={idx} className="example-item">
                                    <div className="form-group">
                                        <label>Scenario {idx + 1}</label>
                                        <input
                                            type="text"
                                            value={example.scenario}
                                            onChange={(e) => updateExample(idx, 'scenario', e.target.value)}
                                            placeholder="Describe the situation..."
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>Ideal Response</label>
                                        <textarea
                                            value={example.ideal_response}
                                            onChange={(e) => updateExample(idx, 'ideal_response', e.target.value)}
                                            placeholder="Expected behavior or output..."
                                            rows={3}
                                        />
                                    </div>
                                    <JellyButton variant="danger" size="sm" onClick={() => removeExample(idx)}>
                                        <Trash2 size={14} /> Remove
                                    </JellyButton>
                                </div>
                            ))}
                            <JellyButton onClick={addExample}>
                                <Plus size={16} /> Add Example
                            </JellyButton>

                            <h3>Few-Shot Prompt Examples (Advanced)</h3>
                            <div className="info-box">
                                <small>These examples are injected directly into the prompt context. Use 'input' and 'output' keys.</small>
                            </div>
                            {fewShotExamples.map((ex, idx) => (
                                <div key={`fs-${idx}`} className="example-item">
                                    <div className="form-group">
                                        <label>Input / User</label>
                                        <textarea
                                            value={ex.input || ''}
                                            onChange={(e) => updateFewShot(idx, 'input', e.target.value)}
                                            placeholder="User input..."
                                            rows={2}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label>Output / Model</label>
                                        <textarea
                                            value={ex.output || ''}
                                            onChange={(e) => updateFewShot(idx, 'output', e.target.value)}
                                            placeholder="Expected model response..."
                                            rows={2}
                                        />
                                    </div>
                                    <JellyButton variant="danger" size="sm" onClick={() => removeFewShot(idx)}>
                                        <Trash2 size={14} /> Remove
                                    </JellyButton>
                                </div>
                            ))}
                            <JellyButton onClick={addFewShot}>
                                <Plus size={16} /> Add Few-Shot Pair
                            </JellyButton>

                            <h3 className="mt-4">Behavioral Constraints</h3>
                            <div className="form-group">
                                <div className="tag-input-wrapper">
                                    <input
                                        type="text"
                                        value={constraintInput}
                                        onChange={(e) => setConstraintInput(e.target.value)}
                                        onKeyPress={(e) => e.key === 'Enter' && addConstraint()}
                                        placeholder="e.g., Never contact candidates before 9 AM"
                                    />
                                    <JellyButton size="sm" onClick={addConstraint}>
                                        <Plus size={16} />
                                    </JellyButton>
                                </div>
                                <ul className="constraint-list">
                                    {behavioralConstraints.map((constraint, idx) => (
                                        <li key={idx}>
                                            {constraint}
                                            <button onClick={() => removeConstraint(idx)}>&times;</button>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'logic' && (
                    <div className="tab-panel">
                        <div className="form-section">
                            <h3>LLM Configuration</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Model Provider *</label>
                                    <select value={modelProvider} onChange={(e) => {
                                        setModelProvider(e.target.value);
                                        const modelsForProvider = modelsByProvider[e.target.value] || [];
                                        if (modelsForProvider.length > 0) {
                                            setModelName(modelsForProvider[0]);
                                        }
                                    }}>
                                        {providers.map(p => (
                                            <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
                                        ))}
                                        {providers.length === 0 && <option value="">No Providers Configured</option>}
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Model Name *</label>
                                    <select value={modelName} onChange={(e) => setModelName(e.target.value)}>
                                        {(modelsByProvider[modelProvider] || []).map(model => (
                                            <option key={model} value={model}>{model}</option>
                                        ))}
                                        {(!modelsByProvider[modelProvider] || modelsByProvider[modelProvider].length === 0) && (
                                            <option value="">No Models Available</option>
                                        )}
                                    </select>
                                </div>
                            </div>

                            <div className="form-row">
                                <div className="form-group">
                                    <label>Temperature: {temperature.toFixed(2)}</label>
                                    <input
                                        type="range"
                                        min="0"
                                        max="2"
                                        step="0.1"
                                        value={temperature}
                                        onChange={(e) => setTemperature(parseFloat(e.target.value))}
                                    />
                                    <small>Lower = deterministic, Higher = creative</small>
                                </div>
                                <div className="form-group">
                                    <label>Top P: {topP.toFixed(2)}</label>
                                    <input
                                        type="range"
                                        min="0"
                                        max="1"
                                        step="0.05"
                                        value={topP}
                                        onChange={(e) => setTopP(parseFloat(e.target.value))}
                                    />
                                </div>
                            </div>

                            <div className="form-row">
                                <div className="form-group">
                                    <label>Max Tokens (optional)</label>
                                    <input
                                        type="number"
                                        value={maxTokens || ''}
                                        onChange={(e) => setMaxTokens(e.target.value ? parseInt(e.target.value) : undefined)}
                                        placeholder="Leave empty for no limit"
                                    />
                                </div>
                                <div className="form-group">
                                    <label>Reasoning Mode</label>
                                    <select value={reasoningMode} onChange={(e) => setReasoningMode(e.target.value)}>
                                        <option value="REACT">ReAct (Thought-Action Loop)</option>
                                        <option value="CHAIN_OF_THOUGHT">Chain of Thought</option>
                                        <option value="REFLECTION">Reflection (Self-Critique)</option>
                                        <option value="TREE_OF_THOUGHTS">Tree of Thoughts</option>
                                    </select>
                                </div>
                            </div>

                            <h3>Context Policy</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Policy Type</label>
                                    <select
                                        value={contextPolicyType}
                                        onChange={(e) => setContextPolicyType(e.target.value as any)}
                                    >
                                        <option value="FULL">Full Context</option>
                                        <option value="LAST_N">Last N Steps</option>
                                        <option value="SLIDING_WINDOW">Sliding Window (Chars)</option>
                                        <option value="EXPLICIT">Explicit Keys Only</option>
                                    </select>
                                </div>
                                {contextPolicyType === 'LAST_N' && (
                                    <div className="form-group">
                                        <label>Number of Steps (N)</label>
                                        <input
                                            type="number"
                                            value={contextPolicyN || 3}
                                            onChange={(e) => setContextPolicyN(parseInt(e.target.value))}
                                        />
                                    </div>
                                )}
                                {contextPolicyType === 'SLIDING_WINDOW' && (
                                    <div className="form-group">
                                        <label>Max Characters</label>
                                        <input
                                            type="number"
                                            value={contextPolicyMaxChars || 4000}
                                            onChange={(e) => setContextPolicyMaxChars(parseInt(e.target.value))}
                                        />
                                    </div>
                                )}
                            </div>
                            <div className="form-group">
                                <label>Summarization Threshold (Chars)</label>
                                <input
                                    type="number"
                                    value={contextPolicySummarizeThreshold || 8000}
                                    onChange={(e) => setContextPolicySummarizeThreshold(parseInt(e.target.value))}
                                    placeholder="8000"
                                />
                                <small>Auto-summarize context if it exceeds this size</small>
                            </div>

                            <h3>Retry Policy</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Max Retries</label>
                                    <input
                                        type="number"
                                        value={maxRetries}
                                        onChange={(e) => setMaxRetries(parseInt(e.target.value) || 0)}
                                        min="0"
                                        max="10"
                                    />
                                </div>
                                <div className="form-group">
                                    <label>Backoff Strategy</label>
                                    <select value={backoffStrategy} onChange={(e) => setBackoffStrategy(e.target.value)}>
                                        <option value="EXPONENTIAL">Exponential</option>
                                        <option value="LINEAR">Linear</option>
                                        <option value="NONE">None</option>
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Backoff Multiplier</label>
                                    <input
                                        type="number"
                                        value={backoffMultiplier}
                                        onChange={(e) => setBackoffMultiplier(parseFloat(e.target.value) || 2.0)}
                                        step="0.1"
                                        min="1"
                                    />
                                </div>
                            </div>

                            <div className="form-group">
                                <label>Retry On (Events)</label>
                                <div className="tag-list">
                                    {['TOOL_FAILURE', 'LLM_ERROR', 'TIMEOUT', 'VALIDATION_ERROR'].map(event => (
                                        <label key={event} className="checkbox-label">
                                            <input
                                                type="checkbox"
                                                checked={retryOn.includes(event)}
                                                onChange={(e) => {
                                                    if (e.target.checked) setRetryOn([...retryOn, event]);
                                                    else setRetryOn(retryOn.filter(item => item !== event));
                                                }}
                                            />
                                            {event}
                                        </label>
                                    ))}
                                </div>
                            </div>

                            <h3>Review Mechanism</h3>
                            <div className="form-group">
                                <label className="checkbox-label">
                                    <input
                                        type="checkbox"
                                        checked={reviewEnabled}
                                        onChange={(e) => setReviewEnabled(e.target.checked)}
                                    />
                                    Enable self-review after execution
                                </label>
                            </div>
                            {reviewEnabled && (
                                <div className="form-group">
                                    <label>Review Prompt</label>
                                    <textarea
                                        value={reviewPrompt}
                                        onChange={(e) => setReviewPrompt(e.target.value)}
                                        placeholder="Review your output for quality and accuracy..."
                                        rows={4}
                                    />
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {activeTab === 'planning' && (
                    <div className="tab-panel">
                        <div className="form-section">
                            <h3>Planning Configuration</h3>
                            <div className="form-group">
                                <label className="checkbox-label">
                                    <input
                                        type="checkbox"
                                        checked={staticPlanEnabled}
                                        onChange={(e) => setStaticPlanEnabled(e.target.checked)}
                                    />
                                    Enable Static Plan (predefined steps)
                                </label>
                                <small>Static plans are defined in the Hierarchy tab</small>
                            </div>

                            <div className="form-group">
                                <label>Fallback Behavior</label>
                                <select value={fallbackBehavior} onChange={(e) => setFallbackBehavior(e.target.value)}>
                                    <option value="ADAPTIVE">Adaptive (LLM can adjust order/tools)</option>
                                    <option value="STRICT">Strict (Must follow exactly)</option>
                                    <option value="DYNAMIC_ONLY">Dynamic Only (Ignore static plan)</option>
                                </select>
                            </div>

                            <div className="form-group">
                                <label className="checkbox-label">
                                    <input
                                        type="checkbox"
                                        checked={dynamicPlanningEnabled}
                                        onChange={(e) => setDynamicPlanningEnabled(e.target.checked)}
                                    />
                                    Enable Dynamic Planning (AI-generated plans)
                                </label>
                            </div>

                            {dynamicPlanningEnabled && (
                                <div className="form-group">
                                    <label>Planning Prompt</label>
                                    <textarea
                                        value={planningPrompt}
                                        onChange={(e) => setPlanningPrompt(e.target.value)}
                                        placeholder="Instructions for how to generate dynamic plans..."
                                        rows={6}
                                    />
                                </div>
                            )}

                            {dynamicPlanningEnabled && (
                                <div className="form-row">
                                    <div className="form-group">
                                        <label>Reconciliation Strategy</label>
                                        <select value={reconciliationStrategy} onChange={(e) => setReconciliationStrategy(e.target.value)}>
                                            <option value="HYBRID">Hybrid (Mix Static & Dynamic)</option>
                                            <option value="STATIC_PRIORITY">Static Priority</option>
                                            <option value="DYNAMIC_PRIORITY">Dynamic Priority</option>
                                        </select>
                                    </div>
                                </div>
                            )}

                            {dynamicPlanningEnabled && (
                                <div className="form-group">
                                    <label>Allowed Deviations</label>
                                    <div className="tag-list">
                                        <label className="checkbox-label">
                                            <input type="checkbox" checked={allowedDeviations.can_add_steps} onChange={(e) => setAllowedDeviations({ ...allowedDeviations, can_add_steps: e.target.checked })} />
                                            Can Add Steps
                                        </label>
                                        <label className="checkbox-label">
                                            <input type="checkbox" checked={allowedDeviations.can_skip_optional_steps} onChange={(e) => setAllowedDeviations({ ...allowedDeviations, can_skip_optional_steps: e.target.checked })} />
                                            Can Skip Optional
                                        </label>
                                        <label className="checkbox-label">
                                            <input type="checkbox" checked={allowedDeviations.can_reorder_steps} onChange={(e) => setAllowedDeviations({ ...allowedDeviations, can_reorder_steps: e.target.checked })} />
                                            Can Reorder
                                        </label>
                                        <label className="checkbox-label">
                                            <input type="checkbox" checked={allowedDeviations.can_change_tools} onChange={(e) => setAllowedDeviations({ ...allowedDeviations, can_change_tools: e.target.checked })} />
                                            Can Change Tools
                                        </label>
                                    </div>
                                </div>
                            )}

                            <h3>Loop Control</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Max Iterations</label>
                                    <input
                                        type="number"
                                        value={maxIterations}
                                        onChange={(e) => setMaxIterations(parseInt(e.target.value) || 1)}
                                        min="1"
                                        max="100"
                                    />
                                </div>
                                <div className="form-group">
                                    <label>Iteration Context Mode</label>
                                    <select value={iterationContextMode} onChange={(e) => setIterationContextMode(e.target.value)}>
                                        <option value="FULL_HISTORY">Full History</option>
                                        <option value="SUMMARIZED">Summarized</option>
                                        <option value="LAST_N">Last N Steps</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'capabilities' && (
                    <div className="tab-panel">
                        <div className="form-section">
                            <h3>Tools</h3>
                            <ToolSelectionPanel
                                selectedTools={selectedTools}
                                onChange={setSelectedTools}
                            />

                            <h3 className="mt-4">Memory</h3>
                            <div className="form-group">
                                <label className="checkbox-label">
                                    <input
                                        type="checkbox"
                                        checked={memoryEnabled}
                                        onChange={(e) => setMemoryEnabled(e.target.checked)}
                                    />
                                    Enable Memory
                                </label>
                            </div>
                            {memoryEnabled && (
                                <>
                                    <div className="form-group">
                                        <label>Memory Scope</label>
                                        <select value={memoryScope} onChange={(e) => setMemoryScope(e.target.value)}>
                                            <option value="SESSION">Session (cleared after execution)</option>
                                            <option value="ENTITY">Entity (persists across runs)</option>
                                            <option value="GLOBAL">Global (shared across entities)</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label>Storage Backend</label>
                                        <select value={memoryStorageBackend} onChange={(e) => setMemoryStorageBackend(e.target.value)}>
                                            <option value="POSTGRES_JSONB">Postgres JSONB</option>
                                            <option value="VECTOR_DB">Vector Database</option>
                                            <option value="REDIS">Redis</option>
                                        </select>
                                    </div>
                                </>
                            )}

                            <h3>Context Engineering</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Max Context Tokens</label>
                                    <input
                                        type="number"
                                        value={maxContextTokens}
                                        onChange={(e) => setMaxContextTokens(parseInt(e.target.value) || 8000)}
                                        min="1000"
                                        max="100000"
                                        step="1000"
                                    />
                                </div>
                                <div className="form-group">
                                    <label>Artifact Mode</label>
                                    <select value={artifactHandlingMode} onChange={(e) => setArtifactHandlingMode(e.target.value)}>
                                        <option value="REFERENCE">Reference</option>
                                        <option value="INLINE">Inline</option>
                                        <option value="SUMMARY">Summary</option>
                                    </select>
                                </div>
                            </div>

                            <div className="form-group">
                                <label>Context Priority (order)</label>
                                <div className="tag-list">
                                    {['SYSTEM_PROMPT', 'STATIC_PLAN', 'USER_INPUT', 'MEMORY', 'TOOLS'].map(item => (
                                        <label key={item} className="checkbox-label">
                                            <input
                                                type="checkbox"
                                                checked={contextPriority.includes(item)}
                                                onChange={(e) => {
                                                    if (e.target.checked) setContextPriority([...contextPriority, item]);
                                                    else setContextPriority(contextPriority.filter(p => p !== item));
                                                }}
                                            />
                                            {item}
                                        </label>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'governance' && (
                    <div className="tab-panel">
                        <div className="form-section">
                            <h3>Cost Controls</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Max Cost Per Execution (USD)</label>
                                    <input
                                        type="number"
                                        value={maxCostUsd || ''}
                                        onChange={(e) => setMaxCostUsd(e.target.value ? parseFloat(e.target.value) : undefined)}
                                        placeholder="No limit"
                                        step="0.01"
                                        min="0"
                                    />
                                </div>
                            </div>

                            <h3>Execution Limits</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Timeout (milliseconds)</label>
                                    <input
                                        type="number"
                                        value={timeoutMs}
                                        onChange={(e) => setTimeoutMs(parseInt(e.target.value) || 300000)}
                                        min="1000"
                                        step="1000"
                                    />
                                </div>
                                <div className="form-group">
                                    <label>Max Recursion Depth</label>
                                    <input
                                        type="number"
                                        value={maxRecursionDepth}
                                        onChange={(e) => setMaxRecursionDepth(parseInt(e.target.value) || 5)}
                                        min="1"
                                        max="10"
                                    />
                                </div>
                            </div>
                            <div className="form-group">
                                <label>Max Tool Calls (optional)</label>
                                <input
                                    type="number"
                                    value={maxToolCalls || ''}
                                    onChange={(e) => setMaxToolCalls(e.target.value ? parseInt(e.target.value) : undefined)}
                                    placeholder="No limit"
                                    min="1"
                                />
                            </div>

                            <h3>Human-In-The-Loop (HITL)</h3>
                            <p className="form-hint">Configure approval checkpoints for critical operations (coming soon)</p>
                        </div>
                    </div>
                )}

                {activeTab === 'contract' && (
                    <div className="tab-panel">
                        <div className="form-section">
                            <h3>IO Contract (JSON Schema)</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Input Schema</label>
                                    <textarea
                                        value={inputSchema}
                                        onChange={(e) => setInputSchema(e.target.value)}
                                        placeholder='{ "type": "object", ... }'
                                        rows={15}
                                        className="code-textarea"
                                    />
                                    <small>JSON Schema for input validation</small>
                                </div>
                                <div className="form-group">
                                    <label>Output Schema</label>
                                    <textarea
                                        value={outputSchema}
                                        onChange={(e) => setOutputSchema(e.target.value)}
                                        placeholder='{ "type": "object", ... }'
                                        rows={15}
                                        className="code-textarea"
                                    />
                                    <small>JSON Schema for output validation</small>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'observability' && (
                    <div className="tab-panel">
                        <div className="form-section">
                            <h3>Observability Settings</h3>
                            <div className="form-group">
                                <label>Log Level</label>
                                <select value={logLevel} onChange={(e) => setLogLevel(e.target.value)}>
                                    <option value="DEBUG">Debug</option>
                                    <option value="INFO">Info</option>
                                    <option value="WARN">Warn</option>
                                    <option value="ERROR">Error</option>
                                </select>
                            </div>
                            <div className="form-group mt-4">
                                <label className="checkbox-label">
                                    <input
                                        type="checkbox"
                                        checked={logThoughts}
                                        onChange={(e) => setLogThoughts(e.target.checked)}
                                    />
                                    Log Internal Thoughts/Reasoning
                                </label>
                            </div>
                            <div className="form-group">
                                <label className="checkbox-label">
                                    <input
                                        type="checkbox"
                                        checked={trackCost}
                                        onChange={(e) => setTrackCost(e.target.checked)}
                                    />
                                    Track Execution Cost & Tokens
                                </label>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'hierarchy' && (
                    <div className="tab-panel hierarchy-tab">
                        <div className="hierarchy-hint">
                            <Info size={16} />
                            <span>Drag entities and tools onto the canvas to define execution flow</span>
                        </div>
                        <EntityFlow
                            initialNodes={hierarchyNodes}
                            initialEdges={hierarchyEdges}
                            onSave={(nodes, edges) => {
                                setHierarchyNodes(nodes);
                                setHierarchyEdges(edges);
                            }}
                        />
                    </div>
                )}
            </div>

            <div className="tabs-footer">
                <JellyButton variant="ghost" onClick={onCancel}>Cancel</JellyButton>
                <JellyButton roseGold onClick={handleSave}>Save Entity</JellyButton>
            </div>
        </div>
    );
};
