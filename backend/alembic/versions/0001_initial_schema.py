"""Initial schema — all domain tables

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-27
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── merchants ──────────────────────────────────────────────────────────
    op.create_table("merchants",
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("recovery_policy", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── customers ──────────────────────────────────────────────────────────
    op.create_table("customers",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.merchant_id"), nullable=False),
        sa.Column("historical_payment_count", sa.Integer, server_default="0"),
        sa.Column("successful_payment_count", sa.Integer, server_default="0"),
        sa.Column("average_transaction_value", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("preferred_payment_methods", postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("last_successful_payment", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_score", sa.Float, server_default="0.5"),
    )
    op.create_index("ix_customers_merchant_id", "customers", ["merchant_id"])

    # ── payment_events ─────────────────────────────────────────────────────
    op.create_table("payment_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.merchant_id")),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.customer_id")),
        sa.Column("payment_id", sa.Text, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.Text, server_default="INR"),
        sa.Column("payment_method", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("failure_code", sa.Text, nullable=True),
        sa.Column("failure_category", sa.Text, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
    )
    op.create_index("ix_payment_events_payment_id", "payment_events", ["payment_id"], unique=True)
    op.create_index("ix_payment_events_merchant_id", "payment_events", ["merchant_id"])
    op.create_index("ix_payment_events_customer_id", "payment_events", ["customer_id"])
    op.create_index("ix_payment_events_timestamp", "payment_events", ["timestamp"])

    # ── recovery_opportunities ─────────────────────────────────────────────
    op.create_table("recovery_opportunities",
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_id", sa.Text, nullable=False),
        sa.Column("recoverability_score", sa.Numeric(4, 3), server_default="0.000"),
        sa.Column("expected_revenue", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("priority", sa.Text, server_default="LOW"),
        sa.Column("status", sa.Text, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_recovery_opportunities_payment_id", "recovery_opportunities", ["payment_id"])
    op.create_index("ix_recovery_opportunities_status", "recovery_opportunities", ["status"])

    # ── workflow_states ────────────────────────────────────────────────────
    op.create_table("workflow_states",
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recovery_opportunities.opportunity_id")),
        sa.Column("temporal_run_id", sa.Text, nullable=True),
        sa.Column("current_state", sa.Text, server_default="PENDING"),
        sa.Column("state_entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("audit_log", postgresql.JSONB, server_default="[]"),
        sa.UniqueConstraint("idempotency_key", name="uq_workflow_idempotency"),
    )
    op.create_index("ix_workflow_states_opportunity_id", "workflow_states", ["opportunity_id"])

    # ── recovery_decisions ─────────────────────────────────────────────────
    op.create_table("recovery_decisions",
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recovery_opportunities.opportunity_id")),
        sa.Column("candidate_actions", postgresql.JSONB, server_default="[]"),
        sa.Column("selected_action", sa.Text, nullable=False),
        sa.Column("expected_value", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("confidence", sa.Numeric(4, 3), server_default="0.000"),
        sa.Column("reasoning", sa.Text, server_default=""),
        sa.Column("model_version", sa.Text, server_default="rules-v1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── interventions ──────────────────────────────────────────────────────
    op.create_table("interventions",
        sa.Column("intervention_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recovery_decisions.decision_id")),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, server_default="PENDING"),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cost", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("external_ref", sa.Text, nullable=True),
    )

    # ── recovery_outcomes ──────────────────────────────────────────────────
    op.create_table("recovery_outcomes",
        sa.Column("outcome_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("intervention_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("interventions.intervention_id")),
        sa.Column("payment_status", sa.Text, nullable=False),
        sa.Column("recovered_amount", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("time_to_recovery", sa.Interval, nullable=True),
        sa.Column("incremental_recovery", sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("experiment_group", sa.Text, server_default="TREATMENT"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── policies ───────────────────────────────────────────────────────────
    op.create_table("policies",
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.merchant_id")),
        sa.Column("max_retry_count", sa.Integer, server_default="2"),
        sa.Column("max_discount_pct", sa.Numeric(4, 2), server_default="5.00"),
        sa.Column("allowed_channels", postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("approval_threshold", sa.Numeric(12, 2), server_default="25000.00"),
        sa.Column("max_intervention_cost", sa.Numeric(12, 2), server_default="50.00"),
        sa.Column("active", sa.Boolean, server_default="true"),
        sa.Column("version", sa.Integer, server_default="1"),
    )
    op.create_index("ix_policies_merchant_id", "policies", ["merchant_id"])

    # ── audit_logs ─────────────────────────────────────────────────────────
    op.create_table("audit_logs",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("output_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("model_version", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("policy_applied", postgresql.JSONB, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    tables = [
        "audit_logs", "policies", "recovery_outcomes", "interventions",
        "recovery_decisions", "workflow_states", "recovery_opportunities",
        "payment_events", "customers", "merchants",
    ]
    for table in tables:
        op.drop_table(table)
