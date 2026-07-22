import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { onboardingService, OnboardingStatus } from '@/services/platform.service';
import {
    soloPackService,
    SoloPackBundle,
    GovernancePreview,
    SoloPackStatus,
} from '@/services/soloPack.service';
import { emailService, EmailConnection } from '@/services/email.service';
import './OnboardingWizard.css';

/**
 * The Solo Pack setup wizard (Inc-2 ONBOARD, 04_onboard_wizard.md §1).
 *
 * Each step maps onto a stage of Pragya's nine-stage engagement flow — the
 * same backend contract (`/ai/onboarding/*`) Pragya drives conversationally
 * in Inc 3. Step keys mirror `auth/onboarding_router.ONBOARDING_STEPS`.
 */
const STEPS = [
    {
        key: 'company_profile',
        icon: '🏢',
        title: 'Set Up Your Workspace',
        description: 'Give your workspace a name and brand identity to get started.',
    },
    {
        key: 'channels',
        icon: '🔗',
        title: 'Connect Your Channels',
        description: 'Where your AI workforce meets your customers. Connect email now — WhatsApp is optional.',
        skippable: true,
    },
    {
        key: 'knowledge',
        icon: '📚',
        title: 'Upload Knowledge (Optional)',
        description: 'Your agents work out of the box. Adding documents about your business improves their answers.',
        skippable: true,
    },
    {
        key: 'pack',
        icon: '🧰',
        title: 'Choose Your AI Workforce',
        description: 'The Solo Pack covers acquisition, care, invoicing, books, compliance and reporting. Or start with a focused bundle.',
    },
    {
        key: 'governance',
        icon: '🛡️',
        title: 'Confirm Governance',
        description: 'Every agent starts at A1 — nothing external happens without your approval.',
    },
    {
        key: 'go_live',
        icon: '🚀',
        title: 'You Are Live',
        description: 'Your AI workforce is active. Approvals land in your console.',
    },
];

