'use client';

import React, { useMemo, useState } from 'react';
import { RecoveryOpportunity } from '@/lib/types';
import { CheckCircle2, Clock, Zap, Eye } from 'lucide-react';
import { AgentTraceModal } from '@/components/AgentTraceModal';

interface Props { opportunities: RecoveryOpportunity[]; onScrollToApprovals: () => void }

/* ── Status → human label ───────────────────────────────── */
const STATUS_LABEL: Record<string, string> = {
  OPEN:               'Detected',
  DIAGNOSING:         'Diagnosing',
  DIAGNOSED:          'Diagnosed',
  STRATEGY_SELECTED:  'Strategy Set',
  AWAITING_POLICY:    'Policy Check',
  AWAITING_APPROVAL:  'Needs Approval',
  IN_PROGRESS:        'In Progress',
  EXECUTING:          'Executing',
  RECOVERED:          'Recovered',
  FAILED:             'Failed',
  POLICY_REJECTED:    'Rejected',
  ABANDONED:          'Abandoned',
};

/* ── 6 pipeline steps with thresholds ───────────────────── */
const STEPS = ['Detect', 'Diagnose', 'Strategy', 'Policy', 'Action', 'Outcome'] as const;

function stepIndex(status: string): number {
  switch (status) {
    case 'OPEN':               return 0;
    case 'DIAGNOSING':
    case 'DIAGNOSED':          return 1;
    case 'STRATEGY_SELECTED':  return 2;
    case 'AWAITING_POLICY':
    case 'AWAITING_APPROVAL':  return 3;
    case 'EXECUTING':
    case 'IN_PROGRESS':        return 4;
    case 'RECOVERED':
    case 'FAILED':
    case 'POLICY_REJECTED':
    case 'ABANDONED':          return 5;
    default:                   return 0;
  }
}

/* ── Inline mini-stepper (6 dots connected by a line) ──── */
function Stepper({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-0 w-full">
      {STEPS.map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <React.Fragment key={label}>
            {/* Connector line */}
            {i > 0 && (
              <div className={`flex-1 h-0.5 rounded-full transition-colors duration-500 ${
                done ? 'bg-emerald-500' : active ? 'bg-cyan-500/40' : 'bg-white/8'
              }`} />
            )}
            {/* Dot + label */}
            <div className="flex flex-col items-center gap-1 shrink-0">
              <div className={`h-3 w-3 rounded-full border-2 transition-all duration-500 ${
                done
                  ? 'bg-emerald-500 border-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]'
                  : active
                  ? 'bg-cyan-500 border-cyan-400 shadow-[0_0_10px_rgba(6,182,212,0.6)]'
                  : 'bg-transparent border-white/15'
              }`} />
              <span className={`text-[9px] font-mono leading-none transition-colors ${
                done ? 'text-emerald-400/70' : active ? 'text-cyan-400' : 'text-slate-600'
              }`}>{label}</span>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}

/* ── Badge helpers ──────────────────────────────────────── */
function StatusBadge({ status }: { status: string }) {
  const isSuccess = status === 'RECOVERED';
  const isFail = ['FAILED', 'POLICY_REJECTED', 'ABANDONED'].includes(status);
  const isPending = status === 'AWAITING_APPROVAL';
  const cls = isSuccess
    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
    : isFail
    ? 'bg-rose-500/15 text-rose-400 border-rose-500/30'
    : isPending
    ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
    : 'bg-slate-500/15 text-slate-300 border-white/10';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-bold font-mono ${cls}`}>
      {isSuccess && <CheckCircle2 className="h-3 w-3" />}
      {isPending && <Clock className="h-3 w-3" />}
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const cls = priority === 'HIGH'
    ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
    : priority === 'MEDIUM'
    ? 'bg-blue-500/15 text-blue-400 border-blue-500/30'
    : 'bg-slate-500/15 text-slate-400 border-white/10';
  return (
    <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold font-mono ${cls}`}>{priority}</span>
  );
}

