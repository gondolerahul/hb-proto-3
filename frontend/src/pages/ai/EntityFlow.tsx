import React, { useState, useCallback, useRef, useEffect } from 'react';
import ReactFlow, {
    addEdge,
    Background,
    Controls,
    MiniMap,
    Connection,
    Edge,
    Node,
    useNodesState,
    useEdgesState,
    Panel
} from 'reactflow';
import 'reactflow/dist/style.css';
import { EntityNode } from './builder-nodes/EntityNode';
import { ToolNode } from './builder-nodes/ToolNode';
import { JellyButton } from '@/components/ui';
import { Save, Wrench, Layers, Trash2, Brain, Zap, Activity, CheckSquare, Square } from 'lucide-react';
import { EntityType, HierarchicalEntity } from '@/types';
import { apiClient } from '@/services/api.client';
import './EntityFlow.css';

const nodeTypes = {
    entityNode: EntityNode,
    toolNode: ToolNode,
};

interface EntityFlowProps {
    initialNodes?: Node[];
    initialEdges?: Edge[];
    onSave: (nodes: Node[], edges: Edge[]) => void;
}

interface Tool {
    name: string;
    description: string;
}

export const EntityFlow: React.FC<EntityFlowProps> = ({ initialNodes = [], initialEdges = [], onSave }) => {
    const reactFlowWrapper = useRef<HTMLDivElement>(null);
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
    const [reactFlowInstance, setReactFlowInstance] = useState<any>(null);
    const [selectedNode, setSelectedNode] = useState<Node | null>(null);

    // Library data
    const [entities, setEntities] = useState<HierarchicalEntity[]>([]);
    const [tools, setTools] = useState<Tool[]>([]);
    const [loadingLibraries, setLoadingLibraries] = useState(true);

    useEffect(() => {
        fetchLibraries();
    }, []);

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

    const onConnect = useCallback((params: Connection | Edge) => setEdges((eds) => addEdge(params, eds)), [setEdges]);

    const onDragOver = useCallback((event: React.DragEvent) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
    }, []);

    const onDrop = useCallback(
        (event: React.DragEvent) => {
            event.preventDefault();

            const reactFlowBounds = reactFlowWrapper.current?.getBoundingClientRect();
            const type = event.dataTransfer.getData('application/reactflow/type');
            const dataPayload = event.dataTransfer.getData('application/reactflow/data');

            if (!type || !reactFlowBounds || !reactFlowInstance) return;

            const position = reactFlowInstance.project({
                x: event.clientX - reactFlowBounds.left,
                y: event.clientY - reactFlowBounds.top,
            });

            let nodeData: any = {
                label: 'New Node',
                description: 'Configure this node...',
            };

            if (dataPayload) {
                const parsedData = JSON.parse(dataPayload);
                if (type === 'entityNode') {
                    nodeData = {
                        label: parsedData.display_name || parsedData.name,
                        type: parsedData.type,
                        description: parsedData.description,
                        entityRef: {
                            id: parsedData.id,
                            name: parsedData.name,
                            type: parsedData.type,
                        },
                    };
                } else if (type === 'toolNode') {
                    nodeData = {
                        label: parsedData.name,
                        description: parsedData.description,
                        toolRef: {
                            tool_id: parsedData.name,
                            name: parsedData.name,
                            description: parsedData.description,
                        },
                    };
                }
            }

            const newNode: Node = {
                id: crypto.randomUUID(),
                type,
                position,
                data: nodeData,
            };

            setNodes((nds) => nds.concat(newNode));
        },
        [reactFlowInstance, setNodes]
    );

    const onNodeClick = (_: React.MouseEvent, node: Node) => {
        setSelectedNode(node);
    };

    const handleNodeDataChange = (newData: any) => {
        if (!selectedNode) return;
        setNodes((nds) =>
            nds.map((node) => {
                if (node.id === selectedNode.id) {
                    return { ...node, data: { ...node.data, ...newData } };
                }
                return node;
            })
        );
        // Update selected node to reflect changes
        setSelectedNode({ ...selectedNode, data: { ...selectedNode.data, ...newData } });
    };

    const deleteNode = () => {
        if (!selectedNode) return;
        setNodes((nds) => nds.filter((n) => n.id !== selectedNode.id));
        setEdges((eds) => eds.filter((e) => e.source !== selectedNode.id && e.target !== selectedNode.id));
        setSelectedNode(null);
    };

    const handleLinkEntity = (entityId: string) => {
        const entity = entities.find(e => e.id === entityId);
        if (entity) {
            handleNodeDataChange({
                label: entity.display_name || entity.name,
                entityRef: {
                    id: entity.id,
                    name: entity.name,
                    type: entity.type,
                },
            });
        }
    };

    const handleLinkTool = (toolName: string) => {
        const tool = tools.find(t => t.name === toolName);
        if (tool) {
            handleNodeDataChange({
                label: tool.name,
                toolRef: {
                    tool_id: tool.name,
                    name: tool.name,
                    description: tool.description,
                },
            });
        }
    };

    return (
        <div className="entity-flow-wrapper">
            <div className="entity-flow-sidebar">
                <h3>Entity Library</h3>
                <p className="sidebar-hint">Drag onto canvas</p>

                {loadingLibraries ? (
                    <div className="library-loading">Loading...</div>
                ) : (
                    <>
                        <div className="draggable-section">
                            <h4>Available Entities</h4>
                            {entities.slice(0, 10).map((entity) => (
                                <div
                                    key={entity.id}
                                    className="draggable-item glass entity-item"
                                    draggable
                                    onDragStart={(e) => {
                                        e.dataTransfer.setData('application/reactflow/type', 'entityNode');
                                        e.dataTransfer.setData('application/reactflow/data', JSON.stringify(entity));
                                    }}
                                >
                                    <div className="item-header">
                                        {entity.type === EntityType.AGENT && <Layers size={14} />}
                                        {entity.type === EntityType.SKILL && <Brain size={14} />}
                                        {entity.type === EntityType.ACTION && <Zap size={14} />}
                                        {entity.type === EntityType.PROCESS && <Activity size={14} />}
                                        <span>{entity.display_name || entity.name}</span>
                                    </div>
                                    <div className="item-type">{entity.type}</div>
                                </div>
                            ))}
                            {entities.length === 0 && (
                                <div className="library-empty">No entities created yet</div>
                            )}
                        </div>

                        <div className="draggable-section">
                            <h4>Available Tools</h4>
                            {tools.map((tool) => (
                                <div
                                    key={tool.name}
                                    className="draggable-item glass tool-item"
                                    draggable
                                    onDragStart={(e) => {
                                        e.dataTransfer.setData('application/reactflow/type', 'toolNode');
                                        e.dataTransfer.setData('application/reactflow/data', JSON.stringify(tool));
                                    }}
                                >
                                    <div className="item-header">
                                        <Wrench size={14} />
                                        <span>{tool.name}</span>
                                    </div>
                                    <div className="item-description">{tool.description}</div>
                                </div>
                            ))}
                        </div>
                    </>
                )}

                {selectedNode && (
                    <div className="node-config-panel mt-8">
                        <h3>Configuration</h3>
                        <div className="form-group">
                            <label>Label</label>
                            <input
                                value={selectedNode.data.label}
                                onChange={(e) => handleNodeDataChange({ label: e.target.value })}
                            />
                        </div>
                        <div className="form-group">
                            <label>Description</label>
                            <textarea
                                value={selectedNode.data.description || ''}
                                onChange={(e) => handleNodeDataChange({ description: e.target.value })}
                                rows={3}
                            />
                        </div>

                        {selectedNode.type === 'entityNode' && (
                            <div className="form-group">
                                <label>Link to Entity</label>
                                <select
                                    value={selectedNode.data.entityRef?.id || ''}
                                    onChange={(e) => handleLinkEntity(e.target.value)}
                                >
                                    <option value="">-- Select Entity --</option>
                                    {entities.map((entity) => (
                                        <option key={entity.id} value={entity.id}>
                                            {entity.display_name || entity.name} ({entity.type})
                                        </option>
                                    ))}
                                </select>
                            </div>
                        )}

                        {selectedNode.type === 'toolNode' && (
                            <div className="form-group">
                                <label>Link to Tool</label>
                                <select
                                    value={selectedNode.data.toolRef?.tool_id || ''}
                                    onChange={(e) => handleLinkTool(e.target.value)}
                                >
                                    <option value="">-- Select Tool --</option>
                                    {tools.map((tool) => (
                                        <option key={tool.name} value={tool.name}>
                                            {tool.name}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        )}

                        <div className="form-group">
                            <label className="checkbox-label">
                                <input
                                    type="checkbox"
                                    checked={selectedNode.data.required ?? true}
                                    onChange={(e) => handleNodeDataChange({ required: e.target.checked })}
                                />
                                Required Step
                            </label>
                        </div>

                        <JellyButton variant="danger" size="sm" className="w-full" onClick={deleteNode}>
                            <Trash2 size={16} /> Remove Node
                        </JellyButton>
                    </div>
                )}
            </div>

            <div className="entity-flow-canvas" ref={reactFlowWrapper}>
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={onConnect}
                    onInit={setReactFlowInstance}
                    onDrop={onDrop}
                    onDragOver={onDragOver}
                    onNodeClick={onNodeClick}
                    nodeTypes={nodeTypes}
                    fitView
                >
                    <Background color="rgba(255,255,255,0.05)" gap={20} />
                    <Controls />
                    <MiniMap
                        nodeColor={(n: any) => {
                            if (n.type === 'toolNode') return '#1890ff';
                            return '#c58e7f';
                        }}
                        maskColor="rgba(0,0,0,0.5)"
                        className="glass"
                    />
                    <Panel position="top-right">
                        <JellyButton roseGold onClick={() => onSave(nodes, edges)}>
                            <Save size={18} /> Save Hierarchy
                        </JellyButton>
                    </Panel>
                </ReactFlow>
            </div>
        </div>
    );
};