const OnboardingWizard: React.FC = () => {
    const navigate = useNavigate();
    const { user } = useAuth();
    const [currentStep, setCurrentStep] = useState(0);
    const [status, setStatus] = useState<OnboardingStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Step 1: company profile
    const [companyName, setCompanyName] = useState('');
    const [industry, setIndustry] = useState('');

    // Step 2: channels
    const [emailConnections, setEmailConnections] = useState<EmailConnection[] | null>(null);

    // Steps 4–5: pack choice + governance preview
    const [bundles, setBundles] = useState<SoloPackBundle[] | null>(null);
    const [selectedBundle, setSelectedBundle] = useState<string>('solo_pack');
    const [preview, setPreview] = useState<GovernancePreview | null>(null);
    const [activated, setActivated] = useState(false);

    // Step 6: live status
    const [liveStatus, setLiveStatus] = useState<SoloPackStatus | null>(null);

    const loadStatus = useCallback(async () => {
        try {
            const s = await onboardingService.getStatus();
            setStatus(s);
            const idx = STEPS.findIndex(step => !s.completed_steps.includes(step.key));
            if (idx >= 0) setCurrentStep(idx);
            if (s.status === 'completed') {
                navigate('/dashboard', { replace: true });
            }
        } catch (err) {
            console.error('Failed to load onboarding status:', err);
        } finally {
            setLoading(false);
        }
    }, [navigate]);

    useEffect(() => {
        loadStatus();
    }, [loadStatus]);

    // Lazy-load each step's data when it becomes current.
    const stepKey = STEPS[currentStep]?.key;
    useEffect(() => {
        setError(null);
        if (stepKey === 'channels' && user?.company_id) {
            emailService.getConnections(user.company_id)
                .then(setEmailConnections)
                .catch(() => setEmailConnections([]));
        }
        if (stepKey === 'pack' && bundles === null) {
            soloPackService.listBundles()
                .then(bs => {
                    setBundles(bs);
                    const def = bs.find(b => b.is_default);
                    if (def) setSelectedBundle(def.key);
                })
                .catch(() => setError('Could not load the bundle catalog. Is the backend reachable?'));
        }
        if (stepKey === 'governance') {
            setPreview(null);
            soloPackService.governancePreview(selectedBundle)
                .then(setPreview)
                .catch(() => setError('Could not load the governance preview.'));
        }
        if (stepKey === 'go_live') {
            soloPackService.getStatus()
                .then(s => {
                    setLiveStatus(s);
                    setActivated(s.activated);
                })
                .catch(() => setError('Could not load activation status.'));
        }
    }, [stepKey, user?.company_id, selectedBundle, bundles]);

    const completeAndAdvance = async (stepData?: Record<string, any>) => {
        const step = STEPS[currentStep];
        setSaving(true);
        setError(null);
        try {
            const updated = await onboardingService.completeStep(step.key, stepData);
            setStatus(updated);
            if (currentStep < STEPS.length - 1) {
                setCurrentStep(currentStep + 1);
            } else {
                await onboardingService.finalizeOnboarding();
                navigate(liveStatus?.console_path || '/ai/approvals', { replace: true });
            }
        } catch (err) {
            console.error('Step completion failed:', err);
            setError('Saving this step failed — please retry.');
        } finally {
            setSaving(false);
        }
    };

    const handleNext = async () => {
        const step = STEPS[currentStep];
        if (step.key === 'company_profile') {
            await completeAndAdvance({
                name: companyName || user?.full_name + "'s Workspace",
                industry,
            });
            return;
        }
        if (step.key === 'governance') {
            // Confirm & activate: seed the chosen bundle, then advance.
            setSaving(true);
            setError(null);
            try {
                await soloPackService.activate(selectedBundle);
                setActivated(true);
            } catch (err) {
                console.error('Activation failed:', err);
                setError('Activation failed — please retry.');
                setSaving(false);
                return;
            }
            setSaving(false);
            await completeAndAdvance({ bundle: selectedBundle });
            return;
        }
        if (step.key === 'pack') {
            await completeAndAdvance({ bundle: selectedBundle });
            return;
        }
        await completeAndAdvance();
    };

    const handleSkipOnboarding = async () => {
        try {
            await onboardingService.skipOnboarding();
            navigate('/dashboard', { replace: true });
        } catch (err) {
            console.error('Skip failed:', err);
        }
    };

    if (loading) {
        return (
            <div className="onboarding-wizard">
                <div style={{ color: 'var(--color-text-tertiary)', fontSize: '0.9rem' }}>
                    Loading setup wizard…
                </div>
            </div>
        );
    }

    const step = STEPS[currentStep];

    return (
        <div className="onboarding-wizard">
            <div className="onboarding-container">
                {/* Progress bar */}
                <div className="onboarding-progress">
                    {STEPS.map((s, i) => (
                        <div
                            key={s.key}
                            className={`progress-step ${
                                status?.completed_steps.includes(s.key) ? 'completed' :
                                i === currentStep ? 'active' : ''
                            }`}
                        />
                    ))}
                </div>

                {/* Step content */}
                <div className="step-card">
                    <div className="step-header">
                        <div className="step-icon">{step.icon}</div>
                        <h2>{step.title}</h2>
                        <p>{step.description}</p>
                    </div>

                    <div className="step-content">
                        {error && <div className="step-error">{error}</div>}

                        {step.key === 'company_profile' && (
                            <>
                                <div className="form-group">
                                    <label>Workspace Name</label>
                                    <input
                                        id="onboarding-company-name"
                                        type="text"
                                        placeholder="e.g. Acme Corp"
                                        value={companyName}
                                        onChange={(e) => setCompanyName(e.target.value)}
                                    />
                                </div>
                                <div className="form-group">
                                    <label>Industry</label>
                                    <select
                                        id="onboarding-industry"
                                        value={industry}
                                        onChange={(e) => setIndustry(e.target.value)}
                                    >
                                        <option value="">Select your industry…</option>
                                        <option value="technology">Technology</option>
                                        <option value="real_estate">Real Estate</option>
                                        <option value="healthcare">Healthcare</option>
                                        <option value="education">Education</option>
                                        <option value="finance">Finance & Banking</option>
                                        <option value="ecommerce">E-Commerce</option>
                                        <option value="consulting">Consulting</option>
                                        <option value="marketing">Marketing & Advertising</option>
                                        <option value="other">Other</option>
                                    </select>
                                </div>
                            </>
                        )}

                        {step.key === 'channels' && (
                            <div className="feature-list">
                                <div className={`feature-item ${emailConnections?.length ? 'completed' : ''}`}>
                                    <div className="feature-icon">📧</div>
                                    <div className="feature-text">
                                        <strong>Email (IMAP/SMTP)</strong>
                                        <span>
                                            {emailConnections === null ? 'Checking…'
                                                : emailConnections.length > 0
                                                    ? `Connected: ${emailConnections.map(c => c.email_address).join(', ')}`
                                                    : 'Not connected yet — your acquisition agent answers inbound email.'}
                                        </span>
                                    </div>
                                    {emailConnections?.length
                                        ? <span className="feature-check">✓</span>
                                        : <button className="btn-step secondary" onClick={() => navigate('/integrations')}>Connect</button>}
                                </div>
                                <div className="feature-item">
                                    <div className="feature-icon">📱</div>
                                    <div className="feature-text">
                                        <strong>WhatsApp Business</strong>
                                        <span>Optional — the WhatsApp gateway routes inbound messages to your workforce.</span>
                                    </div>
                                    <button className="btn-step secondary" onClick={() => navigate('/integrations')}>Set up</button>
                                </div>
                            </div>
                        )}

                        {step.key === 'knowledge' && (
                            <div className="feature-list">
                                <div className="feature-item">
                                    <div className="feature-icon">📄</div>
                                    <div className="feature-text">
                                        <strong>Business documents</strong>
                                        <span>Price lists, service descriptions, FAQs — anything your agents should know.</span>
                                    </div>
                                    <button className="btn-step secondary" onClick={() => navigate('/knowledge')}>Upload</button>
                                </div>
                                <div className="feature-item">
                                    <div className="feature-icon">✨</div>
                                    <div className="feature-text">
                                        <strong>Zero documents required</strong>
                                        <span>Your workforce runs on curated templates from day one; knowledge only sharpens it.</span>
                                    </div>
                                </div>
                            </div>
                        )}

                        {step.key === 'pack' && (
                            <div className="bundle-grid">
                                {bundles === null && <div className="step-hint">Loading bundles…</div>}
                                {bundles?.map(b => (
                                    <button
                                        key={b.key}
                                        className={`bundle-card ${selectedBundle === b.key ? 'selected' : ''} ${!b.available_now ? 'unavailable' : ''}`}
                                        disabled={!b.available_now}
                                        onClick={() => setSelectedBundle(b.key)}
                                    >
                                        <div className="bundle-name">
                                            {b.display_name}
                                            {b.is_default && <span className="bundle-badge">Default</span>}
                                        </div>
                                        <div className="bundle-meta">
                                            {b.available_now
                                                ? `${b.agent_count} agents · ${b.process_codes.join(', ')}`
                                                : `Coming soon · ${(b.all_processes || []).join(', ')}`}
                                        </div>
                                    </button>
                                ))}
                            </div>
                        )}

                        {step.key === 'governance' && (
                            <div className="gov-preview">
                                {preview === null && !error && <div className="step-hint">Loading governance preview…</div>}
                                {preview && (
                                    <>
                                        <div className="gov-note">{preview.autonomy_note}</div>
                                        <div className="gov-section-title">Gateways</div>
                                        <ul className="gov-list">
                                            {preview.gateways.map(g => (
                                                <li key={g.name}>
                                                    <span className="gov-entity">{g.display_name || g.name}</span>
                                                    <span className="gov-tags">
                                                        {g.autonomy_level && <em>{g.autonomy_level}</em>}
                                                        {g.code && <code>{g.code}</code>}
                                                    </span>
                                                </li>
                                            ))}
                                        </ul>
                                        {preview.processes.map(p => (
                                            <React.Fragment key={p.process.name}>
                                                <div className="gov-section-title">
                                                    {p.process.display_name || p.process.name}
                                                    {p.process.code && <code>{p.process.code}</code>}
                                                </div>
                                                <ul className="gov-list">
                                                    {p.agents.map(a => (
                                                        <li key={a.name}>
                                                            <span className="gov-entity">{a.display_name || a.name}</span>
                                                            <span className="gov-tags">
                                                                {a.autonomy_level && <em>{a.autonomy_level}</em>}
                                                                {a.sod_class !== 'none' && <span className="gov-sod">{a.sod_class}</span>}
                                                                {a.checkpoint_keys.length > 0 &&
                                                                    <span className="gov-cp">{a.checkpoint_keys.length} checkpoint{a.checkpoint_keys.length > 1 ? 's' : ''}</span>}
                                                            </span>
                                                        </li>
                                                    ))}
                                                </ul>
                                            </React.Fragment>
                                        ))}
                                    </>
                                )}
                            </div>
                        )}

                        {step.key === 'go_live' && (
                            <div className="feature-list">
                                <div className={`feature-item ${activated ? 'completed' : ''}`}>
                                    <div className="feature-icon">🤖</div>
                                    <div className="feature-text">
                                        <strong>{liveStatus ? `${liveStatus.entity_count} entities active` : 'Checking…'}</strong>
                                        <span>{liveStatus?.entities.slice(0, 6).join(', ')}{liveStatus && liveStatus.entities.length > 6 ? '…' : ''}</span>
                                    </div>
                                    {activated && <span className="feature-check">✓</span>}
                                </div>
                                <div className="feature-item">
                                    <div className="feature-icon">⚡</div>
                                    <div className="feature-text">
                                        <strong>{liveStatus ? `${liveStatus.trigger_count} triggers armed` : '…'}</strong>
                                        <span>Inbound email and messages now route to your workforce.</span>
                                    </div>
                                </div>
                                <div className="feature-item">
                                    <div className="feature-icon">🛎️</div>
                                    <div className="feature-text">
                                        <strong>Your approvals console</strong>
                                        <span>Every external action raises a card there until you promote an agent.</span>
                                    </div>
                                    <button
                                        className="btn-step secondary"
                                        onClick={() => navigate(liveStatus?.console_path || '/ai/approvals')}
                                    >
                                        Open console
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Navigation */}
                    <div className="step-nav">
                        <span className="step-counter">
                            Step {currentStep + 1} of {STEPS.length}
                        </span>
                        <div className="step-nav-buttons">
                            {currentStep > 0 && (
                                <button
                                    className="btn-step secondary"
                                    onClick={() => setCurrentStep(currentStep - 1)}
                                >
                                    ← Back
                                </button>
                            )}
                            {(step as any).skippable && (
                                <button
                                    className="btn-step secondary"
                                    onClick={() => completeAndAdvance()}
                                >
                                    Skip
                                </button>
                            )}
                            <button
                                id="onboarding-next-btn"
                                className="btn-step primary"
                                onClick={handleNext}
                                disabled={saving || (step.key === 'governance' && !preview && !error)}
                            >
                                {saving ? 'Saving…' :
                                    step.key === 'governance' ? (activated ? 'Re-confirm →' : 'Confirm & Activate →') :
                                    currentStep === STEPS.length - 1 ? 'Get Started →' : 'Continue →'}
                            </button>
                        </div>
                    </div>
                </div>

                {/* Skip onboarding entirely */}
                <div style={{ textAlign: 'center', marginTop: 'var(--spacing-4)' }}>
                    <button className="btn-skip" onClick={handleSkipOnboarding}>
                        I'll set this up later — skip to dashboard
                    </button>
                </div>
            </div>
        </div>
    );
};

export default OnboardingWizard;
