import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { GlassCard } from './ui/GlassCard';
import { GlassInput } from './ui/GlassInput';
import { UserCreateAdmin } from '../services/user.service';
import { UserRole, Company, User } from '../types';
import { companyService } from '../services/company.service';

interface CreateUserModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (data: UserCreateAdmin) => Promise<void>;
    currentUser: User | null;
}

export const CreateUserModal: React.FC<CreateUserModalProps> = ({
    isOpen,
    onClose,
    onSubmit,
    currentUser
}) => {
    const [formData, setFormData] = useState({
        email: '',
        password: '',
        full_name: '',
        company_id: '',
        role: '' as UserRole
    });
    const [companies, setCompanies] = useState<Company[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (isOpen && currentUser) {
            fetchAvailableCompanies();
            // Default company_id to current user's company
            setFormData(prev => ({ ...prev, company_id: currentUser.company_id }));
        }
    }, [isOpen, currentUser]);

    const fetchAvailableCompanies = async () => {
        try {
            if (currentUser?.role === 'app_admin') {
                const partners = await companyService.getPartners();
                const tenants = await companyService.getTenants();
                setCompanies([...partners, ...tenants]);
            } else if (currentUser?.role === 'partner_admin') {
                const tenants = await companyService.getTenants();
                // Partner admin should see their own company too
                // For now, let's just use what getTenants returns which should be their tenants
                setCompanies(tenants);
            }
        } catch (err) {
            console.error('Failed to fetch companies', err);
        }
    };

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setLoading(true);

        try {
            await onSubmit(formData as UserCreateAdmin);
            setFormData({
                email: '',
                password: '',
                full_name: '',
                company_id: currentUser?.company_id || '',
                role: '' as UserRole
            });
            onClose();
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to create user');
        } finally {
            setLoading(false);
        }
    };

    const getAvailableRoles = () => {
        if (currentUser?.role === 'app_admin') {
            return [
                UserRole.APP_ADMIN,
                UserRole.PARTNER_ADMIN,
                UserRole.TENANT_ADMIN,
                UserRole.APP_USER,
                UserRole.PARTNER_USER,
                UserRole.TENANT_USER
            ];
        }
        if (currentUser?.role === 'partner_admin') {
            return [
                UserRole.PARTNER_ADMIN,
                UserRole.PARTNER_USER,
                UserRole.TENANT_ADMIN,
                UserRole.TENANT_USER
            ];
        }
        if (currentUser?.role === 'tenant_admin') {
            return [
                UserRole.TENANT_ADMIN,
                UserRole.TENANT_USER
            ];
        }
        return [];
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <GlassCard className="w-full max-w-md p-8 relative">
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 p-2 text-gray-400 hover:text-white transition-colors"
                >
                    <X size={20} />
                </button>

                <h2 className="text-2xl font-bold text-white mb-6">Add New User</h2>

                <form onSubmit={handleSubmit} className="space-y-4">
                    <GlassInput
                        label="Full Name"
                        value={formData.full_name}
                        onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                        placeholder="John Doe"
                        required
                    />
                    <GlassInput
                        label="Email"
                        type="email"
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        placeholder="john@example.com"
                        required
                    />
                    <GlassInput
                        label="Password"
                        type="password"
                        value={formData.password}
                        onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                        placeholder="••••••••"
                        required
                    />

                    <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">Company</label>
                        <select
                            value={formData.company_id}
                            onChange={(e) => setFormData({ ...formData, company_id: e.target.value })}
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-rose-500/50 transition-all font-outfit"
                            required
                        >
                            <option value={currentUser?.company_id} className="bg-gray-900">My Company</option>
                            {companies.map(c => (
                                <option key={c.id} value={c.id} className="bg-gray-900">{c.name}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">Role</label>
                        <select
                            value={formData.role}
                            onChange={(e) => setFormData({ ...formData, role: e.target.value as UserRole })}
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-rose-500/50 transition-all font-outfit"
                            required
                        >
                            <option value="" disabled className="bg-gray-900">Select Role</option>
                            {getAvailableRoles().map(role => (
                                <option key={role} value={role} className="bg-gray-900">{role.replace('_', ' ').toUpperCase()}</option>
                            ))}
                        </select>
                    </div>

                    {error && (
                        <p className="text-red-400 text-sm bg-red-400/10 p-3 rounded-lg border border-red-400/20">
                            {error}
                        </p>
                    )}

                    <div className="flex justify-end gap-4 pt-4">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-6 py-2 text-gray-300 hover:text-white transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={loading || !formData.email || !formData.password || !formData.role}
                            className="px-6 py-2 bg-rose-500 hover:bg-rose-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-all transform hover:scale-105 active:scale-95"
                        >
                            {loading ? 'Creating...' : 'Create'}
                        </button>
                    </div>
                </form>
            </GlassCard>
        </div>
    );
};
