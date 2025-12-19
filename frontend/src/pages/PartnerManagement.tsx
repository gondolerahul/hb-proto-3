import React, { useEffect, useState } from 'react';
import { GlassCard } from '../components/ui/GlassCard';
import { companyService } from '../services/company.service';
import { Company } from '../types';
import { AlertTriangle, CheckCircle, Ban, RefreshCw, Plus } from 'lucide-react';

const PartnerManagement: React.FC = () => {
    const [partners, setPartners] = useState<Company[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

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
            alert('Failed to update partner status');
            fetchPartners();
        }
    };

    if (loading && partners.length === 0) {
        return (
            <div className="p-8 flex justify-center">
                <RefreshCw className="animate-spin text-rose-500" />
            </div>
        );
    }

    return (
        <div className="p-8 space-y-6">
            <div className="flex justify-between items-center">
                <h1 className="text-3xl font-bold text-white">Partner Management</h1>
                <div className="flex gap-4">
                    <button
                        onClick={() => {/* TODO: Implement Create Modal */ }}
                        className="flex items-center gap-2 px-4 py-2 bg-rose-500 hover:bg-rose-600 text-white rounded-lg transition-colors"
                    >
                        <Plus size={20} />
                        Add Partner
                    </button>
                    <button
                        onClick={fetchPartners}
                        className="p-2 rounded-full hover:bg-white/10 transition-colors"
                    >
                        <RefreshCw className="text-rose-300" size={20} />
                    </button>
                </div>
            </div>

            {error && (
                <div className="bg-red-500/20 border border-red-500/50 p-4 rounded-lg text-red-200 flex items-center gap-2">
                    <AlertTriangle size={20} />
                    {error}
                </div>
            )}

            <div className="grid gap-4">
                {partners.map((partner) => (
                    <GlassCard key={partner.id} className="flex justify-between items-center p-6 text-white">
                        <div>
                            <h3 className="text-xl font-semibold text-white">{partner.name}</h3>
                            <div className="flex items-center gap-2 mt-2 text-sm text-gray-300">
                                <span>ID: {partner.id}</span>
                                <span>•</span>
                                <span>Created: {new Date(partner.created_at).toLocaleDateString()}</span>
                            </div>
                        </div>

                        <div className="flex items-center gap-4">
                            <div className={`px-3 py-1 rounded-full text-sm font-medium flex items-center gap-2 ${partner.status === 'active'
                                ? 'bg-green-500/20 text-green-300 border border-green-500/30'
                                : 'bg-red-500/20 text-red-300 border border-red-500/30'
                                }`}>
                                {partner.status === 'active' ? <CheckCircle size={14} /> : <Ban size={14} />}
                                {partner.status.toUpperCase()}
                            </div>

                            <button
                                onClick={() => handleToggleStatus(partner)}
                                className={`px-4 py-2 rounded-lg font-medium transition-all ${partner.status === 'active'
                                    ? 'bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/30'
                                    : 'bg-green-500/20 hover:bg-green-300/30 text-green-300 border border-green-500/30'
                                    }`}
                            >
                                {partner.status === 'active' ? 'Suspend' : 'Activate'}
                            </button>
                        </div>
                    </GlassCard>
                ))}

                {partners.length === 0 && !loading && (
                    <div className="text-center text-gray-400 py-12">
                        No partners found.
                    </div>
                )}
            </div>
        </div>
    );
};

export default PartnerManagement;
