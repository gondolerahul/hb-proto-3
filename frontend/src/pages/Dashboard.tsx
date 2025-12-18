import React from 'react';
import { useAuth } from '@/hooks/useAuth';
import { GlassCard } from '@/components/ui';
import { Brain, Workflow, Clock, FileText } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import './Dashboard.css';

export const Dashboard: React.FC = () => {
    const { user } = useAuth();
    const [stats, setStats] = React.useState({
        agents_active: 0,
        workflows_active: 0,
        executions_today: 0,
        documents_total: 0
    });
    const [recentActivity, setRecentActivity] = React.useState<any[]>([]);

    React.useEffect(() => {
        const fetchData = async () => {
            try {
                const [statsRes, executionsRes] = await Promise.all([
                    apiClient.get('/ai/stats'),
                    apiClient.get('/ai/executions')
                ]);
                setStats(statsRes.data);

                // transform executions to activity items
                const activities = executionsRes.data.slice(0, 5).map((exec: any) => ({
                    id: exec.id,
                    type: 'execution',
                    title: `Workflow Execution: ${exec.status}`,
                    time: new Date(exec.created_at).toLocaleString()
                }));
                setRecentActivity(activities);
            } catch (error) {
                console.error('Failed to fetch dashboard data:', error);
            }
        };
        fetchData();
    }, []);

    return (
        <div className="dashboard">
            <div className="dashboard-header">
                <h1>Welcome back, {user?.full_name}!</h1>
                <p className="dashboard-subtitle">Here's what's happening with your AI agents today</p>
            </div>

            <div className="stats-grid">
                <GlassCard hover className="stat-card">
                    <div className="stat-icon" style={{ background: 'rgba(212, 147, 139, 0.2)' }}>
                        <Brain size={32} color="var(--color-accent-primary)" />
                    </div>
                    <div className="stat-content">
                        <h3>{stats.agents_active}</h3>
                        <p>Active Agents</p>
                    </div>
                </GlassCard>

                <GlassCard hover className="stat-card">
                    <div className="stat-icon" style={{ background: 'rgba(96, 165, 250, 0.2)' }}>
                        <Workflow size={32} color="var(--color-info)" />
                    </div>
                    <div className="stat-content">
                        <h3>{stats.workflows_active}</h3>
                        <p>Workflows</p>
                    </div>
                </GlassCard>

                <GlassCard hover className="stat-card">
                    <div className="stat-icon" style={{ background: 'rgba(74, 222, 128, 0.2)' }}>
                        <Clock size={32} color="var(--color-success)" />
                    </div>
                    <div className="stat-content">
                        <h3>{stats.executions_today}</h3>
                        <p>Executions Today</p>
                    </div>
                </GlassCard>

                <GlassCard hover className="stat-card">
                    <div className="stat-icon" style={{ background: 'rgba(251, 191, 36, 0.2)' }}>
                        <FileText size={32} color="var(--color-warning)" />
                    </div>
                    <div className="stat-content">
                        <h3>{stats.documents_total}</h3>
                        <p>Documents</p>
                    </div>
                </GlassCard>
            </div>

            <div className="dashboard-content">
                <GlassCard className="recent-activity">
                    <h2>Recent Activity</h2>
                    <div className="activity-list">
                        {recentActivity.length === 0 ? (
                            <p>No recent activity</p>
                        ) : (
                            recentActivity.map((activity) => (
                                <div key={activity.id} className="activity-item">
                                    <div className="activity-icon">
                                        <Clock size={20} />
                                    </div>
                                    <div className="activity-details">
                                        <p className="activity-title">{activity.title}</p>
                                        <p className="activity-time">{activity.time}</p>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </GlassCard>
            </div>
        </div>
    );
};
