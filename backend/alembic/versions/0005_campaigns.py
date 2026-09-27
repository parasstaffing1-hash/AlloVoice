"""stale-lead resurrection campaigns + appointment holds.

Revision ID: 0005_campaigns
Revises: 0004_agent_templates
Create Date: 2026-09-27

Creates:
  - lead_campaigns (business-owned outreach campaign header)
  - campaign_members (imported leads, per-campaign phone dedupe in app)
  - appointment_holds (double-book guard with unique hold_ref)

NOTE: validate offline only with
  `alembic upgrade 0004:head --sql`.
Do NOT run against the live DB from dev.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = "0005_campaigns"
down_revision: Union[str, None] = "0004_agent_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lead_campaigns",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="stale_db"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
    )
    op.create_index(
        "ix_lead_campaigns_business_id", "lead_campaigns", ["business_id"]
    )
    op.create_table(
        "campaign_members",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_contact_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["lead_campaigns.id"]),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
    )
    op.create_index(
        "ix_campaign_members_business_id", "campaign_members", ["business_id"]
    )
    op.create_index(
        "ix_campaign_members_campaign_id", "campaign_members", ["campaign_id"]
    )
    op.create_table(
        "appointment_holds",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("hold_ref", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="held"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["campaign_members.id"]),
    )
    op.create_index(
        "ix_appointment_holds_business_id", "appointment_holds", ["business_id"]
    )


def downgrade() -> None:
    # Indexes die with their tables on Postgres; no explicit drop needed.
    op.drop_table("appointment_holds")
    op.drop_table("campaign_members")
    op.drop_table("lead_campaigns")
