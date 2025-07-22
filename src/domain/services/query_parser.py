"""Query company parsing service.

This module provides services for extracting actual company information
from query identifiers and search results.
"""

import re
from typing import NamedTuple

from src.domain.services.company_aggregator import AggregatedCompany
from src.domain.value_objects import Document


class ParsedQueryCompany(NamedTuple):
    """Parsed query company information.

    Attributes:
        name: Company name (actual or query identifier)
        code: Company code if detected, None otherwise
    """

    name: str
    code: str | None


class QueryCompanyParser:
    """Service for parsing and resolving query company information.

    This service extracts actual company information from search results
    and handles various query identifier formats.
    """

    def parse_query_identifier(self, query_identifier: str) -> ParsedQueryCompany:
        """Parse a query identifier to extract potential company code.

        Attempts to detect if the query identifier is a stock code
        based on common patterns (e.g., 6 digits, alphanumeric codes).

        Args:
            query_identifier: The original query string

        Returns:
            ParsedQueryCompany with detected information
        """
        # Trim whitespace
        query_identifier = query_identifier.strip()

        # Check if it looks like a stock code (common patterns)
        # A-share: 6 digits starting with 000, 001, 002, 003, 300, 600, 601, 603, 688
        # HK: 5 digits or less
        # US: 1-5 letters

        # Check for A-share pattern
        if re.match(r"^[0369]\d{5}$", query_identifier):
            return ParsedQueryCompany(name=query_identifier, code=query_identifier)

        # Check for HK stock pattern (1-5 digits, sometimes with leading zeros)
        if re.match(r"^\d{1,5}$", query_identifier):
            return ParsedQueryCompany(name=query_identifier, code=query_identifier)

        # Check for US stock pattern (1-5 uppercase letters)
        if re.match(r"^[A-Z]{1,5}$", query_identifier.upper()):
            return ParsedQueryCompany(
                name=query_identifier, code=query_identifier.upper()
            )

        # Otherwise, treat as company name
        return ParsedQueryCompany(name=query_identifier, code=None)

    def resolve_from_results(
        self,
        query_identifier: str,
        aggregated_companies: list[AggregatedCompany],
    ) -> ParsedQueryCompany:
        """Resolve actual company information from search results.

        Attempts to find the actual company that was queried by looking
        at the first matched document. Falls back to parsing the identifier
        if no matches found.

        Args:
            query_identifier: The original query string
            aggregated_companies: Search results

        Returns:
            ParsedQueryCompany with resolved information
        """
        # If no results, fall back to parsing
        if not aggregated_companies:
            return self.parse_query_identifier(query_identifier)

        # Look for exact match in results (case-insensitive)
        query_lower = query_identifier.lower().strip()

        for company in aggregated_companies:
            # Check if query matches company code
            if company.company_code.lower() == query_lower:
                return ParsedQueryCompany(
                    name=company.company_name, code=company.company_code
                )

            # Check if query matches company name (exact or substring)
            if query_lower in company.company_name.lower():
                return ParsedQueryCompany(
                    name=company.company_name, code=company.company_code
                )

        # If first result has very high score (>0.95) AND seems related,
        # assume it's the query company. Only for short queries (partial match)
        if (
            aggregated_companies[0].relevance_score > 0.95
            and len(query_identifier) <= 3
        ):
            first_company = aggregated_companies[0]
            return ParsedQueryCompany(
                name=first_company.company_name, code=first_company.company_code
            )

        # Otherwise, use parsed identifier with name from first result if available
        parsed = self.parse_query_identifier(query_identifier)
        if aggregated_companies and parsed.code == aggregated_companies[0].company_code:
            return ParsedQueryCompany(
                name=aggregated_companies[0].company_name, code=parsed.code
            )

        return parsed

    def resolve_from_documents(
        self, query_identifier: str, documents: list[Document]
    ) -> ParsedQueryCompany:
        """Resolve company information from raw documents.

        This is an alternative method that works with Document objects
        before aggregation.

        Args:
            query_identifier: The original query string
            documents: List of Document objects

        Returns:
            ParsedQueryCompany with resolved information
        """
        # If no documents, fall back to parsing
        if not documents:
            return self.parse_query_identifier(query_identifier)

        query_lower = query_identifier.lower().strip()

        # Look for exact match in documents
        for doc in documents:
            if doc.company_code.lower() == query_lower:
                return ParsedQueryCompany(name=doc.company_name, code=doc.company_code)

            if query_lower in doc.company_name.lower():
                return ParsedQueryCompany(name=doc.company_name, code=doc.company_code)

        # Check if first document has very high similarity (likely the query company)
        if documents[0].similarity_score > 0.95:
            return ParsedQueryCompany(
                name=documents[0].company_name, code=documents[0].company_code
            )

        # Fall back to parsing
        return self.parse_query_identifier(query_identifier)
