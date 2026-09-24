"""initial

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            sa.String(36),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("key_hash", sa.Text, unique=True, nullable=False),
        sa.Column("app_name", sa.Text, nullable=False),
        sa.Column("owner_email", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "user_violations",
        sa.Column(
            "id",
            sa.String(36),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "app_id",
            sa.String(36),
            sa.ForeignKey("api_keys.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Text, nullable=False),
        sa.Column("count", sa.SmallInteger, nullable=False, server_default=sa.text("0")),
        sa.Column("flagged", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("flagged_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("app_id", "user_id", name="uq_user_violations_app_user"),
    )

    op.create_table(
        "violation_logs",
        sa.Column(
            "id",
            sa.String(36),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "app_id",
            sa.String(36),
            sa.ForeignKey("api_keys.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Text, nullable=False),
        sa.Column("message_text", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_user_violations_app_user", "user_violations", ["app_id", "user_id"])
    op.create_index("ix_violation_logs_app_id", "violation_logs", ["app_id"])
    op.create_index("ix_violation_logs_user_id", "violation_logs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_violation_logs_user_id", table_name="violation_logs")
    op.drop_index("ix_violation_logs_app_id", table_name="violation_logs")
    op.drop_index("ix_user_violations_app_user", table_name="user_violations")
    op.drop_table("violation_logs")
    op.drop_table("user_violations")
    op.drop_table("api_keys")
