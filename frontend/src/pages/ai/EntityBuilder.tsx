import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { JellyButton } from '@/components/ui';
import { X } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { HierarchicalEntity, EntityType, EntityStatus } from '@/types';
import { EntityFlow } from './EntityFlow';
import { Node, Edge } from 'reactflow';
import './EntityBuilder.css';

export const EntityBuilder: React.FC = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [initialNodes, setInitialNodes] = useState<Node[]>([]);
    const [initialEdges, setInitialEdges] = useState<Edge[]>([]);
    const [viewMode, setViewMode] = useState<'visual' | 'advanced'>('visual');

    // Basic Entity State (Metadata)
    const [entityBase, setEntityBase] = useState<Partial<HierarchicalEntity>>({
        name: '',
        display_name: '',
        type: EntityType.AGENT,
        version: '1.0.0',
        status: EntityStatus.ACTIVE,
    });

    useEffect(() => {
        if (id) {
            fetchEntity();
        } else {
            // Default setup for a new entity
            const rootId = 'root';
            setInitialNodes([{
                id: rootId,
                type: 'entityNode',
                position: { x: 250, y: 50 },
                data: {
                    label: 'New Agent',
                    type: EntityType.AGENT,
                    isRoot: true,
                    description: 'The primary controller node.'
                }
            }]);
        }
    }, [id]);

    const fetchEntity = async () => {
        try {
            setLoading(true);
            const { data } = await apiClient.get<HierarchicalEntity>(`/ai/entities/${id}`);
            setEntityBase(data);

            // Map hierarchical steps/tools to nodes/edges
            const nodes: Node[] = [];
            const edges: Edge[] = [];

            // Root Node
            nodes.push({
                id: 'root',
                type: 'entityNode',
                position: { x: 250, y: 50 },
                data: {
                    label: data.display_name || data.name,
                    type: data.type,
                    isRoot: true,
                    description: data.description,
                    childrenCount: data.planning?.static_plan?.steps?.filter(s => s.type === 'CHILD_ENTITY_INVOCATION').length || 0,
                    toolsCount: data.capabilities?.tools?.length || 0
                }
            });

            // Map Steps to Nodes (Simplified for now)
            if (data.planning?.static_plan?.steps) {
                data.planning.static_plan.steps.forEach((step, idx) => {
                    const stepId = step.step_id || `step-${idx}`;
                    nodes.push({
                        id: stepId,
                        type: 'entityNode',
                        position: { x: 250, y: (idx + 1) * 200 },
                        data: {
                            label: step.name,
                            type: step.type === 'CHILD_ENTITY_INVOCATION' ? 'CHILD' : 'STEP',
                            description: step.target?.prompt_template || 'Logic step'
                        }
                    });

                    edges.push({
                        id: `edge-${idx}`,
                        source: idx === 0 ? 'root' : data.planning?.static_plan?.steps?.[idx - 1]?.step_id || `step-${idx - 1}`,
                        target: stepId,
                        animated: true
                    });
                });
            }

            setInitialNodes(nodes);
            setInitialEdges(edges);
        } catch (error) {
            console.error('Failed to fetch entity:', error);
            setError('Failed to load entity architecture');
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async (nodes: Node[], _edges: Edge[]) => {
        setLoading(true);
        setError('');

        // Convert Nodes/Edges back to Hierarchical Payload
        // In a real app, this mapping would be more sophisticated
        const rootNode = nodes.find(n => n.id === 'root' || n.data.isRoot);

        const payload = {
            ...entityBase,
            name: rootNode?.data.label.toLowerCase().replace(/\s+/g, '_') || entityBase.name,
            display_name: rootNode?.data.label || entityBase.display_name,
            description: rootNode?.data.description || entityBase.description,
            // Mapping logic would continue here...
        };

        try {
            if (id) {
                await apiClient.put(`/ai/entities/${id}`, payload);
            } else {
                await apiClient.post('/ai/entities', payload);
            }
            navigate('/ai/entities');
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to save entity architecture');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="entity-builder visual-builder">
            <div className="builder-header">
                <div className="title-section">
                    <div className="breadcrumb">AI Architect / {id ? 'Modify' : 'Create'}</div>
                    <h1>{entityBase.display_name || 'Autonomous Architect'}</h1>
                </div>

                <div className="header-actions">
                    <div className="mode-toggle glass">
                        <button
                            className={viewMode === 'visual' ? 'active' : ''}
                            onClick={() => setViewMode('visual')}
                        >
                            Visual Flow
                        </button>
                        <button
                            className={viewMode === 'advanced' ? 'active' : ''}
                            onClick={() => setViewMode('advanced')}
                        >
                            Advanced Config
                        </button>
                    </div>
                    <JellyButton variant="ghost" onClick={() => navigate('/ai/entities')}>
                        <X size={20} />
                    </JellyButton>
                </div>
            </div>

            <div className="builder-main">
                {loading ? (
                    <div className="loading-state glass">
                        <div className="spinner"></div>
                        <p>Synthesizing Architecture...</p>
                    </div>
                ) : (
                    <EntityFlow
                        initialNodes={initialNodes}
                        initialEdges={initialEdges}
                        onSave={handleSave}
                    />
                )}
            </div>

            {error && <div className="error-toast glass">{error}</div>}
        </div>
    );
};
