import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { MainLayout } from '@/components/layout';
import { LoginPage, RegisterPage } from '@/pages/auth';
import { ForgotPasswordPage, ResetPasswordPage } from '@/pages/auth/PasswordReset';
import { OAuthCallbackPage } from '@/pages/auth/OAuthCallback';
import { Dashboard } from '@/pages/Dashboard';
import { AgentList } from '@/pages/ai/AgentList';
import { AgentBuilder } from '@/pages/ai/AgentBuilder';
import { WorkflowList } from '@/pages/ai/WorkflowList';
import { WorkflowBuilder } from '@/pages/ai/WorkflowBuilder';
import { ExecutionPage } from '@/pages/ai/ExecutionPage';
import { ExecutionHistory } from '@/pages/ai/ExecutionHistory';
import { ExecutionDetail } from '@/pages/ai/ExecutionDetail';
import { KnowledgeBase } from '@/pages/KnowledgeBase';
import { BillingDashboard } from '@/pages/BillingDashboard';
import { SystemConfig } from '@/pages/SystemConfig';
import { UserSettings } from '@/pages/UserSettings';
import TenantManagement from '@/pages/TenantManagement';

// Protected Route Component
interface ProtectedRouteProps {
    children: React.ReactNode;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
    const { isAuthenticated, loading } = useAuth();

    if (loading) {
        return <div className="loading-screen">Loading...</div>;
    }

    return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
};

// Public Route (redirect if authenticated)
const PublicRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
    const { isAuthenticated, loading } = useAuth();

    if (loading) {
        return <div className="loading-screen">Loading...</div>;
    }

    return !isAuthenticated ? <>{children}</> : <Navigate to="/dashboard" replace />;
};

export const AppRouter: React.FC = () => {
    return (
        <BrowserRouter>
            <Routes>
                {/* Public Routes */}
                <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
                <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />
                <Route path="/forgot-password" element={<PublicRoute><ForgotPasswordPage /></PublicRoute>} />
                <Route path="/reset-password" element={<PublicRoute><ResetPasswordPage /></PublicRoute>} />
                <Route path="/auth/callback" element={<OAuthCallbackPage />} />

                {/* Protected Routes */}
                <Route path="/" element={<Navigate to="/dashboard" replace />} />

                {/* Dashboard */}
                <Route
                    path="/dashboard"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <Dashboard />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />

                {/* AI Agents */}
                <Route
                    path="/agents"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <AgentList />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />
                <Route
                    path="/agents/create"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <AgentBuilder />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />
                <Route
                    path="/agents/:id"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <AgentBuilder />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />

                {/* Workflows */}
                <Route
                    path="/workflows"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <WorkflowList />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />
                <Route
                    path="/workflows/create"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <WorkflowBuilder />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />
                <Route
                    path="/workflows/:id"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <WorkflowBuilder />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />

                {/* Execution */}
                <Route
                    path="/execute/:type/:id"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <ExecutionPage />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />

                {/* Executions History */}
                <Route
                    path="/executions"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <ExecutionHistory />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />

                {/* Execution Detail */}
                <Route
                    path="/executions/:id"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <ExecutionDetail />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />

                {/* Knowledge Base */}
                <Route
                    path="/knowledge"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <KnowledgeBase />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />

                {/* Billing */}
                <Route
                    path="/billing"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <BillingDashboard />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />

                {/* System Settings */}
                <Route
                    path="/settings"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <SystemConfig />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />

                {/* User Settings */}
                <Route
                    path="/profile"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <UserSettings />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />

                {/* Tenant Management */}
                <Route
                    path="/tenants"
                    element={
                        <ProtectedRoute>
                            <MainLayout>
                                <TenantManagement />
                            </MainLayout>
                        </ProtectedRoute>
                    }
                />

                {/* 404 Route */}
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
        </BrowserRouter>
    );
};
