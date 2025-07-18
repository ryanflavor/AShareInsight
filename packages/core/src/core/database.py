"""
Database operations module for the AShareInsight project.

Provides database connectivity, CRUD operations, and vector search functionality
using psycopg3 with PostgreSQL and pgvector extension.
"""

import json
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .logging_config import get_logger
from .models import BusinessConcept, Company, SourceDocument

logger = get_logger(__name__)


class DatabaseOperations:
    """Database operations handler for AShareInsight project."""

    def __init__(self, connection_string: str):
        """
        Initialize database operations.

        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string
        self.pool: ConnectionPool | None = None
        self._create_connection_pool()

    def _create_connection_pool(self, min_size: int = 2, max_size: int = 10) -> None:
        """Create connection pool using psycopg3."""
        try:
            self.pool = ConnectionPool(
                self.connection_string,
                min_size=min_size,
                max_size=max_size,
                kwargs={"row_factory": dict_row},  # Return results as dictionaries
            )
            logger.info(
                f"Connection pool created with min_size={min_size}, max_size={max_size}"
            )
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise

    def close(self) -> None:
        """Close connection pool."""
        if self.pool:
            self.pool.close()
            logger.info("Connection pool closed")

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        with self.pool.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def execute_query(self, query: str, params: tuple | None = None) -> None:
        """Execute a query without returning results."""
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                conn.commit()

    # Company operations
    def create_company(self, company: Company) -> Company:
        """Create a new company in the database."""
        query = """
            INSERT INTO companies
            (company_code, company_name_full, company_name_short, exchange,
             created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
        """

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        company.company_code,
                        company.company_name_full,
                        company.company_name_short,
                        company.exchange,
                        company.created_at,
                        company.updated_at,
                    ),
                )
                result = cur.fetchone()
                conn.commit()

        return Company(**result)

    def get_company_by_code(self, company_code: str) -> Company | None:
        """Get company by company code."""
        query = "SELECT * FROM companies WHERE company_code = %s"

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (company_code,))
                result = cur.fetchone()

        return Company(**result) if result else None

    def update_company(self, company_code: str, updates: dict[str, Any]) -> Company:
        """Update company information."""
        # Build dynamic update query
        set_clauses = []
        params = []

        for key, value in updates.items():
            set_clauses.append(f"{key} = %s")
            params.append(value)

        params.append(company_code)

        query = f"""
            UPDATE companies
            SET {", ".join(set_clauses)}
            WHERE company_code = %s
            RETURNING *
        """

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                result = cur.fetchone()
                conn.commit()

        return Company(**result)

    def list_companies(self) -> list[Company]:
        """List all companies."""
        query = "SELECT * FROM companies ORDER BY company_code"

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                results = cur.fetchall()

        return [Company(**row) for row in results]

    def delete_company(self, company_code: str) -> None:
        """Delete a company (cascades to related records)."""
        query = "DELETE FROM companies WHERE company_code = %s"

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (company_code,))
                conn.commit()

    # Source Document operations
    def create_source_document(self, document: SourceDocument) -> SourceDocument:
        """Create a new source document."""
        query = """
            INSERT INTO source_documents
            (doc_id, company_code, doc_type, doc_date, report_title,
             raw_llm_output, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        str(document.doc_id),
                        document.company_code,
                        document.doc_type,
                        document.doc_date,
                        document.report_title,
                        json.dumps(document.raw_llm_output),
                        document.created_at,
                    ),
                )
                result = cur.fetchone()
                conn.commit()

        # Parse JSON fields (UUID fields are already UUID objects with dict_row)
        if isinstance(result["raw_llm_output"], str):
            result["raw_llm_output"] = json.loads(result["raw_llm_output"])
        return SourceDocument(**result)

    def get_document_by_id(self, doc_id: UUID) -> SourceDocument | None:
        """Get document by ID."""
        query = "SELECT * FROM source_documents WHERE doc_id = %s"

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(doc_id),))
                result = cur.fetchone()

        if result:
            # UUID fields are already UUID objects with dict_row
            if isinstance(result["raw_llm_output"], str):
                result["raw_llm_output"] = json.loads(result["raw_llm_output"])
            return SourceDocument(**result)
        return None

    def list_documents_by_company(self, company_code: str) -> list[SourceDocument]:
        """List all documents for a company."""
        query = """
            SELECT * FROM source_documents
            WHERE company_code = %s
            ORDER BY doc_date DESC
        """

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (company_code,))
                results = cur.fetchall()

        documents = []
        for row in results:
            # UUID fields are already UUID objects with dict_row
            if isinstance(row["raw_llm_output"], str):
                row["raw_llm_output"] = json.loads(row["raw_llm_output"])
            documents.append(SourceDocument(**row))

        return documents

    def query_documents_by_jsonb(
        self, json_filter: dict[str, Any]
    ) -> list[SourceDocument]:
        """Query documents by JSONB content."""
        # Build JSONB containment query
        query = """
            SELECT * FROM source_documents
            WHERE raw_llm_output @> %s
            ORDER BY created_at DESC
        """

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (json.dumps(json_filter),))
                results = cur.fetchall()

        documents = []
        for row in results:
            # UUID fields are already UUID objects with dict_row
            if isinstance(row["raw_llm_output"], str):
                row["raw_llm_output"] = json.loads(row["raw_llm_output"])
            documents.append(SourceDocument(**row))

        return documents

    def delete_document(self, doc_id: UUID) -> None:
        """Delete a document."""
        query = "DELETE FROM source_documents WHERE doc_id = %s"

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(doc_id),))
                conn.commit()

    # Business Concept operations
    def create_business_concept(self, concept: BusinessConcept) -> BusinessConcept:
        """Create a new business concept."""
        query = """
            INSERT INTO business_concepts_master
            (concept_id, company_code, concept_name, embedding, concept_details,
             last_updated_from_doc_id, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        str(concept.concept_id),
                        concept.company_code,
                        concept.concept_name,
                        concept.embedding,  # psycopg3 handles list->vector conversion
                        (
                            json.dumps(concept.concept_details)
                            if concept.concept_details
                            else None
                        ),
                        str(concept.last_updated_from_doc_id),
                        concept.updated_at,
                    ),
                )
                result = cur.fetchone()
                conn.commit()

        # Parse fields (UUID fields are already UUID objects with dict_row)
        # Handle vector field - it might be a string or already parsed
        if isinstance(result["embedding"], str):
            # Parse the vector string format "[0.1, 0.2, ...]"
            import ast

            result["embedding"] = ast.literal_eval(result["embedding"])
        else:
            result["embedding"] = list(result["embedding"])  # Convert vector to list

        if result["concept_details"] and isinstance(result["concept_details"], str):
            result["concept_details"] = json.loads(result["concept_details"])

        return BusinessConcept(**result)

    def search_similar_concepts(
        self,
        query_embedding: list[float],
        company_code: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for similar concepts using vector similarity."""
        base_query = """
            SELECT
                concept_id,
                company_code,
                concept_name,
                concept_details,
                embedding <=> %s::vector AS distance
            FROM business_concepts_master
        """

        if company_code:
            base_query += " WHERE company_code = %s"

        base_query += " ORDER BY embedding <=> %s::vector LIMIT %s"

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                if company_code:
                    cur.execute(
                        base_query,
                        (query_embedding, company_code, query_embedding, limit),
                    )
                else:
                    cur.execute(base_query, (query_embedding, query_embedding, limit))

                results = cur.fetchall()

        # Format results
        formatted_results = []
        for row in results:
            row["concept_id"] = str(row["concept_id"])
            if row["concept_details"] and isinstance(row["concept_details"], str):
                row["concept_details"] = json.loads(row["concept_details"])
            formatted_results.append(row)

        return formatted_results

    def update_concept_embedding(
        self,
        concept_id: UUID,
        new_embedding: list[float],
        last_updated_from_doc_id: UUID,
    ) -> BusinessConcept:
        """Update concept embedding."""
        query = """
            UPDATE business_concepts_master
            SET embedding = %s,
                last_updated_from_doc_id = %s
            WHERE concept_id = %s
            RETURNING *
        """

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (new_embedding, str(last_updated_from_doc_id), str(concept_id)),
                )
                result = cur.fetchone()
                conn.commit()

        # Parse fields (UUID fields are already UUID objects with dict_row)
        # Handle vector field - it might be a string or already parsed
        if isinstance(result["embedding"], str):
            # Parse the vector string format "[0.1, 0.2, ...]"
            import ast

            result["embedding"] = ast.literal_eval(result["embedding"])
        else:
            result["embedding"] = list(result["embedding"])  # Convert vector to list

        if result["concept_details"] and isinstance(result["concept_details"], str):
            result["concept_details"] = json.loads(result["concept_details"])

        return BusinessConcept(**result)

    def list_concepts_by_company(self, company_code: str) -> list[BusinessConcept]:
        """List all concepts for a company."""
        query = """
            SELECT * FROM business_concepts_master
            WHERE company_code = %s
            ORDER BY concept_name
        """

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (company_code,))
                results = cur.fetchall()

        concepts = []
        for row in results:
            # UUID fields are already UUID objects with dict_row
            # Handle vector field - it might be a string or already parsed
            if isinstance(row["embedding"], str):
                # Parse the vector string format "[0.1, 0.2, ...]"
                import ast

                row["embedding"] = ast.literal_eval(row["embedding"])
            else:
                row["embedding"] = list(row["embedding"])  # Convert vector to list

            if row["concept_details"] and isinstance(row["concept_details"], str):
                row["concept_details"] = json.loads(row["concept_details"])
            concepts.append(BusinessConcept(**row))

        return concepts


