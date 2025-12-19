import React from 'react';
import { GlassCard } from '../components/ui/GlassCard';

const UserManagement: React.FC = () => {
    return (
        <div className="p-8 space-y-6">
            <h1 className="text-3xl font-bold text-white">User Management</h1>
            <GlassCard className="p-8 text-white">
                <p>User Management interface is coming soon.</p>
                <p className="mt-4 text-gray-400">
                    This page will allow admins to create and manage users within their hierarchical scope.
                </p>
            </GlassCard>
        </div>
    );
};

export default UserManagement;
