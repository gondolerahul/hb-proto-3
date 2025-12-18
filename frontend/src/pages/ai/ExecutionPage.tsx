import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { GlassCard, GlassInput, JellyButton } from '@/components/ui';
import { Play, ArrowLeft, Loader } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import { useSSE } from '@/hooks/useSSE';
import './ExecutionPage.css';

export const ExecutionPage: React.FC = () => {
    const { type, id } = useParams<{ type: 'agent' | 'workflow'; id: string }>();
    const navigate = useNavigate();

    const [name, setName] = useState('');
    const [variables, setVariables] = useState<Record<string, string>>({});
    const [requiredVars, setRequiredVars] = useState<string[]>([]);

    const [executing, setExecuting] = useState(false);
    const [executionId, setExecutionId] = useState<string | null>(null);
    const [output, setOutput] = useState<string>('');
    const [status, setStatus] = useState<'idle' | 'pending' | 'running' | 'completed' | 'failed'>('idle');
    const [error, setError] = useState('');

    // SSE connection
    const sseUrl = executionId ? `${import.meta.env.VITE_API_BASE_URL}/ai/executions/${executionId}/stream` : null;
    const { isConnected } = useSSE(sseUrl, {
        onMessage: (data) => {
            if (data.chunk) {
                setOutput(prev => prev + data.chunk);
            }
            if (data.status) {
                setStatus(data.status);
                if (data.status === 'completed' || data.status === 'failed') {
                    setExecuting(false);
                }
            }
            if (data.result) {
                setOutput(JSON.stringify(data.result, null, 2));
            }
        },
        onComplete: () => {
            setStatus('completed');
            setExecuting(false);
        },
        onError: () => {
            setError('Streaming connection failed');
            setExecuting(false);
        },
    });

    useEffect(() => {
        fetchDetails();
    }, [type, id]);

    const fetchDetails = async () => {
        try {
            const endpoint = type === 'agent' ? `/ai/agents/${id}` : `/ai/workflows/${id}`;
            const { data } = await apiClient.get(endpoint);
            setName(data.name);

            // Extract variables from role/system prompt (for agents)
            if (type === 'agent' && data.role) {
                const regex = /\{\{(\w+)\}\}/g;
                const matches = data.role.matchAll(regex);
                const vars = Array.from(new Set(Array.from(matches, m => m[1])));
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
        setStatus('pending');
        setExecuting(true);

        try {
            const payload = {
                agent_id: type === 'agent' ? id : null,
                workflow_id: type === 'workflow' ? id : null,
                input_data: type === 'agent' ? variables : {},
            };

            const { data } = await apiClient.post('/ai/execute', payload);

            setExecutionId(data.id);
            setStatus('running');
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Execution failed');
            setExecuting(false);
            setStatus('failed');
        }
    };

    const canExecute = type === 'workflow' || requiredVars.every(v => variables[v]?.trim());

    return (
        <div className="execution-page">
            <div className="execution-header">
                <JellyButton variant="ghost" onClick={() => navigate(-1)}>
                    <ArrowLeft size={20} />
                    Back
                </JellyButton>
                <h1>Execute: {name}</h1>
            </div>

            <div className="execution-grid">
                {/* Input Panel */}
                <GlassCard className="execution-input">
                    <h2>Input</h2>

                    {type === 'agent' && requiredVars.length > 0 ? (
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
                            {type === 'workflow'
                                ? 'This workflow will execute all steps in sequence.'
                                : 'This agent requires no input variables.'}
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
                                {status === 'queued' ? 'Queued...' : 'Running...'}
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
                        {isConnected && (
                            <span className="status-badge connected">
                                ● Streaming
                            </span>
                        )}
                        {status && status !== 'idle' && (
                            <span className={`status-badge ${status}`}>
                                {status}
                            </span>
                        )}
                    </div>

                    <div className="output-container">
                        {output ? (
                            <pre className="output-text">{output}</pre>
                        ) : (
                            <div className="output-placeholder">
                                <p>Execution output will appear here...</p>
                            </div>
                        )}
                    </div>
                </GlassCard>
            </div>
        </div>
    );
};
