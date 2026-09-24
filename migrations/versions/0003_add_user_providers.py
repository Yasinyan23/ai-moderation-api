"""add user_providers table

Revision ID: 0003
Revises: 0002
Create Date: 2024-06-01 01:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_providers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("encrypted_key", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_providers_user_id", "user_providers", ["user_id"])
    op.create_index("ix_user_providers_user_provider", "user_providers", ["user_id", "provider"])


def downgrade() -> None:
    op.drop_index("ix_user_providers_user_provider", table_name="user_providers")
    op.drop_index("ix_user_providers_user_id", table_name="user_providers")
    op.drop_table("user_providers")
