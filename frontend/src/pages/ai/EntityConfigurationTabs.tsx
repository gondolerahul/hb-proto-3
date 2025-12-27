import React, { useState, useEffect } from 'react';
import { ToolSelectionPanel } from '@/components/ToolSelectionPanel';
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
    const [behavioralConstraints, setBehavioralConstraints] = useState(entity?.identity?.behavioral_constraints || []);
    const [constraintInput, setConstraintInput] = useState('');

    // Logic Gate State
    const [modelProvider, setModelProvider] = useState(entity?.logic_gate?.reasoning_config?.model_provider || 'google');
    const [modelName, setModelName] = useState(entity?.logic_gate?.reasoning_config?.model_name || 'gemini-2.0-flash-exp');
    const [temperature, setTemperature] = useState(entity?.logic_gate?.reasoning_config?.temperature || 0.7);
    const [topP, setTopP] = useState(entity?.logic_gate?.reasoning_config?.top_p || 1.0);
    const [maxTokens, setMaxTokens] = useState<number | undefined>(entity?.logic_gate?.reasoning_config?.max_tokens);
    const [reasoningMode, setReasoningMode] = useState(entity?.logic_gate?.reasoning_config?.reasoning_mode || 'REACT');
    const [maxRetries, setMaxRetries] = useState(entity?.logic_gate?.retry_policy?.max_retries || 3);
    const [backoffStrategy, setBackoffStrategy] = useState(entity?.logic_gate?.retry_policy?.backoff_strategy || 'EXPONENTIAL');
    const [reviewEnabled, setReviewEnabled] = useState(entity?.logic_gate?.review_mechanism?.enabled || false);
    const [reviewPrompt, setReviewPrompt] = useState(entity?.logic_gate?.review_mechanism?.review_prompt || '');

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

    // Hierarchy State
    const [hierarchyNodes, setHierarchyNodes] = useState<Node[]>([]);
    const [hierarchyEdges, setHierarchyEdges] = useState<Edge[]>([]);

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
                },
                review_mechanism: {
                    enabled: reviewEnabled,
                    review_prompt: reviewPrompt,
                }
            },

            planning: {
                static_plan: {
                    enabled: staticPlanEnabled,
                    steps: convertNodesToSteps(hierarchyNodes, hierarchyEdges),
                },
                dynamic_planning: {
                    enabled: dynamicPlanningEnabled,
                    planning_prompt: planningPrompt,
                },
                loop_control: {
                    max_iterations: maxIterations,
                }
            },

            capabilities: {
                tools: selectedTools.map(toolName => ({ tool_id: toolName })),
                memory: {
                    enabled: memoryEnabled,
                    scope: memoryScope,
                },
                context_engineering: {
                    max_context_tokens: maxContextTokens,
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
            .map((node, idx) => ({
                step_id: node.id,
                order: idx + 1,
                name: node.data.label,
                description: node.data.description || '',
                type: node.data.entityRef ? 'CHILD_ENTITY_INVOCATION' : node.data.toolRef ? 'TOOL_CALL' : 'ACTION',
                target: {
                    entity_id: node.data.entityRef?.id,
                    tool_id: node.data.toolRef?.tool_id,
                    prompt_template: !node.data.entityRef && !node.data.toolRef ? node.data.description : undefined,
                },
                required: node.data.required ?? true,
            }));
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

    const models: Record<string, string[]> = {
        google: ['gemini-2.0-flash-exp', 'gemini-1.5-pro', 'gemini-1.5-flash'],
        openai: ['gpt-4o', 'gpt-4-turbo', 'gpt-3.5-turbo'],
        anthropic: ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229'],
    };

    const tabs = [
        { id: 'overview', label: 'Overview', icon: Info },
        { id: 'identity', label: 'Identity', icon: Brain },
        { id: 'logic', label: 'Logic Gate', icon: Settings },
        { id: 'planning', label: 'Planning', icon: Route },
        { id: 'capabilities', label: 'Capabilities', icon: Wrench },
        { id: 'governance', label: 'Governance', icon: Shield },
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
                                        setModelName(models[e.target.value][0]);
                                    }}>
                                        <option value="google">Google</option>
                                        <option value="openai">OpenAI</option>
                                        <option value="anthropic">Anthropic</option>
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Model Name *</label>
                                    <select value={modelName} onChange={(e) => setModelName(e.target.value)}>
                                        {models[modelProvider].map(model => (
                                            <option key={model} value={model}>{model}</option>
                                        ))}
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

                            <h3>Loop Control</h3>
                            <div className="form-group">
                                <label>Max Iterations</label>
                                <input
                                    type="number"
                                    value={maxIterations}
                                    onChange={(e) => setMaxIterations(parseInt(e.target.value) || 1)}
                                    min="1"
                                    max="100"
                                />
                                <small>Prevents infinite loops</small>
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
                                <div className="form-group">
                                    <label>Memory Scope</label>
                                    <select value={memoryScope} onChange={(e) => setMemoryScope(e.target.value)}>
                                        <option value="SESSION">Session (cleared after execution)</option>
                                        <option value="ENTITY">Entity (persists across runs)</option>
                                        <option value="GLOBAL">Global (shared across entities)</option>
                                    </select>
                                </div>
                            )}

                            <h3>Context Engineering</h3>
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
                                <small>Hard limit for prompt size to prevent overflow</small>
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
