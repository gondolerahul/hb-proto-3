import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { GlassCard, GlassInput, JellyButton } from '@/components/ui';
import { Play, ArrowLeft, Loader } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { useSSE } from '@/hooks/useSSE';
import { HierarchicalEntity, EntityType, RunStatus } from '@/types';
import './ExecutionPage.css';

export const ExecutionPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();

    const [entity, setEntity] = useState<HierarchicalEntity | null>(null);
    const [variables, setVariables] = useState<Record<string, string>>({});
    const [requiredVars, setRequiredVars] = useState<string[]>([]);

    const [executing, setExecuting] = useState(false);
    const [executionId, setExecutionId] = useState<string | null>(null);
    const [output, setOutput] = useState<string>('');
    const [status, setStatus] = useState<RunStatus | 'idle'>('idle');
    const [error, setError] = useState('');

    useEffect(() => {
        fetchDetails();
    }, [id]);

    const fetchDetails = async () => {
        try {
            const { data } = await apiClient.get<HierarchicalEntity>(`/ai/entities/${id}`);
            setEntity(data);

            // Extract variables from prompt template (for actions)
            if (data.type === EntityType.ACTION && data.static_plan?.prompt_template) {
                const regex = /\{\{(\w+)\}\}/g;
                const matches = data.static_plan.prompt_template.matchAll(regex);
                const vars = Array.from(new Set(Array.from(matches, (m: any) => m[1])));
                setRequiredVars(vars);

                // Initialize variable state
                const initialVars: Record<string, string> = {};
                vars.forEach(v => initialVars[v] = '');
                setVariables(initialVars);
            }
        } catch (error) {
            console.error('Failed to fetch details:', error);
            setError('Failed to load execution target');
        }
    };

    const handleExecute = async () => {
        setError('');
        setOutput('');
        setStatus(RunStatus.PENDING);
        setExecuting(true);

        try {
            const payload = {
                entity_id: id,
                input_data: variables,
            };

            const { data } = await apiClient.post('/ai/execute', payload);

            setExecutionId(data.id);
            setStatus(RunStatus.RUNNING);

            // Redirect to history or detail immediately or wait?
            // For HireBuddha, we usually stay on the page or go to detail.
            // Let's go to detail page soon, but for now just show running.
            navigate(`/executions/${data.id}`);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Execution failed');
            setExecuting(false);
            setStatus(RunStatus.FAILED);
        }
    };

    const canExecute = !entity || entity.type !== EntityType.ACTION || requiredVars.every(v => variables[v]?.trim());

    return (
        <div className="execution-page">
            <div className="execution-header">
                <JellyButton variant="ghost" onClick={() => navigate(-1)}>
                    <ArrowLeft size={20} />
                    Back
                </JellyButton>
                <h1>Execute: {entity?.name || 'Loading...'}</h1>
            </div>

            <div className="execution-grid">
                {/* Input Panel */}
                <GlassCard className="execution-input">
                    <h2>Input</h2>

                    {entity?.type === EntityType.ACTION && requiredVars.length > 0 ? (
                        <>
                            <p className="help-text">Provide values for the required variables:</p>
                            {requiredVars.map((varName) => (
                                <GlassInput
                                    key={varName}
                                    label={varName}
                                    value={variables[varName] || ''}
                                    onChange={(e) => setVariables({ ...variables, [varName]: e.target.value })}
                                    required
                                />
                            ))}
                        </>
                    ) : (
                        <p className="help-text">
                            {entity?.type && entity.type !== EntityType.ACTION
                                ? `This ${entity.type.toLowerCase()} will execute its plan recursively.`
                                : 'This action requires no input variables.'}
                        </p>
                    )}

                    <JellyButton
                        roseGold
                        onClick={handleExecute}
                        disabled={executing || !canExecute}
                        className="execute-btn"
                    >
                        {executing ? (
                            <>
                                <Loader className="spin" size={20} />
                                {status === RunStatus.PENDING ? 'Queued...' : 'Running...'}
                            </>
                        ) : (
                            <>
                                <Play size={20} />
                                Execute
                            </>
                        )}
                    </JellyButton>

                    {error && <div className="error-message">{error}</div>}
                </GlassCard>

                {/* Output Panel */}
                <GlassCard className="execution-output">
                    <div className="output-header">
                        <h2>Output</h2>
                        {status && status !== 'idle' && (
                            <span className={`status-badge ${status.toLowerCase()}`}>
                                {status}
                            </span>
                        )}
                    </div>

                    <div className="output-container">
                        {output ? (
                            <pre className="output-text">{output}</pre>
                        ) : (
                            <div className="output-placeholder">
                                <p>Execution triggered. Redirecting to trace view...</p>
                            </div>
                        )}
                    </div>
                </GlassCard>
            </div>
        </div>
    );
};
