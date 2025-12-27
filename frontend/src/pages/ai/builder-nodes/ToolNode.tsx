import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Wrench } from 'lucide-react';
import './nodes.css';

export const ToolNode = memo(({ data, selected }: NodeProps) => {
    return (
        <div className={`entity-node glass tool-node ${selected ? 'selected' : ''}`}>
            <Handle type="target" position={Position.Left} className="node-handle" />

            <div className="node-header">
                <div className="node-icon tool-icon">
                    <Wrench size={16} />
                </div>
                <div className="node-title-area">
                    <div className="node-label">{data.label || 'Tool'}</div>
                    <div className="node-type">External Tool</div>
                </div>
            </div>

            <div className="node-description">{data.description}</div>
        </div>
    );
});
