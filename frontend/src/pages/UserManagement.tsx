import React, { useEffect, useState } from 'react';
import { GlassCard } from '../components/ui/GlassCard';
import { userService, UserCreateAdmin } from '../services/user.service';
import { authService } from '../services/auth.service';
import { User, UserRole } from '../types';
import { AlertTriangle, RefreshCw, Plus, Mail, Shield, Building, Ban, CheckCircle } from 'lucide-react';
import { CreateUserModal } from '../components/CreateUserModal';

const UserManagement: React.FC = () => {
    const [users, setUsers] = useState<User[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [currentUser, setCurrentUser] = useState<User | null>(null);

    const fetchUsers = async () => {
        try {
            setLoading(true);
            const data = await userService.getUsers();
            setUsers(data);
            setError(null);
        } catch (err) {
            setError('Failed to load users');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const fetchCurrentUser = async () => {
        try {
            const user = await authService.getCurrentUser();
            setCurrentUser(user);
        } catch (err) {
            console.error('Failed to fetch current user', err);
        }
    };

    useEffect(() => {
        fetchUsers();
        fetchCurrentUser();
    }, []);

    const handleCreateUser = async (data: UserCreateAdmin) => {
        await userService.createUser(data);
        fetchUsers();
    };

    const handleToggleStatus = async (user: User) => {
        try {
            const newStatus = !user.is_active;
            await userService.updateUser(user.id, { is_active: newStatus });

            // Optimistic update
            setUsers(users.map(u =>
                u.id === user.id ? { ...u, is_active: newStatus } : u
            ));
        } catch (err) {
            console.error('Failed to update user status', err);
            alert('Failed to update user status');
            fetchUsers();
        }
    };

    const getRoleBadgeColor = (role: string) => {
        switch (role) {
            case UserRole.APP_ADMIN: return 'bg-purple-500/20 text-purple-300 border-purple-500/30';
            case UserRole.PARTNER_ADMIN: return 'bg-blue-500/20 text-blue-300 border-blue-500/30';
            case UserRole.TENANT_ADMIN: return 'bg-green-500/20 text-green-300 border-green-500/30';
            default: return 'bg-gray-500/20 text-gray-300 border-gray-500/30';
        }
    };

    if (loading && users.length === 0) {
        return (
            <div className="p-8 flex justify-center">
                <RefreshCw className="animate-spin text-rose-500" />
            </div>
        );
    }

    return (
        <div className="p-8 space-y-6">
            <div className="flex justify-between items-center">
                <h1 className="text-3xl font-bold text-white">User Management</h1>
                <div className="flex gap-4">
                    <button
                        onClick={() => setIsModalOpen(true)}
                        className="flex items-center gap-2 px-4 py-2 bg-rose-500 hover:bg-rose-600 text-white rounded-lg transition-colors"
                    >
                        <Plus size={20} />
                        Add User
                    </button>
                    <button
                        onClick={fetchUsers}
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
                {users.map((user) => (
                    <GlassCard key={user.id} className="flex justify-between items-center p-6 text-white">
                        <div className="flex items-center gap-4">
                            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-rose-500 to-rose-700 flex items-center justify-center text-xl font-bold">
                                {user.full_name.charAt(0)}
                            </div>
                            <div>
                                <h3 className="text-xl font-semibold text-white">{user.full_name}</h3>
                                <div className="flex items-center gap-4 mt-1 text-sm text-gray-400">
                                    <span className="flex items-center gap-1">
                                        <Mail size={14} /> {user.email}
                                    </span>
                                    <span className="flex items-center gap-1">
                                        <Building size={14} /> {user.company_id}
                                    </span>
                                </div>
                            </div>
                        </div>

                        <div className="flex items-center gap-4">
                            <div className={`px-3 py-1 rounded-full text-sm font-medium flex items-center gap-2 ${getRoleBadgeColor(user.role)} border`}>
                                <Shield size={14} />
                                {user.role.replace('_', ' ').toUpperCase()}
                            </div>

                            <div className={`px-3 py-1 rounded-full text-sm font-medium flex items-center gap-2 ${user.is_active
                                ? 'bg-green-500/20 text-green-300 border-green-500/30'
                                : 'bg-red-500/20 text-red-300 border-red-500/30'
                                } border`}>
                                {user.is_active ? <CheckCircle size={14} /> : <Ban size={14} />}
                                {user.is_active ? 'ACTIVE' : 'SUSPENDED'}
                            </div>

                            <button
                                onClick={() => handleToggleStatus(user)}
                                className={`px-4 py-2 rounded-lg font-medium transition-all ${user.is_active
                                    ? 'bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/30'
                                    : 'bg-green-500/20 hover:bg-green-300/30 text-green-300 border border-green-500/30'
                                    }`}
                            >
                                {user.is_active ? 'Suspend' : 'Activate'}
                            </button>
                        </div>
                    </GlassCard>
                ))}

                {users.length === 0 && !loading && (
                    <div className="text-center text-gray-400 py-12">
                        No users found.
                    </div>
                )}
            </div>

            <CreateUserModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                onSubmit={handleCreateUser}
                currentUser={currentUser}
            />
        </div>
    );
};

export default UserManagement;
