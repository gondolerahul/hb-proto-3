import React, { useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useTheme } from '@/hooks/useTheme';
import { GlassCard, GlassInput, JellyButton } from '@/components/ui';
import { Save, Moon, Sun } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import './UserSettings.css';

export const UserSettings: React.FC = () => {
    const { user } = useAuth();
    const { theme, toggleTheme } = useTheme();
    const [fullName, setFullName] = useState(user?.full_name || '');
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState('');
    const [error, setError] = useState('');

    const handleProfileUpdate = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setSuccess('');
        setLoading(true);

        try {
            await apiClient.put('/auth/profile', { full_name: fullName });
            setSuccess('Profile updated successfully');
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to update profile');
        } finally {
            setLoading(false);
        }
    };

    const handlePasswordChange = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setSuccess('');

        if (newPassword.length < 12) {
            setError('New password must be at least 12 characters');
            return;
        }

        if (newPassword !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }

        setLoading(true);

        try {
            await apiClient.put('/auth/password', {
                current_password: currentPassword,
                new_password: newPassword,
            });
            setSuccess('Password changed successfully');
            setCurrentPassword('');
            setNewPassword('');
            setConfirmPassword('');
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to change password');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="user-settings">
            <div className="page-header">
                <h1>Settings</h1>
                <p>Manage your account preferences</p>
            </div>

            {/* Theme Toggle */}
            <GlassCard className="settings-section">
                <h2>Appearance</h2>
                <div className="theme-toggle-section">
                    <div>
                        <h3>Theme</h3>
                        <p className="help-text">Choose your preferred color scheme</p>
                    </div>
                    <JellyButton
                        variant="secondary"
                        onClick={toggleTheme}
                        className="theme-toggle-btn"
                    >
                        {theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
                        {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
                    </JellyButton>
                </div>
            </GlassCard>

            {/* Profile Settings */}
            <GlassCard className="settings-section">
                <h2>Profile Information</h2>
                <form onSubmit={handleProfileUpdate} className="settings-form">
                    <GlassInput
                        label="Email"
                        value={user?.email || ''}
                        disabled
                    />
                    <GlassInput
                        label="Full Name"
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        required
                    />
                    <GlassInput
                        label="Role"
                        value={user?.role || ''}
                        disabled
                    />

                    {success && <div className="success-message">{success}</div>}
                    {error && <div className="error-message">{error}</div>}

                    <JellyButton
                        type="submit"
                        roseGold
                        disabled={loading}
                    >
                        <Save size={20} />
                        {loading ? 'Saving...' : 'Save Changes'}
                    </JellyButton>
                </form>
            </GlassCard>

            {/* Password Change */}
            <GlassCard className="settings-section">
                <h2>Change Password</h2>
                <form onSubmit={handlePasswordChange} className="settings-form">
                    <GlassInput
                        type="password"
                        label="Current Password"
                        value={currentPassword}
                        onChange={(e) => setCurrentPassword(e.target.value)}
                        required
                    />
                    <GlassInput
                        type="password"
                        label="New Password (min 12 characters)"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        required
                    />
                    <GlassInput
                        type="password"
                        label="Confirm New Password"
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        required
                    />

                    <JellyButton
                        type="submit"
                        roseGold
                        disabled={loading}
                    >
                        <Save size={20} />
                        {loading ? 'Changing...' : 'Change Password'}
                    </JellyButton>
                </form>
            </GlassCard>
        </div>
    );
};
