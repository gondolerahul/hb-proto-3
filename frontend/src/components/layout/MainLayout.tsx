import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useTheme } from '@/hooks/useTheme';
import {
    LayoutDashboard,
    Brain,
    Workflow,
    Play,
    Database,
    DollarSign,
    Settings,
    Menu,
    X,
    LogOut,
    User,
    Moon,
    Sun,
} from 'lucide-react';
import './MainLayout.css';

interface MainLayoutProps {
    children: React.ReactNode;
}

export const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [userMenuOpen, setUserMenuOpen] = useState(false);
    const { logout, user } = useAuth();
    const { theme, toggleTheme } = useTheme();
    const location = useLocation();

    const navItems = [
        { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
        ...((user?.role === 'partner_admin' || user?.role === 'PARTNER_ADMIN') ? [{ path: '/tenants', label: 'Tenants', icon: User }] : []),
        { path: '/agents', label: 'AI Agents', icon: Brain },
        { path: '/workflows', label: 'Workflows', icon: Workflow },
        { path: '/executions', label: 'Executions', icon: Play },
        { path: '/knowledge', label: 'Knowledge Base', icon: Database },
        { path: '/billing', label: 'Billing', icon: DollarSign },
        { path: '/settings', label: 'Settings', icon: Settings },
    ];

    const isActive = (path: string) => location.pathname.startsWith(path);

    return (
        <div className="main-layout">
            <div className="liquid-background" />

            {/* Sidebar */}
            <aside className={`sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
                <div className="sidebar-header">
                    <h2 className="text-rose-gold">HireBuddha</h2>
                    <button
                        className="sidebar-toggle"
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                    >
                        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
                    </button>
                </div>

                <nav className="sidebar-nav">
                    {navItems.map((item) => {
                        const Icon = item.icon;
                        return (
                            <Link
                                key={item.path}
                                to={item.path}
                                className={`nav-item ${isActive(item.path) ? 'active' : ''}`}
                            >
                                <Icon size={20} />
                                {sidebarOpen && <span>{item.label}</span>}
                            </Link>
                        );
                    })}
                </nav>
            </aside>

            {/* Main Content */}
            <div className="main-content">
                <header className="top-header glass">
                    <h1>Welcome to HireBuddha</h1>

                    <div className="header-actions">
                        <button
                            className="theme-toggle-icon"
                            onClick={toggleTheme}
                            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
                        >
                            {theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
                        </button>

                        <div className="user-menu">
                            <button
                                className="user-menu-button"
                                onClick={() => setUserMenuOpen(!userMenuOpen)}
                            >
                                <User size={20} />
                                <span>{user?.full_name || user?.email}</span>
                            </button>

                            {userMenuOpen && (
                                <div className="user-menu-dropdown glass">
                                    <Link
                                        to="/profile"
                                        className="user-menu-item"
                                        onClick={() => setUserMenuOpen(false)}
                                    >
                                        <User size={16} />
                                        Profile Settings
                                    </Link>
                                    <button className="user-menu-item" onClick={logout}>
                                        <LogOut size={16} />
                                        Logout
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </header>

                <main>{children}</main>
            </div>
        </div>
    );
};
