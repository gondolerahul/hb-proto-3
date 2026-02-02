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
        <div className="page-container dashboard">
            <header className="page-header">
                <div>
                    <h1>Welcome back, {user?.full_name}!</h1>
                    <p>Orchestrating your neural network today</p>
                </div>
            </header>

            <div className="standard-grid mb-12">
                <GlassCard hover className="p-6 flex items-center gap-6">
                    <div className="stat-icon-box bg-rose-gold/10 p-4 rounded-xl text-rose-gold">
                        <Brain size={32} />
                    </div>
                    <div>
                        <div className="text-3xl font-bold bg-gradient-rose-gold-text bg-clip-text text-transparent">{stats.agents_active}</div>
                        <div className="text-sm text-tertiary font-medium uppercase tracking-wider">Active Units</div>
                    </div>
                </GlassCard>

                <GlassCard hover className="p-6 flex items-center gap-6">
                    <div className="stat-icon-box bg-blue-500/10 p-4 rounded-xl text-blue-400">
                        <Workflow size={32} />
                    </div>
                    <div>
                        <div className="text-3xl font-bold text-blue-400">{stats.workflows_active}</div>
                        <div className="text-sm text-tertiary font-medium uppercase tracking-wider">Active Logic</div>
                    </div>
                </GlassCard>

                <GlassCard hover className="p-6 flex items-center gap-6">
                    <div className="stat-icon-box bg-green-500/10 p-4 rounded-xl text-green-400">
                        <Clock size={32} />
                    </div>
                    <div>
                        <div className="text-3xl font-bold text-green-400">{stats.executions_today}</div>
                        <div className="text-sm text-tertiary font-medium uppercase tracking-wider">Cycles Today</div>
                    </div>
                </GlassCard>

                <GlassCard hover className="p-6 flex items-center gap-6">
                    <div className="stat-icon-box bg-amber-500/10 p-4 rounded-xl text-amber-400">
                        <FileText size={32} />
                    </div>
                    <div>
                        <div className="text-3xl font-bold text-amber-400">{stats.documents_total}</div>
                        <div className="text-sm text-tertiary font-medium uppercase tracking-wider">Knowledge Assets</div>
                    </div>
                </GlassCard>
            </div>

            <div className="dashboard-content max-w-2xl">
                <GlassCard className="p-8">
                    <h2 className="text-xl mb-6 font-semibold flex items-center gap-2">
                        <Clock size={20} className="text-rose-gold" />
                        Neural Trail
                    </h2>
                    <div className="space-y-4">
                        {recentActivity.length === 0 ? (
                            <div className="py-10 text-center opacity-30">
                                <Clock size={48} className="mx-auto mb-2" />
                                <p>No cycles recorded yet</p>
                            </div>
                        ) : (
                            recentActivity.map((activity) => (
                                <div key={activity.id} className="flex items-center gap-4 p-4 rounded-xl bg-white/5 border border-white/5 hover:border-white/10 transition-colors">
                                    <div className="p-2 rounded-lg bg-rose-gold/10 text-rose-gold">
                                        <Clock size={16} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium white-space-nowrap truncate">{activity.title}</p>
                                        <p className="text-[10px] text-tertiary font-mono">{activity.time}</p>
                                    </div>
                                    <div className="badge badge-ready scale-75">LIVE</div>
                                </div>
                            ))
                        )}
                    </div>
                </GlassCard>
            </div>
        </div>
    );
};
