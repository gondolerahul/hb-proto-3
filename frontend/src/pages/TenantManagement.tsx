import React, { useEffect, useState } from 'react';
import { GlassCard, JellyButton } from '@/components/ui';
import { companyService, CompanyCreate } from '@/services/company.service';
import { authService } from '@/services/auth.service';
import { Company, User } from '@/types';
import { AlertTriangle, CheckCircle, Ban, RefreshCw, Plus, Building } from 'lucide-react';
import { CreateCompanyModal } from '@/components/CreateCompanyModal';

const TenantManagement: React.FC = () => {
    const [tenants, setTenants] = useState<Company[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [currentUser, setCurrentUser] = useState<User | null>(null);

    const fetchTenants = async () => {
        try {
            setLoading(true);
            const data = await companyService.getTenants();
            setTenants(data);
            setError(null);
        } catch (err) {
            setError('Failed to load tenants');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const fetchUser = async () => {
        try {
            const user = await authService.getCurrentUser();
            setCurrentUser(user);
        } catch (err) {
            console.error('Failed to fetch user', err);
        }
    };

    useEffect(() => {
        fetchTenants();
        fetchUser();
    }, []);

    const handleToggleStatus = async (tenant: Company) => {
        try {
            const newStatus = tenant.status === 'active' ? 'suspended' : 'active';
            await companyService.updateCompany(tenant.id, { status: newStatus });

            // Optimistic update
            setTenants(tenants.map(t =>
                t.id === tenant.id ? { ...t, status: newStatus } : t
            ));
        } catch (err) {
            console.error('Failed to update tenant status', err);
            setError('Failed to update status');
            fetchTenants();
        }
    };

    const handleCreateTenant = async (data: CompanyCreate) => {
        await companyService.createCompany(data);
        fetchTenants();
    };

    return (
        <div className="container py-8">
            <div className="flex justify-between items-center mb-10">
                <div>
                    <h1 className="text-rose-gold">Tenant Management</h1>
                    <p className="text-secondary">Orchestrate sub-tenant environments and logic isolation</p>
                </div>
                <div className="flex gap-4">
                    <JellyButton onClick={fetchTenants} variant="ghost">
                        <RefreshCw size={20} className={loading ? 'spin' : ''} />
                    </JellyButton>
                    <JellyButton onClick={() => setIsModalOpen(true)} roseGold>
                        <Plus size={20} /> Add Tenant
                    </JellyButton>
                </div>
            </div>

            {error && (
                <div className="error-banner glass mb-8 p-4 flex items-center gap-3">
                    <AlertTriangle className="text-error" size={20} />
                    <span className="text-error">{error}</span>
                </div>
            )}

            <div className="grid gap-6">
                {tenants.map((tenant) => (
                    <GlassCard key={tenant.id} className="p-6" hover>
                        <div className="flex justify-between items-center w-full">
                            <div className="flex items-center gap-6">
                                <div className="user-avatar text-rose-gold">
                                    <Building size={24} />
                                </div>
                                <div>
                                    <h3 className="mb-1">{tenant.name}</h3>
                                    <div className="flex items-center gap-4 text-xs text-tertiary font-mono">
                                        <span>ID: {tenant.id}</span>
                                        <span>•</span>
                                        <span>Created: {new Date(tenant.created_at).toLocaleDateString()}</span>
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center gap-6">
                                <div className={`badge ${tenant.status === 'active' ? 'badge-ready' : 'badge-failed'}`}>
                                    {tenant.status === 'active' ? <CheckCircle size={14} /> : <Ban size={14} />}
                                    {tenant.status.toUpperCase()}
                                </div>

                                <JellyButton
                                    onClick={() => handleToggleStatus(tenant)}
                                    variant={tenant.status === 'active' ? 'danger' : 'primary'}
                                    size="sm"
                                >
                                    {tenant.status === 'active' ? 'Suspend' : 'Activate'}
                                </JellyButton>
                            </div>
                        </div>
                    </GlassCard>
                ))}

                {tenants.length === 0 && !loading && (
                    <div className="text-center py-20 opacity-30">
                        <Building size={64} className="mx-auto mb-4" />
                        <p>No tenant environments found in scope.</p>
                    </div>
                )}
            </div>

            <CreateCompanyModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                onSubmit={handleCreateTenant}
                type="TENANT"
                parentId={currentUser?.company_id}
            />
        </div>
    );
};

export default TenantManagement;
