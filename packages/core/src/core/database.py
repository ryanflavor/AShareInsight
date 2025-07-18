"""
Database operations module for the AShareInsight project with halfvec support.

Provides database connectivity, CRUD operations, and vector search functionality
using psycopg3 with PostgreSQL and pgvector extension. Updated to use halfvec
type for 2560-dimensional vectors with HNSW indexing support.
"""

import json
from contextlib import contextmanager
from typing import Any
from uuid import UUID

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
        """Get company by stock code."""
        query = "SELECT * FROM companies WHERE company_code = %s"

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (company_code,))
                result = cur.fetchone()

        return Company(**result) if result else None

    def update_company(
        self,
        company_code: str,
        company_name_short: str | None = None,
        exchange: str | None = None,
    ) -> Company | None:
        """Update company information."""
        updates = []
        params = []

        if company_name_short is not None:
            updates.append("company_name_short = %s")
            params.append(company_name_short)

        if exchange is not None:
            updates.append("exchange = %s")
            params.append(exchange)

        if not updates:
            return self.get_company(company_code)

        params.append(company_code)
        query = f"""
            UPDATE companies
            SET {", ".join(updates)}
            WHERE company_code = %s
            RETURNING *
        """

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                result = cur.fetchone()
                conn.commit()

        return Company(**result) if result else None

    def list_companies(self, exchange: str | None = None) -> list[Company]:
        """List all companies, optionally filtered by exchange."""
        query = "SELECT * FROM companies"
        params = ()

        if exchange:
            query += " WHERE exchange = %s"
            params = (exchange,)

        query += " ORDER BY company_code"

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                results = cur.fetchall()

        return [Company(**row) for row in results]

    # Source document operations
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

        # Parse JSON field
        if result["raw_llm_output"] and isinstance(result["raw_llm_output"], str):
            result["raw_llm_output"] = json.loads(result["raw_llm_output"])

        return SourceDocument(**result)

    def get_source_document_by_id(self, doc_id: UUID) -> SourceDocument | None:
        """Get source document by UUID."""
        query = "SELECT * FROM source_documents WHERE doc_id = %s"

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(doc_id),))
                result = cur.fetchone()

        if not result:
            return None

        # Parse JSON field
        if result["raw_llm_output"] and isinstance(result["raw_llm_output"], str):
            result["raw_llm_output"] = json.loads(result["raw_llm_output"])

        return SourceDocument(**result)

    def list_documents_by_company(
        self, company_code: str, doc_type: str | None = None
    ) -> list[SourceDocument]:
        """List documents for a company, optionally filtered by type."""
        query = "SELECT * FROM source_documents WHERE company_code = %s"
        params = [company_code]

        if doc_type:
            query += " AND doc_type = %s"
            params.append(doc_type)

        query += " ORDER BY doc_date DESC"

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                results = cur.fetchall()

        documents = []
        for row in results:
            if row["raw_llm_output"] and isinstance(row["raw_llm_output"], str):
                row["raw_llm_output"] = json.loads(row["raw_llm_output"])
            documents.append(SourceDocument(**row))

        return documents

    # Business concept operations
    def create_business_concept(self, concept: BusinessConcept) -> BusinessConcept:
        """Create a new business concept."""
        query = """
            INSERT INTO business_concepts_master
            (concept_id, company_code, concept_name, embedding,
             concept_details, last_updated_from_doc_id, updated_at)
            VALUES (%s, %s, %s, %s::halfvec(2560), %s, %s, %s)
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
                        concept.embedding,  # Will be cast to halfvec
                        json.dumps(concept.concept_details)
                        if concept.concept_details
                        else None,
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

    def get_business_concept_by_id(self, concept_id: UUID) -> BusinessConcept | None:
        """Get business concept by UUID."""
        query = "SELECT * FROM business_concepts_master WHERE concept_id = %s"

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (str(concept_id),))
                result = cur.fetchone()

        if not result:
            return None

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

    def search_concepts_by_similarity(
        self,
        query_embedding: list[float],
        company_code: str | None = None,
        limit: int = 10,
        distance_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar business concepts using HNSW index on halfvec column.

        Now supports efficient search on 2560-dimensional vectors using the
        HNSW index created on the halfvec column.

        Args:
            query_embedding: 2560-dimensional query vector
            company_code: Optional filter by company code
            limit: Maximum number of results to return
            distance_threshold: Optional maximum distance threshold

        Returns:
            List of similar concepts with their distances
        """
        # Build base query with halfvec distance operator
        base_query = """
            SELECT
                concept_id,
                company_code,
                concept_name,
                concept_details,
                embedding <-> %s::halfvec(2560) AS distance
            FROM business_concepts_master
            WHERE 1=1
        """

        params = [query_embedding]

        # Add optional filters
        if company_code:
            base_query += " AND company_code = %s"
            params.append(company_code)

        if distance_threshold is not None:
            base_query += " AND embedding <-> %s::halfvec(2560) <= %s"
            params.extend([query_embedding, distance_threshold])

        # HNSW index will automatically be used for ORDER BY distance
        base_query += " ORDER BY embedding <-> %s::halfvec(2560) LIMIT %s"
        params.extend([query_embedding, limit])

        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(base_query, params)
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
        """Update concept embedding with halfvec type."""
        query = """
            UPDATE business_concepts_master
            SET embedding = %s::halfvec(2560),
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
            # Handle vector field
            if isinstance(row["embedding"], str):
                import ast

                row["embedding"] = ast.literal_eval(row["embedding"])
            else:
                row["embedding"] = list(row["embedding"])

            if row["concept_details"] and isinstance(row["concept_details"], str):
                row["concept_details"] = json.loads(row["concept_details"])

            concepts.append(BusinessConcept(**row))

        return concepts

    def check_halfvec_support(self) -> dict[str, Any]:
        """
        Check if halfvec type is supported and HNSW index is available.

        Returns:
            Dictionary with support status and version information
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                # Check pgvector version
                cur.execute(
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
                )
                version_result = cur.fetchone()

                # Check if halfvec type exists
                cur.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'halfvec')"
                )
                halfvec_result = cur.fetchone()

                # Check if HNSW index exists on our table
                cur.execute("""
                    SELECT indexname, indexdef 
                    FROM pg_indexes 
                    WHERE tablename = 'business_concepts_master' 
                    AND indexdef LIKE '%hnsw%'
                """)
                index_result = cur.fetchone()

        return {
            "pgvector_version": version_result["extversion"]
            if version_result
            else None,
            "halfvec_supported": halfvec_result["exists"] if halfvec_result else False,
            "hnsw_index": index_result if index_result else None,
            "max_dimensions": 4000
            if halfvec_result and halfvec_result["exists"]
            else 2000,
        }


# Legacy DatabaseConnection class for backward compatibility
class DatabaseConnection:
    """Legacy database connection class for backward compatibility."""

    def __init__(self, connection_string: str):
        """Initialize with automatic connection pool creation."""
        self.operations = DatabaseOperations(connection_string)
        self.pool = self.operations.pool

    def close(self):
        """Close the connection pool."""
        self.operations.close()
