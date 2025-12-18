import React, { useState, useEffect } from 'react';
import { GlassCard } from '@/components/ui';
import { DollarSign, TrendingUp, Users } from 'lucide-react';
import { apiClient } from '@/services/api.client';
import './BillingDashboard.css';

interface BillingStats {
    total_revenue: number;
    total_commission: number;
    active_tenants: number;
    monthly_data: Array<{
        month: string;
        revenue: number;
        commission: number;
    }>;
}

export const BillingDashboard: React.FC = () => {
    const [stats, setStats] = useState<BillingStats | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchBillingStats();
    }, []);

    const fetchBillingStats = async () => {
        try {
            const { data } = await apiClient.get('/billing/stats');
            setStats(data);
        } catch (error) {
            console.error('Failed to fetch billing stats:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return <div className="loading">Loading billing data...</div>;
    }

    return (
        <div className="billing-dashboard">
            <div className="page-header">
                <h1>Billing & Reports</h1>
                <p>View your earnings and commission reports</p>
            </div>

            <div className="stats-grid">
                <GlassCard hover className="stat-card">
                    <div className="stat-icon" style={{ background: 'rgba(74, 222, 128, 0.2)' }}>
                        <DollarSign size={32} color="var(--color-success)" />
                    </div>
                    <div className="stat-content">
                        <h3>${stats?.total_revenue.toFixed(2) || '0.00'}</h3>
                        <p>Total Revenue</p>
                    </div>
                </GlassCard>

                <GlassCard hover className="stat-card">
                    <div className="stat-icon" style={{ background: 'rgba(212, 147, 139, 0.2)' }}>
                        <TrendingUp size={32} color="var(--color-accent-primary)" />
                    </div>
                    <div className="stat-content">
                        <h3>${stats?.total_commission.toFixed(2) || '0.00'}</h3>
                        <p>Total Commission</p>
                    </div>
                </GlassCard>

                <GlassCard hover className="stat-card">
                    <div className="stat-icon" style={{ background: 'rgba(96, 165, 250, 0.2)' }}>
                        <Users size={32} color="var(--color-info)" />
                    </div>
                    <div className="stat-content">
                        <h3>{stats?.active_tenants || 0}</h3>
                        <p>Active Tenants</p>
                    </div>
                </GlassCard>
            </div>

            <GlassCard className="monthly-report">
                <h2>Monthly Breakdown</h2>
                <div className="report-table">
                    <table>
                        <thead>
                            <tr>
                                <th>Month</th>
                                <th>Revenue</th>
                                <th>Commission</th>
                                <th>Margin</th>
                            </tr>
                        </thead>
                        <tbody>
                            {stats?.monthly_data?.map((month) => (
                                <tr key={month.month}>
                                    <td>{month.month}</td>
                                    <td>${month.revenue.toFixed(2)}</td>
                                    <td>${month.commission.toFixed(2)}</td>
                                    <td>
                                        {((month.commission / month.revenue) * 100).toFixed(1)}%
                                    </td>
                                </tr>
                            )) || (
                                    <tr>
                                        <td colSpan={4} className="empty-row">No data available</td>
                                    </tr>
                                )}
                        </tbody>
                    </table>
                </div>
            </GlassCard>
        </div>
    );
};
