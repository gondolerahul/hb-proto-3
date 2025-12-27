import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { JellyButton } from '@/components/ui';
import { X } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { HierarchicalEntity } from '@/types';
import { EntityConfigurationTabs } from './EntityConfigurationTabs';
import './EntityBuilder.css';

export const EntityBuilder: React.FC = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [entity, setEntity] = useState<HierarchicalEntity | undefined>(undefined);

    useEffect(() => {
        if (id) {
            fetchEntity();
        }
    }, [id]);

    const fetchEntity = async () => {
        try {
            setLoading(true);
            const { data } = await apiClient.get<HierarchicalEntity>(`/ai/entities/${id}`);
            setEntity(data);
        } catch (error) {
            console.error('Failed to fetch entity:', error);
            setError('Failed to load entity');
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async (entityData: any) => {
        setLoading(true);
        setError('');

        try {
            if (id) {
                await apiClient.put(`/ai/entities/${id}`, entityData);
            } else {
                await apiClient.post('/ai/entities', entityData);
            }
            navigate('/ai/entities');
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to save entity');
        } finally {
            setLoading(false);
        }
    };

    const handleCancel = () => {
        navigate('/ai/entities');
    };

    return (
        <div className="entity-builder">
            <div className="builder-header">
                <div className="title-section">
                    <div className="breadcrumb">AI Architect / {id ? 'Edit' : 'Create'}</div>
                    <h1>{entity?.display_name || entity?.name || 'New Entity'}</h1>
                </div>

                <div className="header-actions">
                    <JellyButton variant="ghost" onClick={handleCancel}>
                        <X size={20} />
                    </JellyButton>
                </div>
            </div>

            <div className="builder-main">
                {loading && !entity ? (
                    <div className="loading-state glass">
                        <div className="spinner"></div>
                        <p>Loading Entity...</p>
                    </div>
                ) : (
                    <EntityConfigurationTabs
                        entity={entity}
                        onSave={handleSave}
                        onCancel={handleCancel}
                    />
                )}
            </div>

            {error && <div className="error-toast glass">{error}</div>}
        </div>
    );
};
