"""convert_embedding_to_halfvec

Revision ID: 09888a569d40
Revises: 802b53cde839
Create Date: 2025-07-22 15:12:05.076185

"""

import os
from collections.abc import Sequence
from pathlib import Path

import yaml

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "09888a569d40"
down_revision: str | Sequence[str] | None = "802b53cde839"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def get_vector_config():
    """Load vector configuration from config files."""
    # Default to development config
    config_file = os.environ.get("CONFIG_FILE", "development.yaml")
    config_path = Path(__file__).parent.parent.parent.parent / "config" / config_file

    if not config_path.exists():
        # Fallback to development.yaml if specified config doesn't exist
        config_path = (
            Path(__file__).parent.parent.parent.parent / "config" / "development.yaml"
        )

    # Default values if config file doesn't exist
    defaults = {
        "dimension": 2560,
        "distance_metric": "cosine",
        "m": 16,
        "ef_construction": 200,
    }

    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
            dimension = (
                config.get("models", {})
                .get("embedding", {})
                .get("dimension", defaults["dimension"])
            )
            vector_config = config.get("vector_store", {}).get("index", {})
            distance_metric = vector_config.get(
                "distance_metric", defaults["distance_metric"]
            )
            m = vector_config.get("m", defaults["m"])
            ef_construction = vector_config.get(
                "ef_construction", defaults["ef_construction"]
            )
            return dimension, distance_metric, m, ef_construction

    return (
        defaults["dimension"],
        defaults["distance_metric"],
        defaults["m"],
        defaults["ef_construction"],
    )


def upgrade() -> None:
    """Convert embedding column from TEXT to vector and create HNSW index."""
    dimension, distance_metric, m, ef_construction = get_vector_config()

    # First, ensure the pgvector extension is enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Convert the embedding column from TEXT to vector with configured dimension
    # Note: We use ALTER COLUMN with USING to handle the type conversion
    # The USING clause is necessary when changing from TEXT to a different type
    op.execute(f"""
        ALTER TABLE business_concepts_master 
        ALTER COLUMN embedding TYPE vector({dimension}) 
        USING NULL::vector({dimension})
    """)

    # Create HNSW index for efficient similarity search
    # Using configured distance metric
    op.execute(f"""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_business_concepts_embedding_hnsw
        ON business_concepts_master 
        USING hnsw (embedding vector_{distance_metric}_ops)
        WITH (m = {m}, ef_construction = {ef_construction})
    """)


def downgrade() -> None:
    """Revert embedding column back to TEXT and drop HNSW index."""
    # Drop the HNSW index first
    op.execute("DROP INDEX IF EXISTS idx_business_concepts_embedding_hnsw;")

    # Convert the column back to TEXT
    op.execute("""
        ALTER TABLE business_concepts_master 
        ALTER COLUMN embedding TYPE TEXT 
        USING embedding::text
    """)
