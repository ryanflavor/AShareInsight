"""create_source_documents_table

Revision ID: a044ad7fcc44
Revises:
Create Date: 2025-07-20 19:42:34.458775

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a044ad7fcc44"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create source_documents table for archiving LLM extraction results."""
    # Enable pgvector extension if not already enabled
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Create companies table if it doesn't exist (referenced by foreign key)
    op.create_table(
        "companies",
        sa.Column("company_code", sa.String(10), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("exchange", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("company_code"),
        if_not_exists=True,
    )

    # Create source_documents table
    op.create_table(
        "source_documents",
        sa.Column(
            "doc_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("company_code", sa.String(10), nullable=False),
        sa.Column("doc_type", sa.String(50), nullable=False),
        sa.Column("doc_date", sa.Date(), nullable=False),
        sa.Column("report_title", sa.Text(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column(
            "raw_llm_output", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "extraction_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "processing_status",
            sa.String(20),
            server_default="completed",
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "doc_type IN ('annual_report', 'research_report')", name="check_doc_type"
        ),
        sa.ForeignKeyConstraint(
            ["company_code"],
            ["companies.company_code"],
            name="fk_source_documents_company_code",
        ),
        sa.PrimaryKeyConstraint("doc_id"),
        sa.UniqueConstraint("file_hash", name="uq_source_documents_file_hash"),
    )

    # Create indexes
    op.create_index(
        "idx_company_date",
        "source_documents",
        ["company_code", "doc_date"],
        unique=False,
    )
    op.create_index("idx_doc_type", "source_documents", ["doc_type"], unique=False)
    op.create_index(
        "idx_processing_status", "source_documents", ["processing_status"], unique=False
    )


def downgrade() -> None:
    """Drop source_documents table and related objects."""
    # Drop indexes
    op.drop_index("idx_processing_status", table_name="source_documents")
    op.drop_index("idx_doc_type", table_name="source_documents")
    op.drop_index("idx_company_date", table_name="source_documents")

    # Drop tables
    op.drop_table("source_documents")

    # Note: We don't drop the companies table as it may be used by other parts of the system
    # Also not dropping extensions as they may be used elsewhere
