'use client';

import React, { useRef, useState } from 'react';
import { PendingApproval } from '@/lib/types';
import { submitApprovalDecision } from '@/lib/api-client';
import { Check, CheckCircle2, XCircle } from 'lucide-react';

interface Props {
  approvals: PendingApproval[];
  onRefresh: () => void;
  innerRef?: React.RefObject<HTMLElement | null>;
}

function formatNumber(v: string | number): string {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  if (isNaN(n)) return '0';
  return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function fmtINR(v: string | number): string {
  return `₹${formatNumber(v)}`;
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
    <section ref={innerRef} className="space-y-2.5 pt-2">
      <div className="flex items-center gap-2 text-[11px] font-mono tracking-wider text-slate-400 uppercase">
        <span className="h-1.5 w-1.5 rounded-full bg-[#10B981]" />
        <span>APPROVAL QUEUE</span>
      </div>

      {feedback && (
        <div
          className={`p-3 rounded-xl border text-xs font-mono transition-all ${
            feedback.ok
              ? 'bg-[#ECFDF5] border-[#A7F3D0] text-[#059669]'
              : 'bg-[#FEF2F2] border-[#FECACA] text-[#DC2626]'
          }`}
        >
          {feedback.msg}
        </div>
      )}

      {approvals.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200/90 p-8 text-center shadow-2xs">
          <div className="h-10 w-10 rounded-full bg-[#ECFDF5] border border-[#A7F3D0] flex items-center justify-center text-[#059669] mx-auto mb-3">
            <Check className="h-5 w-5 stroke-[2.5]" />
          </div>
          <div className="font-semibold text-slate-700 text-sm tracking-tight">
            All clear — engine running autonomously
          </div>
          <div className="text-slate-400 text-xs mt-1">
            No human decisions required right now
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {approvals.map((item) => (
            <div
              key={item.approval_id}
              className="bg-white rounded-2xl border-2 border-amber-300/80 p-5 shadow-xs space-y-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs text-slate-400 font-mono">
                    {item.merchant_name || 'High-Value Payment Review'}
                  </div>
                  <div className="text-xl font-bold font-mono text-amber-600 mt-0.5">
                    {fmtINR(item.amount)}
                  </div>
                </div>
                <div className="text-right">
                  <span className="px-2.5 py-0.5 rounded-md border border-rose-200 bg-rose-50 text-rose-600 text-[11px] font-mono">
                    {(item.failure_reason || 'INSUFFICIENT_FUNDS').replace(/_/g, ' ')}
                  </span>
                  <div className="text-[10px] text-slate-400 font-mono mt-1">
                    {timeAgo(item.created_at)}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 text-xs font-mono text-slate-600 pt-1">
                <span>AI Recommends:</span>
                <span className="px-2 py-0.5 rounded-md border border-cyan-200 bg-cyan-50 text-cyan-700 font-bold text-[11px]">
                  {(item.recommended_strategy || 'PAYMENT_LINK').replace(/_/g, ' ')}
                </span>
              </div>

              <div className="flex items-center gap-2.5 pt-2 border-t border-slate-100">
                <button
                  onClick={() => decide(item.opportunity_id || item.approval_id, false)}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-slate-50 hover:bg-rose-50 border border-slate-200 hover:border-rose-300 text-slate-600 hover:text-rose-600 font-bold text-xs font-mono transition-all cursor-pointer"
                >
                  <XCircle className="h-4 w-4" /> Reject
                </button>
                <button
                  onClick={() => decide(item.opportunity_id || item.approval_id, true)}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-[#10B981] hover:bg-[#059669] text-white font-bold text-xs font-mono shadow-xs transition-all cursor-pointer"
                >
                  <CheckCircle2 className="h-4 w-4" /> Approve
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
