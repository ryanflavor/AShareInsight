#!/usr/bin/env python3
"""
Database setup and verification script for AShareInsight project.

This script:
1. Creates the database if it doesn't exist
2. Runs the initialization SQL script
3. Verifies all tables and operations work correctly
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.errors import DuplicateDatabase

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.core.src.core.database import DatabaseOperations
from packages.core.src.core.logging_config import setup_logging
from packages.core.src.core.models import BusinessConcept, Company, SourceDocument


def create_database_if_not_exists(connection_params: dict, db_name: str) -> None:
    """Create database if it doesn't exist."""
    # Connect to default postgres database to create our database
    admin_params = connection_params.copy()
    admin_params["dbname"] = "postgres"

    try:
        with psycopg.connect(**admin_params) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                try:
                    cur.execute(f"CREATE DATABASE {db_name}")
                    print(f"✅ Created database: {db_name}")
                except DuplicateDatabase:
                    print(f"ℹ️  Database '{db_name}' already exists")
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        raise


def run_init_sql(connection_string: str, sql_file: Path) -> None:
    """Run the initialization SQL script."""
    print(f"\n📄 Running initialization script: {sql_file}")

    try:
        with psycopg.connect(connection_string) as conn:
            with conn.cursor() as cur:
                # Read and execute SQL file
                sql_content = sql_file.read_text()
                cur.execute(sql_content)
                conn.commit()
                print("✅ Database schema initialized successfully")
    except Exception as e:
        print(f"❌ Error running init SQL: {e}")
        raise


def verify_database_setup(db_ops: DatabaseOperations) -> None:
    """Verify database setup with comprehensive tests."""
    print("\n🔍 Verifying database setup...")

    try:
        # Test 1: Create a company
        print("\n1️⃣ Testing company operations...")
        company = Company(
            company_code="TEST001",
            company_name_full="测试公司股份有限公司",
            company_name_short="测试公司",
            exchange="测试交易所",
        )
        created_company = db_ops.create_company(company)
        print(f"   ✅ Created company: {created_company.company_code}")

        # Test 2: Retrieve company
        retrieved = db_ops.get_company_by_code("TEST001")
        assert retrieved is not None
        assert retrieved.company_name_full == company.company_name_full
        print("   ✅ Retrieved company successfully")

        # Test 3: Create source document
        print("\n2️⃣ Testing source document operations...")
        doc = SourceDocument(
            company_code="TEST001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="2023年度测试报告",
            raw_llm_output={
                "concepts": ["零售业务", "批发业务"],
                "metrics": {"revenue": 1000000, "profit": 100000},
            },
        )
        created_doc = db_ops.create_source_document(doc)
        print(f"   ✅ Created document: {created_doc.doc_id}")

        # Test 4: Create business concept with vector
        print("\n3️⃣ Testing business concept operations...")
        concept = BusinessConcept(
            company_code="TEST001",
            concept_name="零售业务",
            embedding=[0.1] * 2560,  # Test embedding
            concept_details={"description": "公司主要零售业务", "category": "主营业务"},
            last_updated_from_doc_id=created_doc.doc_id,
        )
        created_concept = db_ops.create_business_concept(concept)
        print(f"   ✅ Created concept: {created_concept.concept_name}")

        # Test 5: Vector similarity search
        print("\n4️⃣ Testing vector similarity search...")
        query_embedding = [0.11] * 2560  # Slightly different embedding
        results = db_ops.search_similar_concepts(
            query_embedding, company_code="TEST001", limit=5
        )
        assert len(results) > 0
        assert results[0]["concept_name"] == "零售业务"
        print(f"   ✅ Vector search found {len(results)} similar concepts")
        print(
            f"   📊 Top result: {results[0]['concept_name']} (distance: {results[0]['distance']:.4f})"
        )

        # Test 6: JSONB query
        print("\n5️⃣ Testing JSONB queries...")
        docs = db_ops.query_documents_by_jsonb({"concepts": ["零售业务"]})
        assert len(docs) == 1
        print(f"   ✅ JSONB query found {len(docs)} documents")

        # Test 7: Foreign key constraints
        print("\n6️⃣ Testing foreign key constraints...")
        try:
            # Try to create document with non-existent company
            bad_doc = SourceDocument(
                company_code="INVALID",
                doc_type="annual_report",
                doc_date=datetime.now().date(),
                report_title="Invalid",
                raw_llm_output={},
            )
            db_ops.create_source_document(bad_doc)
            print("   ❌ Foreign key constraint not working!")
        except Exception:
            print("   ✅ Foreign key constraints working correctly")

        # Test 8: Cascade delete
        print("\n7️⃣ Testing cascade delete...")
        initial_docs = len(db_ops.list_documents_by_company("TEST001"))
        initial_concepts = len(db_ops.list_concepts_by_company("TEST001"))

        db_ops.delete_company("TEST001")

        final_docs = len(db_ops.list_documents_by_company("TEST001"))
        final_concepts = len(db_ops.list_concepts_by_company("TEST001"))

        assert final_docs == 0
        assert final_concepts == 0
        print(
            f"   ✅ Cascade delete removed {initial_docs} documents and {initial_concepts} concepts"
        )

        # Test 9: Transaction rollback
        print("\n8️⃣ Testing transaction rollback...")
        # Create a company for transaction test
        test_company = Company(
            company_code="TRANS001", company_name_full="Transaction Test Company"
        )
        db_ops.create_company(test_company)

        try:
            with db_ops.transaction() as conn:
                with conn.cursor() as cur:
                    # This should succeed
                    cur.execute(
                        "INSERT INTO source_documents (company_code, doc_type, doc_date, report_title, raw_llm_output) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (
                            "TRANS001",
                            "annual_report",
                            datetime.now().date(),
                            "Test",
                            "{}",
                        ),
                    )
                    # This should fail (invalid company)
                    cur.execute(
                        "INSERT INTO source_documents (company_code, doc_type, doc_date, report_title, raw_llm_output) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (
                            "INVALID",
                            "annual_report",
                            datetime.now().date(),
                            "Test",
                            "{}",
                        ),
                    )
        except Exception:
            pass

        # Verify no documents were created
        trans_docs = db_ops.list_documents_by_company("TRANS001")
        assert len(trans_docs) == 0
        print("   ✅ Transaction rollback working correctly")

        # Cleanup
        db_ops.delete_company("TRANS001")

        print("\n✅ All database verification tests passed!")

    except Exception as e:
        import traceback

        print(f"\n❌ Verification failed: {e}")
        print("Traceback:")
        traceback.print_exc()
        raise


