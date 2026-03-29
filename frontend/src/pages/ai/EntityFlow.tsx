import React, { useState, useCallback, useRef, useEffect } from 'react';
import ReactFlow, {
    addEdge, Background, Controls, MiniMap, Connection, Edge, Node,
    useNodesState, useEdgesState, Panel, EdgeLabelRenderer, BaseEdge, getStraightPath,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { EntityNode } from './builder-nodes/EntityNode';
import { ToolNode } from './builder-nodes/ToolNode';
import { JellyButton } from '@/components/ui';
import { Save, Wrench, Layers, Trash2, Brain, Zap, Activity, Plus, Settings, Search, AlertTriangle } from 'lucide-react';
import { EntityType, HierarchicalEntity } from '@/types';
import { apiClient } from '@/services/api.client';
import './EntityFlow.css';

// ── Custom edge with a clickable label for relationship type ──────────────────
const RelationshipEdge = ({ sourceX, sourceY, targetX, targetY, label, style, markerEnd, data }: any) => {
    const [edgePath, labelX, labelY] = getStraightPath({ sourceX, sourceY, targetX, targetY });
    return (
        <>
            <BaseEdge path={edgePath} markerEnd={markerEnd} style={style} />
            <EdgeLabelRenderer>
                <div
                    style={{ position: 'absolute', transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`, pointerEvents: 'all' }}
                    className={`edge-relationship-label rel-${(label || 'SEQUENTIAL').toLowerCase()}`}
                    onClick={data?.onLabelClick}
                >
                    {label || 'SEQUENTIAL'}
                </div>
            </EdgeLabelRenderer>
        </>
    );
};

const nodeTypes = { entityNode: EntityNode, toolNode: ToolNode };
const edgeTypes = { relationship: RelationshipEdge };

const STEP_TYPE_COLORS: Record<string, string> = {
    PROCESS: '#7c3aed',
    AGENT: '#2563eb',
    SKILL: '#059669',
    ACTION: '#d97706',
    TOOL_CALL: '#0891b2',
    THOUGHT: '#6b7280',
};

interface Tool { name: string; description: string; }

interface EntityFlowProps {
    initialNodes?: Node[];
    initialEdges?: Edge[];
    onSave: (nodes: Node[], edges: Edge[]) => void;
}

export const EntityFlow: React.FC<EntityFlowProps> = ({ initialNodes = [], initialEdges = [], onSave }) => {
    const reactFlowWrapper = useRef<HTMLDivElement>(null);
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(
        initialEdges.map(e => ({ ...e, type: 'relationship', animated: e.label === 'PARALLEL' }))
    );
    const [reactFlowInstance, setReactFlowInstance] = useState<any>(null);
    const [selectedNode, setSelectedNode] = useState<Node | null>(null);
    const [sidebarTab, setSidebarTab] = useState<'entities' | 'tools' | 'config'>('entities');

    // Library data
    const [entities, setEntities] = useState<HierarchicalEntity[]>([]);
    const [tools, setTools] = useState<Tool[]>([]);
    const [loadingLibraries, setLoadingLibraries] = useState(true);
    const [entitySearch, setEntitySearch] = useState('');
    const [toolSearch, setToolSearch] = useState('');

    useEffect(() => { fetchLibraries(); }, []);

    const fetchLibraries = async () => {
        try {
            const [entitiesRes, toolsRes] = await Promise.all([
                apiClient.get<HierarchicalEntity[]>('/ai/entities'),
                apiClient.get<Tool[]>('/ai/tools'),
            ]);
            setEntities(entitiesRes.data);
            setTools(toolsRes.data);
        } catch (error) {
            console.error('Failed to fetch libraries:', error);
        } finally {
            setLoadingLibraries(false);
        }
    };

    // ── Connection / edge callbacks ───────────────────────────────────────────
    const onConnect = useCallback((params: Connection | Edge) => {
        setEdges((eds) => addEdge({ ...params, type: 'relationship', label: 'SEQUENTIAL', animated: false }, eds));
    }, [setEdges]);

    const cycleEdgeRelationship = (edgeId: string) => {
        const cycle: Record<string, string> = { SEQUENTIAL: 'PARALLEL', PARALLEL: 'CONDITIONAL', CONDITIONAL: 'SEQUENTIAL' };
        setEdges(eds => eds.map(e => e.id === edgeId
            ? { ...e, label: cycle[String(e.label || 'SEQUENTIAL')], animated: cycle[String(e.label || 'SEQUENTIAL')] === 'PARALLEL' }
            : e
        ));
    };

    // Attach onLabelClick to each edge's data
    const enrichedEdges = edges.map(e => ({
        ...e,
        data: { ...e.data, onLabelClick: () => cycleEdgeRelationship(e.id) },
    }));

    // ── Drag / drop ───────────────────────────────────────────────────────────
    const onDragOver = useCallback((event: React.DragEvent) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
    }, []);

    const onDrop = useCallback((event: React.DragEvent) => {
        event.preventDefault();
        const bounds = reactFlowWrapper.current?.getBoundingClientRect();
        const type = event.dataTransfer.getData('application/reactflow/type');
        const payload = event.dataTransfer.getData('application/reactflow/data');
        if (!type || !bounds || !reactFlowInstance) return;

        const position = reactFlowInstance.project({ x: event.clientX - bounds.left, y: event.clientY - bounds.top });
        let nodeData: any = { label: 'New Node', description: '', stepType: 'ACTION' };

        if (payload) {
            const parsed = JSON.parse(payload);
            if (type === 'entityNode') {
                nodeData = { label: parsed.display_name || parsed.name, description: parsed.description, stepType: parsed.type, entityRef: { id: parsed.id, name: parsed.name, type: parsed.type } };
            } else if (type === 'toolNode') {
                nodeData = { label: parsed.name, description: parsed.description, stepType: 'TOOL_CALL', toolRef: { tool_id: parsed.name, name: parsed.name } };
            }
        }

        setNodes(nds => nds.concat({ id: crypto.randomUUID(), type, position, data: nodeData }));
    }, [reactFlowInstance, setNodes]);

    // ── Node selection ────────────────────────────────────────────────────────
    const onNodeClick = (_: React.MouseEvent, node: Node) => {
        setSelectedNode(node);
        setSidebarTab('config');
    };

    const onPaneClick = () => {
        setSelectedNode(null);
        if (sidebarTab === 'config') setSidebarTab('entities');
    };

    const handleNodeDataChange = (newData: any) => {
        if (!selectedNode) return;
        setNodes(nds => nds.map(n => n.id === selectedNode.id ? { ...n, data: { ...n.data, ...newData } } : n));
        setSelectedNode(prev => prev ? { ...prev, data: { ...prev.data, ...newData } } : null);
    };

    const deleteNode = () => {
        if (!selectedNode) return;
        setNodes(nds => nds.filter(n => n.id !== selectedNode.id));
        setEdges(eds => eds.filter(e => e.source !== selectedNode.id && e.target !== selectedNode.id));
        setSelectedNode(null);
        setSidebarTab('entities');
    };

    const addActionNode = () => {
        const position = reactFlowInstance?.project({ x: 400, y: 200 + nodes.length * 120 }) || { x: 400, y: 200 };
        setNodes(nds => nds.concat({ id: crypto.randomUUID(), type: 'entityNode', position, data: { label: 'New Step', description: '', stepType: 'ACTION', required: true } }));
    };

    const handleLinkEntity = (entityId: string) => {
        const entity = entities.find(e => e.id === entityId);
        if (entity) handleNodeDataChange({ label: entity.display_name || entity.name, entityRef: { id: entity.id, name: entity.name, type: entity.type }, stepType: entity.type });
    };

    const handleLinkTool = (toolName: string) => {
        const tool = tools.find(t => t.name === toolName);
        if (tool) handleNodeDataChange({ label: tool.name, toolRef: { tool_id: tool.name, name: tool.name }, stepType: 'TOOL_CALL' });
    };

    const autoLayout = () => {
        setNodes(nds => nds.map((n, idx) => ({ ...n, position: { x: 300 + (idx % 3) * 250, y: 100 + Math.floor(idx / 3) * 160 } })));
    };

    // ── Filters ───────────────────────────────────────────────────────────────
    const filteredEntities = entities.filter(e =>
        (e.display_name || e.name).toLowerCase().includes(entitySearch.toLowerCase()) ||
        e.type.toLowerCase().includes(entitySearch.toLowerCase())
    );
    const filteredTools = tools.filter(t => t.name.toLowerCase().includes(toolSearch.toLowerCase()));

    const entityTypeIcon = (type: EntityType) => {
        if (type === EntityType.AGENT) return <Layers size={13} />;
        if (type === EntityType.SKILL) return <Brain size={13} />;
        if (type === EntityType.ACTION) return <Zap size={13} />;
        return <Activity size={13} />;
    };

    const stepOrderIndex = (node: Node) => nodes.findIndex(n => n.id === node.id) + 1;

    return (
        <div className="entity-flow-wrapper">
            {/* ── Sidebar ─────────────────────────────────────────────────── */}
            <div className="entity-flow-sidebar">
                <div className="sidebar-tabs">
                    <button className={`sidebar-tab-btn ${sidebarTab === 'entities' ? 'active' : ''}`} onClick={() => setSidebarTab('entities')}><Layers size={14} /> Entities</button>
                    <button className={`sidebar-tab-btn ${sidebarTab === 'tools' ? 'active' : ''}`} onClick={() => setSidebarTab('tools')}><Wrench size={14} /> Tools</button>
                    <button className={`sidebar-tab-btn ${sidebarTab === 'config' ? 'active' : ''}`} onClick={() => setSidebarTab('config')}><Settings size={14} /> Config</button>
                </div>

                {/* Add manual action node */}
                <div className="sidebar-add-btn">
                    <JellyButton size="sm" onClick={addActionNode} className="w-full">
                        <Plus size={14} /> Add Action Step
                    </JellyButton>
                </div>

                {/* ──── Entities tab ──── */}
                {sidebarTab === 'entities' && (
                    <div className="sidebar-section">
                        <div className="sidebar-search">
                            <Search size={13} />
                            <input type="text" value={entitySearch} onChange={e => setEntitySearch(e.target.value)} placeholder="Search entities..." />
                        </div>
                        {loadingLibraries ? <div className="library-loading">Loading...</div> : (
                            <>
                                {filteredEntities.map(entity => (
                                    <div
                                        key={entity.id}
                                        className={`draggable-item entity-item entity-type-${entity.type.toLowerCase()}`}
                                        draggable
                                        onDragStart={(e) => {
                                            e.dataTransfer.setData('application/reactflow/type', 'entityNode');
                                            e.dataTransfer.setData('application/reactflow/data', JSON.stringify(entity));
                                        }}
                                    >
                                        <div className="item-header">
                                            {entityTypeIcon(entity.type)}
                                            <span>{entity.display_name || entity.name}</span>
                                        </div>
                                        <span className={`type-badge type-badge-${entity.type.toLowerCase()}`}>{entity.type}</span>
                                    </div>
                                ))}
                                {filteredEntities.length === 0 && <div className="library-empty">No entities found</div>}
                            </>
                        )}
                    </div>
                )}

                {/* ──── Tools tab ──── */}
                {sidebarTab === 'tools' && (
                    <div className="sidebar-section">
                        <div className="sidebar-search">
                            <Search size={13} />
                            <input type="text" value={toolSearch} onChange={e => setToolSearch(e.target.value)} placeholder="Search tools..." />
                        </div>
                        {loadingLibraries ? <div className="library-loading">Loading...</div> : (
                            <>
                                {filteredTools.map(tool => (
                                    <div
                                        key={tool.name}
                                        className="draggable-item tool-item"
                                        draggable
                                        onDragStart={(e) => {
                                            e.dataTransfer.setData('application/reactflow/type', 'toolNode');
                                            e.dataTransfer.setData('application/reactflow/data', JSON.stringify(tool));
                                        }}
                                    >
                                        <div className="item-header"><Wrench size={13} /><span>{tool.name}</span></div>
                                        <div className="item-description">{tool.description}</div>
                                    </div>
                                ))}
                                {filteredTools.length === 0 && <div className="library-empty">No tools found</div>}
                            </>
                        )}
                    </div>
                )}

                {/* ──── Config panel ──── */}
                {sidebarTab === 'config' && selectedNode && (
                    <div className="sidebar-section node-config-panel">
                        <div className="config-node-header">
                            <span className="step-order-badge">Step {stepOrderIndex(selectedNode)}</span>
                            <span className={`type-badge type-badge-${(selectedNode.data.stepType || 'action').toLowerCase()}`}>{selectedNode.data.stepType || 'ACTION'}</span>
                        </div>
                        <div className="form-group">
                            <label>Step Name</label>
                            <input value={selectedNode.data.label} onChange={(e) => handleNodeDataChange({ label: e.target.value })} />
                        </div>
                        <div className="form-group">
                            <label>Description / Prompt Template</label>
                            <textarea value={selectedNode.data.description || ''} onChange={(e) => handleNodeDataChange({ description: e.target.value })} rows={3} placeholder="What should this step do?" />
                        </div>
                        <div className="form-group">
                            <label>Step Type</label>
                            <select value={selectedNode.data.stepType || 'ACTION'} onChange={(e) => handleNodeDataChange({ stepType: e.target.value, entityRef: undefined, toolRef: undefined })}>
                                <option value="ACTION">ACTION — Direct instruction</option>
                                <option value="THOUGHT">THOUGHT — Internal reasoning</option>
                                <option value="TOOL_CALL">TOOL_CALL — Tool execution</option>
                                <option value="CHILD_ENTITY_INVOCATION">CHILD_ENTITY — Sub-agent call</option>
                            </select>
                        </div>

                        {selectedNode.data.stepType === 'CHILD_ENTITY_INVOCATION' || selectedNode.data.entityRef ? (
                            <div className="form-group">
                                <label>Link to Entity</label>
                                <select value={selectedNode.data.entityRef?.id || ''} onChange={(e) => handleLinkEntity(e.target.value)}>
                                    <option value="">-- Select Entity --</option>
                                    {entities.map(e => <option key={e.id} value={e.id}>{e.display_name || e.name} ({e.type})</option>)}
                                </select>
                            </div>
                        ) : null}

                        {selectedNode.data.stepType === 'TOOL_CALL' || selectedNode.data.toolRef ? (
                            <div className="form-group">
                                <label>Link to Tool</label>
                                <select value={selectedNode.data.toolRef?.tool_id || ''} onChange={(e) => handleLinkTool(e.target.value)}>
                                    <option value="">-- Select Tool --</option>
                                    {tools.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
                                </select>
                            </div>
                        ) : null}

                        <div className="form-group">
                            <label className="checkbox-label">
                                <input type="checkbox" checked={selectedNode.data.required ?? true} onChange={(e) => handleNodeDataChange({ required: e.target.checked })} />
                                Required Step
                            </label>
                        </div>

                        <JellyButton variant="danger" size="sm" className="w-full" onClick={deleteNode}>
                            <Trash2 size={16} /> Remove Node
                        </JellyButton>
                    </div>
                )}
                {sidebarTab === 'config' && !selectedNode && (
                    <div className="sidebar-section">
                        <div className="no-selection-hint">
                            <AlertTriangle size={20} />
                            <p>Click a node on the canvas to configure it</p>
                        </div>
                    </div>
                )}
            </div>

            {/* ── Canvas ──────────────────────────────────────────────────── */}
            <div className="entity-flow-canvas" ref={reactFlowWrapper}>
                <ReactFlow
                    nodes={nodes}
                    edges={enrichedEdges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={onConnect}
                    onInit={setReactFlowInstance}
                    onDrop={onDrop}
                    onDragOver={onDragOver}
                    onNodeClick={onNodeClick}
                    onPaneClick={onPaneClick}
                    nodeTypes={nodeTypes}
                    edgeTypes={edgeTypes}
                    fitView
                >
                    <Background color="rgba(255,255,255,0.05)" gap={20} />
                    <Controls />
                    <MiniMap
                        nodeColor={(n: any) => {
                            const type = n.data?.stepType || n.data?.entityRef?.type || 'ACTION';
                            return STEP_TYPE_COLORS[type] || '#c58e7f';
                        }}
                        maskColor="rgba(0,0,0,0.5)"
                        className="glass"
                    />
                    <Panel position="top-right">
                        <div style={{ display: 'flex', gap: 8 }}>
                            <JellyButton size="sm" onClick={autoLayout}>Auto-Layout</JellyButton>
                            <JellyButton roseGold onClick={() => onSave(nodes, edges)}>
                                <Save size={18} /> Save Hierarchy
                            </JellyButton>
                        </div>
                    </Panel>
                    <Panel position="bottom-center">
                        <div className="edge-legend">
                            <span className="legend-item rel-sequential">SEQUENTIAL</span>
                            <span className="legend-item rel-parallel">PARALLEL</span>
                            <span className="legend-item rel-conditional">CONDITIONAL</span>
                            <small>Click an edge label to cycle its type</small>
                        </div>
                    </Panel>
                </ReactFlow>
            </div>
        </div>
    );
};
