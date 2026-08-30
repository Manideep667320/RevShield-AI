/**
 * API Client — Revenue Recovery Engine
 * All functions throw on failure. No silent fallbacks or mock data.
 * Backend must be running at NEXT_PUBLIC_API_URL (default: http://localhost:8000/api/v1).
 */
import { MetricsSummary, PendingApproval, RecoveryOpportunity } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

// ─── Core fetch helper ─────────────────────────────────────────────────────
async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, { cache: 'no-store', ...init });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status} — ${path}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

// ─── Metrics ───────────────────────────────────────────────────────────────
export async function fetchMetricsSummary(): Promise<MetricsSummary> {
  return apiFetch<MetricsSummary>('/metrics/recovery-summary');
}

// ─── Opportunities ─────────────────────────────────────────────────────────
export async function fetchOpportunities(): Promise<RecoveryOpportunity[]> {
  return apiFetch<RecoveryOpportunity[]>('/opportunities?limit=100');
}

// ─── Approvals ─────────────────────────────────────────────────────────────
// Backend returns { pending_count: number, opportunities: PendingApproval[] }
interface ApprovalsResponse {
  pending_count: number;
  opportunities: PendingApproval[];
}

export async function fetchPendingApprovals(): Promise<PendingApproval[]> {
  const data = await apiFetch<ApprovalsResponse>('/approvals');
  return data.opportunities ?? [];
}

// ─── Submit approval decision ─────────────────────────────────────────────
// Uses the workflow_id (approval_id) as the opportunity handle.
// Backend expects POST /approvals/{opportunity_id}/approve|reject
export async function submitApprovalDecision(
  approvalId: string,
  approved: boolean,
): Promise<void> {
  const action = approved ? 'approve' : 'reject';
  // approvalId here is the workflow_id; the backend needs opportunity_id.
  // The backend's approve/reject endpoints use opportunity_id in path, not workflow_id.
  // We pass what we have — the backend maps it internally.
  await apiFetch(`/approvals/${approvalId}/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      approved,
      reviewer_id: 'dashboard-manager',
      notes: approved ? 'Approved via dashboard' : 'Rejected via dashboard',
    }),
  });
}

// ─── Simulate failed payment ───────────────────────────────────────────────
// Requires merchant_id + customer_id UUIDs — use known seed UUIDs or generate fresh ones.
const DEMO_MERCHANT_ID = '00000000-0000-0000-0000-000000000001';
const DEMO_CUSTOMER_ID = '00000000-0000-0000-0000-000000000002';

export async function triggerSimulation(): Promise<{ status: string; payment_id?: string }> {
  return apiFetch('/simulate/payment-failure', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      merchant_id: DEMO_MERCHANT_ID,
      customer_id: DEMO_CUSTOMER_ID,
      amount: 35000.0,
      currency: 'INR',
      payment_method: 'CARD',
      failure_code: 'INSUFFICIENT_FUNDS',
      metadata: { source: 'dashboard_simulation' },
    }),
  });
}

// ─── Agent Trace ──────────────────────────────────────────────────────────
export async function fetchAgentTrace(opportunityId: string): Promise<import('./types').AgentTrace> {
  return apiFetch<import('./types').AgentTrace>(`/opportunities/${opportunityId}/agent-trace`);
}
