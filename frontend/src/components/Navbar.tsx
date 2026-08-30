'use client';

import React, { useRef, useState } from 'react';
import { Zap, RefreshCw, Activity } from 'lucide-react';
import { triggerSimulation } from '@/lib/api-client';

interface NavbarProps { onSimulated: () => void }

export function Navbar({ onSimulated }: NavbarProps) {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleSimulate = async () => {
    if (busy) return;
    if (timer.current) clearTimeout(timer.current);
    setBusy(true);
    setStatus('Injecting…');
    try {
      const res = await triggerSimulation();
      setStatus(`✓ ${res.payment_id ?? 'sim'}`);
    } catch (err: unknown) {
      console.error('Simulation request failed:', err);
      setStatus('! Failed');
    } finally {
      timer.current = setTimeout(() => { setBusy(false); setStatus(null); onSimulated(); }, 1500);
    }
  };

  return (
    <header className="glass-panel sticky top-0 z-50 border-b border-white/8 px-6 py-3.5 flex items-center justify-between gap-4">
      {/* Brand */}
      <div className="flex items-center gap-3">
        <div className="relative h-9 w-9 rounded-xl bg-gradient-to-br from-emerald-500 via-cyan-500 to-violet-500 flex items-center justify-center shadow-lg shadow-cyan-500/20">
          <Zap className="h-4.5 w-4.5 text-white drop-shadow" />
          <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-emerald-400 border-2 border-[#07090E] animate-pulse" />
        </div>
        <div>
          <h1 className="text-lg font-bold tracking-tight text-white leading-none">Revenue Recovery</h1>
          <p className="text-[10px] text-slate-500 font-mono tracking-widest mt-0.5">AI-POWERED AUTONOMOUS ENGINE</p>
        </div>
      </div>

      {/* Simulate button */}
      <button
        onClick={handleSimulate}
        disabled={busy}
        className="relative flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-xs font-mono shadow-lg transition-all duration-200 cursor-pointer overflow-hidden
          bg-gradient-to-r from-amber-500 to-orange-500 text-black
          hover:from-amber-400 hover:to-orange-400 hover:shadow-amber-400/25 hover:scale-[1.02]
          active:scale-95 disabled:opacity-60 disabled:cursor-not-allowed disabled:scale-100"
      >
        {busy && <span className="absolute inset-0 animate-shimmer" />}
        {busy
          ? <RefreshCw className="h-4 w-4 animate-spin relative z-10" />
          : <Activity className="h-4 w-4 relative z-10" />
        }
        <span className="relative z-10">{status || '+ Simulate Failed Payment'}</span>
      </button>
    </header>
  );
}
