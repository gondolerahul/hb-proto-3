import React, { useEffect, useState } from 'react';
import { GlassCard, JellyButton } from '@/components/ui';
import { companyService, CompanyCreate } from '@/services/company.service';
import { Company } from '@/types';
import { AlertTriangle, CheckCircle, Ban, RefreshCw, Plus, Building } from 'lucide-react';
import { CreateCompanyModal } from '@/components/CreateCompanyModal';

const PartnerManagement: React.FC = () => {
    const [partners, setPartners] = useState<Company[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isModalOpen, setIsModalOpen] = useState(false);

    const fetchPartners = async () => {
        try {
            setLoading(true);
            const data = await companyService.getPartners();
            setPartners(data);
            setError(null);
        } catch (err) {
            setError('Failed to load partners');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchPartners();
    }, []);

    const handleToggleStatus = async (partner: Company) => {
        try {
            const newStatus = partner.status === 'active' ? 'suspended' : 'active';
            await companyService.updateCompany(partner.id, { status: newStatus });

            // Optimistic update
            setPartners(partners.map(p =>
                p.id === partner.id ? { ...p, status: newStatus } : p
            ));
        } catch (err) {
            console.error('Failed to update partner status', err);
            setError('Failed to update status');
            fetchPartners();
        }
    };

    const handleCreatePartner = async (data: CompanyCreate) => {
        await companyService.createCompany(data);
        fetchPartners();
    };

    return (
        <div className="container py-8">
            <div className="flex justify-between items-center mb-10">
                <div>
                    <h1 className="text-rose-gold">Partner Management</h1>
                    <p className="text-secondary">Manage upstream partner entities and authorizations</p>
                </div>
                <div className="flex gap-4">
                    <JellyButton onClick={fetchPartners} variant="ghost">
                        <RefreshCw size={20} className={loading ? 'spin' : ''} />
                    </JellyButton>
                    <JellyButton onClick={() => setIsModalOpen(true)} roseGold>
                        <Plus size={20} /> Add Partner
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
                {partners.map((partner) => (
                    <GlassCard key={partner.id} className="p-6" hover>
                        <div className="flex justify-between items-center w-full">
                            <div className="flex items-center gap-6">
                                <div className="user-avatar text-rose-gold">
                                    <Building size={24} />
                                </div>
                                <div>
                                    <h3 className="mb-1">{partner.name}</h3>
                                    <div className="flex items-center gap-4 text-xs text-tertiary font-mono">
                                        <span>ID: {partner.id}</span>
                                        <span>•</span>
                                        <span>Created: {new Date(partner.created_at).toLocaleDateString()}</span>
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center gap-6">
                                <div className={`badge ${partner.status === 'active' ? 'badge-ready' : 'badge-failed'}`}>
                                    {partner.status === 'active' ? <CheckCircle size={14} /> : <Ban size={14} />}
                                    {partner.status.toUpperCase()}
                                </div>

                                <JellyButton
                                    onClick={() => handleToggleStatus(partner)}
                                    variant={partner.status === 'active' ? 'danger' : 'primary'}
                                    size="sm"
                                >
                                    {partner.status === 'active' ? 'Suspend' : 'Activate'}
                                </JellyButton>
                            </div>
                        </div>
                    </GlassCard>
                ))}

                {partners.length === 0 && !loading && (
                    <div className="text-center py-20 opacity-30">
                        <Building size={64} className="mx-auto mb-4" />
                        <p>No partners registered in the system architect.</p>
                    </div>
                )}
            </div>

            <CreateCompanyModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                onSubmit={handleCreatePartner}
                type="PARTNER"
            />
        </div>
    );
};

export default PartnerManagement;