def verify_postgresql_version(db_ops: DatabaseOperations) -> None:
    """Verify PostgreSQL and pgvector versions."""
    print("\n📊 Database version information:")

    with psycopg.connect(db_ops.connection_string) as conn:
        with conn.cursor() as cur:
            # PostgreSQL version
            cur.execute("SELECT version();")
            pg_version = cur.fetchone()[0]
            print(f"   PostgreSQL: {pg_version.split(',')[0]}")

            # pgvector version
            cur.execute(
                "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
            )
            vector_ext = cur.fetchone()
            if vector_ext:
                print(f"   pgvector: {vector_ext[1]}")
            else:
                print("   ❌ pgvector extension not found!")

            # List tables
            cur.execute("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public' 
                AND tablename IN ('companies', 'source_documents', 'business_concepts_master')
                ORDER BY tablename
            """)
            tables = [row[0] for row in cur.fetchall()]
            print(f"   Tables created: {', '.join(tables)}")

            # Note: HNSW index not created due to pgvector 2000-dimension limit
            print(
                "   ℹ️  HNSW index: Not created (pgvector limit: max 2000 dims, we use 2560)"
            )
            print("   ℹ️  Using exact nearest neighbor search without index")


def main():
    """Main function to set up and verify database."""
    setup_logging(level="INFO")

    print("🚀 AShareInsight Database Setup")
    print("=" * 50)

    # Get database configuration from environment or use defaults
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_user = os.getenv("POSTGRES_USER", "postgres")
    db_password = os.getenv("POSTGRES_PASSWORD", "test123")
    db_name = os.getenv("POSTGRES_DB", "ashareinsight")

    # Connection parameters
    connection_params = {
        "host": db_host,
        "port": db_port,
        "user": db_user,
        "password": db_password,
    }

    # Create database if needed
    create_database_if_not_exists(connection_params, db_name)

    # Full connection string
    connection_string = (
        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )

    # Run initialization SQL
    sql_file = Path(__file__).parent.parent / "init-db.sql"
    if sql_file.exists():
        run_init_sql(connection_string, sql_file)
    else:
        print(f"❌ SQL file not found: {sql_file}")
        return 1

    # Initialize database operations
    db_ops = DatabaseOperations(connection_string)

    try:
        # Verify PostgreSQL version and extensions
        verify_postgresql_version(db_ops)

        # Run comprehensive verification tests
        verify_database_setup(db_ops)

        print("\n✅ Database setup completed successfully!")
        print(
            f"📍 Connection string: postgresql://{db_user}:****@{db_host}:{db_port}/{db_name}"
        )

        return 0

    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        return 1

    finally:
        db_ops.close()


if __name__ == "__main__":
    sys.exit(main())
