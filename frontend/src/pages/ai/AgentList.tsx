import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { GlassCard, JellyButton } from '@/components/ui';
import { Plus, Brain, Edit, Trash2 } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { Agent } from '@/types';
import './AgentList.css';

export const AgentList: React.FC = () => {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchAgents();
    }, []);

    const fetchAgents = async () => {
        try {
            const { data } = await apiClient.get('/ai/agents');
            setAgents(data);
        } catch (error) {
            console.error('Failed to fetch agents:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (id: string) => {
        if (window.confirm('Are you sure you want to delete this agent?')) {
            try {
                await apiClient.delete(`/ai/agents/${id}`);
                setAgents(agents.filter(agent => agent.id !== id));
            } catch (error) {
                console.error('Failed to delete agent:', error);
            }
        }
    };

    if (loading) {
        return <div className="loading">Loading agents...</div>;
    }

    return (
        <div className="agent-list-page">
            <div className="page-header">
                <div>
                    <h1>AI Agents</h1>
                    <p>Create and manage your intelligent agents</p>
                </div>
                <Link to="/agents/create">
                    <JellyButton roseGold>
                        <Plus size={20} />
                        Create Agent
                    </JellyButton>
                </Link>
            </div>

            <div className="agents-grid">
                {agents.length === 0 ? (
                    <GlassCard className="empty-state">
                        <Brain size={64} color="var(--color-text-tertiary)" />
                        <h3>No agents yet</h3>
                        <p>Create your first AI agent to get started</p>
                        <Link to="/agents/create">
                            <JellyButton roseGold>
                                <Plus size={20} />
                                Create Agent
                            </JellyButton>
                        </Link>
                    </GlassCard>
                ) : (
                    agents.map((agent) => (
                        <GlassCard key={agent.id} hover className="agent-card">
                            <div className="agent-card-header">
                                <div className="agent-icon">
                                    <Brain size={24} />
                                </div>
                                <h3>{agent.name}</h3>
                            </div>

                            {agent.description && (
                                <p className="agent-description">{agent.description}</p>
                            )}

                            <div className="agent-meta">
                                <span className="agent-model">{agent.llm_config.model}</span>
                                <span className="agent-temp">Temp: {agent.llm_config.temperature}</span>
                            </div>

                            {agent.llm_config.tools && agent.llm_config.tools.length > 0 && (
                                <div className="agent-tools">
                                    <span>Tools:</span>
                                    {agent.llm_config.tools.map((tool) => (
                                        <span key={tool} className="tool-badge">{tool}</span>
                                    ))}
                                </div>
                            )}

                            <div className="agent-actions">
                                <Link to={`/agents/${agent.id}`}>
                                    <JellyButton variant="secondary">
                                        <Edit size={16} />
                                        Edit
                                    </JellyButton>
                                </Link>
                                <JellyButton
                                    variant="ghost"
                                    onClick={() => handleDelete(agent.id)}
                                >
                                    <Trash2 size={16} />
                                    Delete
                                </JellyButton>
                            </div>
                        </GlassCard>
                    ))
                )}
            </div>
        </div>
    );
};
