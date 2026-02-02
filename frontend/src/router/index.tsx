import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { MainLayout } from '@/components/layout';
import { UserRole } from '@/types';

// Lazy load pages
const LoginPage = lazy(() => import('@/pages/auth').then(m => ({ default: m.LoginPage })));
const RegisterPage = lazy(() => import('@/pages/auth').then(m => ({ default: m.RegisterPage })));
const ForgotPasswordPage = lazy(() => import('@/pages/auth/PasswordReset').then(m => ({ default: m.ForgotPasswordPage })));
const ResetPasswordPage = lazy(() => import('@/pages/auth/PasswordReset').then(m => ({ default: m.ResetPasswordPage })));
const OAuthCallbackPage = lazy(() => import('@/pages/auth/OAuthCallback').then(m => ({ default: m.OAuthCallbackPage })));
const Dashboard = lazy(() => import('@/pages/Dashboard').then(m => ({ default: m.Dashboard })));
const EntityLibrary = lazy(() => import('@/pages/ai/EntityLibrary').then(m => ({ default: m.EntityLibrary })));
const EntityBuilder = lazy(() => import('@/pages/ai/EntityBuilder').then(m => ({ default: m.EntityBuilder })));
const ExecutionPage = lazy(() => import('@/pages/ai/ExecutionPage').then(m => ({ default: m.ExecutionPage })));
const ExecutionHistory = lazy(() => import('@/pages/ai/ExecutionHistory').then(m => ({ default: m.ExecutionHistory })));
const ExecutionDetail = lazy(() => import('@/pages/ai/ExecutionDetail').then(m => ({ default: m.ExecutionDetail })));
const HITLPanel = lazy(() => import('@/pages/ai/HITLPanel').then(m => ({ default: m.HITLPanel })));
const KnowledgeBase = lazy(() => import('@/pages/KnowledgeBase').then(m => ({ default: m.KnowledgeBase })));
const IntegrationsPage = lazy(() => import('@/pages/IntegrationsPage').then(m => ({ default: m.IntegrationsPage })));
const UserSettings = lazy(() => import('@/pages/UserSettings').then(m => ({ default: m.UserSettings })));
const PlatformManagement = lazy(() => import('@/pages/PlatformManagement').then(m => ({ default: m.PlatformManagement })));

// Loading Component for Suspense
const PageLoader = () => (
    <div className="loading-container">
        <div className="pulse">
            <div className="loading">Initializing...</div>
        </div>
    </div>
);

// Protected Route Component
interface ProtectedRouteProps {
    children: React.ReactNode;
    allowedRoles?: UserRole[];
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, allowedRoles }) => {
    const { isAuthenticated, user, loading } = useAuth();

    if (loading) {
        return <PageLoader />;
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    if (allowedRoles && user && !allowedRoles.includes(user.role)) {
        return <Navigate to="/dashboard" replace />;
    }

    return <>{children}</>;
};

// Public Route (redirect if authenticated)
const PublicRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const { isAuthenticated, loading } = useAuth();

    if (loading) {
        return <PageLoader />;
    }

    return !isAuthenticated ? <>{children}</> : <Navigate to="/dashboard" replace />;
};

export const AppRouter: React.FC = () => {
    return (
        <BrowserRouter>
            <Suspense fallback={<PageLoader />}>
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

                    {/* Hierarchical Entities */}
                    <Route
                        path="/ai/entities"
                        element={
                            <ProtectedRoute>
                                <MainLayout>
                                    <EntityLibrary />
                                </MainLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/ai/entities/create"
                        element={
                            <ProtectedRoute>
                                <MainLayout>
                                    <EntityBuilder />
                                </MainLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/ai/entities/edit/:id"
                        element={
                            <ProtectedRoute>
                                <MainLayout>
                                    <EntityBuilder />
                                </MainLayout>
                            </ProtectedRoute>
                        }
                    />

                    {/* Legacy Redirects */}
                    <Route path="/agents" element={<Navigate to="/ai/entities" replace />} />
                    <Route path="/workflows" element={<Navigate to="/ai/entities" replace />} />
                    <Route path="/agents/create" element={<Navigate to="/ai/entities/create" replace />} />
                    <Route path="/workflows/create" element={<Navigate to="/ai/entities/create" replace />} />
                    <Route path="/agents/:id" element={<Navigate to="/ai/entities/edit/:id" replace />} />
                    <Route path="/workflows/:id" element={<Navigate to="/ai/entities/edit/:id" replace />} />

                    {/* Execution */}
                    <Route
                        path="/ai/execute/:id"
                        element={
                            <ProtectedRoute>
                                <MainLayout>
                                    <ExecutionPage />
                                </MainLayout>
                            </ProtectedRoute>
                        }
                    />
                    <Route path="/execute/:type/:id" element={<Navigate to="/ai/execute/:id" replace />} />

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

                    {/* HITL Oversights */}
                    <Route
                        path="/ai/approvals"
                        element={
                            <ProtectedRoute>
                                <MainLayout>
                                    <HITLPanel />
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

                    {/* Integrations */}
                    <Route
                        path="/integrations"
                        element={
                            <ProtectedRoute>
                                <MainLayout>
                                    <IntegrationsPage />
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

                    {/* Platform Management (Consolidated Partners, Tenants, Users) */}
                    <Route
                        path="/platform-management"
                        element={
                            <ProtectedRoute allowedRoles={[UserRole.APP_ADMIN, UserRole.PARTNER_ADMIN, UserRole.TENANT_ADMIN]}>
                                <MainLayout>
                                    <PlatformManagement />
                                </MainLayout>
                            </ProtectedRoute>
                        }
                    />

                    {/* Legacy Management Redirects */}
                    <Route path="/partners" element={<Navigate to="/platform-management" replace />} />
                    <Route path="/tenants" element={<Navigate to="/platform-management" replace />} />
                    <Route path="/users" element={<Navigate to="/platform-management" replace />} />

                    {/* 404 Route */}
                    <Route path="*" element={<Navigate to="/dashboard" replace />} />
                </Routes>
            </Suspense>
        </BrowserRouter>
    );
};
