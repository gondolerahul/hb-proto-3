import React, { useState } from 'react';
import { X } from 'lucide-react';
import { GlassCard } from './ui/GlassCard';
import { GlassInput } from './ui/GlassInput';
import { CompanyCreate } from '../services/company.service';

interface CreateCompanyModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (data: CompanyCreate) => Promise<void>;
    type: 'PARTNER' | 'TENANT';
    parentId?: string;
}

export const CreateCompanyModal: React.FC<CreateCompanyModalProps> = ({
    isOpen,
    onClose,
    onSubmit,
    type,
    parentId
}) => {
    const [name, setName] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setLoading(true);

        try {
            await onSubmit({
                name,
                type,
                parent_id: parentId
            });
            setName('');
            onClose();
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to create company');
        } finally {
            setLoading(false);
        }
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

                <h2 className="text-2xl font-bold text-white mb-6">
                    Add New {type.charAt(0) + type.slice(1).toLowerCase()}
                </h2>

                <form onSubmit={handleSubmit} className="space-y-6">
                    <GlassInput
                        label="Company Name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder={`Enter ${type.toLowerCase()} name`}
                        required
                    />

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
                            disabled={loading || !name.trim()}
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
