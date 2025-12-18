import React, { useEffect, useState } from 'react';
import { GlassCard } from '../components/ui/GlassCard';
import { tenantService, Tenant } from '../services/tenant.service';
import { AlertTriangle, CheckCircle, Ban, RefreshCw } from 'lucide-react';

const TenantManagement: React.FC = () => {
    const [tenants, setTenants] = useState<Tenant[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchTenants = async () => {
        try {
            setLoading(true);
            const data = await tenantService.getTenants();
            setTenants(data);
            setError(null);
        } catch (err) {
            setError('Failed to load tenants');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchTenants();
    }, []);

    const handleToggleStatus = async (tenant: Tenant) => {
        try {
            const newStatus = tenant.status === 'active' ? 'suspended' : 'active';
            await tenantService.updateTenant(tenant.id, { status: newStatus });

            // Optimistic update
            setTenants(tenants.map(t =>
                t.id === tenant.id ? { ...t, status: newStatus } : t
            ));
        } catch (err) {
            console.error('Failed to update tenant status', err);
            // Revert or show error
            alert('Failed to update tenant status');
            fetchTenants();
        }
    };

    if (loading) {
        return (
            <div className="p-8 flex justify-center">
                <RefreshCw className="animate-spin text-rose-500" />
            </div>
        );
    }

    return (
        <div className="p-8 space-y-6">
            <div className="flex justify-between items-center">
                <h1 className="text-3xl font-bold text-white">Tenant Management</h1>
                <button
                    onClick={fetchTenants}
                    className="p-2 rounded-full hover:bg-white/10 transition-colors"
                >
                    <RefreshCw className="text-rose-300" size={20} />
                </button>
            </div>

            {error && (
                <div className="bg-red-500/20 border border-red-500/50 p-4 rounded-lg text-red-200 flex items-center gap-2">
                    <AlertTriangle size={20} />
                    {error}
                </div>
            )}

            <div className="grid gap-4">
                {tenants.map((tenant) => (
                    <GlassCard key={tenant.id} className="flex justify-between items-center p-6">
                        <div>
                            <h3 className="text-xl font-semibold text-white">{tenant.name}</h3>
                            <div className="flex items-center gap-2 mt-2 text-sm text-gray-300">
                                <span>ID: {tenant.id}</span>
                                <span>•</span>
                                <span>Created: {new Date(tenant.created_at).toLocaleDateString()}</span>
                            </div>
                        </div>

                        <div className="flex items-center gap-4">
                            <div className={`px-3 py-1 rounded-full text-sm font-medium flex items-center gap-2 ${tenant.status === 'active'
                                    ? 'bg-green-500/20 text-green-300 border border-green-500/30'
                                    : 'bg-red-500/20 text-red-300 border border-red-500/30'
                                }`}>
                                {tenant.status === 'active' ? <CheckCircle size={14} /> : <Ban size={14} />}
                                {tenant.status.toUpperCase()}
                            </div>

                            <button
                                onClick={() => handleToggleStatus(tenant)}
                                className={`px-4 py-2 rounded-lg font-medium transition-all ${tenant.status === 'active'
                                        ? 'bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/30'
                                        : 'bg-green-500/20 hover:bg-green-500/30 text-green-300 border border-green-500/30'
                                    }`}
                            >
                                {tenant.status === 'active' ? 'Suspend' : 'Activate'}
                            </button>
                        </div>
                    </GlassCard>
                ))}

                {tenants.length === 0 && !loading && (
                    <div className="text-center text-gray-400 py-12">
                        No tenants found.
                    </div>
                )}
            </div>
        </div>
    );
};

export default TenantManagement;
