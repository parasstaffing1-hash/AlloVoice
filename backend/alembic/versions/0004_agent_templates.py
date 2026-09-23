"""agent templates + custom agents (portfolio template engine).

Revision ID: 0004_agent_templates
Revises: 0003_tenant_ids
Create Date: 2026-09-23

Creates:
  - agent_templates (platform-owned voice/chat packs, config JSONB)
  - custom_agents (business overrides of a platform template)

NOTE: validate offline only with
  `alembic upgrade 0003:head --sql`.
Do NOT run against the live DB from dev.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = "0004_agent_templates"
down_revision: Union[str, None] = "0003_tenant_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_templates",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="voice"),
        sa.Column("industry", sa.String(64), nullable=False, server_default=""),
        sa.Column("locale", sa.String(16), nullable=False, server_default="en-GB"),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "custom_agents",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("template_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("overrides", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
    )


def downgrade() -> None:
    op.drop_table("custom_agents")
    op.drop_table("agent_templates")
