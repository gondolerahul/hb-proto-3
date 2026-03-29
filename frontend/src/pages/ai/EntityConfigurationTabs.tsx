import React, { useState, useEffect } from 'react';
import { ToolSelectionPanel } from '@/components/ToolSelectionPanel';
import { JellyButton } from '@/components/ui';
import { Info, Brain, Settings, Route, Wrench, Shield, Layers, Plus, Trash2, User, Mic, Sliders, Key } from 'lucide-react';
import { EntityType, EntityStatus, HierarchicalEntity } from '@/types';
import { EntityFlow } from './EntityFlow';
import { Node, Edge } from 'reactflow';
import './EntityConfigurationTabs.css';

const GEMINI_VOICES = [
    'Aoede', 'Puck', 'Charon', 'Kore', 'Fenrir', 'Orbit', 'Zephyr', 'Leda',
    'Orus', 'Rigel', 'Schedar', 'Pulcherrima', 'Achird', 'Zubenelgenubi',
    'Vindemiatrix', 'Sadachbia', 'Sadaltager', 'Sulafat',
];

interface EntityConfigurationTabsProps {
    entity?: HierarchicalEntity;
    onSave: (entityData: any) => void;
    onCancel: () => void;
}

export const EntityConfigurationTabs: React.FC<EntityConfigurationTabsProps> = ({ entity, onSave, onCancel }) => {
    const [activeTab, setActiveTab] = useState('overview');

    // ── Overview State ────────────────────────────────────────────────────────
    const [name, setName] = useState(entity?.name || '');
    const [displayName, setDisplayName] = useState(entity?.display_name || '');
    const [type, setType] = useState<EntityType>(entity?.type || EntityType.AGENT);
    const [description, setDescription] = useState(entity?.description || '');
    const [goal, setGoal] = useState(entity?.goal || '');
    const [version, setVersion] = useState(entity?.version || '1.0.0');
    const [status, setStatus] = useState<EntityStatus>(entity?.status || EntityStatus.DRAFT);
    const [tags, setTags] = useState<string[]>(entity?.tags || []);
    const [tagInput, setTagInput] = useState('');

    // ── Identity State — AgentPersona ─────────────────────────────────────────
    const [personaName, setPersonaName] = useState(entity?.identity?.name || '');
    const [personaRole, setPersonaRole] = useState(entity?.identity?.role || '');
    const [personaBio, setPersonaBio] = useState(entity?.identity?.bio || '');
    const [profileImageUrl, setProfileImageUrl] = useState(entity?.identity?.profile_image_url || '');

    // Personality Matrix
    const [tone, setTone] = useState(entity?.identity?.personality?.tone || 'professional');
    const [verbosity, setVerbosity] = useState(entity?.identity?.personality?.verbosity || 'concise');
    const [empathyLevel, setEmpathyLevel] = useState<number>(entity?.identity?.personality?.empathy_level ?? 0.7);
    const [humorLevel, setHumorLevel] = useState<number>(entity?.identity?.personality?.humor_level ?? 0.2);
    const [formality, setFormality] = useState(entity?.identity?.personality?.formality || 'semi-formal');
    const [decisionConfidence, setDecisionConfidence] = useState<number>(entity?.identity?.personality?.decision_confidence ?? 0.8);

    // Voice Config
    const [voiceName, setVoiceName] = useState(entity?.identity?.voice?.voice_name || 'Aoede');
    const [languageCode, setLanguageCode] = useState(entity?.identity?.voice?.language_code || 'en-US');
    const [speakingRate, setSpeakingRate] = useState<number>(entity?.identity?.voice?.speaking_rate ?? 1.0);
    const [voicePitch, setVoicePitch] = useState<number>(entity?.identity?.voice?.pitch ?? 0.0);

    // Prompt engineering
    const [systemPrompt, setSystemPrompt] = useState(entity?.identity?.system_prompt || '');
    const [fewShotExamples, setFewShotExamples] = useState<{ [key: string]: string }[]>(entity?.identity?.few_shot_examples || []);
    const [behavioralConstraints, setBehavioralConstraints] = useState<string[]>(entity?.identity?.behavioral_constraints || []);
    const [constraintInput, setConstraintInput] = useState('');

    // Dynamic injection hooks
    const [greetingTemplate, setGreetingTemplate] = useState(entity?.identity?.greeting_template || '');
    const [escalationMessage, setEscalationMessage] = useState(entity?.identity?.escalation_message || '');
    const [closingMessage, setClosingMessage] = useState(entity?.identity?.closing_message || '');

    // ── Logic Gate State ──────────────────────────────────────────────────────
    const [taskType, setTaskType] = useState(entity?.logic_gate?.reasoning_config?.task_type || 'text_generation');
    const [temperature, setTemperature] = useState(entity?.logic_gate?.reasoning_config?.temperature || 0.7);
    const [topP, setTopP] = useState(entity?.logic_gate?.reasoning_config?.top_p || 1.0);
    const [maxTokens, setMaxTokens] = useState<number | undefined>(entity?.logic_gate?.reasoning_config?.max_tokens);
    const [reasoningMode, setReasoningMode] = useState(entity?.logic_gate?.reasoning_config?.reasoning_mode || 'REACT');
    const [maxRetries, setMaxRetries] = useState(entity?.logic_gate?.retry_policy?.max_retries || 3);
    const [backoffStrategy, setBackoffStrategy] = useState(entity?.logic_gate?.retry_policy?.backoff_strategy || 'EXPONENTIAL');
    const [backoffMultiplier, setBackoffMultiplier] = useState(entity?.logic_gate?.retry_policy?.backoff_multiplier || 2.0);
    const [retryOn, setRetryOn] = useState<string[]>(entity?.logic_gate?.retry_policy?.retry_on || ['TOOL_FAILURE', 'LLM_ERROR', 'TIMEOUT']);
    const [reviewEnabled, setReviewEnabled] = useState(entity?.logic_gate?.review_mechanism?.enabled || false);
    const [reviewPrompt, setReviewPrompt] = useState(entity?.logic_gate?.review_mechanism?.review_prompt || '');
    const [reviewOnFailure, setReviewOnFailure] = useState(entity?.logic_gate?.review_mechanism?.on_failure || 'RETRY');
    const [successCriteria] = useState<any[]>(entity?.logic_gate?.review_mechanism?.success_criteria || []);

    // Context Policy
    const [contextPolicyType, setContextPolicyType] = useState<'FULL' | 'LAST_N' | 'SLIDING_WINDOW' | 'EXPLICIT'>(entity?.logic_gate?.context_policy?.type || 'FULL');
    const [contextPolicyN, setContextPolicyN] = useState<number | undefined>(entity?.logic_gate?.context_policy?.n);
    const [contextPolicyMaxChars, setContextPolicyMaxChars] = useState<number | undefined>(entity?.logic_gate?.context_policy?.max_chars);
    const [contextPolicySummarizeThreshold, setContextPolicySummarizeThreshold] = useState<number | undefined>(entity?.logic_gate?.context_policy?.summarize_threshold);
    const [preserveKeys, setPreserveKeys] = useState<string[]>(entity?.logic_gate?.context_policy?.preserve_keys || []);
    const [preserveKeyInput, setPreserveKeyInput] = useState('');

    // ── Planning State ────────────────────────────────────────────────────────
    const [staticPlanEnabled, setStaticPlanEnabled] = useState(entity?.planning?.static_plan?.enabled ?? true);
    const [fallbackBehavior, setFallbackBehavior] = useState(entity?.planning?.static_plan?.fallback_behavior || 'ADAPTIVE');
    const [dynamicPlanningEnabled, setDynamicPlanningEnabled] = useState(entity?.planning?.dynamic_planning?.enabled ?? false);
    const [planningPrompt, setPlanningPrompt] = useState(entity?.planning?.dynamic_planning?.planning_prompt || '');
    const [reconciliationStrategy, setReconciliationStrategy] = useState(entity?.planning?.dynamic_planning?.reconciliation_strategy || 'HYBRID');
    const [allowedDeviations, setAllowedDeviations] = useState(entity?.planning?.dynamic_planning?.allowed_deviations || {
        can_add_steps: true, can_skip_optional_steps: true, can_reorder_steps: false, can_change_tools: false
    });
    const [maxIterations, setMaxIterations] = useState(entity?.planning?.loop_control?.max_iterations || 10);
    const [iterationContextMode, setIterationContextMode] = useState(entity?.planning?.loop_control?.iteration_context_mode || 'FULL_HISTORY');

    // ── Capabilities State ────────────────────────────────────────────────────
    const [selectedTools, setSelectedTools] = useState<string[]>(
        entity?.capabilities?.tools?.map((t: any) => t.tool_id || t) || []
    );
    const [memoryEnabled, setMemoryEnabled] = useState(entity?.capabilities?.memory?.enabled || false);
    const [memoryMode, setMemoryMode] = useState(entity?.capabilities?.memory?.mode || 'STANDARD');
    // STANDARD mode
    const [episodicMemoryCount, setEpisodicMemoryCount] = useState(entity?.capabilities?.memory?.episodic_memory_count || 10);
    const [semanticSearchEnabled, setSemanticSearchEnabled] = useState(entity?.capabilities?.memory?.semantic_search_enabled ?? true);
    const [semanticTopK, setSemanticTopK] = useState(entity?.capabilities?.memory?.semantic_top_k || 5);
    // CORTEX mode
    const [cortexMaxChildren, setCortexMaxChildren] = useState(entity?.capabilities?.memory?.cortex_config?.max_children || 12);
    const [cortexPageSize, setCortexPageSize] = useState(entity?.capabilities?.memory?.cortex_config?.page_size_tokens || 8000);
    const [cortexContextBudget, setCortexContextBudget] = useState(entity?.capabilities?.memory?.cortex_config?.context_budget_pct || 40);
    const [cortexAutoCheckpoint, setCortexAutoCheckpoint] = useState(entity?.capabilities?.memory?.cortex_config?.auto_checkpoint ?? true);
    const [cortexResumeEnabled, setCortexResumeEnabled] = useState(entity?.capabilities?.memory?.cortex_config?.resume_enabled ?? true);
    // Context Engineering (CORTEX-native)
    const [injectEpisodicMemory, setInjectEpisodicMemory] = useState(entity?.capabilities?.context_engineering?.inject_episodic_memory ?? true);
    const [injectSemanticContext, setInjectSemanticContext] = useState(entity?.capabilities?.context_engineering?.inject_semantic_context ?? true);
    const [injectCortexViewport, setInjectCortexViewport] = useState(entity?.capabilities?.context_engineering?.inject_cortex_viewport ?? true);
    const [noTruncation, setNoTruncation] = useState(entity?.capabilities?.context_engineering?.no_truncation ?? true);
    // Context Sources
    const [contextSources, setContextSources] = useState<any[]>(entity?.capabilities?.context_engineering?.context_sources || []);

    // ── Governance State ──────────────────────────────────────────────────────
    const [maxCostUsd, setMaxCostUsd] = useState<number | undefined>(entity?.governance?.max_cost_usd);
    const [timeoutMs, setTimeoutMs] = useState(entity?.governance?.timeout_ms || 300000);
    const [maxRecursionDepth, setMaxRecursionDepth] = useState(entity?.governance?.execution_limits?.max_recursion_depth || 5);
    const [maxToolCalls, setMaxToolCalls] = useState<number | undefined>(entity?.governance?.execution_limits?.max_tool_calls);
    const [hitlCheckpoints] = useState(entity?.governance?.hitl_checkpoints || []);
    const [checkpointEveryNSteps, setCheckpointEveryNSteps] = useState(entity?.governance?.checkpoint_every_n_steps || 3);
    const [longRunning, setLongRunning] = useState<boolean>(entity?.governance?.long_running ?? true);

    // ── IO Contract State ─────────────────────────────────────────────────────
    const [inputSchema, setInputSchema] = useState(JSON.stringify(entity?.io_contract?.input_schema || { type: 'object', properties: {} }, null, 2));
    const [outputSchema, setOutputSchema] = useState(JSON.stringify(entity?.io_contract?.output_schema || { type: 'object', properties: {} }, null, 2));

    // ── Observability State ───────────────────────────────────────────────────
    const [logLevel, setLogLevel] = useState(entity?.observability?.log_level || 'INFO');
    const [logThoughts, setLogThoughts] = useState(entity?.observability?.log_thoughts ?? true);
    const [trackCost, setTrackCost] = useState(entity?.observability?.track_cost ?? true);

    const [hierarchyNodes, setHierarchyNodes] = useState<Node[]>([]);
    const [hierarchyEdges, setHierarchyEdges] = useState<Edge[]>([]);

    useEffect(() => {
        if (entity?.planning?.static_plan?.steps && entity.planning.static_plan.steps.length > 0) {
            const steps = entity.planning.static_plan.steps;
            const nodes: Node[] = steps.map((step: any, idx: number) => ({
                id: step.step_id || crypto.randomUUID(),
                type: step.type === 'CHILD_ENTITY_INVOCATION' ? 'entityNode' : step.type === 'TOOL_CALL' ? 'toolNode' : 'defaultNode',
                position: { x: 400, y: 100 + idx * 150 },
                data: {
                    label: step.name, description: step.description, required: step.required,
                    entityRef: step.target?.entity_id ? { id: step.target.entity_id } : undefined,
                    toolRef: step.target?.tool_id ? { tool_id: step.target.tool_id } : undefined,
                    stepType: step.type,
                }
            }));
            setHierarchyNodes(nodes);
            const edges: Edge[] = [];
            for (let i = 0; i < nodes.length - 1; i++) {
                edges.push({ id: `e${nodes[i].id}-${nodes[i + 1].id}`, source: nodes[i].id, target: nodes[i + 1].id, animated: true, label: 'SEQUENTIAL' });
            }
            setHierarchyEdges(edges);
        }
    }, [entity?.id]);

    // ── Tag Handlers ──────────────────────────────────────────────────────────
    const addTag = () => {
        if (tagInput.trim() && !tags.includes(tagInput.trim())) { setTags([...tags, tagInput.trim()]); setTagInput(''); }
    };
    const removeTag = (tag: string) => setTags(tags.filter(t => t !== tag));

    // ── Constraint Handlers ───────────────────────────────────────────────────
    const addConstraint = () => {
        if (constraintInput.trim()) { setBehavioralConstraints([...behavioralConstraints, constraintInput.trim()]); setConstraintInput(''); }
    };
    const removeConstraint = (idx: number) => setBehavioralConstraints(behavioralConstraints.filter((_, i) => i !== idx));

    // ── Few-Shot Handlers ─────────────────────────────────────────────────────
    const addFewShot = () => setFewShotExamples([...fewShotExamples, { input: '', output: '' }]);
    const updateFewShot = (idx: number, key: string, value: string) => {
        const u = [...fewShotExamples]; u[idx] = { ...u[idx], [key]: value }; setFewShotExamples(u);
    };
    const removeFewShot = (idx: number) => setFewShotExamples(fewShotExamples.filter((_, i) => i !== idx));

    // ── Preserve Key Handlers ─────────────────────────────────────────────────
    const addPreserveKey = () => {
        if (preserveKeyInput.trim() && !preserveKeys.includes(preserveKeyInput.trim())) {
            setPreserveKeys([...preserveKeys, preserveKeyInput.trim()]); setPreserveKeyInput('');
        }
    };
    const removePreserveKey = (key: string) => setPreserveKeys(preserveKeys.filter(k => k !== key));

    // ── Convert graph → steps/children ───────────────────────────────────────
    const convertNodesToSteps = (nodes: Node[], edges: Edge[]) =>
        nodes.filter(n => n.id !== 'root').map((node, idx) => ({
            step_id: node.id, order: idx + 1, name: node.data.label,
            description: node.data.description || '',
            type: node.data.entityRef ? 'CHILD_ENTITY_INVOCATION' : node.data.toolRef ? 'TOOL_CALL' : (node.data.stepType || 'ACTION'),
            target: {
                entity_id: node.data.entityRef?.id, tool_id: node.data.toolRef?.tool_id,
                prompt_template: !node.data.entityRef && !node.data.toolRef ? node.data.description : undefined,
                input_dependencies: edges.filter(e => e.target === node.id).map(e => e.source),
            },
            required: node.data.required ?? true,
        }));

    const extractChildrenFromGraph = (nodes: Node[], edges: Edge[]) =>
        nodes.filter(n => n.data.entityRef).map(n => ({
            child_id: n.data.entityRef.id, child_type: n.data.entityRef.type,
            relationship: edges.find(e => e.target === n.id)?.label || 'SEQUENTIAL',
        }));

    // ── Save ──────────────────────────────────────────────────────────────────
    const handleSave = () => {
        const entityData = {
            name, display_name: displayName, type, description, goal, version, status, tags,

            identity: {
                name: personaName, role: personaRole, bio: personaBio || undefined,
                profile_image_url: profileImageUrl || undefined,
                personality: { tone, verbosity, empathy_level: empathyLevel, humor_level: humorLevel, formality, decision_confidence: decisionConfidence },
                voice: { voice_name: voiceName, language_code: languageCode, speaking_rate: speakingRate, pitch: voicePitch },
                system_prompt: systemPrompt,
                behavioral_constraints: behavioralConstraints,
                few_shot_examples: fewShotExamples,
                greeting_template: greetingTemplate || undefined,
                escalation_message: escalationMessage || undefined,
                closing_message: closingMessage || undefined,
            },

            logic_gate: {
                reasoning_config: { task_type: taskType, temperature, top_p: topP, max_tokens: maxTokens, reasoning_mode: reasoningMode },
                retry_policy: { max_retries: maxRetries, backoff_strategy: backoffStrategy, backoff_multiplier: backoffMultiplier, retry_on: retryOn },
                review_mechanism: { enabled: reviewEnabled, review_prompt: reviewPrompt, on_failure: reviewOnFailure, success_criteria: successCriteria },
                context_policy: { type: contextPolicyType, n: contextPolicyN, max_chars: contextPolicyMaxChars, summarize_threshold: contextPolicySummarizeThreshold, preserve_keys: preserveKeys },
            },

            planning: {
                static_plan: { enabled: staticPlanEnabled, steps: convertNodesToSteps(hierarchyNodes, hierarchyEdges), fallback_behavior: fallbackBehavior },
                dynamic_planning: { enabled: dynamicPlanningEnabled, planning_prompt: planningPrompt, reconciliation_strategy: reconciliationStrategy, allowed_deviations: allowedDeviations },
                loop_control: { max_iterations: maxIterations, iteration_context_mode: iterationContextMode },
            },

            capabilities: {
                tools: selectedTools.map(toolName => ({ tool_id: toolName })),
                memory: {
                    enabled: memoryEnabled,
                    mode: memoryMode,
                    episodic_memory_count: episodicMemoryCount,
                    semantic_search_enabled: semanticSearchEnabled,
                    semantic_top_k: semanticTopK,
                    ...(memoryMode === 'CORTEX' ? {
                        cortex_config: {
                            max_children: cortexMaxChildren,
                            page_size_tokens: cortexPageSize,
                            context_budget_pct: cortexContextBudget,
                            auto_checkpoint: cortexAutoCheckpoint,
                            resume_enabled: cortexResumeEnabled,
                        }
                    } : {}),
                },
                context_engineering: {
                    context_sources: contextSources,
                    inject_episodic_memory: injectEpisodicMemory,
                    inject_semantic_context: injectSemanticContext,
                    inject_cortex_viewport: injectCortexViewport,
                    no_truncation: noTruncation,
                },
            },

            governance: {
                max_cost_usd: maxCostUsd, timeout_ms: timeoutMs,
                execution_limits: { max_recursion_depth: maxRecursionDepth, max_tool_calls: maxToolCalls },
                hitl_checkpoints: hitlCheckpoints,
                checkpoint_every_n_steps: checkpointEveryNSteps,
                long_running: longRunning,
            },

            io_contract: { input_schema: JSON.parse(inputSchema), output_schema: JSON.parse(outputSchema) },
            observability: { log_level: logLevel, log_thoughts: logThoughts, track_cost: trackCost },
            hierarchy: { children: extractChildrenFromGraph(hierarchyNodes, hierarchyEdges), is_atomic: hierarchyNodes.length === 0 },
        };
        onSave(entityData);
    };

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
                    <button key={tab.id} className={`tab-button ${activeTab === tab.id ? 'active' : ''}`} onClick={() => setActiveTab(tab.id)}>
                        <tab.icon size={16} />{tab.label}
                    </button>
                ))}
            </div>

            <div className="tabs-content">
                {/* ═══════════════════════════════════ OVERVIEW ══════════════════════════════════ */}
                {activeTab === 'overview' && (
                    <div className="tab-panel">
                        <div className="form-section">
                            <h3>Basic Information</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Name (ID) *</label>
                                    <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="unique_entity_name" />
                                    <small>Unique identifier, lowercase with underscores</small>
                                </div>
                                <div className="form-group">
                                    <label>Display Name</label>
                                    <input type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Human-friendly Name" />
                                </div>
                            </div>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Entity Type *</label>
                                    <select value={type} onChange={(e) => setType(e.target.value as EntityType)}>
                                        {Object.values(EntityType).map(t => <option key={t} value={t}>{t}</option>)}
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Status</label>
                                    <select value={status} onChange={(e) => setStatus(e.target.value as EntityStatus)}>
                                        {Object.values(EntityStatus).map(s => <option key={s} value={s}>{s}</option>)}
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Version</label>
                                    <input type="text" value={version} onChange={(e) => setVersion(e.target.value)} placeholder="1.0.0" />
                                </div>
                            </div>
                            <div className="form-group">
                                <label>Description</label>
                                <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Describe what this entity does..." rows={4} />
                            </div>
                            <div className="form-group">
                                <label>Goal / Objective</label>
                                <textarea value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Define the primary objective this entity should achieve. This is injected into the LLM prompt." rows={3} />
                                <small>Used in prompt generation — tells the LLM what this entity&apos;s mission is</small>
                            </div>
                            <div className="form-group">
                                <label>Tags</label>
                                <div className="tag-input-wrapper">
                                    <input type="text" value={tagInput} onChange={(e) => setTagInput(e.target.value)} onKeyPress={(e) => e.key === 'Enter' && addTag()} placeholder="Add tag..." />
                                    <JellyButton size="sm" onClick={addTag}><Plus size={16} /></JellyButton>
                                </div>
                                <div className="tag-list">
                                    {tags.map(tag => (<span key={tag} className="tag">{tag}<button onClick={() => removeTag(tag)}>&times;</button></span>))}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* ═══════════════════════════════════ IDENTITY ══════════════════════════════════ */}
                {activeTab === 'identity' && (
                    <div className="tab-panel">

                        {/* Core Identity */}
                        <div className="form-section">
                            <h3><User size={16} /> Agent Identity</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Agent Name</label>
                                    <input type="text" value={personaName} onChange={(e) => setPersonaName(e.target.value)} placeholder="e.g., Aria" />
                                    <small>Human name for the agent persona</small>
                                </div>
                                <div className="form-group">
                                    <label>Role</label>
                                    <input type="text" value={personaRole} onChange={(e) => setPersonaRole(e.target.value)} placeholder="e.g., EMI Collection Specialist" />
                                </div>
                            </div>
                            <div className="form-group">
                                <label>Bio</label>
                                <textarea value={personaBio} onChange={(e) => setPersonaBio(e.target.value)} placeholder="1–2 sentence backstory for richer personality..." rows={2} />
                            </div>
                            <div className="form-group">
                                <label>Avatar / Profile Image URL</label>
                                <input type="text" value={profileImageUrl} onChange={(e) => setProfileImageUrl(e.target.value)} placeholder="https://..." />
                            </div>
                        </div>

                        {/* Personality Matrix */}
                        <div className="form-section">
                            <h3><Sliders size={16} /> Personality Matrix</h3>
                            <p className="form-hint">These dimensions are injected into the system prompt to shape how the agent communicates.</p>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Tone</label>
                                    <select value={tone} onChange={(e) => setTone(e.target.value)}>
                                        <option value="professional">Professional</option>
                                        <option value="friendly">Friendly</option>
                                        <option value="formal">Formal</option>
                                        <option value="empathetic">Empathetic</option>
                                        <option value="assertive">Assertive</option>
                                        <option value="casual">Casual</option>
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Verbosity</label>
                                    <select value={verbosity} onChange={(e) => setVerbosity(e.target.value)}>
                                        <option value="concise">Concise — short, direct</option>
                                        <option value="moderate">Moderate — balanced</option>
                                        <option value="verbose">Verbose — thorough</option>
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Formality</label>
                                    <select value={formality} onChange={(e) => setFormality(e.target.value)}>
                                        <option value="formal">Formal</option>
                                        <option value="semi-formal">Semi-formal</option>
                                        <option value="casual">Casual</option>
                                    </select>
                                </div>
                            </div>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Empathy Level: <strong>{empathyLevel.toFixed(1)}</strong></label>
                                    <input type="range" min="0" max="1" step="0.1" value={empathyLevel} onChange={(e) => setEmpathyLevel(parseFloat(e.target.value))} />
                                    <div className="range-labels"><span>Robotic</span><span>Highly Empathetic</span></div>
                                </div>
                                <div className="form-group">
                                    <label>Humor Level: <strong>{humorLevel.toFixed(1)}</strong></label>
                                    <input type="range" min="0" max="1" step="0.1" value={humorLevel} onChange={(e) => setHumorLevel(parseFloat(e.target.value))} />
                                    <div className="range-labels"><span>None</span><span>Frequent</span></div>
                                </div>
                                <div className="form-group">
                                    <label>Decision Confidence: <strong>{decisionConfidence.toFixed(1)}</strong></label>
                                    <input type="range" min="0" max="1" step="0.05" value={decisionConfidence} onChange={(e) => setDecisionConfidence(parseFloat(e.target.value))} />
                                    <div className="range-labels"><span>Escalate Often</span><span>Act Autonomously</span></div>
                                </div>
                            </div>
                        </div>

                        {/* Voice Configuration */}
                        <div className="form-section">
                            <h3><Mic size={16} /> Voice Configuration <span className="badge-chip">Gemini Live</span></h3>
                            <p className="form-hint">Applied when this agent is used in real-time voice or streaming sessions.</p>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Voice Name</label>
                                    <select value={voiceName} onChange={(e) => setVoiceName(e.target.value)}>
                                        {GEMINI_VOICES.map(v => <option key={v} value={v}>{v}</option>)}
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Language Code (BCP-47)</label>
                                    <input type="text" value={languageCode} onChange={(e) => setLanguageCode(e.target.value)} placeholder="en-US" />
                                    <small>e.g., en-US, hi-IN, en-GB, es-US</small>
                                </div>
                            </div>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Speaking Rate: <strong>{speakingRate.toFixed(2)}×</strong></label>
                                    <input type="range" min="0.25" max="4.0" step="0.05" value={speakingRate} onChange={(e) => setSpeakingRate(parseFloat(e.target.value))} />
                                    <div className="range-labels"><span>0.25× Slow</span><span>4.0× Fast</span></div>
                                </div>
                                <div className="form-group">
                                    <label>Pitch: <strong>{voicePitch > 0 ? '+' : ''}{voicePitch.toFixed(1)} st</strong></label>
                                    <input type="range" min="-20" max="20" step="0.5" value={voicePitch} onChange={(e) => setVoicePitch(parseFloat(e.target.value))} />
                                    <div className="range-labels"><span>−20 Deep</span><span>+20 High</span></div>
                                </div>
                            </div>
                        </div>

                        {/* System Prompt */}
                        <div className="form-section">
                            <h3><Brain size={16} /> System Prompt</h3>
                            <div className="form-group">
                                <textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} placeholder="Define the role, constraints, tone, and behavior..." rows={10} className="code-textarea" />
                                <small>Core instruction. The personality matrix above is automatically appended at runtime by the backend.</small>
                            </div>
                        </div>

                        {/* Dynamic Injection Hooks */}
                        <div className="form-section">
                            <h3>Dynamic Injection Hooks</h3>
                            <div className="form-group">
                                <label>Greeting Template</label>
                                <textarea value={greetingTemplate} onChange={(e) => setGreetingTemplate(e.target.value)} placeholder="Hello! I'm {name}, your {role}. How can I help you today?" rows={2} />
                                <small>First utterance when the agent starts a conversation</small>
                            </div>
                            <div className="form-group">
                                <label>Escalation Message</label>
                                <textarea value={escalationMessage} onChange={(e) => setEscalationMessage(e.target.value)} placeholder="Let me connect you with a human specialist who can better assist you." rows={2} />
                                <small>What to say when escalating to a human agent</small>
                            </div>
                            <div className="form-group">
                                <label>Closing Message</label>
                                <textarea value={closingMessage} onChange={(e) => setClosingMessage(e.target.value)} placeholder="Thank you for reaching out. Have a great day!" rows={2} />
                                <small>End-of-conversation closing statement</small>
                            </div>
                        </div>

                        {/* Behavioral Constraints */}
                        <div className="form-section">
                            <h3>Behavioral Constraints</h3>
                            <div className="form-group">
                                <div className="tag-input-wrapper">
                                    <input type="text" value={constraintInput} onChange={(e) => setConstraintInput(e.target.value)} onKeyPress={(e) => e.key === 'Enter' && addConstraint()} placeholder="e.g., Never contact candidates before 9 AM" />
                                    <JellyButton size="sm" onClick={addConstraint}><Plus size={16} /></JellyButton>
                                </div>
                                <ul className="constraint-list">
                                    {behavioralConstraints.map((c, idx) => (<li key={idx}>{c}<button onClick={() => removeConstraint(idx)}>&times;</button></li>))}
                                </ul>
                            </div>
                        </div>

                        {/* Few-Shot Examples */}
                        <div className="form-section">
                            <h3>Few-Shot Prompt Examples</h3>
                            <div className="info-box"><small>These pairs are injected into the prompt to illustrate expected input→output behavior.</small></div>
                            {fewShotExamples.map((ex, idx) => (
                                <div key={`fs-${idx}`} className="example-item">
                                    <div className="form-group">
                                        <label>User Input</label>
                                        <textarea value={ex.input || ''} onChange={(e) => updateFewShot(idx, 'input', e.target.value)} placeholder="User input..." rows={2} />
                                    </div>
                                    <div className="form-group">
                                        <label>Model Response</label>
                                        <textarea value={ex.output || ''} onChange={(e) => updateFewShot(idx, 'output', e.target.value)} placeholder="Expected model response..." rows={2} />
                                    </div>
                                    <JellyButton variant="danger" size="sm" onClick={() => removeFewShot(idx)}><Trash2 size={14} /> Remove</JellyButton>
                                </div>
                            ))}
                            <JellyButton onClick={addFewShot}><Plus size={16} /> Add Few-Shot Pair</JellyButton>
                        </div>
                    </div>
                )}

                {/* ═══════════════════════════════════ LOGIC GATE ════════════════════════════════ */}
                {activeTab === 'logic' && (
                    <div className="tab-panel">
                        <div className="form-section">
                            <h3>Task Configuration</h3>
                            <p className="form-hint">
                                Select the task type for this entity. The AI model used at runtime is resolved
                                automatically from the <strong>AI Model Configuration</strong> system defaults —
                                administrators configure models per task in the Service Integration page.
                            </p>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Task Type *</label>
                                    <select value={taskType} onChange={(e) => setTaskType(e.target.value)}>
                                        <option value="text_generation">💬 Text Generation</option>
                                        <option value="thinking">🧠 Thinking / Reasoning</option>
                                        <option value="text_to_image">🖼️ Text to Image</option>
                                        <option value="image_to_image">🔄 Image to Image</option>
                                        <option value="text_to_speech">🔊 Text to Speech</option>
                                        <option value="text_to_music">🎵 Text to Music / Audio</option>
                                        <option value="text_to_video">🎬 Text to Video</option>
                                        <option value="text_to_3d">🧊 Text to 3D</option>
                                        <option value="image_to_video">📹 Image to Video</option>
                                        <option value="audio_to_video">🎙️ Audio to Video</option>
                                        <option value="speech_to_speech">🗣️ Speech to Speech (Real-time)</option>
                                    </select>
                                    <small>The LLM Router will dispatch to the model configured for this task type.</small>
                                </div>
                                <div className="form-group">
                                    <label>Reasoning Mode</label>
                                    <select value={reasoningMode} onChange={(e) => setReasoningMode(e.target.value as any)}>
                                        <option value="REACT">ReAct (Thought-Action Loop)</option>
                                        <option value="CHAIN_OF_THOUGHT">Chain of Thought</option>
                                        <option value="REFLECTION">Reflection (Self-Critique)</option>
                                        <option value="TREE_OF_THOUGHTS">Tree of Thoughts</option>
                                    </select>
                                </div>
                            </div>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Temperature: {temperature.toFixed(2)}</label>
                                    <input type="range" min="0" max="2" step="0.1" value={temperature} onChange={(e) => setTemperature(parseFloat(e.target.value))} />
                                    <small>Lower = deterministic, Higher = creative</small>
                                </div>
                                <div className="form-group">
                                    <label>Top P: {topP.toFixed(2)}</label>
                                    <input type="range" min="0" max="1" step="0.05" value={topP} onChange={(e) => setTopP(parseFloat(e.target.value))} />
                                </div>
                            </div>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Max Tokens (optional)</label>
                                    <input type="number" value={maxTokens || ''} onChange={(e) => setMaxTokens(e.target.value ? parseInt(e.target.value) : undefined)} placeholder="Leave empty for no limit" />
                                </div>
                            </div>
                        </div>

                        <div className="form-section">
                            <h3>Context Policy</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Policy Type</label>
                                    <select value={contextPolicyType} onChange={(e) => setContextPolicyType(e.target.value as any)}>
                                        <option value="FULL">Full Context</option>
                                        <option value="LAST_N">Last N Steps</option>
                                        <option value="SLIDING_WINDOW">Sliding Window (Chars)</option>
                                        <option value="EXPLICIT">Explicit Keys Only</option>
                                    </select>
                                </div>
                                {contextPolicyType === 'LAST_N' && (
                                    <div className="form-group">
                                        <label>Number of Steps (N)</label>
                                        <input type="number" value={contextPolicyN || 3} onChange={(e) => setContextPolicyN(parseInt(e.target.value))} />
                                    </div>
                                )}
                                {contextPolicyType === 'SLIDING_WINDOW' && (
                                    <div className="form-group">
                                        <label>Max Characters</label>
                                        <input type="number" value={contextPolicyMaxChars || 4000} onChange={(e) => setContextPolicyMaxChars(parseInt(e.target.value))} />
                                    </div>
                                )}
                            </div>
                            <div className="form-group">
                                <label>Summarization Threshold (Chars)</label>
                                <input type="number" value={contextPolicySummarizeThreshold || 8000} onChange={(e) => setContextPolicySummarizeThreshold(parseInt(e.target.value))} placeholder="8000" />
                                <small>Auto-summarize context if it exceeds this size</small>
                            </div>
                            <div className="form-group">
                                <label><Key size={14} /> Preserve Keys during Summarization</label>
                                <div className="tag-input-wrapper">
                                    <input type="text" value={preserveKeyInput} onChange={(e) => setPreserveKeyInput(e.target.value)} onKeyPress={(e) => e.key === 'Enter' && addPreserveKey()} placeholder="e.g., customer_name, product_id" />
                                    <JellyButton size="sm" onClick={addPreserveKey}><Plus size={16} /></JellyButton>
                                </div>
                                <div className="tag-list">
                                    {preserveKeys.map(key => (<span key={key} className="tag key-tag">{key}<button onClick={() => removePreserveKey(key)}>&times;</button></span>))}
                                </div>
                                <small>These context keys are always preserved verbatim when the context is summarized (replaces hardcoded domain tokens)</small>
                            </div>
                        </div>

                        <div className="form-section">
                            <h3>Retry Policy</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Max Retries</label>
                                    <input type="number" value={maxRetries} onChange={(e) => setMaxRetries(parseInt(e.target.value) || 0)} min="0" max="10" />
                                </div>
                                <div className="form-group">
                                    <label>Backoff Strategy</label>
                                    <select value={backoffStrategy} onChange={(e) => setBackoffStrategy(e.target.value as any)}>
                                        <option value="EXPONENTIAL">Exponential</option>
                                        <option value="LINEAR">Linear</option>
                                        <option value="NONE">None</option>
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Backoff Multiplier</label>
                                    <input type="number" value={backoffMultiplier} onChange={(e) => setBackoffMultiplier(parseFloat(e.target.value) || 2.0)} step="0.1" min="1" />
                                </div>
                            </div>
                            <div className="form-group">
                                <label>Retry On (Events)</label>
                                <div className="tag-list">
                                    {['TOOL_FAILURE', 'LLM_ERROR', 'TIMEOUT', 'VALIDATION_ERROR'].map(event => (
                                        <label key={event} className="checkbox-label">
                                            <input type="checkbox" checked={retryOn.includes(event)} onChange={(e) => { if (e.target.checked) setRetryOn([...retryOn, event]); else setRetryOn(retryOn.filter(i => i !== event)); }} />
                                            {event}
                                        </label>
                                    ))}
                                </div>
                            </div>
                        </div>

                        <div className="form-section">
                            <h3>Review Mechanism</h3>
                            <div className="form-group">
                                <label className="checkbox-label">
                                    <input type="checkbox" checked={reviewEnabled} onChange={(e) => setReviewEnabled(e.target.checked)} />
                                    Enable self-review after execution
                                </label>
                            </div>
                            {reviewEnabled && (
                                <>
                                    <div className="form-group">
                                        <label>Review Prompt</label>
                                        <textarea value={reviewPrompt} onChange={(e) => setReviewPrompt(e.target.value)} placeholder="Review your output for quality and accuracy..." rows={4} />
                                    </div>
                                    <div className="form-group">
                                        <label>On Failure</label>
                                        <select value={reviewOnFailure} onChange={(e) => setReviewOnFailure(e.target.value as any)}>
                                            <option value="RETRY">Retry</option>
                                            <option value="ESCALATE">Escalate</option>
                                            <option value="ABORT">Abort</option>
                                        </select>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                )}

                {/* ═══════════════════════════════════ PLANNING ══════════════════════════════════ */}
                {activeTab === 'planning' && (
                    <div className="tab-panel">
                        <div className="form-section">
                            <h3>Planning Configuration</h3>
                            <div className="form-group">
                                <label className="checkbox-label">
                                    <input type="checkbox" checked={staticPlanEnabled} onChange={(e) => setStaticPlanEnabled(e.target.checked)} />
                                    Enable Static Plan (predefined steps)
                                </label>
                                <small>Static plans are defined in the Hierarchy tab</small>
                            </div>
                            <div className="form-group">
                                <label>Fallback Behavior</label>
                                <select value={fallbackBehavior} onChange={(e) => setFallbackBehavior(e.target.value as any)}>
                                    <option value="ADAPTIVE">Adaptive (LLM can adjust order/tools)</option>
                                    <option value="STRICT">Strict (Must follow exactly)</option>
                                    <option value="DYNAMIC_ONLY">Dynamic Only (Ignore static plan)</option>
                                </select>
                            </div>
                            <div className="form-group">
                                <label className="checkbox-label">
                                    <input type="checkbox" checked={dynamicPlanningEnabled} onChange={(e) => setDynamicPlanningEnabled(e.target.checked)} />
                                    Enable Dynamic Planning (AI-generated plans)
                                </label>
                            </div>
                            {dynamicPlanningEnabled && (
                                <>
                                    <div className="form-group">
                                        <label>Planning Prompt</label>
                                        <textarea value={planningPrompt} onChange={(e) => setPlanningPrompt(e.target.value)} placeholder="Instructions for how to generate dynamic plans..." rows={6} />
                                    </div>
                                    <div className="form-row">
                                        <div className="form-group">
                                            <label>Reconciliation Strategy</label>
                                            <select value={reconciliationStrategy} onChange={(e) => setReconciliationStrategy(e.target.value as any)}>
                                                <option value="HYBRID">Hybrid (Mix Static & Dynamic)</option>
                                                <option value="STATIC_PRIORITY">Static Priority</option>
                                                <option value="DYNAMIC_PRIORITY">Dynamic Priority</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div className="form-group">
                                        <label>Allowed Deviations</label>
                                        <div className="tag-list">
                                            <label className="checkbox-label"><input type="checkbox" checked={allowedDeviations.can_add_steps} onChange={(e) => setAllowedDeviations({ ...allowedDeviations, can_add_steps: e.target.checked })} />Can Add Steps</label>
                                            <label className="checkbox-label"><input type="checkbox" checked={allowedDeviations.can_skip_optional_steps} onChange={(e) => setAllowedDeviations({ ...allowedDeviations, can_skip_optional_steps: e.target.checked })} />Can Skip Optional</label>
                                            <label className="checkbox-label"><input type="checkbox" checked={allowedDeviations.can_reorder_steps} onChange={(e) => setAllowedDeviations({ ...allowedDeviations, can_reorder_steps: e.target.checked })} />Can Reorder</label>
                                            <label className="checkbox-label"><input type="checkbox" checked={allowedDeviations.can_change_tools} onChange={(e) => setAllowedDeviations({ ...allowedDeviations, can_change_tools: e.target.checked })} />Can Change Tools</label>
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                        <div className="form-section">
                            <h3>Loop Control</h3>
                            <div className="form-row">
                                <div className="form-group">
                                    <label>Max Iterations</label>
                                    <input type="number" value={maxIterations} onChange={(e) => setMaxIterations(parseInt(e.target.value) || 1)} min="1" max="100" />
                                </div>
                                <div className="form-group">
                                    <label>Iteration Context Mode</label>
                                    <select value={iterationContextMode} onChange={(e) => setIterationContextMode(e.target.value as any)}>
                                        <option value="FULL_HISTORY">Full History</option>
                                        <option value="SUMMARIZED">Summarized</option>
                                        <option value="LAST_N">Last N Steps</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* ═══════════════════════════════════ CAPABILITIES ══════════════════════════════ */}
                {activeTab === 'capabilities' && (
                    <div className="tab-panel">
                        <div className="form-section">
                            <h3>Tools</h3>
                            <ToolSelectionPanel selectedTools={selectedTools} onChange={setSelectedTools} />
                        </div>
                        <div className="form-section">
                            <h3 className="mt-4">Memory</h3>
                            <div className="form-group">
                                <label className="checkbox-label">
                                    <input type="checkbox" checked={memoryEnabled} onChange={(e) => setMemoryEnabled(e.target.checked)} />
                                    Enable Memory
                                </label>
                            </div>
                            {memoryEnabled && (
                                <>
                                    <div className="form-group">
                                        <label>Memory Mode</label>
                                        <select value={memoryMode} onChange={(e) => setMemoryMode(e.target.value)}>
                                            <option value="STANDARD">Standard (Episodic + Semantic)</option>
                                            <option value="CORTEX">CORTEX (Cognitive Tree — Unbounded)</option>
                                        </select>
                                        <small>{memoryMode === 'CORTEX' ? 'Uses the CORTEX cognitive tree for persistent, navigable, unbounded context.' : 'Uses episodic memory (last N interactions) and semantic document search.'}</small>
                                    </div>
                                    {memoryMode === 'STANDARD' && (
                                        <div className="form-row">
                                            <div className="form-group">
                                                <label>Episodic Memory Count</label>
                                                <input type="number" value={episodicMemoryCount} onChange={(e) => setEpisodicMemoryCount(parseInt(e.target.value) || 10)} min="1" max="50" />
                                                <small>How many past interactions to inject</small>
                                            </div>
                                            <div className="form-group">
                                                <label className="checkbox-label">
                                                    <input type="checkbox" checked={semanticSearchEnabled} onChange={(e) => setSemanticSearchEnabled(e.target.checked)} />
                                                    Enable Semantic Search (pgvector)
                                                </label>
                                            </div>
                                            {semanticSearchEnabled && (
                                                <div className="form-group">
                                                    <label>Semantic Top K</label>
                                                    <input type="number" value={semanticTopK} onChange={(e) => setSemanticTopK(parseInt(e.target.value) || 5)} min="1" max="20" />
                                                </div>
                                            )}
                                        </div>
                                    )}
                                    {memoryMode === 'CORTEX' && (
                                        <div className="form-row">
                                            <div className="form-group">
                                                <label>Max Children per Node</label>
                                                <input type="number" value={cortexMaxChildren} onChange={(e) => setCortexMaxChildren(parseInt(e.target.value) || 12)} min="4" max="32" />
                                            </div>
                                            <div className="form-group">
                                                <label>Page Size (tokens)</label>
                                                <input type="number" value={cortexPageSize} onChange={(e) => setCortexPageSize(parseInt(e.target.value) || 8000)} min="1000" max="32000" step="1000" />
                                            </div>
                                            <div className="form-group">
                                                <label>Context Budget: {cortexContextBudget}%</label>
                                                <input type="range" min="10" max="80" step="5" value={cortexContextBudget} onChange={(e) => setCortexContextBudget(parseInt(e.target.value))} />
                                                <div className="range-labels"><span>10%</span><span>80%</span></div>
                                            </div>
                                            <div className="form-group">
                                                <label className="checkbox-label">
                                                    <input type="checkbox" checked={cortexAutoCheckpoint} onChange={(e) => setCortexAutoCheckpoint(e.target.checked)} />
                                                    Auto-Checkpoint
                                                </label>
                                            </div>
                                            <div className="form-group">
                                                <label className="checkbox-label">
                                                    <input type="checkbox" checked={cortexResumeEnabled} onChange={(e) => setCortexResumeEnabled(e.target.checked)} />
                                                    Resume Enabled
                                                </label>
                                            </div>
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                        <div className="form-section">
                            <h3>Context Engineering</h3>
                            <p className="form-hint">CORTEX-native context handling — no truncation, unbounded context via tree navigation.</p>
                            <div className="form-row">
                                <div className="form-group">
                                    <label className="checkbox-label">
                                        <input type="checkbox" checked={injectEpisodicMemory} onChange={(e) => setInjectEpisodicMemory(e.target.checked)} />
                                        Inject Episodic Memory
                                    </label>
                                    <small>Include recent interaction history</small>
                                </div>
                                <div className="form-group">
                                    <label className="checkbox-label">
                                        <input type="checkbox" checked={injectSemanticContext} onChange={(e) => setInjectSemanticContext(e.target.checked)} />
                                        Inject Semantic Context
                                    </label>
                                    <small>Include relevant document chunks</small>
                                </div>
                                <div className="form-group">
                                    <label className="checkbox-label">
                                        <input type="checkbox" checked={injectCortexViewport} onChange={(e) => setInjectCortexViewport(e.target.checked)} />
                                        Inject CORTEX Viewport
                                    </label>
                                    <small>Include cognitive tree viewport</small>
                                </div>
                                <div className="form-group">
                                    <label className="checkbox-label">
                                        <input type="checkbox" checked={noTruncation} onChange={(e) => setNoTruncation(e.target.checked)} />
                                        No Truncation (CORTEX handles unbounded context)
                                    </label>
                                </div>
                            </div>
                            <h4 style={{ marginTop: '1rem' }}>Context Sources</h4>
                            <p className="form-hint">Attach design-time documents, knowledge base references, or CORTEX trees from previous executions.</p>
                            {contextSources.map((src: any, idx: number) => (
                                <div key={idx} className="example-item" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                    <select value={src.source_type} onChange={(e) => {
                                        const updated = [...contextSources]; updated[idx] = { ...src, source_type: e.target.value }; setContextSources(updated);
                                    }}>
                                        <option value="DOCUMENT">📄 Document</option>
                                        <option value="KNOWLEDGE_BASE">📚 Knowledge Base</option>
                                        <option value="CORTEX_TREE">🧠 CORTEX Tree</option>
                                        <option value="DB_RECORDS">🗃️ DB Records</option>
                                    </select>
                                    <input type="text" value={src.reference_id || ''} onChange={(e) => {
                                        const updated = [...contextSources]; updated[idx] = { ...src, reference_id: e.target.value }; setContextSources(updated);
                                    }} placeholder="Reference ID" style={{ flex: 1 }} />
                                    <input type="text" value={src.description || ''} onChange={(e) => {
                                        const updated = [...contextSources]; updated[idx] = { ...src, description: e.target.value }; setContextSources(updated);
                                    }} placeholder="Description" style={{ flex: 1 }} />
                                    <JellyButton variant="danger" size="sm" onClick={() => setContextSources(contextSources.filter((_: any, i: number) => i !== idx))}>
                                        <Trash2 size={14} />
                                    </JellyButton>
                                </div>
                            ))}
                            <JellyButton size="sm" onClick={() => setContextSources([...contextSources, { source_type: 'DOCUMENT', reference_id: '', description: '', ingest_to_cortex: true }])}>
                                <Plus size={16} /> Add Context Source
                            </JellyButton>
                        </div>
                    </div>
                )}

                {/* ═══════════════════════════════════ GOVERNANCE ════════════════════════════════ */}
                {
                    activeTab === 'governance' && (
                        <div className="tab-panel">
                            <div className="form-section">
                                <h3>Cost Controls</h3>
                                <div className="form-row">
                                    <div className="form-group">
                                        <label>Max Cost Per Execution (USD)</label>
                                        <input type="number" value={maxCostUsd || ''} onChange={(e) => setMaxCostUsd(e.target.value ? parseFloat(e.target.value) : undefined)} placeholder="No limit" step="0.01" min="0" />
                                    </div>
                                </div>
                            </div>
                            <div className="form-section">
                                <h3>Execution Limits</h3>
                                <div className="form-row">
                                    <div className="form-group">
                                        <label>Timeout (milliseconds)</label>
                                        <input type="number" value={timeoutMs} onChange={(e) => setTimeoutMs(parseInt(e.target.value) || 300000)} min="1000" step="1000" />
                                    </div>
                                    <div className="form-group">
                                        <label>Max Recursion Depth</label>
                                        <input type="number" value={maxRecursionDepth} onChange={(e) => setMaxRecursionDepth(parseInt(e.target.value) || 5)} min="1" max="10" />
                                    </div>
                                </div>
                                <div className="form-group">
                                    <label>Max Tool Calls (optional)</label>
                                    <input type="number" value={maxToolCalls || ''} onChange={(e) => setMaxToolCalls(e.target.value ? parseInt(e.target.value) : undefined)} placeholder="No limit" min="1" />
                                </div>
                                <div className="form-group">
                                    <label>Checkpoint Every N Steps</label>
                                    <input type="number" value={checkpointEveryNSteps} onChange={(e) => setCheckpointEveryNSteps(parseInt(e.target.value) || 3)} min="1" />
                                    <small>Persist execution state to DB for resuming after N steps.</small>
                                </div>
                            </div>
                            <div className="form-section">
                                <h3>Human-In-The-Loop (HITL)</h3>
                                <p className="form-hint">Configure approval checkpoints for critical operations. HITL approvals are unblocked via Redis pub/sub on the backend.</p>
                            </div>
                            <div className="form-section">
                                <h3>🧠 CORTEX Memory Architecture</h3>
                                <div className="form-group">
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                                        <input type="checkbox" checked={longRunning} onChange={(e) => setLongRunning(e.target.checked)} style={{ width: '18px', height: '18px', accentColor: '#6366f1' }} />
                                        <span>Enable Long-Running / CORTEX Mode</span>
                                    </label>
                                    <small style={{ marginTop: '6px', display: 'block', color: '#94a3b8' }}>
                                        When enabled, the agent uses a persistent cognitive tree (CORTEX) for memory and reasoning. This provides hierarchical memory, viewport-based navigation, automatic checkpointing, and context compaction — ideal for complex, multi-step tasks.
                                    </small>
                                </div>
                            </div>
                        </div>
                    )
                }

                {/* ═══════════════════════════════════ IO CONTRACT ═══════════════════════════════ */}
                {
                    activeTab === 'contract' && (
                        <div className="tab-panel">
                            <div className="form-section">
                                <h3>IO Contract (JSON Schema)</h3>
                                <div className="form-row">
                                    <div className="form-group">
                                        <label>Input Schema</label>
                                        <textarea value={inputSchema} onChange={(e) => setInputSchema(e.target.value)} placeholder='{ "type": "object", ... }' rows={15} className="code-textarea" />
                                        <small>JSON Schema for input validation</small>
                                    </div>
                                    <div className="form-group">
                                        <label>Output Schema</label>
                                        <textarea value={outputSchema} onChange={(e) => setOutputSchema(e.target.value)} placeholder='{ "type": "object", ... }' rows={15} className="code-textarea" />
                                        <small>JSON Schema for output validation</small>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )
                }

                {/* ═══════════════════════════════════ OBSERVABILITY ═════════════════════════════ */}
                {
                    activeTab === 'observability' && (
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
                                        <input type="checkbox" checked={logThoughts} onChange={(e) => setLogThoughts(e.target.checked)} />
                                        Log Internal Thoughts/Reasoning
                                    </label>
                                </div>
                                <div className="form-group">
                                    <label className="checkbox-label">
                                        <input type="checkbox" checked={trackCost} onChange={(e) => setTrackCost(e.target.checked)} />
                                        Track Execution Cost & Tokens
                                    </label>
                                </div>
                            </div>
                        </div>
                    )
                }

                {/* ═══════════════════════════════════ HIERARCHY ═════════════════════════════════ */}
                {
                    activeTab === 'hierarchy' && (
                        <div className="tab-panel hierarchy-tab">
                            <div className="hierarchy-hint">
                                <Info size={16} />
                                <span>Drag entities and tools onto the canvas to define execution flow. Click edges to set relationship type (SEQUENTIAL / PARALLEL / CONDITIONAL).</span>
                            </div>
                            <EntityFlow
                                initialNodes={hierarchyNodes}
                                initialEdges={hierarchyEdges}
                                onSave={(nodes, edges) => { setHierarchyNodes(nodes); setHierarchyEdges(edges); }}
                            />
                        </div>
                    )
                }
            </div >

            <div className="tabs-footer">
                <JellyButton variant="ghost" onClick={onCancel}>Cancel</JellyButton>
                <JellyButton roseGold onClick={handleSave}>Save Entity</JellyButton>
            </div>
        </div >
    );
};
