"""tenant isolation: business_id on invoices/quotes/reviews/job_photos.

Revision ID: 0003_tenant_ids
Revises: 0002_business_locale
Create Date: 2026-09-19

Adds nullable business_id FK to 4 tables and backfills from the
job/customer parents (both carry business_id, NOT NULL FKs, so every
row resolves). Enforcement lives in route-layer scoping; columns stay
nullable to avoid breaking any edge-case historical rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_tenant_ids"
down_revision: Union[str, None] = "0002_business_locale"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("invoices", "quotes", "reviews", "job_photos")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("business_id", sa.UUID(), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table}_business_id", table, "businesses",
            ["business_id"], ["id"],
        )
    # Backfill from parents (all NOT NULL FKs — full coverage expected).
    op.execute(
        "UPDATE invoices i SET business_id = c.business_id "
        "FROM customers c WHERE i.customer_id = c.id AND i.business_id IS NULL"
    )
    op.execute(
        "UPDATE quotes q SET business_id = c.business_id "
        "FROM customers c WHERE q.customer_id = c.id AND q.business_id IS NULL"
    )
    op.execute(
        "UPDATE reviews r SET business_id = j.business_id "
        "FROM jobs j WHERE r.job_id = j.id AND r.business_id IS NULL"
    )
    op.execute(
        "UPDATE job_photos p SET business_id = j.business_id "
        "FROM jobs j WHERE p.job_id = j.id AND p.business_id IS NULL"
    )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f"fk_{table}_business_id", table, type_="foreignkey")
        op.drop_column(table, "business_id")
