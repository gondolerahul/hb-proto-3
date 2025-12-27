import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Brain, Zap, Wrench, Layers } from 'lucide-react';
import { EntityType } from '@/types';
import './nodes.css';

const IconMap = {
    [EntityType.ACTION]: Zap,
    [EntityType.SKILL]: Brain,
    [EntityType.AGENT]: Layers,
    [EntityType.PROCESS]: Zap, // Defaulting for now
};

export const EntityNode = memo(({ data, selected }: NodeProps) => {
    const Icon = IconMap[data.type as EntityType] || Brain;
    const isRoot = data.isRoot;

    return (
        <div className={`entity-node glass ${data.type.toLowerCase()} ${selected ? 'selected' : ''} ${isRoot ? 'root-node' : ''}`}>
            {!isRoot && <Handle type="target" position={Position.Left} className="node-handle" />}

            <div className="node-header">
                <div className="node-icon">
                    <Icon size={16} />
                </div>
                <div className="node-title-area">
                    <div className="node-label">{data.label || 'Untitled'}</div>
                    <div className="node-type">{data.type}</div>
                </div>
            </div>

            {data.description && (
                <div className="node-description">{data.description}</div>
            )}

            {data.childrenCount > 0 && (
                <div className="node-stats">
                    <Layers size={12} />
                    <span>{data.childrenCount} Nested Entities</span>
                </div>
            )}

            {data.toolsCount > 0 && (
                <div className="node-stats">
                    <Wrench size={12} />
                    <span>{data.toolsCount} Tools</span>
                </div>
            )}

            <Handle type="source" position={Position.Right} className="node-handle" />
        </div>
    );
});
