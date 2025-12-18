import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { GlassCard, JellyButton } from '@/components/ui';
import { Plus, Workflow as WorkflowIcon, Edit, Trash2, Play } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { Workflow } from '@/types';
import './WorkflowList.css';

export const WorkflowList: React.FC = () => {
    const [workflows, setWorkflows] = useState<Workflow[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchWorkflows();
    }, []);

    const fetchWorkflows = async () => {
        try {
            const { data } = await apiClient.get('/ai/workflows');
            setWorkflows(data);
        } catch (error) {
            console.error('Failed to fetch workflows:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (id: string) => {
        if (window.confirm('Are you sure you want to delete this workflow?')) {
            try {
                await apiClient.delete(`/ai/workflows/${id}`);
                setWorkflows(workflows.filter(w => w.id !== id));
            } catch (error) {
                console.error('Failed to delete workflow:', error);
            }
        }
    };

    if (loading) {
        return <div className="loading">Loading workflows...</div>;
    }

    return (
        <div className="workflow-list-page">
            <div className="page-header">
                <div>
                    <h1>Workflows</h1>
                    <p>Create multi-agent workflows for complex tasks</p>
                </div>
                <Link to="/workflows/create">
                    <JellyButton roseGold>
                        <Plus size={20} />
                        Create Workflow
                    </JellyButton>
                </Link>
            </div>

            <div className="workflows-grid">
                {workflows.length === 0 ? (
                    <GlassCard className="empty-state">
                        <WorkflowIcon size={64} color="var(--color-text-tertiary)" />
                        <h3>No workflows yet</h3>
                        <p>Create your first workflow to chain multiple agents together</p>
                        <Link to="/workflows/create">
                            <JellyButton roseGold>
                                <Plus size={20} />
                                Create Workflow
                            </JellyButton>
                        </Link>
                    </GlassCard>
                ) : (
                    workflows.map((workflow) => (
                        <GlassCard key={workflow.id} hover className="workflow-card">
                            <div className="workflow-card-header">
                                <div className="workflow-icon">
                                    <WorkflowIcon size={24} />
                                </div>
                                <h3>{workflow.name}</h3>
                            </div>

                            {workflow.description && (
                                <p className="workflow-description">{workflow.description}</p>
                            )}

                            <div className="workflow-meta">
                                <span className="workflow-steps">
                                    {workflow.dag?.steps?.length || 0} steps
                                </span>
                            </div>

                            <div className="workflow-actions">
                                <Link to={`/execute/workflow/${workflow.id}`}>
                                    <JellyButton variant="secondary">
                                        <Play size={16} />
                                        Execute
                                    </JellyButton>
                                </Link>
                                <Link to={`/workflows/${workflow.id}`}>
                                    <JellyButton variant="secondary">
                                        <Edit size={16} />
                                        Edit
                                    </JellyButton>
                                </Link>
                                <JellyButton
                                    variant="ghost"
                                    onClick={() => handleDelete(workflow.id)}
                                >
                                    <Trash2 size={16} />
                                </JellyButton>
                            </div>
                        </GlassCard>
                    ))
                )}
            </div>
        </div>
    );
};
