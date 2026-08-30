'use client';

import React from 'react';
import { MetricsSummary } from '@/lib/types';

interface Props { metrics: MetricsSummary; pendingCount: number }

function parseVal(v: string | number | undefined): number {
  if (v == null) return 0;
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return isNaN(n) ? 0 : n;
}

function fmtINR(v: string | number | undefined): string {
  const n = parseVal(v);
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
  return `₹${n.toLocaleString('en-IN')}`;
}

/* Animated SVG ring — visually shows a percentage as a circular arc */
function Ring({ pct, color, size = 56 }: { pct: number; color: string; size?: number }) {
  const r = (size - 6) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - Math.min(pct, 100) / 100);
  return (
    <svg width={size} height={size} className="shrink-0 -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={5} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke={color} strokeWidth={5} strokeLinecap="round"
        strokeDasharray={circ} strokeDashoffset={offset}
        className="transition-all duration-1000 ease-out"
      />
    </svg>
  );
}

export function HeroMetrics({ metrics, pendingCount }: Props) {
  const cards = [
    {
      label: 'Revenue at Risk',
      value: fmtINR(metrics.total_expected_revenue),
      sub: `${metrics.total_opportunities} failed payments`,
      accent: 'rose',
      ringPct: Math.min(metrics.total_opportunities * 10, 100),
      ringColor: '#F43F5E',
    },
    {
      label: 'Recovered',
      value: fmtINR(metrics.total_recovered_amount),
      sub: `${metrics.recovery_rate_pct}% recovery rate`,
      accent: 'emerald',
      ringPct: metrics.recovery_rate_pct,
      ringColor: '#10B981',
    },
    {
      label: 'Net Profit',
      value: fmtINR(metrics.net_incremental_revenue),
      sub: `${metrics.roi_pct}x ROI after costs`,
      accent: 'cyan',
      ringPct: Math.min(metrics.roi_pct * 3, 100),
      ringColor: '#06B6D4',
    },
    {
      label: 'Pending Actions',
      value: String(pendingCount),
      sub: pendingCount === 0 ? 'All clear — autonomous' : 'Awaiting your decision',
      accent: pendingCount > 0 ? 'amber' : 'emerald',
      ringPct: pendingCount > 0 ? 75 : 100,
      ringColor: pendingCount > 0 ? '#F59E0B' : '#10B981',
    },
  ];

  const accentMap: Record<string, { border: string; text: string; glow: string }> = {
    rose:    { border: 'border-rose-500/25',    text: 'text-rose-400',    glow: 'shadow-rose-500/8' },
    emerald: { border: 'border-emerald-500/25', text: 'text-emerald-400', glow: 'shadow-emerald-500/8' },
    cyan:    { border: 'border-cyan-500/25',    text: 'text-cyan-400',    glow: 'shadow-cyan-500/8' },
    amber:   { border: 'border-amber-500/25',   text: 'text-amber-400',   glow: 'shadow-amber-500/8' },
  };

  return (
    <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 stagger-children">
      {cards.map((c) => {
        const a = accentMap[c.accent] ?? accentMap.cyan;
        return (
          <div
            key={c.label}
            className={`glass-panel glass-panel-hover rounded-2xl p-6 flex items-center gap-5 ${a.border} ${a.glow} animate-fade-slide-up`}
          >
            {/* Ring */}
            <div className="relative flex items-center justify-center">
              <Ring pct={c.ringPct} color={c.ringColor} />
              <span className={`absolute text-[11px] font-bold font-mono ${a.text}`}>
                {c.ringPct < 100 ? `${Math.round(c.ringPct)}%` : '✓'}
              </span>
            </div>
            {/* Text */}
            <div className="min-w-0 space-y-1">
              <div className="text-[11px] font-mono text-slate-500 uppercase tracking-widest truncate">{c.label}</div>
              <div className={`text-2xl font-bold font-mono ${a.text} animate-count-up leading-none`}>{c.value}</div>
              <div className="text-[11px] font-mono text-slate-500 truncate">{c.sub}</div>
            </div>
          </div>
        );
      })}
    </section>
  );
}
