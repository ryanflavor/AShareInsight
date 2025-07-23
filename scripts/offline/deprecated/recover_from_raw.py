#!/usr/bin/env python3
"""
Recover from Raw Responses Script

This script processes raw LLM responses that were saved but failed parsing,
allowing recovery without re-calling the expensive LLM API.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import click
import structlog
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.infrastructure.llm.langchain.parsers import (
    AnnualReportParser,
    ResearchReportParser,
)
from src.infrastructure.llm.langchain.parsers.base import MarkdownExtractor

logger = structlog.get_logger()
console = Console()


class RawResponseRecovery:
    """Recover data from saved raw LLM responses."""

    def __init__(self):
        self.annual_report_parser = AnnualReportParser()
        self.research_report_parser = ResearchReportParser()
        self.markdown_extractor = MarkdownExtractor()

        self.stats = {
            "total_raw_files": 0,
            "already_extracted": 0,
            "successfully_recovered": 0,
            "failed_recovery": 0,
        }

    def find_raw_responses_without_extraction(self):
        """Find raw response files that don't have corresponding extracted JSON."""
        raw_responses_dir = Path("data/raw_responses")
        missing_extractions = []

        # Check annual reports
        annual_raw_dir = raw_responses_dir / "annual_reports"
        if annual_raw_dir.exists():
            for raw_file in annual_raw_dir.glob("*.json"):
                # Try to find matching extracted file
                # Extract company name from filename
                if "_raw_response.json" in raw_file.name:
                    # New format: {company}_{timestamp}_raw_response.json
                    parts = raw_file.name.replace("_raw_response.json", "").rsplit(
                        "_", 1
                    )
                    if len(parts) >= 2:
                        company_part = parts[0]
                        # Check if extracted file exists
                        extracted_pattern = f"*{company_part}*_extracted.json"
                    else:
                        extracted_pattern = "*_extracted.json"
                else:
                    # Old format: raw_response_{timestamp}.json
                    extracted_pattern = "*_extracted.json"

                extracted_dir = Path("data/extracted/annual_reports")
                matching_extracted = list(extracted_dir.glob(extracted_pattern))

                if not matching_extracted:
                    missing_extractions.append(
                        {
                            "raw_file": raw_file,
                            "doc_type": "annual_report",
                        }
                    )

        # Check research reports
        research_raw_dir = raw_responses_dir / "research_reports"
        if research_raw_dir.exists():
            for raw_file in research_raw_dir.glob("*.json"):
                extracted_dir = Path("data/extracted/research_reports")
                # For research reports, we can't easily match by name
                # So check if the number of extracted files is less than raw files
                missing_extractions.append(
                    {
                        "raw_file": raw_file,
                        "doc_type": "research_report",
                    }
                )

        self.stats["total_raw_files"] = len(list(raw_responses_dir.rglob("*.json")))
        return missing_extractions

    async def recover_from_raw_response(self, raw_file_info):
        """Recover extraction from a raw response file."""
        raw_file = raw_file_info["raw_file"]
        doc_type = raw_file_info["doc_type"]

        try:
            # Load raw response
            with open(raw_file, encoding="utf-8") as f:
                raw_data = json.load(f)

            response_content = raw_data.get("response_content", "")
            metadata = raw_data.get("metadata", {})

            # Extract JSON from response
            # The response contains JSON wrapped in ```json ... ```
            import re

            json_match = re.search(
                r"```json\s*(.*?)\s*```", response_content, re.DOTALL
            )
            if json_match:
                json_str = json_match.group(1)
            else:
                # Fallback to markdown extractor
                json_str = self.markdown_extractor.extract_json_from_text(
                    response_content
                )

            # Parse JSON string to dict first
            try:
                import json as json_module

                parsed_json = json_module.loads(json_str)
                logger.info(f"Parsed JSON keys: {list(parsed_json.keys())}")
            except Exception as e:
                logger.error(f"Failed to parse JSON: {e}")
                logger.error(f"JSON string (first 500 chars): {json_str[:500]}")
                raise

            # Parse based on document type
            # Skip the parser and use the parsed JSON directly since it's already valid
            if doc_type == "annual_report":
                from src.domain.entities import AnnualReportExtraction

                extraction_data = AnnualReportExtraction(**parsed_json)
            else:
                from src.domain.entities import ResearchReportExtraction

                extraction_data = ResearchReportExtraction(**parsed_json)

            # Determine output filename
            if metadata.get("company_name"):
                company_name = metadata["company_name"]
                output_filename = f"{company_name}_2024年年度报告摘要_extracted.json"
            else:
                # Try to extract from raw filename
                if "_raw_response.json" in raw_file.name:
                    parts = raw_file.name.replace("_raw_response.json", "").rsplit(
                        "_", 1
                    )
                    if len(parts) >= 2:
                        company_name = parts[0]
                        output_filename = (
                            f"{company_name}_2024年年度报告摘要_extracted.json"
                        )
                    else:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        output_filename = f"recovered_{timestamp}_extracted.json"
                else:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_filename = f"recovered_{timestamp}_extracted.json"

            # Save extracted JSON
            output_dir = Path(f"data/extracted/{doc_type}s")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / output_filename

            # Prepare extraction result
            result_data = {
                "document_type": doc_type,
                "extraction_data": extraction_data.model_dump(mode="json"),
                "extraction_metadata": {
                    "model_version": raw_data.get("model", "unknown"),
                    "prompt_version": raw_data.get("prompt_version", "1.0.0"),
                    "extraction_timestamp": raw_data.get(
                        "timestamp", datetime.now().isoformat()
                    ),
                    "processing_time_seconds": 0,  # Unknown from raw response
                    "token_usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                    },
                    "file_hash": "",  # Unknown from raw response
                },
                "raw_llm_response": response_content,
            }

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)

            self.stats["successfully_recovered"] += 1
            logger.info(
                f"Successfully recovered {output_filename} from {raw_file.name}"
            )

            return {
                "success": True,
                "output_file": output_path,
                "extraction_data": extraction_data,
            }

        except Exception as e:
            self.stats["failed_recovery"] += 1
            logger.error(f"Failed to recover from {raw_file}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "raw_file": raw_file,
            }

    async def run(self, specific_file=None):
        """Run the recovery process."""
        console.print("\n[bold cyan]=== RAW RESPONSE RECOVERY ===[/bold cyan]\n")

        if specific_file:
            # Process specific file
            raw_file = Path(specific_file)
            if not raw_file.exists():
                console.print(f"[red]File not found: {specific_file}[/red]")
                return

            # Determine document type from path
            if "annual_report" in str(raw_file):
                doc_type = "annual_report"
            elif "research_report" in str(raw_file):
                doc_type = "research_report"
            else:
                console.print(
                    "[red]Cannot determine document type from file path[/red]"
                )
                return

            result = await self.recover_from_raw_response(
                {
                    "raw_file": raw_file,
                    "doc_type": doc_type,
                }
            )

            if result["success"]:
                console.print(
                    f"[green]✅ Successfully recovered: {result['output_file']}[/green]"
                )
            else:
                console.print(f"[red]❌ Recovery failed: {result['error']}[/red]")

        else:
            # Find all missing extractions
            missing = self.find_raw_responses_without_extraction()

            console.print(
                f"[bold]Found {len(missing)} raw responses without extractions[/bold]"
            )
            console.print(f"Total raw files: {self.stats['total_raw_files']}")

            if not missing:
                console.print("\n[green]All raw responses have been extracted![/green]")
                return

            # Show what will be processed
            table = Table(title="Raw Responses to Process")
            table.add_column("File", style="cyan")
            table.add_column("Type", style="yellow")
            table.add_column("Modified", style="green")

            for item in missing[:10]:
                raw_file = item["raw_file"]
                table.add_row(
                    raw_file.name,
                    item["doc_type"],
                    datetime.fromtimestamp(raw_file.stat().st_mtime).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                )

            if len(missing) > 10:
                table.add_row("...", f"... and {len(missing) - 10} more", "...")

            console.print(table)

            # Process all missing
            if click.confirm("\nProceed with recovery?"):
                console.print("\n[bold]Processing raw responses...[/bold]")

                for item in missing:
                    await self.recover_from_raw_response(item)

                # Show results
                console.print("\n[bold]=== RECOVERY RESULTS ===[/bold]")

                results_table = Table()
                results_table.add_column("Metric", style="cyan")
                results_table.add_column("Count", style="green")

                results_table.add_row(
                    "Total Raw Files", str(self.stats["total_raw_files"])
                )
                results_table.add_row(
                    "Successfully Recovered", str(self.stats["successfully_recovered"])
                )
                results_table.add_row(
                    "Failed Recovery", str(self.stats["failed_recovery"])
                )

                console.print(results_table)

                if self.stats["successfully_recovered"] > 0:
                    console.print(
                        "\n[green]✅ Recovery complete! Run the pipeline again to process these extracted files.[/green]"
                    )


@click.command()
@click.option(
    "--file",
    help="Specific raw response file to recover",
)
def main(file):
    """Recover extractions from saved raw LLM responses."""
    recovery = RawResponseRecovery()
    asyncio.run(recovery.run(file))


if __name__ == "__main__":
    main()
