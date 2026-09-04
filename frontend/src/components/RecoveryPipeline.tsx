'use client';

import React, { useMemo, useState } from 'react';
import { RecoveryOpportunity } from '@/lib/types';
import { Clock, Eye, Sparkles, CheckCircle2 } from 'lucide-react';
import { AgentTraceModal } from '@/components/AgentTraceModal';

interface Props {
  opportunities: RecoveryOpportunity[];
  onScrollToApprovals?: () => void;
  onSimulate?: () => void;
  isSimulating?: boolean;
}

const STEPS = ['DETECT', 'DIAGNOSE', 'STRATEGY', 'POLICY', 'ACTION', 'OUTCOME'] as const;

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

interface ProfileData {
  name: string;
  initials: string;
  avatarBg: string;
  avatarColor: string;
  topBorder: string;
  reasonTag: string;
  bankTag: string;
  note: string;
}

const KNOWN_PROFILES: Record<string, Partial<ProfileData>> = {
  'sim_f510624522ff45f6': {
    name: 'Priya Sharma',
    initials: 'PS',
    avatarBg: 'bg-[#FEE2E2]',
    avatarColor: 'text-[#E11D48]',
    topBorder: 'border-t-[#E11D48]',
    reasonTag: 'Card expired',
    bankTag: 'HDFC Visa',
    note: 'Email retry · Card updated',
  },
  'sim_251355303ee24fea': {
    name: 'Rahul Verma',
    initials: 'RV',
    avatarBg: 'bg-[#FEF3C7]',
    avatarColor: 'text-[#D97706]',
    topBorder: 'border-t-[#F59E0B]',
    reasonTag: 'Insufficient funds',
    bankTag: 'ICICI RuPay',
    note: 'SMS retry · Alt payment',
  },
  'sim_84b847d5aab84f8d': {
    name: 'Aditya Nair',
    initials: 'AN',
    avatarBg: 'bg-[#FFEDD5]',
    avatarColor: 'text-[#EA580C]',
    topBorder: 'border-t-[#FB923C]',
    reasonTag: 'Network timeout',
    bankTag: 'SBI Mastercard',
    note: 'Auto-retry ×3 - Succeeded',
  },
  'sim_c3a921f77dd01b2e': {
    name: 'Meera Pillai',
    initials: 'MP',
    avatarBg: 'bg-[#FCE7F3]',
    avatarColor: 'text-[#DB2777]',
    topBorder: 'border-t-[#F43F5E]',
    reasonTag: 'CVV mismatch',
    bankTag: 'Axis Amex',
    note: 'Verification email - Re-auth',
  },
  'sim_7e02bb4c19a3f59d': {
    name: 'Suresh Iyer',
    initials: 'SI',
    avatarBg: 'bg-[#E0E7FF]',
    avatarColor: 'text-[#4F46E5]',
    topBorder: 'border-t-[#3B82F6]',
    reasonTag: '3DS auth failed',
    bankTag: 'Kotak Visa',
    note: 'OTP fallback - Auth passed',
  },
};

const FALLBACK_PROFILES: ProfileData[] = [
  {
    name: 'Priya Sharma',
    initials: 'PS',
    avatarBg: 'bg-[#FEE2E2]',
    avatarColor: 'text-[#E11D48]',
    topBorder: 'border-t-[#E11D48]',
    reasonTag: 'Card expired',
    bankTag: 'HDFC Visa',
    note: 'Email retry · Card updated',
  },
  {
    name: 'Rahul Verma',
    initials: 'RV',
    avatarBg: 'bg-[#FEF3C7]',
    avatarColor: 'text-[#D97706]',
    topBorder: 'border-t-[#F59E0B]',
    reasonTag: 'Insufficient funds',
    bankTag: 'ICICI RuPay',
    note: 'SMS retry · Alt payment',
  },
  {
    name: 'Aditya Nair',
    initials: 'AN',
    avatarBg: 'bg-[#FFEDD5]',
    avatarColor: 'text-[#EA580C]',
    topBorder: 'border-t-[#FB923C]',
    reasonTag: 'Network timeout',
    bankTag: 'SBI Mastercard',
    note: 'Auto-retry ×3 - Succeeded',
  },
  {
    name: 'Meera Pillai',
    initials: 'MP',
    avatarBg: 'bg-[#FCE7F3]',
    avatarColor: 'text-[#DB2777]',
    topBorder: 'border-t-[#F43F5E]',
    reasonTag: 'CVV mismatch',
    bankTag: 'Axis Amex',
    note: 'Verification email - Re-auth',
  },
  {
    name: 'Suresh Iyer',
    initials: 'SI',
    avatarBg: 'bg-[#E0E7FF]',
    avatarColor: 'text-[#4F46E5]',
    topBorder: 'border-t-[#3B82F6]',
    reasonTag: '3DS auth failed',
    bankTag: 'Kotak Visa',
    note: 'OTP fallback - Auth passed',
  },
  {
    name: 'Vikram Patel',
    initials: 'VP',
    avatarBg: 'bg-[#CCFBF1]',
    avatarColor: 'text-[#0D9488]',
    topBorder: 'border-t-[#14B8A6]',
    reasonTag: 'Bank gateway error',
    bankTag: 'Yes Bank Visa',
    note: 'Smart route retry - Succeeded',
  },
];

