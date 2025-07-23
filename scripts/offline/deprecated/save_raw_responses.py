#!/usr/bin/env python3
"""
Enhanced batch extraction script that saves raw LLM responses.
This allows reprocessing without re-calling the expensive LLM API.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from structlog import get_logger

from src.infrastructure.llm.langchain.parsers.base import MarkdownExtractor

logger = get_logger(__name__)


class RawResponseManager:
    """Manages saving and loading of raw LLM responses."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.raw_responses_dir = data_dir / "raw_responses"
        self.raw_responses_dir.mkdir(exist_ok=True)

        # Create subdirectories for different document types
        (self.raw_responses_dir / "annual_reports").mkdir(exist_ok=True)
        (self.raw_responses_dir / "research_reports").mkdir(exist_ok=True)

    def save_raw_response(
        self, doc_path: Path, doc_type: str, raw_response: str, metadata: dict = None
    ) -> Path:
        """Save raw LLM response to file.

        Args:
            doc_path: Original document path
            doc_type: Document type (annual_reports or research_reports)
            raw_response: Raw LLM response text
            metadata: Additional metadata to save

        Returns:
            Path to saved raw response file
        """
        # Generate filename based on original document
        response_filename = f"{doc_path.stem}_raw_response.json"
        response_path = self.raw_responses_dir / doc_type / response_filename

        # Prepare data to save
        data = {
            "original_document": str(doc_path),
            "document_type": doc_type,
            "raw_response": raw_response,
            "saved_at": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        # Save to file
        with open(response_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(
            "Saved raw LLM response",
            response_path=str(response_path),
            response_size=len(raw_response),
        )

        return response_path

    def load_raw_response(self, doc_path: Path, doc_type: str) -> dict | None:
        """Load previously saved raw response.

        Args:
            doc_path: Original document path
            doc_type: Document type

        Returns:
            Saved response data or None if not found
        """
        response_filename = f"{doc_path.stem}_raw_response.json"
        response_path = self.raw_responses_dir / doc_type / response_filename

        if not response_path.exists():
            return None

        with open(response_path, encoding="utf-8") as f:
            return json.load(f)

    def reprocess_raw_response(self, raw_response_path: Path) -> dict:
        """Reprocess a saved raw response without calling LLM again.

        Args:
            raw_response_path: Path to saved raw response file

        Returns:
            Parsed extraction data
        """
        # Load saved response
        with open(raw_response_path, encoding="utf-8") as f:
            data = json.load(f)

        raw_response = data["raw_response"]
        doc_type = data["document_type"]

        # Extract JSON using the improved extraction logic
        extractor = MarkdownExtractor()
        json_str = extractor.extract_json_from_text(raw_response)

        # Parse JSON
        parsed_data = json.loads(json_str)

        logger.info(
            "Reprocessed raw response successfully",
            doc_type=doc_type,
            num_fields=len(parsed_data.keys()),
        )

        return parsed_data


def main():
    """Example usage of RawResponseManager."""
    import click

    @click.command()
    @click.option(
        "--data-dir",
        type=click.Path(exists=True, path_type=Path),
        default=Path("data"),
        help="Data directory path",
    )
    @click.option(
        "--reprocess",
        type=click.Path(exists=True, path_type=Path),
        help="Reprocess a specific raw response file",
    )
    def cli(data_dir: Path, reprocess: Path | None):
        """Raw response management utility."""
        manager = RawResponseManager(data_dir)

        if reprocess:
            # Reprocess existing raw response
            try:
                result = manager.reprocess_raw_response(reprocess)
                print(f"Successfully reprocessed: {reprocess}")
                print(f"Extracted fields: {list(result.keys())}")
            except Exception as e:
                print(f"Error reprocessing: {e}")
        else:
            # Show available raw responses
            print("Available raw responses:")
            for doc_type in ["annual_reports", "research_reports"]:
                responses_dir = manager.raw_responses_dir / doc_type
                if responses_dir.exists():
                    files = list(responses_dir.glob("*_raw_response.json"))
                    print(f"\n{doc_type}: {len(files)} files")
                    for f in files[:5]:  # Show first 5
                        print(f"  - {f.name}")
                    if len(files) > 5:
                        print(f"  ... and {len(files) - 5} more")

    cli()


if __name__ == "__main__":
    main()
