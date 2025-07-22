"""Fix schema mismatch - add missing columns

Revision ID: 802b53cde839
Revises: 002_business_concepts_master
Create Date: 2025-07-22 14:16:24.144078

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "802b53cde839"
down_revision: str | Sequence[str] | None = "002_business_concepts_master"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Fix schema mismatch between migration and SQLAlchemy models."""
    # Add missing columns to companies table
    # Migration created 'company_name' but model expects 'company_name_full' and 'company_name_short'
    op.add_column(
        "companies", sa.Column("company_name_full", sa.String(255), nullable=True)
    )
    op.add_column(
        "companies", sa.Column("company_name_short", sa.String(100), nullable=True)
    )

    # Copy data from company_name to company_name_full
    op.execute(
        "UPDATE companies SET company_name_full = company_name WHERE company_name IS NOT NULL"
    )

    # Now we can make company_name_full not nullable
    op.alter_column("companies", "company_name_full", nullable=False)

    # Drop the old company_name column that doesn't match the model
    op.drop_column("companies", "company_name")

    # Add missing original_content column to source_documents table
    op.add_column(
        "source_documents", sa.Column("original_content", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    """Revert schema changes."""
    # Remove original_content column from source_documents table
    op.drop_column("source_documents", "original_content")

    # Add back the old company_name column
    op.add_column("companies", sa.Column("company_name", sa.String(255), nullable=True))

    # Copy data from company_name_full back to company_name
    op.execute(
        "UPDATE companies SET company_name = company_name_full WHERE company_name_full IS NOT NULL"
    )

    # Make company_name not nullable
    op.alter_column("companies", "company_name", nullable=False)

    # Remove the new columns
    op.drop_column("companies", "company_name_short")
    op.drop_column("companies", "company_name_full")
