import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { GlassCard, JellyButton } from '@/components/ui';
import { Plus, Brain, Workflow, Zap, Activity, Edit, Trash2, Play } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { HierarchicalEntity, EntityType } from '@/types';
import './EntityLibrary.css';

export const EntityLibrary: React.FC = () => {
    const [entities, setEntities] = useState<HierarchicalEntity[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState<EntityType | 'ALL'>('ALL');

    useEffect(() => {
        fetchEntities();
    }, []);

    const fetchEntities = async () => {
        try {
            const { data } = await apiClient.get('/ai/entities');
            setEntities(data);
        } catch (error) {
            console.error('Failed to fetch entities:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (id: string) => {
        if (window.confirm('Are you sure you want to delete this entity?')) {
            try {
                await apiClient.delete(`/ai/entities/${id}`);
                setEntities(entities.filter(e => e.id !== id));
            } catch (error) {
                console.error('Failed to delete entity:', error);
            }
        }
    };

    const getTypeIcon = (type: EntityType) => {
        switch (type) {
            case EntityType.ACTION: return <Zap size={20} />;
            case EntityType.SKILL: return <Activity size={20} />;
            case EntityType.AGENT: return <Brain size={20} />;
            case EntityType.PROCESS: return <Workflow size={20} />;
        }
    };

    const getTypeColor = (type: EntityType) => {
        switch (type) {
            case EntityType.ACTION: return 'var(--color-primary)';
            case EntityType.SKILL: return 'var(--color-secondary)';
            case EntityType.AGENT: return 'var(--color-rose-gold)';
            case EntityType.PROCESS: return 'var(--color-accent)';
        }
    };

    const filteredEntities = filter === 'ALL' 
        ? entities 
        : entities.filter(e => e.type === filter);

    if (loading) {
        return <div className="loading">Initializing Neural Hub...</div>;
    }

    return (
        <div className="entity-library-page">
            <div className="page-header">
                <div>
                    <h1>Entity Library</h1>
                    <p>Orchestrate Actions, Skills, Agents, and Processes</p>
                </div>
                <div className="header-actions">
                    <Link to="/ai/entities/create">
                        <JellyButton roseGold>
                            <Plus size={20} />
                            Create Entity
                        </JellyButton>
                    </Link>
                </div>
            </div>

            <div className="filter-tabs">
                {(['ALL', ...Object.values(EntityType)] as const).map(t => (
                    <button 
                        key={t}
                        className={`filter-tab ${filter === t ? 'active' : ''}`}
                        onClick={() => setFilter(t)}
                    >
                        {t}
                    </button>
                ))}
            </div>

            <div className="entities-grid">
                {filteredEntities.length === 0 ? (
                    <GlassCard className="empty-state">
                        <Brain size={64} color="var(--color-text-tertiary)" />
                        <h3>Nothing here yet</h3>
                        <p>Begin by creating an Atomic Action or a Complex Process</p>
                    </GlassCard>
                ) : (
                    filteredEntities.map((entity) => (
                        <GlassCard key={entity.id} hover className="entity-card">
                            <div className="entity-card-header">
                                <div className="entity-icon" style={{ color: getTypeColor(entity.type) }}>
                                    {getTypeIcon(entity.type)}
                                </div>
                                <div className="entity-info">
                                    <h3>{entity.name}</h3>
                                    <span className="entity-type-badge" style={{ backgroundColor: getTypeColor(entity.type) + '22', color: getTypeColor(entity.type) }}>
                                        {entity.type}
                                    </span>
                                </div>
                            </div>

                            <p className="entity-description">
                                {entity.description || 'No description provided.'}
                            </p>

                            <div className="entity-meta">
                                {entity.llm_config && (
                                    <span className="meta-item">{entity.llm_config.model}</span>
                                )}
                                {entity.static_plan?.steps && (
                                    <span className="meta-item">{entity.static_plan.steps.length} steps</span>
                                )}
                            </div>

                            <div className="entity-actions">
                                <Link to={`/ai/execute/${entity.id}`}>
                                    <JellyButton variant="primary">
                                        <Play size={16} />
                                        Run
                                    </JellyButton>
                                </Link>
                                <Link to={`/ai/entities/edit/${entity.id}`}>
                                    <JellyButton variant="secondary">
                                        <Edit size={16} />
                                        Edit
                                    </JellyButton>
                                </Link>
                                <JellyButton
                                    variant="ghost"
                                    onClick={() => handleDelete(entity.id)}
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
