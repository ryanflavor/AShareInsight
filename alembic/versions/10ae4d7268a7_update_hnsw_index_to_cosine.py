"""update_hnsw_index_to_cosine

Revision ID: 10ae4d7268a7
Revises: 09888a569d40
Create Date: 2025-07-22 15:21:03.871465

"""

import os
from collections.abc import Sequence
from pathlib import Path

import yaml

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "10ae4d7268a7"
down_revision: str | Sequence[str] | None = "09888a569d40"
branch_labels: str | Sequence[str] | None = None
depends_on: Sequence[str] | None = None


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
    defaults = {"distance_metric": "cosine", "m": 16, "ef_construction": 200}

    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
            vector_config = config.get("vector_store", {}).get("index", {})
            distance_metric = vector_config.get(
                "distance_metric", defaults["distance_metric"]
            )
            m = vector_config.get("m", defaults["m"])
            ef_construction = vector_config.get(
                "ef_construction", defaults["ef_construction"]
            )
            return distance_metric, m, ef_construction

    return defaults["distance_metric"], defaults["m"], defaults["ef_construction"]


def upgrade() -> None:
    """Update HNSW index to use cosine distance metric."""
    distance_metric, m, ef_construction = get_vector_config()

    # Drop the existing index
    op.execute("DROP INDEX IF EXISTS idx_business_concepts_embedding_hnsw;")

    # Recreate the index with the configured distance metric
    # Note: We need to use the actual column type which is halfvec, not vector
    op.execute(f"""
        CREATE INDEX idx_business_concepts_embedding_hnsw
        ON business_concepts_master 
        USING hnsw (embedding halfvec_{distance_metric}_ops)
        WITH (m = {m}, ef_construction = {ef_construction})
    """)


def downgrade() -> None:
    """Revert index back to L2 distance metric."""
    # Drop the cosine index
    op.execute("DROP INDEX IF EXISTS idx_business_concepts_embedding_hnsw;")

    # Recreate with L2 distance
    op.execute("""
        CREATE INDEX idx_business_concepts_embedding_hnsw
        ON business_concepts_master 
        USING hnsw (embedding halfvec_l2_ops)
        WITH (m = 16, ef_construction = 200)
    """)
