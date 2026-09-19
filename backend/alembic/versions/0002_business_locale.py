"""business locale fields (multi-country core)

Revision ID: 0002_business_locale
Revises: 0001_baseline
Create Date: 2026-09-19

Adds the MISSING multi-country locale columns to the businesses table:
  - country_code VARCHAR(2)   default 'GB'
  - tax_rate     FLOAT        default 20.0
  - tax_name     VARCHAR(16)  default 'VAT'

(currency + timezone already exist in live DB from create_all — not repeated.)

NOTE: deploy with `alembic upgrade head`. Do NOT run against the live DB
from dev — the live Aiven DB is still stamped at 0001_baseline.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_business_locale"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("country_code", sa.String(2), server_default="GB", nullable=False),
    )
    op.add_column(
        "businesses",
        sa.Column("tax_rate", sa.Float(), server_default="20.0", nullable=False),
    )
    op.add_column(
        "businesses",
        sa.Column("tax_name", sa.String(16), server_default="VAT", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("businesses", "tax_name")
    op.drop_column("businesses", "tax_rate")
    op.drop_column("businesses", "country_code")
