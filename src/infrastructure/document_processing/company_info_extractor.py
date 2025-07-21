#!/usr/bin/env python3
"""Company information extraction utilities.

This module provides functions to extract company information from annual reports,
including company code, short name, full name, and year.
"""

import re
from pathlib import Path


class CompanyInfoExtractor:
    """Extract company information from document content."""

    def extract_info(
        self, file_path: Path, content: str = None
    ) -> dict[str, str | None]:
        """Extract all company information from a file.

        Args:
            file_path: Path to the document file
            content: Optional pre-loaded content (to avoid reading file twice)

        Returns:
            Dictionary with keys: code, short_name, full_name, year
        """
        if content is None:
            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                return {
                    "code": None,
                    "short_name": None,
                    "full_name": None,
                    "year": None,
                }

        # Extract each piece of information
        info = {
            "code": self.extract_code(content),
            "short_name": self.extract_short_name(content),
            "full_name": self.extract_full_name(content),
            "year": self.extract_year(file_path, content),
        }

        return info

    def extract_code(self, content: str) -> str | None:
        """Extract company stock code from content."""
        # Patterns to match various formats
        patterns = [
            # Format: 证券代码:300690 or 公司代码:688448
            r"(?:证券代码|股票代码|公司代码)[：:]\s*(\d{6})",
            # Format in tables: 股票代码 | 300691
            r"股票代码[^\d]*\|\s*(\d{6})",
            # Any context with "代码" followed by 6 digits
            r"代码[：:\s]*[|｜]?\s*(\d{6})",
            # Fallback: any standalone 6-digit number in first 1000 chars
            r"\b(\d{6})\b",
        ]

        # Search in first 5000 characters for efficiency
        search_content = content[:5000]

        for pattern in patterns:
            match = re.search(pattern, search_content)
            if match:
                code = match.group(1)
                # Validate it's a valid stock code (000000-999999)
                if code.isdigit() and 0 < int(code) <= 999999:
                    return code

        return None

    def extract_short_name(self, content: str) -> str | None:
        """Extract company short name from content."""
        patterns = [
            # Format: 证券简称:双一科技 or 公司简称:磁谷科技
            r"(?:证券简称|股票简称|公司简称)[：:]\s*([^\s,，、]+)",
            # Format in tables with possible HTML/markdown
            r"股票简称[^\|]*\|\s*([^<\|]+?)(?:<|$|\|)",
            # Clean any markdown formatting
            r"简称[：:]\s*([^\s]+)",
        ]

        search_content = content[:5000]

        for pattern in patterns:
            match = re.search(pattern, search_content)
            if match:
                name = match.group(1).strip()
                # Clean up any HTML/markdown tags
                name = re.sub(r"<[^>]+>", "", name)
                name = re.sub(r"\*+", "", name)
                if name and len(name) > 1:
                    return name

        return None

    def extract_full_name(self, content: str) -> str | None:
        """Extract company full name from content."""
        # Try multiple strategies

        # Strategy 1: Look for company name in headers/titles
        header_patterns = [
            # Markdown headers with company name
            r"^#\s*(.+?(?:股份有限公司|有限公司|股份公司|集团公司))\s*$",
            # Company name followed by year and report type
            r"^#\s*(.+?(?:股份有限公司|有限公司|股份公司|集团公司))\s*\*?\*?20\d{2}",
            # Title format
            r"(.+?(?:股份有限公司|有限公司|股份公司|集团公司))\s*20\d{2}\s*年年度报告",
        ]

        for pattern in header_patterns:
            match = re.search(pattern, content[:2000], re.MULTILINE)
            if match:
                name = match.group(1).strip()
                if self._validate_company_name(name):
                    return name

        # Strategy 2: Look for explicit company name fields
        field_patterns = [
            r"公司名称[：:]\s*([^\n\|]+)",
            r"全称[：:]\s*([^\n\|]+?(?:公司))",
        ]

        for pattern in field_patterns:
            match = re.search(pattern, content[:5000])
            if match:
                name = match.group(1).strip()
                if self._validate_company_name(name):
                    return name

        # Strategy 3: Try to construct from short name
        short_name = self.extract_short_name(content)
        if short_name:
            # Look for full company name containing the short name
            pattern = rf"({re.escape(short_name)}[^。\n]*?(?:股份有限公司|有限公司|股份公司|集团公司))"
            match = re.search(pattern, content[:10000])
            if match:
                name = match.group(1).strip()
                if self._validate_company_name(name):
                    return name

        return None

    def extract_year(self, file_path: Path, content: str) -> int | None:
        """Extract report year from filename or content."""
        # Priority 1: Extract from filename
        filename_year = re.search(r"(20\d{2})", file_path.stem)
        if filename_year:
            year = int(filename_year.group(1))
            if 2020 <= year <= 2030:  # Reasonable year range
                return year

        # Priority 2: Extract from content headers
        year_patterns = [
            r"(20\d{2})\s*年年度报告",
            r"(20\d{2})\s*年度报告",
            r"(20\d{2})\s*年年报",
        ]

        for pattern in year_patterns:
            match = re.search(pattern, content[:2000])
            if match:
                year = int(match.group(1))
                if 2020 <= year <= 2030:
                    return year

        return None

    def _validate_company_name(self, name: str) -> bool:
        """Validate if a string is a valid company name."""
        if not name:
            return False

        # Must contain "公司" or similar
        company_suffixes = ["公司", "集团", "企业"]
        if not any(suffix in name for suffix in company_suffixes):
            return False

        # Reasonable length
        if len(name) < 4 or len(name) > 50:
            return False

        # Should not contain certain invalid patterns
        invalid_patterns = ["报告", "摘要", "年度", "年报", "\n", "\r", "|"]
        if any(pattern in name for pattern in invalid_patterns):
            return False

        return True


def extract_company_info_from_path(file_path: Path) -> tuple[str | None, int | None]:
    """Quick extraction of company code and year from file path.

    This is a simplified version for use in incremental extraction.

    Args:
        file_path: Path to the document

    Returns:
        Tuple of (company_code, year) or (None, None) if not found
    """
    extractor = CompanyInfoExtractor()

    # Try to extract from filename first
    filename = file_path.stem

    # Extract company code (6 digits)
    code_match = re.search(r"(\d{6})", filename)
    company_code = code_match.group(1) if code_match else None

    # Extract year
    year_match = re.search(r"(20\d{2})", filename)
    year = int(year_match.group(1)) if year_match else None

    # If not found in filename, read file content
    if not company_code or not year:
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read(5000)  # Read first 5KB

            info = extractor.extract_info(file_path, content)
            if not company_code:
                company_code = info["code"]
            if not year:
                year = info["year"]
        except Exception:
            pass

    return company_code, year