# Legacy DatabaseConnection class for backward compatibility
class DatabaseConnection(DatabaseOperations):
    """Legacy database connection class for backward compatibility."""

    def create_connection_pool(self, min_size: int = 2, max_size: int = 10) -> None:
        """Create connection pool (for backward compatibility)."""
        # Already created in __init__, just log
        logger.info("Connection pool already created")

    def test_basic_connectivity(self) -> dict[str, Any]:
        """Test basic database connectivity."""
        try:
            with psycopg.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    # Test basic query
                    cur.execute("SELECT version();")
                    version = cur.fetchone()[0]

                    # Test pgvector extension
                    cur.execute(
                        "SELECT extname, extversion FROM pg_extension "
                        "WHERE extname = 'vector';"
                    )
                    vector_ext = cur.fetchone()

                    # Test database info
                    cur.execute("SELECT current_database(), current_user;")
                    db_info = cur.fetchone()

                    return {
                        "status": "success",
                        "postgresql_version": version,
                        "vector_extension": {
                            "name": vector_ext[0] if vector_ext else None,
                            "version": vector_ext[1] if vector_ext else None,
                        },
                        "database": db_info[0],
                        "user": db_info[1],
                    }
        except Exception as e:
            logger.error(f"Connectivity test failed: {e}")
            return {"status": "failed", "error": str(e)}

    def test_connection_pool(self) -> dict[str, Any]:
        """Test connection pooling functionality."""
        if not self.pool:
            return {"status": "failed", "error": "Connection pool not initialized"}

        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 'Connection pool test successful' as result;")
                    result = cur.fetchone()[0]

                    return {
                        "status": "success",
                        "message": result,
                        "pool_stats": {
                            "min_size": self.pool.min_size,
                            "max_size": self.pool.max_size,
                        },
                    }
        except Exception as e:
            logger.error(f"Connection pool test failed: {e}")
            return {"status": "failed", "error": str(e)}

    def close_pool(self) -> None:
        """Close connection pool (for backward compatibility)."""
        self.close()
