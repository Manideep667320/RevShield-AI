export interface MetricsSummary {
  total_opportunities: number;
  recovered_opportunities: number;
  recovery_rate_pct: number;
  total_expected_revenue: string;
  total_recovered_amount: string;
  total_incremental_recovery: string;
  total_intervention_cost: string;
  net_incremental_revenue: string;
  roi_pct: number;
  period_days?: number;
}

export interface RecoveryOpportunity {
  opportunity_id: string;
  payment_id: string;
  recoverability_score: number;
  expected_revenue: number | string;
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
  status: 'OPEN' | 'DIAGNOSING' | 'DIAGNOSED' | 'STRATEGY_SELECTED' | 'AWAITING_POLICY' | 'AWAITING_APPROVAL' | 'IN_PROGRESS' | 'EXECUTING' | 'RECOVERED' | 'FAILED' | 'POLICY_REJECTED' | 'ABANDONED';
  created_at: string;
  updated_at: string;
  merchant_name?: string;
  failure_reason?: string;
  selected_action?: string;
  clearance_token?: string;
}

export interface PendingApproval {
  approval_id: string;
  opportunity_id: string;
  merchant_name: string;
  customer_id: string;
  amount: string;
  failure_reason: string;
  recommended_strategy: string;
  created_at: string;
}

export interface AuditEntry {
  audit_id: string;
  timestamp: string;
  actor: string;
  action: string;
  confidence: number;
  input_snapshot: Record<string, any>;
  output_snapshot: Record<string, any>;
}

export interface AgentTraceStage {
  agent: string;
  status: string;
  [key: string]: any;
}

export interface AgentTrace {
  opportunity_id: string;
  payment_id: string;
  current_status: string;
  workflow_state: string;
  stages: {
    detect: AgentTraceStage;
    diagnose: AgentTraceStage;
    strategy: AgentTraceStage;
    policy: AgentTraceStage;
    action: AgentTraceStage;
    outcome: AgentTraceStage;
  };
}