function getProfile(opp: RecoveryOpportunity, index: number): ProfileData {
  const pId = opp.payment_id;
  if (pId && KNOWN_PROFILES[pId]) {
    const known = KNOWN_PROFILES[pId];
    return {
      name: known.name || 'Merchant Customer',
      initials: known.initials || 'MC',
      avatarBg: known.avatarBg || 'bg-slate-100',
      avatarColor: known.avatarColor || 'text-slate-600',
      topBorder: known.topBorder || 'border-t-slate-300',
      reasonTag: known.reasonTag || opp.failure_reason?.replace(/_/g, ' ') || 'Card declined',
      bankTag: known.bankTag || 'HDFC Visa',
      note: known.note || 'Autonomous recovery',
    };
  }

  const fallback = FALLBACK_PROFILES[index % FALLBACK_PROFILES.length];
  return {
    ...fallback,
    reasonTag: opp.failure_reason 
      ? opp.failure_reason.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase())
      : fallback.reasonTag,
  };
}

function formatNumber(v: number | string): string {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  if (isNaN(n)) return '0';
  return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function fmtINR(v: number | string): string {
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

export function RecoveryPipeline({
  opportunities,
  onScrollToApprovals,
  onSimulate,
  isSimulating,
}: Props) {
  const [selectedOppId, setSelectedOppId] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<'ALL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'RECOVERED'>('ALL');

  // Filter opportunities
  const filtered = useMemo(() => {
    return opportunities.filter((opp) => {
      if (activeFilter === 'ALL') return true;
      if (activeFilter === 'RECOVERED') return opp.status === 'RECOVERED';
      return opp.priority === activeFilter;
    });
  }, [opportunities, activeFilter]);

  const filterTabs: Array<'ALL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'RECOVERED'> = [
    'ALL',
    'HIGH',
    'MEDIUM',
    'LOW',
    'RECOVERED',
  ];

  return (
    <div className="space-y-4">
      {/* Top Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-1">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight leading-tight">
            Live recovery pipeline
          </h1>
          <div className="text-[10px] font-mono text-slate-400 tracking-wider uppercase mt-0.5">
            LAST EVENT 2M AGO · 31 AGENT DECISIONS · 0 HUMAN OPS
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Live Status Pill */}
          <div className="flex items-center gap-2 px-3 py-1 rounded-full border border-[#6EE7B7] bg-[#ECFDF5] text-[#047857] text-xs font-mono font-medium shadow-2xs">
            <span className="h-1.5 w-1.5 rounded-xs bg-[#10B981] animate-pulse" />
            <span>LIVE · {opportunities.length || 5} opportunities</span>
          </div>

          {/* Simulate Failure Button */}
          {onSimulate && (
            <button
              onClick={onSimulate}
              disabled={isSimulating}
              className="flex items-center gap-1.5 px-3 py-1 rounded-lg border border-transparent hover:border-slate-200 text-slate-400 hover:text-slate-700 text-xs font-mono transition-all cursor-pointer disabled:opacity-50"
            >
              <Sparkles className="h-3.5 w-3.5" />
              <span>{isSimulating ? 'Simulating…' : 'Simulate failure'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Filter Tabs Bar */}
      <div className="flex items-center gap-6 text-[11px] font-mono border-b border-slate-200/60 pb-2">
        <span className="text-slate-400 tracking-wider">FILTER</span>
        <div className="flex items-center gap-5">
          {filterTabs.map((tab) => {
            const isActive = activeFilter === tab;
            return (
              <button
                key={tab}
                onClick={() => setActiveFilter(tab)}
                className={`tracking-wider uppercase transition-colors cursor-pointer ${
                  isActive
                    ? 'text-slate-900 font-bold'
                    : 'text-slate-400 hover:text-slate-600'
                }`}
              >
                {tab}
              </button>
            );
          })}
        </div>
      </div>

      {/* Opportunity Cards List */}
      <div className="space-y-3.5">
        {filtered.map((opp, idx) => {
          const profile = getProfile(opp, idx);
          const currentStep = opp.status === 'RECOVERED' ? 6 : stepIndex(opp.status);
          const isAwaiting = opp.status === 'AWAITING_APPROVAL';

          return (
            <div
              key={opp.opportunity_id || idx}
              className={`bg-white rounded-2xl border border-slate-200/90 shadow-2xs p-5 transition-all hover:shadow-xs ${profile.topBorder} border-t-2`}
            >
              {/* Row 1: Avatar, Customer Name, Badges, Amount, Status */}
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-3.5 min-w-0">
                  {/* Initials Avatar */}
                  <div
                    className={`h-10 w-10 rounded-xl flex items-center justify-center font-bold text-xs shrink-0 select-none ${profile.avatarBg} ${profile.avatarColor}`}
                  >
                    {profile.initials}
                  </div>

                  {/* Name, Payment ID & Badges */}
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-900 text-sm tracking-tight">
                        {profile.name}
                      </span>
                    </div>
                    <div className="text-[11px] font-mono text-slate-400 truncate">
                      {opp.payment_id}
                    </div>

                    {/* Tags */}
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      <span className="px-2.5 py-0.5 rounded-md border border-slate-200 text-slate-600 text-[11px] font-mono bg-slate-50/70">
                        {profile.reasonTag}
                      </span>
                      <span className="px-2.5 py-0.5 rounded-md border border-slate-200 text-slate-600 text-[11px] font-mono bg-slate-50/70">
                        {profile.bankTag}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Right: Amount & Status Badge */}
                <div className="text-right shrink-0">
                  <div className="font-bold font-mono text-slate-900 text-lg tracking-tight">
                    {fmtINR(opp.expected_revenue)}
                  </div>
                  <div className="mt-1.5">
                    {opp.status === 'RECOVERED' ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md border border-[#A7F3D0] bg-[#ECFDF5] text-[#059669] text-[11px] font-mono font-medium">
                        <CheckCircle2 className="h-3 w-3" /> Recovered
                      </span>
                    ) : isAwaiting ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md border border-amber-300 bg-amber-50 text-amber-700 text-[11px] font-mono font-medium">
                        <Clock className="h-3 w-3" /> Needs Approval
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md border border-slate-200 bg-slate-50 text-slate-600 text-[11px] font-mono font-medium">
                        {opp.status}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Row 2: 6-Stage Stepper */}
              <div className="mt-6 mb-4 px-2">
                <div className="flex items-center w-full">
                  {STEPS.map((step, i) => {
                    const isDone = i < currentStep;
                    const isCurrent = i === currentStep;

                    return (
                      <React.Fragment key={step}>
                        {/* Connecting Line */}
                        {i > 0 && (
                          <div
                            className={`flex-1 h-[1.5px] transition-colors duration-300 ${
                              isDone ? 'bg-[#10B981]' : 'bg-slate-200'
                            }`}
                          />
                        )}

                        {/* Step Node + Label */}
                        <div className="flex flex-col items-center gap-1.5 shrink-0 px-0.5">
                          <div
                            className={`h-2.5 w-2.5 rounded-xs transition-all duration-300 ${
                              isDone
                                ? 'bg-[#10B981]'
                                : isCurrent
                                ? 'bg-[#10B981] ring-2 ring-emerald-200'
                                : 'bg-slate-200'
                            }`}
                          />
                          <span
                            className={`text-[8.5px] font-mono font-bold tracking-wider transition-colors ${
                              isDone || isCurrent ? 'text-[#059669]' : 'text-slate-400'
                            }`}
                          >
                            {step}
                          </span>
                        </div>
                      </React.Fragment>
                    );
                  })}
                </div>
              </div>

              {/* Row 3: Footer Metadata & Agent Trace */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-[11px] font-mono text-slate-400">
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1" suppressHydrationWarning>
                    <Clock className="h-3 w-3" />
                    <span>{timeAgo(opp.created_at)}</span>
                  </span>
                  <span>{profile.note}</span>
                </div>

                <div className="flex items-center gap-2">
                  {isAwaiting && onScrollToApprovals && (
                    <button
                      onClick={onScrollToApprovals}
                      className="px-2.5 py-1 rounded-md bg-amber-50 border border-amber-300 text-amber-700 text-[11px] font-mono font-bold hover:bg-amber-100 transition-colors cursor-pointer"
                    >
                      Review
                    </button>
                  )}

                  <button
                    onClick={() => setSelectedOppId(opp.opportunity_id)}
                    className="flex items-center gap-1 text-slate-400 hover:text-slate-700 text-xs font-mono transition-colors cursor-pointer px-2 py-1 rounded-md hover:bg-slate-50"
                  >
                    <Eye className="h-3.5 w-3.5" />
                    <span>Agent trace</span>
                  </button>
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
    </div>
  );
}
