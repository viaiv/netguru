"""add admin tables: plans, subscriptions, audit_logs, usage_metrics

Revision ID: a1b2c3d4e5f6
Revises: 73ac7a56a0b9
Create Date: 2026-02-13 18:00:00.000000

"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "73ac7a56a0b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- plans ---
    op.create_table(
        "plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("stripe_product_id", sa.String(255), nullable=True),
        sa.Column("stripe_price_id", sa.String(255), nullable=True),
        sa.Column("price_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "billing_period", sa.String(20), nullable=False, server_default="monthly"
        ),
        sa.Column("upload_limit_daily", sa.Integer, nullable=False, server_default="10"),
        sa.Column("max_file_size_mb", sa.Integer, nullable=False, server_default="100"),
        sa.Column(
            "max_conversations_daily", sa.Integer, nullable=False, server_default="50"
        ),
        sa.Column(
            "max_tokens_daily", sa.Integer, nullable=False, server_default="100000"
        ),
        sa.Column("features", JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_plans_id", "plans", ["id"])

    # --- subscriptions ---
    op.create_table(
        "subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True, unique=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="active"
        ),
        sa.Column("current_period_start", sa.DateTime, nullable=True),
        sa.Column("current_period_end", sa.DateTime, nullable=True),
        sa.Column(
            "cancel_at_period_end", sa.Boolean, nullable=False, server_default="false"
        ),
        sa.Column("canceled_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_subscriptions_id", "subscriptions", ["id"])
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    op.create_index(
        "ix_subscriptions_stripe_customer_id",
        "subscriptions",
        ["stripe_customer_id"],
    )
    op.create_index(
        "ix_subscriptions_stripe_subscription_id",
        "subscriptions",
        ["stripe_subscription_id"],
        unique=True,
    )

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("changes", JSON, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_audit_logs_id", "audit_logs", ["id"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # --- usage_metrics ---
    op.create_table(
        "usage_metrics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_date", sa.Date, nullable=False),
        sa.Column("uploads_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("messages_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_used", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "metric_date", name="uq_usage_user_date"),
    )
    op.create_index("ix_usage_metrics_id", "usage_metrics", ["id"])
    op.create_index("ix_usage_metrics_user_id", "usage_metrics", ["user_id"])
    op.create_index("ix_usage_metrics_metric_date", "usage_metrics", ["metric_date"])

    # --- seed default plans ---
    plans_table = sa.table(
        "plans",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("display_name", sa.String),
        sa.column("price_cents", sa.Integer),
        sa.column("billing_period", sa.String),
        sa.column("upload_limit_daily", sa.Integer),
        sa.column("max_file_size_mb", sa.Integer),
        sa.column("max_conversations_daily", sa.Integer),
        sa.column("max_tokens_daily", sa.Integer),
        sa.column("features", JSON),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )

    op.bulk_insert(
        plans_table,
        [
            {
                "id": str(uuid4()),
                "name": "solo",
                "display_name": "Solo Engineer",
                "price_cents": 2900,
                "billing_period": "monthly",
                "upload_limit_daily": 10,
                "max_file_size_mb": 50,
                "max_conversations_daily": 30,
                "max_tokens_daily": 50000,
                "features": {
                    "rag_global": True,
                    "rag_local": False,
                    "pcap_analysis": True,
                    "topology_generation": False,
                },
                "is_active": True,
                "sort_order": 1,
            },
            {
                "id": str(uuid4()),
                "name": "team",
                "display_name": "Team / MSP",
                "price_cents": 19900,
                "billing_period": "monthly",
                "upload_limit_daily": 100,
                "max_file_size_mb": 100,
                "max_conversations_daily": 200,
                "max_tokens_daily": 500000,
                "features": {
                    "rag_global": True,
                    "rag_local": True,
                    "pcap_analysis": True,
                    "topology_generation": True,
                },
                "is_active": True,
                "sort_order": 2,
            },
            {
                "id": str(uuid4()),
                "name": "enterprise",
                "display_name": "Enterprise",
                "price_cents": 0,
                "billing_period": "monthly",
                "upload_limit_daily": 9999,
                "max_file_size_mb": 500,
                "max_conversations_daily": 9999,
                "max_tokens_daily": 9999999,
                "features": {
                    "rag_global": True,
                    "rag_local": True,
                    "pcap_analysis": True,
                    "topology_generation": True,
                    "custom_tools": True,
                },
                "is_active": True,
                "sort_order": 3,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("usage_metrics")
    op.drop_table("audit_logs")
    op.drop_table("subscriptions")
    op.drop_table("plans")
