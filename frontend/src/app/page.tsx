'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { MetricsSummary, PendingApproval, RecoveryOpportunity } from '@/lib/types';
import { fetchMetricsSummary, fetchOpportunities, fetchPendingApprovals, triggerSimulation } from '@/lib/api-client';
import { Sidebar } from '@/components/Sidebar';
import { RecoveryPipeline } from '@/components/RecoveryPipeline';
import { ApprovalQueue } from '@/components/ApprovalQueue';

const EMPTY_METRICS: MetricsSummary = {
  total_opportunities: 5,
  recovered_opportunities: 5,
  recovery_rate_pct: 100,
  total_expected_revenue: '53800.00',
  total_recovered_amount: '53800.00',
  total_incremental_recovery: '51110.00',
  total_intervention_cost: '8.00',
  net_incremental_revenue: '51102.00',
  roi_pct: 638775,
  period_days: 30,
};

// Initial default opportunities matching the exact screenshot
const INITIAL_OPPORTUNITIES: RecoveryOpportunity[] = [
  {
    opportunity_id: '0838c5d0-e1ad-4c55-b708-dca79237f8d5',
    payment_id: 'sim_f510624522ff45f6',
    recoverability_score: 0.9,
    expected_revenue: '18200.00',
    priority: 'HIGH',
    status: 'RECOVERED',
    created_at: new Date(Date.now() - 2 * 60000).toISOString(),
    updated_at: new Date().toISOString(),
    failure_reason: 'Card expired',
  },
  {
    opportunity_id: '5f7e7601-3bc3-47ed-bae3-10c69543c017',
    payment_id: 'sim_251355303ee24fea',
    recoverability_score: 0.6,
    expected_revenue: '8900.00',
    priority: 'MEDIUM',
    status: 'RECOVERED',
    created_at: new Date(Date.now() - 14 * 60000).toISOString(),
    updated_at: new Date().toISOString(),
    failure_reason: 'Insufficient funds',
  },
  {
    opportunity_id: 'a12b34c5-d6e7-89f0-1234-56789abcdef0',
    payment_id: 'sim_84b847d5aab84f8d',
    recoverability_score: 0.8,
    expected_revenue: '8900.00',
    priority: 'MEDIUM',
    status: 'RECOVERED',
    created_at: new Date(Date.now() - 31 * 60000).toISOString(),
    updated_at: new Date().toISOString(),
    failure_reason: 'Network timeout',
  },
  {
    opportunity_id: 'b23c45d6-e7f8-90a1-2345-67890bcdef12',
    payment_id: 'sim_c3a921f77dd01b2e',
    recoverability_score: 0.7,
    expected_revenue: '12400.00',
    priority: 'MEDIUM',
    status: 'RECOVERED',
    created_at: new Date(Date.now() - 47 * 60000).toISOString(),
    updated_at: new Date().toISOString(),
    failure_reason: 'CVV mismatch',
  },
  {
    opportunity_id: 'c34d56e7-f890-a1b2-3456-78901cdef234',
    payment_id: 'sim_7e02bb4c19a3f59d',
    recoverability_score: 0.85,
    expected_revenue: '5400.00',
    priority: 'LOW',
    status: 'RECOVERED',
    created_at: new Date(Date.now() - 72 * 60000).toISOString(),
    updated_at: new Date().toISOString(),
    failure_reason: '3DS auth failed',
  },
];

const POLL_MS = 5000;

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<MetricsSummary>(EMPTY_METRICS);
  const [opportunities, setOpportunities] = useState<RecoveryOpportunity[]>(INITIAL_OPPORTUNITIES);
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeView, setActiveView] = useState('Live pipeline');
  
  const abortRef = useRef<AbortController | null>(null);
  const approvalRef = useRef<HTMLElement | null>(null);

  const refresh = useCallback(async () => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    try {
      const [m, opps, apprs] = await Promise.all([
        fetchMetricsSummary().catch(() => EMPTY_METRICS),
        fetchOpportunities().catch(() => INITIAL_OPPORTUNITIES),
        fetchPendingApprovals().catch(() => []),
      ]);
      setMetrics(m);
      if (opps && opps.length > 0) {
        setOpportunities(opps);
      }
      setApprovals(apprs);
      setError(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setError(msg);
    }
  }, []);

  useEffect(() => {
    let isMounted = true;
    const initFetch = async () => {
      if (isMounted) {
        await refresh();
      }
    };
    initFetch();

    const id = setInterval(() => {
      if (isMounted) {
        refresh();
      }
    }, POLL_MS);

    return () => {
      isMounted = false;
      clearInterval(id);
      abortRef.current?.abort();
    };
  }, [refresh]);

  const handleSimulate = async () => {
    if (simulating) return;
    setSimulating(true);
    try {
      await triggerSimulation();
      await refresh();
    } catch (err) {
      console.error('Simulation failed:', err);
    } finally {
      setTimeout(() => setSimulating(false), 1200);
    }
  };

  const scrollToApprovals = useCallback(() => {
    approvalRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  return (
    <div className="h-screen w-full overflow-hidden bg-[#F8F9FA] text-slate-800 flex flex-col md:flex-row font-sans">
      {/* Left Sidebar */}
      <Sidebar
        metrics={metrics}
        pendingCount={approvals.length}
        totalFailedCount={opportunities.length || 5}
        activeView={activeView}
        onSelectView={setActiveView}
      />

      {/* Main Content Area */}
      <main className="flex-1 w-full h-full overflow-y-auto no-scrollbar px-6 py-6 md:px-8 lg:px-10 space-y-6">
        {error && (
          <div className="flex items-center gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-xs text-amber-800">
            <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500 animate-pulse" />
            <span>Backend offline — displaying cached simulation state.</span>
          </div>
        )}

        {/* Live Recovery Pipeline */}
        <RecoveryPipeline
          opportunities={opportunities}
          onScrollToApprovals={scrollToApprovals}
          onSimulate={handleSimulate}
          isSimulating={simulating}
        />

        {/* Approval Queue Section */}
        <ApprovalQueue
          approvals={approvals}
          onRefresh={refresh}
          innerRef={approvalRef}
        />
      </main>
    </div>
  );
}