function FailureBadge({ reason }: { reason: string }) {
  const label = (reason || 'UNKNOWN').replace(/_/g, ' ');
  return (
    <span className="px-2 py-0.5 rounded-full border border-rose-500/20 bg-rose-500/8 text-rose-300 text-[10px] font-mono">
      {label}
    </span>
  );
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function fmtINR(v: number | string): string {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  if (isNaN(n)) return '₹0';
  return `₹${n.toLocaleString('en-IN')}`;
}

export function RecoveryPipeline({ opportunities, onScrollToApprovals }: Props) {
  const [selectedOppId, setSelectedOppId] = useState<string | null>(null);

  /* Sort by newest created_at. Show top 20 recent opportunities. */
  const sorted = useMemo(() => {
    return [...opportunities]
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 20);
  }, [opportunities]);

  if (sorted.length === 0) {
    return (
      <section className="glass-panel rounded-2xl p-10 text-center space-y-3 animate-fade-slide-up">
        <Zap className="h-10 w-10 text-cyan-500/30 mx-auto" />
        <p className="text-slate-500 font-mono text-sm">No recovery opportunities yet.</p>
        <p className="text-slate-600 font-mono text-xs">Click <strong className="text-amber-400">+ Simulate Failed Payment</strong> above to create one.</p>
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between px-1">
        <h2 className="text-sm font-bold font-mono text-white tracking-wide">LIVE RECOVERY PIPELINE</h2>
        <span className="flex items-center gap-1.5 text-xs font-mono text-emerald-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse-glow" /> {sorted.length} opportunities
        </span>
      </div>

      <div className="space-y-2.5">
        {sorted.map((opp) => {
          const idx = stepIndex(opp.status);
          const isAwaiting = opp.status === 'AWAITING_APPROVAL';
          const isTerminal = ['RECOVERED', 'FAILED', 'POLICY_REJECTED', 'ABANDONED'].includes(opp.status);

          return (
            <div
              key={opp.opportunity_id}
              className={`glass-panel rounded-xl p-4 transition-all duration-300 animate-fade-slide-up ${
                isAwaiting
                  ? 'border-amber-500/30 shadow-[0_0_20px_rgba(245,158,11,0.08)]'
                  : isTerminal && opp.status === 'RECOVERED'
                  ? 'border-emerald-500/20'
                  : 'border-white/8'
              }`}
            >
              {/* Row 1: Info + badges + amount */}
              <div className="flex items-center justify-between gap-4 mb-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="min-w-0">
                    <div className="font-mono text-xs text-slate-400 truncate">
                      {opp.payment_id}
                    </div>
                  </div>
                  <FailureBadge reason={opp.failure_reason || 'UNKNOWN'} />
                  <PriorityBadge priority={opp.priority} />
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <span className="font-mono text-sm font-bold text-white">{fmtINR(opp.expected_revenue)}</span>
                  <StatusBadge status={opp.status} />
                </div>
              </div>

              {/* Row 2: Stepper */}
              <div className="px-2">
                <Stepper current={isTerminal ? 6 : idx} />
              </div>

              {/* Row 3: Action strip + meta */}
              <div className="flex items-center justify-between mt-3 pt-2 border-t border-white/5">
                <div className="flex items-center gap-3 text-[10px] font-mono text-slate-600">
                  <span>{opp.selected_action ? `Strategy: ${opp.selected_action.replace(/_/g, ' ')}` : ''}</span>
                  <span>{timeAgo(opp.created_at)}</span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setSelectedOppId(opp.opportunity_id)}
                    className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-cyan-500/10 border border-cyan-500/25 text-cyan-300 text-[11px] font-bold font-mono hover:bg-cyan-500/20 transition-all active:scale-95 cursor-pointer"
                  >
                    <Eye className="h-3 w-3" /> Agent Trace
                  </button>

                  {isAwaiting && (
                    <button
                      onClick={onScrollToApprovals}
                      className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-300 text-[11px] font-bold font-mono hover:bg-amber-500/25 transition-all active:scale-95 cursor-pointer"
                    >
                      <Clock className="h-3 w-3" /> Review
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Agent Trace Modal */}
      <AgentTraceModal
        opportunityId={selectedOppId}
        onClose={() => setSelectedOppId(null)}
      />
    </section>
  );
}
