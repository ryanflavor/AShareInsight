"""Batch document extraction use case for processing multiple files efficiently."""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from tqdm import tqdm

from src.application.ports.llm_service import LLMServicePort
from src.domain.entities.extraction import DocumentExtractionResult
from src.infrastructure.document_processing.loader import DocumentLoader
from src.infrastructure.monitoring import LLMMetrics, trace_span
from src.shared.config.settings import Settings

logger = structlog.get_logger(__name__)


class BatchExtractDocumentsUseCase:
    """Batch processing for document extraction with concurrency and rate limiting."""

    def __init__(self, llm_service: LLMServicePort, settings: Settings):
        """Initialize batch processor.

        Args:
            llm_service: LLM service implementation.
            settings: Application settings.
        """
        self.llm_service = llm_service
        self.settings = settings
        self.document_loader = DocumentLoader()

        # Rate limiting
        self.rate_limiter = asyncio.Semaphore(settings.llm.batch_size)
        self.calls_per_minute = settings.llm.rate_limit_per_minute
        self.last_call_times: list[float] = []

        # Progress tracking
        self.checkpoint_file = Path(".batch_progress.json")
        self.processed_files: set[str] = set()
        self.failed_files: dict[str, str] = {}

    def execute(
        self,
        file_paths: list[Path],
        document_type: str,
        resume: bool = True,
    ) -> dict[str, Any]:
        """Execute batch extraction on multiple files.

        Args:
            file_paths: List of file paths to process.
            document_type: Type of documents (annual_report or research_report).
            resume: Whether to resume from last checkpoint.

        Returns:
            Dictionary with processing results and statistics.
        """
        start_time = time.time()

        # Load checkpoint if resuming
        if resume and self.checkpoint_file.exists():
            self._load_checkpoint()
            logger.info(
                "Resuming from checkpoint",
                processed=len(self.processed_files),
                failed=len(self.failed_files),
            )

        # Filter out already processed files
        remaining_files = [
            fp for fp in file_paths if str(fp) not in self.processed_files
        ]

        logger.info(
            "Starting batch processing",
            total_files=len(file_paths),
            remaining=len(remaining_files),
            batch_size=self.settings.llm.batch_size,
            max_workers=self.settings.llm.max_workers,
        )

        # Process files with thread pool
        with ThreadPoolExecutor(max_workers=self.settings.llm.max_workers) as executor:
            # Submit tasks
            future_to_file = {
                executor.submit(
                    self._process_single_file, file_path, document_type
                ): file_path
                for file_path in remaining_files
            }

            # Progress bar
            with tqdm(total=len(remaining_files), desc="Processing files") as pbar:
                for future in as_completed(future_to_file):
                    file_path = future_to_file[future]

                    try:
                        result = future.result()
                        self.processed_files.add(str(file_path))

                        # Update progress
                        pbar.update(1)
                        pbar.set_postfix(
                            success=len(self.processed_files),
                            failed=len(self.failed_files),
                        )

                        # Checkpoint periodically
                        if (
                            len(self.processed_files)
                            % self.settings.batch_checkpoint_interval
                            == 0
                        ):
                            self._save_checkpoint()

                    except Exception as e:
                        logger.error(
                            "Failed to process file",
                            file_path=str(file_path),
                            error=str(e),
                        )
                        self.failed_files[str(file_path)] = str(e)

                        # Check error threshold
                        error_rate = len(self.failed_files) / (
                            len(self.processed_files) + len(self.failed_files)
                        )
                        if error_rate > self.settings.batch_error_threshold:
                            logger.error(
                                "Error threshold exceeded, stopping batch",
                                error_rate=error_rate,
                                threshold=self.settings.batch_error_threshold,
                            )
                            break

        # Final checkpoint
        self._save_checkpoint()

        # Calculate statistics
        total_time = time.time() - start_time
        success_count = len(self.processed_files) - len(
            [fp for fp in self.failed_files if fp in self.processed_files]
        )

        results = {
            "total_files": len(file_paths),
            "processed": len(self.processed_files),
            "successful": success_count,
            "failed": len(self.failed_files),
            "total_time_seconds": total_time,
            "average_time_per_file": total_time / len(self.processed_files)
            if self.processed_files
            else 0,
            "failed_files": self.failed_files,
        }

        logger.info("Batch processing completed", **results)

        return results

    def _process_single_file(
        self, file_path: Path, document_type: str
    ) -> DocumentExtractionResult:
        """Process a single file with rate limiting.

        Args:
            file_path: Path to the file.
            document_type: Type of document.

        Returns:
            Extraction result.
        """
        # Rate limiting
        self._apply_rate_limit()

        with trace_span(
            "batch.process_file",
            {"file_path": str(file_path), "document_type": document_type},
        ):
            try:
                # Load document
                document = self.document_loader.load(file_path)

                # Extract data
                if document_type == "annual_report":
                    extracted_data = self.llm_service.extract_annual_report(
                        document.content, document.metadata
                    )
                else:
                    extracted_data = self.llm_service.extract_research_report(
                        document.content, document.metadata
                    )

                # Record success metrics
                LLMMetrics.record_document_processing(
                    document_type=document_type,
                    document_size=len(document.content),
                    processing_time=0,  # Will be calculated by span
                    success=True,
                )

                return extracted_data

            except Exception as e:
                # Record failure metrics
                LLMMetrics.record_document_processing(
                    document_type=document_type,
                    document_size=0,
                    processing_time=0,
                    success=False,
                    error=str(e),
                )
                raise

    def _apply_rate_limit(self) -> None:
        """Apply rate limiting to respect API limits."""
        current_time = time.time()

        # Remove calls older than 1 minute
        self.last_call_times = [
            t for t in self.last_call_times if current_time - t < 60
        ]

        # If we've hit the rate limit, wait
        if len(self.last_call_times) >= self.calls_per_minute:
            wait_time = 60 - (current_time - self.last_call_times[0])
            if wait_time > 0:
                logger.debug(f"Rate limit reached, waiting {wait_time:.1f}s")
                time.sleep(wait_time)

        # Record this call
        self.last_call_times.append(current_time)

    def _save_checkpoint(self) -> None:
        """Save processing progress to checkpoint file."""
        checkpoint_data = {
            "processed_files": list(self.processed_files),
            "failed_files": self.failed_files,
            "timestamp": datetime.now().isoformat(),
        }

        with open(self.checkpoint_file, "w") as f:
            json.dump(checkpoint_data, f, indent=2)

        logger.debug("Checkpoint saved", file=str(self.checkpoint_file))

    def _load_checkpoint(self) -> None:
        """Load processing progress from checkpoint file."""
        try:
            with open(self.checkpoint_file) as f:
                checkpoint_data = json.load(f)

            self.processed_files = set(checkpoint_data.get("processed_files", []))
            self.failed_files = checkpoint_data.get("failed_files", {})

            logger.info(
                "Checkpoint loaded",
                timestamp=checkpoint_data.get("timestamp"),
                processed=len(self.processed_files),
                failed=len(self.failed_files),
            )
        except Exception as e:
            logger.warning("Failed to load checkpoint", error=str(e))
