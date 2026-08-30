'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { MetricsSummary, PendingApproval, RecoveryOpportunity } from '@/lib/types';
import { fetchMetricsSummary, fetchOpportunities, fetchPendingApprovals } from '@/lib/api-client';
import { Navbar } from '@/components/Navbar';
import { HeroMetrics } from '@/components/HeroMetrics';
import { RecoveryPipeline } from '@/components/RecoveryPipeline';
import { ApprovalQueue } from '@/components/ApprovalQueue';

const EMPTY_METRICS: MetricsSummary = {
  total_opportunities: 0,
  recovered_opportunities: 0,
  recovery_rate_pct: 0,
  total_expected_revenue: '0.00',
  total_recovered_amount: '0.00',
  total_incremental_recovery: '0.00',
  total_intervention_cost: '0.00',
  net_incremental_revenue: '0.00',
  roi_pct: 0,
  period_days: 30,
};

const POLL_MS = 5000;

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<MetricsSummary>(EMPTY_METRICS);
  const [opportunities, setOpportunities] = useState<RecoveryOpportunity[]>([]);
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const approvalRef = useRef<HTMLElement | null>(null);

  const refresh = useCallback(async () => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    try {
      const [m, opps, apprs] = await Promise.all([
        fetchMetricsSummary(),
        fetchOpportunities(),
        fetchPendingApprovals(),
      ]);
      setMetrics(m);
      setOpportunities(opps);
      setApprovals(apprs);
      setError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => { clearInterval(id); abortRef.current?.abort(); };
  }, [refresh]);

  const scrollToApprovals = useCallback(() => {
    approvalRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  return (
    <div className="min-h-screen bg-[#07090E] text-slate-100 flex flex-col font-sans">
      <Navbar onSimulated={refresh} />

      {error && (
        <div className="mx-6 mt-4 flex items-center gap-3 rounded-xl border border-rose-500/30 bg-rose-950/30 px-4 py-3 text-sm text-rose-300 backdrop-blur-sm">
          <span className="h-2 w-2 shrink-0 rounded-full bg-rose-500 animate-pulse" />
          <span>
            <strong>Backend offline</strong> — could not reach{' '}
            <code className="text-rose-200">{process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}</code>.
          </span>
        </div>
      )}

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-4 text-slate-500">
            <div className="h-10 w-10 rounded-full border-2 border-t-emerald-400 border-slate-700 animate-spin" />
            <p className="text-sm font-mono">Connecting to backend…</p>
          </div>
        </div>
      ) : (
        <main className="flex-1 p-6 max-w-6xl mx-auto w-full space-y-8">
          {/* Section 1: Hero KPIs */}
          <HeroMetrics metrics={metrics} pendingCount={approvals.length} />

          {/* Section 2: Live Pipeline */}
          <RecoveryPipeline opportunities={opportunities} onScrollToApprovals={scrollToApprovals} />

          {/* Section 3: Approval Queue */}
          <ApprovalQueue approvals={approvals} onRefresh={refresh} innerRef={approvalRef} />
        </main>
      )}
    </div>
  );
}
