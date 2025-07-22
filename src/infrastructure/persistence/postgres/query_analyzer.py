"""Query analysis utilities for PostgreSQL vector search.

This module provides utilities for analyzing query performance
and ensuring indexes are properly utilized.
"""

import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


async def analyze_vector_search_query(
    conn: asyncpg.Connection,
    embedding: list[float],
    similarity_threshold: float = 0.7,
    limit: int = 10,
) -> dict[str, Any]:
    """Analyze the execution plan for a vector search query.

    Args:
        conn: Database connection
        embedding: Query embedding vector
        similarity_threshold: Minimum similarity threshold
        limit: Result limit

    Returns:
        Dictionary containing query plan analysis
    """
    # Use EXPLAIN ANALYZE to get execution plan
    query = """
    EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
    SELECT
        concept_id,
        company_code,
        concept_name,
        1 - (embedding <=> $1::halfvec(2560)) as similarity_score
    FROM business_concepts_master
    WHERE
        is_active = true
        AND 1 - (embedding <=> $1::halfvec(2560)) >= $2
    ORDER BY embedding <=> $1::halfvec(2560)
    LIMIT $3
    """

    result = await conn.fetchval(query, embedding, similarity_threshold, limit)

    # Parse the JSON plan
    import json

    plan = json.loads(result)[0]

    # Extract key metrics
    analysis = {
        "execution_time_ms": plan.get("Execution Time", 0),
        "planning_time_ms": plan.get("Planning Time", 0),
        "total_time_ms": plan.get("Execution Time", 0) + plan.get("Planning Time", 0),
        "uses_index": False,
        "index_name": None,
        "rows_scanned": 0,
        "plan_details": plan["Plan"],
    }

    # Check if HNSW index was used
    plan_str = json.dumps(plan)
    if "Index Scan" in plan_str and "idx_concepts_embedding" in plan_str:
        analysis["uses_index"] = True
        analysis["index_name"] = "idx_concepts_embedding"
        logger.info("HNSW index is being used for vector search")
    else:
        logger.warning("HNSW index NOT being used - possible performance issue")

    # Extract row counts
    if "Plan" in plan and "Actual Rows" in plan["Plan"]:
        analysis["rows_scanned"] = plan["Plan"]["Actual Rows"]

    return analysis


async def verify_hnsw_index_exists(conn: asyncpg.Connection) -> bool:
    """Verify that the HNSW index exists on the embeddings column.

    Args:
        conn: Database connection

    Returns:
        True if HNSW index exists, False otherwise
    """
    query = """
    SELECTEXISTS (
        SELECT1
        FROM pg_indexes
        WHERE
            schemaname = 'public'
            AND tablename = 'business_concepts_master'
            AND indexname = 'idx_concepts_embedding'
    )
    """

    exists = await conn.fetchval(query)

    if exists:
        # Get index details
        details_query = """
        SELECT
            indexdef,
            pg_size_pretty(pg_relation_size(indexrelid::regclass)) as index_size
        FROM pg_indexes
        JOIN pg_stat_user_indexes ON indexrelname = indexname
        WHERE
            schemaname = 'public'
            AND tablename = 'business_concepts_master'
            AND indexname = 'idx_concepts_embedding'
        """

        row = await conn.fetchrow(details_query)
        if row:
            logger.info(
                f"HNSW index found: {row['indexdef']}, Size: {row['index_size']}"
            )
    else:
        logger.error("HNSW index 'idx_concepts_embedding' not found!")

    return exists


async def get_index_statistics(conn: asyncpg.Connection) -> dict[str, Any]:
    """Get statistics about index usage.

    Args:
        conn: Database connection

    Returns:
        Dictionary with index usage statistics
    """
    query = """
    SELECT
        indexrelname as index_name,
        idx_scan as index_scans,
        idx_tup_read as tuples_read,
        idx_tup_fetch as tuples_fetched,
        pg_size_pretty(pg_relation_size(indexrelid::regclass)) as index_size
    FROM pg_stat_user_indexes
    WHERE
        schemaname = 'public'
        AND tablename = 'business_concepts_master'
        AND indexrelname = 'idx_concepts_embedding'
    """

    row = await conn.fetchrow(query)

    if row:
        return dict(row)
    else:
        return {
            "index_name": "idx_concepts_embedding",
            "status": "NOT FOUND",
            "index_scans": 0,
            "tuples_read": 0,
            "tuples_fetched": 0,
            "index_size": "0 bytes",
        }
