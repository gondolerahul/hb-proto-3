import React, { useState, useEffect, useCallback } from 'react';
import { DollarSign, Download, RefreshCw, ChevronDown, TrendingUp } from 'lucide-react';
import { billingService, BillingEvent, ReportTotals } from '@/services/billing.service';
import './Report.css';

const GROUPING_OPTIONS = [
    { value: '', label: 'No Grouping' },
    { value: 'partner', label: 'By Partner' },
    { value: 'tenant', label: 'By Tenant' },
    { value: 'user', label: 'By User' },
    { value: 'process', label: 'By Process' },
    { value: 'agent', label: 'By Agent' },
];

function getCurrentMonthStr(): string {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
}

function formatUSD(val: number): string {
    return `$${val.toFixed(4)}`;
}

function exportToCSV(events: BillingEvent[], filename: string) {
    const headers = ['Period', 'Grouping', 'Total Billing', 'Platform Fees', 'Partner Fees', 'Discounts', 'Tel In', 'Tel Out', 'Images', 'Videos'];
    const rows = events.map((e) => [
        e.period_month, e.grouping_value || '', e.total_billing,
        e.platform_fee_amount, e.partner_fee_amount, e.discount_amount,
        e.telephony_in_minutes, e.telephony_out_minutes, e.image_gen_count, e.video_gen_count,
    ]);
    const csv = [headers, ...rows].map((r) => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
}

const SummaryCard: React.FC<{ label: string; value: string; accent?: boolean }> = ({ label, value, accent }) => (
    <div className={`summary-card glass ${accent ? 'accent' : ''}`}>
        <p className="summary-label">{label}</p>
        <p className="summary-value">{value}</p>
    </div>
);

export const BillingReport: React.FC = () => {
    const [events, setEvents] = useState<BillingEvent[]>([]);
    const [totals, setTotals] = useState<ReportTotals>({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [periodMonth, setPeriodMonth] = useState(getCurrentMonthStr());
    const [groupingType, setGroupingType] = useState('');

    const fetchReport = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await billingService.getBillingReport({
                period_month: periodMonth,
                grouping_type: groupingType || undefined,
            });
            setEvents(res.events);
            setTotals(res.totals);
        } catch (e: any) {
            setError(e?.response?.data?.detail || 'Failed to load billing report');
        } finally {
            setLoading(false);
        }
    }, [periodMonth, groupingType]);

    useEffect(() => { fetchReport(); }, [fetchReport]);

    return (
        <div className="report-page">
            <div className="page-header">
                <div>
                    <h1 className="page-title">
                        <DollarSign size={24} style={{ marginRight: '0.5rem' }} />
                        Billing Report
                    </h1>
                    <p className="page-subtitle">Client-facing revenue and billing totals</p>
                </div>
                <div className="report-header-actions">
                    <button className="btn-secondary" onClick={fetchReport}>
                        <RefreshCw size={14} /> Refresh
                    </button>
                    <button
                        className="btn-secondary"
                        onClick={() => exportToCSV(events, `billing-${periodMonth}.csv`)}
                    >
                        <Download size={14} /> Export CSV
                    </button>
                </div>
            </div>

            {/* Controls */}
            <div className="report-controls glass">
                <div className="control-group">
                    <label>Period (Month)</label>
                    <input
                        type="month"
                        value={periodMonth.slice(0, 7)}
                        onChange={(e) => setPeriodMonth(`${e.target.value}-01`)}
                    />
                </div>
                <div className="control-group">
                    <label>Group By</label>
                    <div className="select-wrapper">
                        <select value={groupingType} onChange={(e) => setGroupingType(e.target.value)}>
                            {GROUPING_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
                        </select>
                        <ChevronDown size={14} />
                    </div>
                </div>
            </div>

            {/* Summary Cards */}
            <div className="summary-grid">
                <SummaryCard accent label="Total Revenue (TB)" value={formatUSD(totals.total_revenue || 0)} />
                <SummaryCard label="Platform Fees" value={formatUSD(totals.total_platform_fees || 0)} />
                <SummaryCard label="Partner Fees" value={formatUSD(totals.total_partner_fees || 0)} />
                <SummaryCard label="Total Discounts" value={`-${formatUSD(totals.total_discounts || 0)}`} />
            </div>

            {/* Formula Legend */}
            <div className="formula-card glass">
                <div className="formula-header">
                    <TrendingUp size={16} />
                    <span>TB Formula</span>
                </div>
                <code className="formula-text">
                    TB = (c × mf) + (c × mf × pf) + (c × mf × spf) - (c × mf × d)
                </code>
                <div className="formula-legend">
                    <span><b>c</b> = base cost</span>
                    <span><b>mf</b> = multiplier factor</span>
                    <span><b>pf</b> = platform fee %</span>
                    <span><b>spf</b> = partner fee %</span>
                    <span><b>d</b> = discount %</span>
                </div>
            </div>

            {error && <div className="error-banner">{error}</div>}

            {loading ? (
                <div className="loading-state"><div className="pulse">Loading report…</div></div>
            ) : events.length === 0 ? (
                <div className="empty-state glass">
                    <div className="empty-icon">💰</div>
                    <h3>No billing data for this period</h3>
                    <p>Complete billable tasks to see revenue entries appear here.</p>
                </div>
            ) : (
                <div className="report-table-wrapper glass">
                    <table className="report-table">
                        <thead>
                            <tr>
                                <th>Period</th>
                                {groupingType && <th>Grouping</th>}
                                <th>Telephony</th>
                                <th>Images</th>
                                <th>Videos</th>
                                <th>Platform Fee</th>
                                <th>Partner Fee</th>
                                <th>Discount</th>
                                <th className="highlight-col">Total Billing (TB)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {events.map((e) => (
                                <tr key={e.id}>
                                    <td>{e.period_month}</td>
                                    {groupingType && <td>{e.grouping_value || '—'}</td>}
                                    <td className="num">
                                        {e.telephony_in_minutes.toFixed(1)}↓ / {e.telephony_out_minutes.toFixed(1)}↑
                                    </td>
                                    <td className="num">{e.image_gen_count}</td>
                                    <td className="num">{e.video_gen_count}</td>
                                    <td className="num">{formatUSD(e.platform_fee_amount)}</td>
                                    <td className="num">{formatUSD(e.partner_fee_amount)}</td>
                                    <td className="num deduction">-{formatUSD(e.discount_amount)}</td>
                                    <td className="num total highlight-col">{formatUSD(e.total_billing)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};
