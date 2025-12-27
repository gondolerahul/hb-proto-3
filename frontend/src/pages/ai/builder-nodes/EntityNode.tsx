import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Brain, Zap, Wrench, Layers, CheckCircle2, AlertCircle } from 'lucide-react';
import { EntityType } from '@/types';
import './nodes.css';

const IconMap = {
    [EntityType.ACTION]: Zap,
    [EntityType.SKILL]: Brain,
    [EntityType.AGENT]: Layers,
    [EntityType.PROCESS]: Layers,
};

export const EntityNode = memo(({ data, selected }: NodeProps) => {
    const Icon = IconMap[data.type as EntityType] || Brain;
    const isRoot = data.isRoot;
    const hasEntityRef = !!data.entityRef;

    return (
        <div className={`entity-node glass ${data.type?.toLowerCase() || 'default'} ${selected ? 'selected' : ''} ${isRoot ? 'root-node' : ''} ${hasEntityRef ? 'linked' : ''}`}>
            {!isRoot && <Handle type="target" position={Position.Left} className="node-handle" />}

            <div className="node-header">
                <div className="node-icon">
                    <Icon size={16} />
                </div>
                <div className="node-title-area">
                    <div className="node-label">{data.label || 'Untitled'}</div>
                    <div className="node-type">{data.type || 'GENERIC'}</div>
                </div>
                {hasEntityRef && (
                    <div className="node-status-icon" title="Linked to entity">
                        <CheckCircle2 size={14} />
                    </div>
                )}
                {data.required === false && (
                    <div className="node-optional-badge" title="Optional step">OPT</div>
                )}
            </div>

            {data.description && (
                <div className="node-description">{data.description}</div>
            )}

            {hasEntityRef && (
                <div className="node-footer">
                    <span className="node-ref-label">→ {data.entityRef.name}</span>
                </div>
            )}

            <Handle type="source" position={Position.Right} className="node-handle" />
        </div>
    );
});
