"""Dues-collection calling engine.

Revision ID: 0006_collections
Revises: 0005_campaigns
Create Date: 2026-10-05

Creates:
  - collection_attempts (business-owned dues-collection call queue/outcomes)

NOTE: validate offline only with
  `alembic upgrade 0005:head --sql`.
Do NOT run against the live DB from dev.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


# revision identifiers, used by Alembic.
revision: str = "0006_collections"
down_revision: Union[str, None] = "0005_campaigns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collection_attempts",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("amount_pence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("channel", sa.String(16), nullable=False, server_default="voice"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("outcome_note", sa.Text(), nullable=True),
        sa.Column("promise_date", sa.DateTime(), nullable=True),
        sa.Column("call_sid", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
    )
    op.create_index(
        "ix_collection_attempts_business_id", "collection_attempts", ["business_id"]
    )
    op.create_index(
        "ix_collection_attempts_invoice_id", "collection_attempts", ["invoice_id"]
    )


def downgrade() -> None:
    # Indexes die with their tables on Postgres; no explicit drop needed.
    op.drop_table("collection_attempts")
