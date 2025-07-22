"""Create business_concepts_master and concept_relations tables

Revision ID: 002_business_concepts_master
Revises: a044ad7fcc44
Create Date: 2025-07-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_business_concepts_master"
down_revision: str | None = "a044ad7fcc44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create business_concepts_master and concept_relations tables."""

    # Create business_concepts_master table
    op.create_table(
        "business_concepts_master",
        sa.Column(
            "concept_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("company_code", sa.String(length=10), nullable=False),
        sa.Column("concept_name", sa.String(length=255), nullable=False),
        sa.Column("concept_category", sa.String(length=50), nullable=False),
        sa.Column("importance_score", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("development_stage", sa.String(length=50), nullable=True),
        sa.Column(
            "embedding", sa.Text(), nullable=True
        ),  # halfvec(2560) - to be migrated later
        sa.Column(
            "concept_details", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "last_updated_from_doc_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("concept_id"),
        sa.ForeignKeyConstraint(
            ["company_code"],
            ["companies.company_code"],
            name="fk_business_concepts_company_code",
        ),
        sa.ForeignKeyConstraint(
            ["last_updated_from_doc_id"],
            ["source_documents.doc_id"],
            name="fk_business_concepts_doc_id",
        ),
        sa.CheckConstraint(
            "concept_category IN ('核心业务', '新兴业务', '战略布局')",
            name="check_concept_category",
        ),
        sa.CheckConstraint(
            "importance_score >= 0 AND importance_score <= 1",
            name="check_importance_score",
        ),
        sa.UniqueConstraint(
            "company_code", "concept_name", name="uq_company_concept_name"
        ),
    )

    # Create indexes for business_concepts_master
    op.create_index(
        "idx_company_code", "business_concepts_master", ["company_code"], unique=False
    )
    op.create_index(
        "idx_importance_score",
        "business_concepts_master",
        ["importance_score"],
        unique=False,
    )

    # Create concept_relations table
    op.create_table(
        "concept_relations",
        sa.Column(
            "relation_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source_concept_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_entity_type", sa.String(length=50), nullable=False),
        sa.Column("target_entity_name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("relation_id"),
        sa.ForeignKeyConstraint(
            ["source_concept_id"],
            ["business_concepts_master.concept_id"],
            name="fk_concept_relations_concept_id",
        ),
    )

    # Create index for concept_relations
    op.create_index(
        "idx_source_concept", "concept_relations", ["source_concept_id"], unique=False
    )


def downgrade() -> None:
    """Drop concept_relations and business_concepts_master tables."""

    # Drop concept_relations first due to foreign key constraint
    op.drop_index("idx_source_concept", table_name="concept_relations")
    op.drop_table("concept_relations")

    # Drop business_concepts_master
    op.drop_index("idx_importance_score", table_name="business_concepts_master")
    op.drop_index("idx_company_code", table_name="business_concepts_master")
    op.drop_table("business_concepts_master")
