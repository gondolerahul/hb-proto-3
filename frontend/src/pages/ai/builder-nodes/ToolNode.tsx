import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Wrench, CheckCircle2 } from 'lucide-react';
import './nodes.css';

export const ToolNode = memo(({ data, selected }: NodeProps) => {
    const hasToolRef = !!data.toolRef;

    return (
        <div className={`entity-node glass tool-node ${selected ? 'selected' : ''} ${hasToolRef ? 'linked' : ''}`}>
            <Handle type="target" position={Position.Left} className="node-handle" />

            <div className="node-header">
                <div className="node-icon tool-icon">
                    <Wrench size={16} />
                </div>
                <div className="node-title-area">
                    <div className="node-label">{data.label || 'Tool'}</div>
                    <div className="node-type">External Tool</div>
                </div>
                {hasToolRef && (
                    <div className="node-status-icon" title="Linked to tool">
                        <CheckCircle2 size={14} />
                    </div>
                )}
            </div>

            {data.description && (
                <div className="node-description">{data.description}</div>
            )}

            {hasToolRef && (
                <div className="node-footer">
                    <span className="node-ref-label">→ {data.toolRef.name}</span>
                </div>
            )}

            <Handle type="source" position={Position.Right} className="node-handle" />
        </div>
    );
});
