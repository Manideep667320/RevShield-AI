'use client';

import React, { useEffect, useState } from 'react';
import { AgentTrace } from '@/lib/types';
import { fetchAgentTrace } from '@/lib/api-client';
import {
  X,
  Search,
  Stethoscope,
  Target,
  ShieldCheck,
  Zap,
  TrendingUp,
  CheckCircle2,
  Clock,
  AlertCircle,
  Code2,
} from 'lucide-react';

interface Props {
  opportunityId: string | null;
  onClose: () => void;
}

const STAGES = [
  { id: 'detect',   name: '1. Detect',   icon: Search,      color: 'text-emerald-400', border: 'border-emerald-500/30', bg: 'bg-emerald-500/10' },
  { id: 'diagnose', name: '2. Diagnose', icon: Stethoscope, color: 'text-violet-400',  border: 'border-violet-500/30',  bg: 'bg-violet-500/10' },
  { id: 'strategy', name: '3. Strategy', icon: Target,       color: 'text-cyan-400',    border: 'border-cyan-500/30',    bg: 'bg-cyan-500/10' },
  { id: 'policy',   name: '4. Policy',   icon: ShieldCheck, color: 'text-amber-400',   border: 'border-amber-500/30',   bg: 'bg-amber-500/10' },
  { id: 'action',   name: '5. Action',   icon: Zap,         color: 'text-blue-400',    border: 'border-blue-500/30',    bg: 'bg-blue-500/10' },
  { id: 'outcome',  name: '6. Outcome',  icon: TrendingUp,  color: 'text-teal-400',    border: 'border-teal-500/30',    bg: 'bg-teal-500/10' },
] as const;

