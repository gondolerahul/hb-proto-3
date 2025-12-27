import React, { useState, useCallback, useRef } from 'react';
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
import { Save, Wrench, Layers, Trash2, Brain, Zap } from 'lucide-react';
import { EntityType } from '@/types';
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

export const EntityFlow: React.FC<EntityFlowProps> = ({ initialNodes = [], initialEdges = [], onSave }) => {
    const reactFlowWrapper = useRef<HTMLDivElement>(null);
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
    const [reactFlowInstance, setReactFlowInstance] = useState<any>(null);
    const [selectedNode, setSelectedNode] = useState<Node | null>(null);

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
            const entityType = event.dataTransfer.getData('application/reactflow/entityType');

            if (!type || !reactFlowBounds || !reactFlowInstance) return;

            const position = reactFlowInstance.project({
                x: event.clientX - reactFlowBounds.left,
                y: event.clientY - reactFlowBounds.top,
            });

            const newNode: Node = {
                id: crypto.randomUUID(),
                type,
                position,
                data: {
                    label: `New ${entityType || 'Node'}`,
                    type: entityType,
                    description: 'Configure this node...',
                    childrenCount: 0,
                    toolsCount: 0
                },
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
    };

    const deleteNode = () => {
        if (!selectedNode) return;
        setNodes((nds) => nds.filter((n) => n.id !== selectedNode.id));
        setEdges((eds) => eds.filter((e) => e.source !== selectedNode.id && e.target !== selectedNode.id));
        setSelectedNode(null);
    };

    return (
        <div className="entity-flow-wrapper">
            <div className="entity-flow-sidebar">
                <h3>Components</h3>
                <p className="sidebar-hint">Drag onto canvas</p>

                <div className="draggable-section">
                    <h4>AI Entities</h4>
                    <div
                        className="draggable-item glass"
                        draggable
                        onDragStart={(e) => {
                            e.dataTransfer.setData('application/reactflow/type', 'entityNode');
                            e.dataTransfer.setData('application/reactflow/entityType', EntityType.AGENT);
                        }}
                    >
                        <Layers size={16} /> Agent
                    </div>
                    <div
                        className="draggable-item glass"
                        draggable
                        onDragStart={(e) => {
                            e.dataTransfer.setData('application/reactflow/type', 'entityNode');
                            e.dataTransfer.setData('application/reactflow/entityType', EntityType.SKILL);
                        }}
                    >
                        <Brain size={16} /> Skill
                    </div>
                    <div
                        className="draggable-item glass"
                        draggable
                        onDragStart={(e) => {
                            e.dataTransfer.setData('application/reactflow/type', 'entityNode');
                            e.dataTransfer.setData('application/reactflow/entityType', EntityType.ACTION);
                        }}
                    >
                        <Zap size={16} /> Action
                    </div>
                </div>

                <div className="draggable-section">
                    <h4>Functional Units</h4>
                    <div
                        className="draggable-item glass tool-item"
                        draggable
                        onDragStart={(e) => {
                            e.dataTransfer.setData('application/reactflow/type', 'toolNode');
                        }}
                    >
                        <Wrench size={16} /> Tool
                    </div>
                </div>

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
                                value={selectedNode.data.description}
                                onChange={(e) => handleNodeDataChange({ description: e.target.value })}
                            />
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
                            <Save size={18} /> Save Architecture
                        </JellyButton>
                    </Panel>
                </ReactFlow>
            </div>
        </div>
    );
};
