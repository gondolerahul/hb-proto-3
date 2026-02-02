import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useTheme } from '@/hooks/useTheme';
import {
    LayoutDashboard,
    Play,
    Database,
    Settings,
    Menu,
    X,
    LogOut,
    User,
    Moon,
    Sun,
    Users,
    Building,
    Shield,
    Layers
} from 'lucide-react';
import { UserRole } from '@/types';
import logo from '@/assets/logo.png';
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
        ...(([UserRole.APP_ADMIN, UserRole.PARTNER_ADMIN, UserRole.TENANT_ADMIN].includes(user?.role as UserRole)) ? [{ path: '/platform-management', label: 'Platform Management', icon: Shield }] : []),
        { path: '/ai/entities', label: 'Entity Library', icon: Layers },
        { path: '/ai/approvals', label: 'Guardian Oversight', icon: Shield },
        { path: '/executions', label: 'Executions', icon: Play },
        { path: '/knowledge', label: 'Knowledge Base', icon: Database },
        { path: '/integrations', label: 'Integrations', icon: Settings },
    ];

    const isActive = (path: string) => location.pathname.startsWith(path);

    return (
        <div className="main-layout">

            {/* Sidebar */}
            <aside className={`sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
                <div className="sidebar-header">
                    <div className="logo-container">
                        <img src={logo} alt="HireBuddha" className="sidebar-logo-img" />
                        {sidebarOpen && <h2 className="text-rose-gold">HireBuddha</h2>}
                    </div>
                    <button
                        className="sidebar-toggle"
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        aria-expanded={sidebarOpen}
                        aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
                    >
                        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
                    </button>
                </div>

                <nav className="sidebar-nav">
                    <div className="sidebar-nav-links">
                        {navItems.map((item) => {
                            const Icon = item.icon;
                            return (
                                <Link
                                    key={item.path}
                                    to={item.path}
                                    className={`nav-item ${isActive(item.path) ? 'active' : ''}`}
                                    title={!sidebarOpen ? item.label : ''}
                                >
                                    <div className="nav-item-icon">
                                        <Icon size={20} />
                                    </div>
                                    {sidebarOpen && <span className="nav-item-label">{item.label}</span>}
                                </Link>
                            );
                        })}
                    </div>

                    <div className="sidebar-footer pt-4 border-t border-white/5 mt-4 space-y-2">
                        <button
                            className="theme-toggle-button w-full"
                            onClick={toggleTheme}
                            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
                        >
                            <div className="nav-item-icon">
                                {theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
                            </div>
                            {sidebarOpen && <span>{theme === 'dark' ? 'Luminescence' : 'Eclipse'} Mode</span>}
                        </button>

                        <div className="user-menu">
                            <button
                                className="user-menu-button w-full"
                                onClick={() => setUserMenuOpen(!userMenuOpen)}
                            >
                                <div className="nav-item-icon">
                                    <User size={20} />
                                </div>
                                {sidebarOpen && <span className="truncate flex-1 text-left">{user?.full_name || user?.email}</span>}
                            </button>

                            {userMenuOpen && (
                                <div className={`user-menu-dropdown glass ${sidebarOpen ? 'open' : 'closed-compact'}`}>
                                    <Link
                                        to="/profile"
                                        className="user-menu-item"
                                        onClick={() => setUserMenuOpen(false)}
                                    >
                                        <User size={16} />
                                        {sidebarOpen && <span>Profile Settings</span>}
                                    </Link>
                                    <button className="user-menu-item" onClick={logout}>
                                        <LogOut size={16} />
                                        {sidebarOpen && <span>Logout</span>}
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </nav>
            </aside>

            {/* Main Content */}
            <div className="main-content">
                <main>{children}</main>
            </div>
        </div>
    );
};