export function AgentTraceModal({ opportunityId, onClose }: Props) {
  const [trace, setTrace] = useState<AgentTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeStage, setActiveStage] = useState<typeof STAGES[number]['id']>('detect');
  const [showRawJson, setShowRawJson] = useState(false);

  useEffect(() => {
    if (!opportunityId) {
      setTrace(null);
      return;
    }
    setLoading(true);
    setError(null);
    fetchAgentTrace(opportunityId)
      .then((data) => setTrace(data))
      .catch((err) => setError(err.message || 'Failed to load agent trace'))
      .finally(() => setLoading(false));
  }, [opportunityId]);

  if (!opportunityId) return null;

  const currentStageData = trace?.stages?.[activeStage];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-fade-in">
      <div className="glass-panel w-full max-w-4xl max-h-[90vh] rounded-2xl border border-white/15 flex flex-col shadow-2xl overflow-hidden animate-fade-slide-up">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-white/[0.02]">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-xl bg-cyan-500/15 border border-cyan-500/30 flex items-center justify-center text-cyan-400 font-bold font-mono">
              AI
            </div>
            <div>
              <h2 className="text-base font-bold font-mono text-white flex items-center gap-2 leading-none">
                AGENT TRACE INSPECTOR
                {trace && (
                  <span className="px-2 py-0.5 text-[10px] font-mono bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 rounded-md">
                    {trace.current_status}
                  </span>
                )}
              </h2>
              <p className="text-[11px] text-slate-500 font-mono mt-1">
                Opportunity: <span className="text-slate-300 font-bold">{opportunityId}</span>
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex-1 flex flex-col items-center justify-center p-12 text-slate-500 font-mono space-y-3">
            <div className="h-8 w-8 rounded-full border-2 border-t-cyan-400 border-slate-700 animate-spin" />
            <p className="text-xs">Extracting agent outputs from pipeline…</p>
          </div>
        ) : error ? (
          <div className="flex-1 p-8 text-center space-y-2">
            <AlertCircle className="h-8 w-8 text-rose-400 mx-auto" />
            <p className="text-rose-300 font-mono text-sm">{error}</p>
          </div>
        ) : trace ? (
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            {/* Stage Selector Tabs */}
            <div className="flex items-center gap-1.5 px-6 py-3 border-b border-white/10 overflow-x-auto no-scrollbar bg-white/[0.01]">
              {STAGES.map((s) => {
                const Icon = s.icon;
                const isActive = activeStage === s.id;
                const stageInfo = trace.stages[s.id];
                const isDone = stageInfo?.status === 'COMPLETED';

                return (
                  <button
                    key={s.id}
                    onClick={() => setActiveStage(s.id)}
                    className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-mono transition-all cursor-pointer whitespace-nowrap border ${
                      isActive
                        ? `${s.bg} ${s.border} text-white font-bold shadow-md`
                        : 'bg-white/[0.02] border-white/8 text-slate-400 hover:text-slate-200 hover:bg-white/5'
                    }`}
                  >
                    <Icon className={`h-3.5 w-3.5 ${s.color}`} />
                    <span>{s.name}</span>
                    {isDone ? (
                      <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0" />
                    ) : (
                      <Clock className="h-3 w-3 text-slate-600 shrink-0" />
                    )}
                  </button>
                );
              })}
            </div>

            {/* Stage Details */}
            <div className="flex-1 p-6 overflow-y-auto space-y-6">
              {/* Header card for current active stage */}
              <div className="glass-panel rounded-xl p-5 border-white/10 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span className="px-2.5 py-1 rounded-full bg-cyan-500/15 text-cyan-300 text-xs font-mono font-bold border border-cyan-500/30">
                      {currentStageData?.agent || activeStage.toUpperCase()}
                    </span>
                    <span className="text-xs font-mono text-slate-400">
                      Status: <strong className="text-emerald-400">{currentStageData?.status}</strong>
                    </span>
                  </div>

                  <button
                    onClick={() => setShowRawJson(!showRawJson)}
                    className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 text-slate-400 hover:text-white text-[11px] font-mono transition-colors cursor-pointer"
                  >
                    <Code2 className="h-3.5 w-3.5" />
                    {showRawJson ? 'Formatted View' : 'Raw JSON'}
                  </button>
                </div>

                {showRawJson ? (
                  <pre className="p-4 rounded-xl bg-black/60 border border-white/10 text-[11px] font-mono text-emerald-400 overflow-x-auto">
                    {JSON.stringify(currentStageData, null, 2)}
                  </pre>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 pt-1">
                    {currentStageData &&
                      Object.entries(currentStageData)
                        .filter(([k]) => !['agent', 'status'].includes(k))
                        .map(([key, val]) => (
                          <div key={key} className="p-3 rounded-lg bg-white/[0.03] border border-white/5 space-y-1">
                            <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                              {key.replace(/_/g, ' ')}
                            </div>
                            <div className="text-xs font-mono font-semibold text-white truncate">
                              {typeof val === 'object'
                                ? JSON.stringify(val)
                                : typeof val === 'boolean'
                                ? val
                                  ? '✓ Yes / True'
                                  : '✗ No / False'
                                : String(val)}
                            </div>
                          </div>
                        ))}
                  </div>
                )}
              </div>

              {/* Special Stage Reasoning / Rule Cards */}
              {activeStage === 'strategy' && currentStageData?.reasoning && (
                <div className="p-4 rounded-xl border border-cyan-500/20 bg-cyan-500/5 space-y-1.5 font-mono text-xs">
                  <div className="text-cyan-400 font-bold">AI STRATEGY REASONING & EXPECTED VALUE EVALUATION:</div>
                  <div className="text-slate-300 leading-relaxed">{currentStageData.reasoning}</div>
                </div>
              )}

              {activeStage === 'policy' && currentStageData?.policy_rules && (
                <div className="p-4 rounded-xl border border-amber-500/20 bg-amber-500/5 space-y-2 font-mono text-xs">
                  <div className="text-amber-400 font-bold">MERCHANT POLICY GUARDRAILS EVALUATED:</div>
                  <div className="space-y-1">
                    {currentStageData.policy_rules.map((rule: string, i: number) => (
                      <div key={i} className="flex items-center gap-2 text-slate-300">
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                        <span>{rule}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
