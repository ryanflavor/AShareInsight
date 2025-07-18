#!/usr/bin/env python3
"""
Unified database initialization script for AShareInsight project.

This script handles:
1. Database creation
2. Schema initialization (with halfvec support)
3. Verification of setup
4. Optional test data insertion
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import psycopg
from psycopg.errors import DuplicateDatabase

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.core.src.core.config import get_settings
from packages.core.src.core.database import DatabaseOperations
from packages.core.src.core.logging_config import get_logger, setup_logging
from packages.core.src.core.models import BusinessConcept, Company, SourceDocument

# Setup logging
setup_logging(level="INFO")
logger = get_logger(__name__)


def create_database_if_not_exists(connection_params: dict, db_name: str) -> None:
    """Create database if it doesn't exist."""
    admin_params = connection_params.copy()
    admin_params["dbname"] = "postgres"

    try:
        with psycopg.connect(**admin_params) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE {db_name}")
                logger.info(f"Database '{db_name}' created successfully")
    except DuplicateDatabase:
        logger.info(f"Database '{db_name}' already exists")
    except Exception as e:
        logger.error(f"Failed to create database: {e}")
        raise


def execute_init_sql(connection_string: str, sql_file: Path) -> None:
    """Execute the initialization SQL script."""
    logger.info(f"Executing SQL script: {sql_file}")

    if not sql_file.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_file}")

    sql_content = sql_file.read_text()

    with psycopg.connect(connection_string) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_content)
            conn.commit()

    logger.info("SQL script executed successfully")


def verify_database_setup(db_ops: DatabaseOperations) -> dict:
    """Verify database setup including halfvec support."""
    results = {
        "tables_created": False,
        "halfvec_supported": False,
        "hnsw_index_created": False,
        "pgvector_version": None,
        "operations_verified": False,
    }

    try:
        # Check tables
        with db_ops.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tablename 
                    FROM pg_tables 
                    WHERE schemaname = 'public' 
                    AND tablename IN ('companies', 'source_documents', 'business_concepts_master')
                """)
                tables = [row["tablename"] for row in cur.fetchall()]
                results["tables_created"] = len(tables) == 3
                logger.info(f"Tables found: {tables}")

        # Check halfvec support
        halfvec_info = db_ops.check_halfvec_support()
        results["halfvec_supported"] = halfvec_info["halfvec_supported"]
        results["pgvector_version"] = halfvec_info["pgvector_version"]
        results["hnsw_index_created"] = bool(halfvec_info.get("hnsw_index"))

        logger.info(f"pgvector version: {results['pgvector_version']}")
        logger.info(f"halfvec support: {results['halfvec_supported']}")
        logger.info(f"HNSW index: {results['hnsw_index_created']}")

        # Test basic operations
        test_company = Company(
            company_code="TEST001", company_name_full="Test Company Limited"
        )
        _ = db_ops.create_company(test_company)

        # Clean up test data
        with db_ops.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM companies WHERE company_code = %s", ("TEST001",)
                )
                conn.commit()

        results["operations_verified"] = True
        logger.info("Database operations verified successfully")

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        raise

    return results


def insert_sample_data(db_ops: DatabaseOperations) -> None:
    """Insert sample data for testing."""
    logger.info("Inserting sample data...")

    # Create sample company
    company = Company(
        company_code="000001",
        company_name_full="平安银行股份有限公司",
        company_name_short="平安银行",
        exchange="深圳证券交易所",
    )

    try:
        db_ops.create_company(company)
        logger.info(f"Created company: {company.company_code}")
    except Exception as e:
        logger.warning(f"Company may already exist: {e}")

    # Create sample document
    doc = SourceDocument(
        company_code="000001",
        doc_type="annual_report",
        doc_date=datetime.now().date(),
        report_title="2023年年度报告",
        raw_llm_output={
            "business_segments": ["零售银行", "公司银行", "资金同业"],
            "key_metrics": {"revenue": 1000000000, "profit": 200000000},
        },
    )
    created_doc = db_ops.create_source_document(doc)
    logger.info(f"Created document: {created_doc.doc_id}")

    # Create sample business concepts
    concepts = [
        ("零售银行业务", "Retail banking operations"),
        ("公司银行业务", "Corporate banking operations"),
        ("资金同业业务", "Interbank operations"),
    ]

    for concept_name, description in concepts:
        # Generate random embedding
        embedding = np.random.randn(2560).astype(np.float32)
        embedding = (embedding / np.linalg.norm(embedding)).tolist()

        concept = BusinessConcept(
            company_code="000001",
            concept_name=concept_name,
            embedding=embedding,
            concept_details={"description": description},
            last_updated_from_doc_id=created_doc.doc_id,
        )
        _ = db_ops.create_business_concept(concept)
        logger.info(f"Created concept: {concept_name}")

    logger.info("Sample data inserted successfully")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Initialize AShareInsight database")
    parser.add_argument(
        "--sample-data",
        action="store_true",
        help="Insert sample data after initialization",
    )
    parser.add_argument(
        "--verify-only", action="store_true", help="Only verify existing database setup"
    )
    parser.add_argument(
        "--sql-file",
        type=Path,
        default=Path(__file__).parent.parent / "init-db.sql",
        help="Path to initialization SQL file",
    )

    args = parser.parse_args()

    # Get database settings
    settings = get_settings()

    # Parse connection string
    import urllib.parse

    parsed = urllib.parse.urlparse(settings.database.connection_string)
    connection_params = {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": parsed.username,
        "password": parsed.password,
        "dbname": parsed.path.lstrip("/"),
    }

    db_name = connection_params["dbname"]

    # Initialize database operations
    db_ops = None

    try:
        if not args.verify_only:
            # Create database if needed
            create_database_if_not_exists(connection_params, db_name)

            # Execute initialization SQL
            execute_init_sql(settings.database.connection_string, args.sql_file)

        # Initialize database operations
        db_ops = DatabaseOperations(settings.database.connection_string)

        # Verify setup
        results = verify_database_setup(db_ops)

        # Print summary
        print("\n" + "=" * 50)
        print("Database Setup Summary")
        print("=" * 50)
        for key, value in results.items():
            status = "✅" if value else "❌"
            if key == "pgvector_version":
                print(f"pgvector version: {value}")
            else:
                print(f"{key}: {status}")

        # Insert sample data if requested
        if args.sample_data and not args.verify_only:
            insert_sample_data(db_ops)

        print("\n✅ Database initialization completed successfully!")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        print(f"\n❌ Database initialization failed: {e}")
        sys.exit(1)

    finally:
        if db_ops:
            db_ops.close()


if __name__ == "__main__":
    main()
