import React, { useEffect, useState } from 'react';
import { GlassCard, JellyButton } from '@/components/ui';
import { userService, UserCreateAdmin } from '@/services/user.service';
import { authService } from '@/services/auth.service';
import { User, UserRole } from '@/types';
import { AlertTriangle, RefreshCw, Plus, Mail, Shield, Building, Ban, CheckCircle, User as UserIcon } from 'lucide-react';
import { CreateUserModal } from '@/components/CreateUserModal';

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
            setError('Failed to update status');
            fetchUsers();
        }
    };

    const getRoleBadgeColor = (role: string) => {
        switch (role) {
            case UserRole.APP_ADMIN: return 'badge-purple';
            case UserRole.PARTNER_ADMIN: return 'badge-blue';
            case UserRole.TENANT_ADMIN: return 'badge-green';
            default: return 'badge-gray';
        }
    };

    return (
        <div className="container py-8">
            <div className="flex justify-between items-center mb-10">
                <div>
                    <h1 className="text-rose-gold">User Management</h1>
                    <p className="text-secondary">Orchestrate access control and identities</p>
                </div>
                <div className="flex gap-4">
                    <JellyButton onClick={fetchUsers} variant="ghost">
                        <RefreshCw size={20} className={loading ? 'spin' : ''} />
                    </JellyButton>
                    <JellyButton onClick={() => setIsModalOpen(true)} roseGold>
                        <Plus size={20} /> Add User
                    </JellyButton>
                </div>
            </div>

            {error && (
                <div className="error-toast glass mb-6">
                    <AlertTriangle size={20} />
                    {error}
                </div>
            )}

            <div className="grid gap-6">
                {users.map((user) => (
                    <GlassCard key={user.id} className="user-card" hover>
                        <div className="flex justify-between items-center w-full">
                            <div className="flex items-center gap-6">
                                <div className="user-avatar text-rose-gold">
                                    {user.full_name.charAt(0)}
                                </div>
                                <div className="user-info">
                                    <h3 className="mb-1">{user.full_name}</h3>
                                    <div className="flex items-center gap-6 text-sm text-tertiary">
                                        <span className="flex items-center gap-2">
                                            <Mail size={14} /> {user.email}
                                        </span>
                                        <span className="flex items-center gap-2">
                                            <Building size={14} /> {user.company_id}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center gap-6">
                                <div className={`badge ${getRoleBadgeColor(user.role)}`}>
                                    <Shield size={14} />
                                    {user.role.replace('_', ' ').toUpperCase()}
                                </div>

                                <div className={`badge ${user.is_active ? 'badge-ready' : 'badge-failed'}`}>
                                    {user.is_active ? <CheckCircle size={14} /> : <Ban size={14} />}
                                    {user.is_active ? 'ACTIVE' : 'SUSPENDED'}
                                </div>

                                <JellyButton
                                    onClick={() => handleToggleStatus(user)}
                                    variant={user.is_active ? 'danger' : 'primary'}
                                    size="sm"
                                >
                                    {user.is_active ? 'Suspend' : 'Activate'}
                                </JellyButton>
                            </div>
                        </div>
                    </GlassCard>
                ))}

                {users.length === 0 && !loading && (
                    <div className="text-center py-20 opacity-50">
                        <UserIcon size={64} className="mx-auto mb-4" />
                        <p>No identities found in current scope.</p>
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
