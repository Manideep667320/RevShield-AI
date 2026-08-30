'use client';

import React, { useRef, useState } from 'react';
import { PendingApproval } from '@/lib/types';
import { submitApprovalDecision } from '@/lib/api-client';
import { CheckCircle2, XCircle, AlertTriangle, ShieldCheck } from 'lucide-react';

interface Props {
  approvals: PendingApproval[];
  onRefresh: () => void;
  innerRef?: React.RefObject<HTMLElement | null>;
}

function fmtINR(v: string | number): string {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  if (isNaN(n)) return '₹0';
  return `₹${n.toLocaleString('en-IN')}`;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  return `${Math.floor(mins / 60)}h ago`;
}

export function ApprovalQueue({ approvals: propApprovals, onRefresh, innerRef }: Props) {
  const [removedIds, setRemovedIds] = useState<Set<string>>(new Set());
  const [feedback, setFeedback] = useState<{ msg: string; ok: boolean } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const approvals = propApprovals.filter((a) => !removedIds.has(a.approval_id));

  const decide = async (id: string, approved: boolean) => {
    setRemovedIds((s) => new Set(s).add(id));
    setFeedback({
      msg: approved ? '✓ Approved — executing recovery strategy.' : '✗ Rejected — opportunity held.',
      ok: approved,
    });
    try {
      await submitApprovalDecision(id, approved);
    } catch (err: unknown) {
      console.error('Approval decision failed:', err);
      setFeedback({ msg: '! Action decision failed to reach backend.', ok: false });
    } finally {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        setFeedback(null);
        setRemovedIds(new Set());
        onRefresh();
      }, 2000);
    }
  };

  return (
    <section ref={innerRef} className="space-y-3 scroll-mt-6">
      <div className="flex items-center justify-between px-1">
        <h2 className="text-sm font-bold font-mono text-white tracking-wide flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-amber-400" />
          APPROVAL QUEUE
        </h2>
        {approvals.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse-glow" />
            <span className="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 text-[10px] font-mono font-bold border border-amber-500/30">
              {approvals.length} pending
            </span>
          </span>
        )}
      </div>

      {/* Feedback toast */}
      {feedback && (
        <div className={`flex items-center gap-2.5 px-4 py-3 rounded-xl border text-xs font-mono animate-fade-slide-up ${
          feedback.ok
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
            : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
        }`}>
          {feedback.ok ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <AlertTriangle className="h-4 w-4 shrink-0" />}
          {feedback.msg}
        </div>
      )}

      {approvals.length === 0 ? (
        <div className="glass-panel rounded-2xl p-8 text-center space-y-2 animate-fade-slide-up">
          <CheckCircle2 className="h-8 w-8 text-emerald-500/30 mx-auto" />
          <p className="text-slate-500 font-mono text-sm">All clear — engine running autonomously.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {approvals.map((item) => (
            <div
              key={item.approval_id}
              className="glass-panel rounded-xl p-5 border-amber-500/20 space-y-3 animate-fade-slide-up hover:border-amber-500/35 transition-all"
            >
              {/* Header row */}
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-mono text-xs text-slate-400 truncate">{item.merchant_name}</div>
                  <div className="text-amber-400 font-bold font-mono text-xl mt-0.5">{fmtINR(item.amount)}</div>
                </div>
                <div className="text-right shrink-0">
                  <span className="px-2 py-0.5 rounded-full border border-rose-500/20 bg-rose-500/8 text-rose-300 text-[10px] font-mono">
                    {(item.failure_reason || 'UNKNOWN').replace(/_/g, ' ')}
                  </span>
                  <div className="text-[10px] text-slate-600 font-mono mt-1">{timeAgo(item.created_at)}</div>
                </div>
              </div>

              {/* Strategy recommendation */}
              <div className="flex items-center gap-2 text-[11px] font-mono">
                <span className="text-slate-500">AI recommends:</span>
                <span className="px-2 py-0.5 rounded-full border border-cyan-500/25 bg-cyan-500/10 text-cyan-300 font-bold">
                  {(item.recommended_strategy || 'RETRY').replace(/_/g, ' ')}
                </span>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2.5 pt-2 border-t border-white/5">
                <button
                  onClick={() => decide(item.opportunity_id || item.approval_id, false)}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-rose-500/8 hover:bg-rose-500/15 border border-rose-500/20 hover:border-rose-500/35 text-rose-300 font-bold text-[11px] font-mono transition-all active:scale-95 cursor-pointer"
                >
                  <XCircle className="h-3.5 w-3.5" /> Reject
                </button>
                <button
                  onClick={() => decide(item.opportunity_id || item.approval_id, true)}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-[11px] font-mono shadow-lg shadow-emerald-500/15 transition-all hover:scale-[1.02] active:scale-95 cursor-pointer"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" /> Approve
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
