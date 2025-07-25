#!/usr/bin/env python3
"""
Production-Ready Document Processing Pipeline

Complete all-in-one pipeline with:
- Database content clearing (preserving structure)
- Checkpoint management
- Document extraction
- Business concept fusion
- Vector index building
- Comprehensive error recovery
"""

import asyncio
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import click
import structlog
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Load environment variables with override
load_dotenv(override=True)

from sqlalchemy import select

from src.infrastructure.persistence.postgres.connection import get_session
from src.infrastructure.persistence.postgres.models import (
    SourceDocumentModel,
)
from src.shared.utils.timezone import now_china

logger = structlog.get_logger()
console = Console()


class FileLock:
    """Simple file-based lock to prevent concurrent processing of same file."""

    def __init__(self, lock_dir: Path = Path("data/temp/locks")):
        self.lock_dir = lock_dir
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self._held_locks = set()

    def _get_lock_path(self, file_path: Path) -> Path:
        """Get lock file path for given file."""
        # Use hash of absolute path to create lock filename
        path_hash = hashlib.md5(str(file_path.absolute()).encode()).hexdigest()
        return self.lock_dir / f"{path_hash}.lock"

    async def acquire(self, file_path: Path, timeout: float = 30.0) -> bool:
        """Try to acquire lock for file.

        Args:
            file_path: Path to file to lock
            timeout: Maximum time to wait for lock (seconds)

        Returns:
            True if lock acquired, False if timeout
        """
        lock_path = self._get_lock_path(file_path)
        start_time = asyncio.get_event_loop().time()

        while True:
            try:
                # Try to create lock file exclusively
                lock_path.touch(exist_ok=False)
                self._held_locks.add(lock_path)
                logger.debug(f"Acquired lock for {file_path.name}")
                return True
            except FileExistsError:
                # Lock already held, check if timeout
                if asyncio.get_event_loop().time() - start_time > timeout:
                    logger.warning(f"Timeout acquiring lock for {file_path.name}")
                    return False
                # Wait a bit and retry
                await asyncio.sleep(0.1)

    def release(self, file_path: Path):
        """Release lock for file."""
        lock_path = self._get_lock_path(file_path)
        if lock_path in self._held_locks:
            try:
                lock_path.unlink()
                self._held_locks.remove(lock_path)
                logger.debug(f"Released lock for {file_path.name}")
            except FileNotFoundError:
                # Lock already released
                pass

    def release_all(self):
        """Release all held locks (cleanup)."""
        for lock_path in list(self._held_locks):
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
        self._held_locks.clear()


class DocumentState:
    """Track document processing state with checkpoints."""

    def __init__(self, file_path: Path, db_record: Any | None = None):
        self.file_path = file_path
        self.file_hash = self._calculate_hash()
        self.last_modified = file_path.stat().st_mtime
        self.checkpoint_file = Path(
            f"data/temp/checkpoints/{file_path.stem}_checkpoint.json"
        )
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing checkpoint if available
        self.state = self._load_checkpoint()

        # If no checkpoint but DB record exists, reconstruct state from DB
        if (
            not self.checkpoint_file.exists()
            and db_record
            and db_record.file_hash == self.file_hash
        ):
            self._reconstruct_from_db(db_record)

    def _calculate_hash(self) -> str:
        """Calculate file hash."""
        sha256_hash = hashlib.sha256()
        with open(self.file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _reconstruct_from_db(self, db_record):
        """Reconstruct checkpoint state from database record."""
        # Mark extraction and archive as success since document is in DB
        self.state["stages"]["extraction"]["status"] = "success"
        self.state["stages"]["extraction"]["timestamp"] = str(db_record.created_at)

        self.state["stages"]["archive"]["status"] = "success"
        self.state["stages"]["archive"]["timestamp"] = str(db_record.created_at)
        self.state["stages"]["archive"]["doc_id"] = str(db_record.doc_id)

        # Assume fusion and vectorization were completed if document is in DB
        # This prevents reprocessing of already imported documents
        self.state["stages"]["fusion"]["status"] = "success"
        self.state["stages"]["fusion"]["timestamp"] = str(db_record.created_at)

        self.state["stages"]["vectorization"]["status"] = "success"
        self.state["stages"]["vectorization"]["timestamp"] = str(db_record.created_at)

        logger.info(
            f"Reconstructed checkpoint for {self.file_path.name} from DB record"
        )

    def _load_checkpoint(self) -> dict:
        """Load checkpoint from disk."""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file) as f:
                    return json.load(f)
            except:
                pass

        return {
            "file_path": str(self.file_path),
            "file_hash": self.file_hash,
            "last_modified": self.last_modified,
            "stages": {
                "extraction": {"status": "pending", "timestamp": None, "error": None},
                "archive": {"status": "pending", "timestamp": None, "doc_id": None},
                "fusion": {"status": "pending", "timestamp": None, "concepts": 0},
                "vectorization": {"status": "pending", "timestamp": None, "vectors": 0},
            },
            "created_at": now_china().isoformat(),
            "updated_at": now_china().isoformat(),
        }

    def update_stage(self, stage: str, status: str, **kwargs):
        """Update stage status and save checkpoint."""
        self.state["stages"][stage]["status"] = status
        self.state["stages"][stage]["timestamp"] = now_china().isoformat()
        self.state["stages"][stage].update(kwargs)
        self.state["updated_at"] = now_china().isoformat()
        self._save_checkpoint()

    def _save_checkpoint(self):
        """Save checkpoint to disk."""
        with open(self.checkpoint_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def is_complete(self) -> bool:
        """Check if all stages completed successfully."""
        return all(
            stage["status"] == "success" for stage in self.state["stages"].values()
        )

    def needs_reprocessing(
        self,
        db_record: Any | None,
        existing_companies: set | None = None,
        extract_company_code_func=None,
    ) -> bool:
        """Check if document needs reprocessing."""
        # FIRST AND MOST IMPORTANT: Check if extracted JSON already exists
        # This prevents expensive LLM calls
        path_str = str(self.file_path)
        if "annual_reports" in path_str or "annual_report" in path_str:
            doc_type = "annual_report"
        elif "research_reports" in path_str or "research_report" in path_str:
            doc_type = "research_report"
        else:
            # Default based on file name patterns
            if (
                "年度报告" in self.file_path.name
                or "annual" in self.file_path.name.lower()
            ):
                doc_type = "annual_report"
            else:
                doc_type = "research_report"

        output_path = Path(
            f"data/extracted/{doc_type}s/{self.file_path.stem}_extracted.json"
        )
        if output_path.exists():
            logger.info(
                f"Extracted JSON already exists for {self.file_path.name}, skipping ALL processing to save money"
            )
            # Mark all stages as complete in checkpoint to avoid confusion
            self.state["stages"]["extraction"]["status"] = "success"
            self.state["stages"]["archive"]["status"] = "success"
            self.state["stages"]["fusion"]["status"] = "success"
            self.state["stages"]["vectorization"]["status"] = "success"
            self._save_checkpoint()
            return False

        # NEW: For annual reports, check if company already exists
        # This avoids adding files from existing companies to the processing queue
        if (
            doc_type == "annual_report"
            and existing_companies
            and extract_company_code_func
        ):
            # Use the provided function to extract company code
            company_code = extract_company_code_func(self.file_path)

            if company_code and company_code in existing_companies:
                logger.info(
                    f"Company {company_code} already exists in database, skipping {self.file_path.name} to save LLM costs"
                )
                # Create minimal extracted JSON to mark as processed
                import json

                output_dir = Path(f"data/extracted/{doc_type}s")
                output_dir.mkdir(parents=True, exist_ok=True)

                minimal_data = {
                    "document_type": doc_type,
                    "extraction_data": {
                        "company_code": company_code,
                        "company_name_full": f"Company {company_code}",
                        "company_name_short": f"Company {company_code}",
                    },
                    "extraction_metadata": {
                        "extraction_method": "existing_company_skip_early",
                        "llm_skipped": True,
                        "timestamp": now_china().isoformat(),
                        "file_path": str(self.file_path),
                    },
                }

                # Save minimal extraction JSON
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(minimal_data, f, ensure_ascii=False, indent=2)

                # Mark all stages as complete
                self.state["stages"]["extraction"]["status"] = "success"
                self.state["stages"]["archive"]["status"] = "success"
                self.state["stages"]["fusion"]["status"] = "success"
                self.state["stages"]["vectorization"]["status"] = "success"
                self._save_checkpoint()
                return False

        if not db_record:
            return True

        # Check if file was modified after DB record
        if db_record.file_hash != self.file_hash:
            logger.info(f"File {self.file_path.name} modified since last import")
            return True

        # If document exists in DB with matching hash and no checkpoint file exists,
        # assume it was successfully processed (backwards compatibility)
        if not self.checkpoint_file.exists() and db_record.file_hash == self.file_hash:
            logger.debug(
                f"File {self.file_path.name} already in DB with matching hash, skipping"
            )
            return False

        # Check if all stages completed
        if not self.is_complete():
            return True

        return False


class ProductionPipeline:
    """Production-ready pipeline with proper state management."""

    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self.file_lock = FileLock()
        self.stats = {
            "total_files": 0,
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "reprocessed": 0,
            "locked_skip": 0,
            "llm_skipped": 0,
            "db_cleared": False,
            "checkpoints_cleared": False,
            "indices_created": False,
        }
        self.existing_companies = set()  # Cache for existing companies

    async def fetch_existing_companies(self):
        """Fetch all existing company codes from database."""
        try:
            # Import CompanyModel here to avoid linter issues
            from src.infrastructure.persistence.postgres.models import CompanyModel

            async with get_session() as session:
                stmt = select(CompanyModel.company_code)
                result = await session.execute(stmt)
                self.existing_companies = set(result.scalars().all())
                logger.info(
                    f"Found {len(self.existing_companies)} existing companies in database"
                )
        except Exception as e:
            logger.error(f"Failed to fetch existing companies: {e}")
            self.existing_companies = set()

    def extract_company_code_from_file(self, file_path: Path) -> str | None:
        """Extract company code from file name or content preview."""
        import re

        # Try to extract from filename first
        # Common patterns: 300257_xxx, 300257东方网力, etc.
        filename_pattern = r"(\d{6})(?:_|[^\d])"
        match = re.search(filename_pattern, file_path.stem)
        if match:
            return match.group(1)

        # If no code in filename, try reading first few lines of file
        try:
            with open(file_path, encoding="utf-8") as f:
                # Read first 2000 characters for better coverage
                content = f.read(2000)

                # Pattern 1: Look for patterns like "股票代码：300257" or "证券代码：300257"
                # Support both Chinese and English colons, with optional spaces and asterisks
                code_pattern = r"(?:股票代码|证券代码|代码)\s*[：:]\s*\**(\d{6})\**"
                match = re.search(code_pattern, content)
                if match:
                    return match.group(1)

                # Pattern 2: Look for 6-digit codes in table format (e.g., |002259|)
                table_pattern = r"\|\s*(\d{6})\s*\|"
                match = re.search(table_pattern, content)
                if match:
                    return match.group(1)

                # Pattern 3: Look for 6-digit codes with brackets
                bracket_pattern = r"[（(](\d{6})[）)]"
                match = re.search(bracket_pattern, content)
                if match:
                    return match.group(1)

                # Pattern 4: Simple 6-digit pattern at start of lines
                simple_pattern = r"^(\d{6})\b"
                match = re.search(simple_pattern, content, re.MULTILINE)
                if match:
                    return match.group(1)

                # Pattern 5: Look for "A股代码" or similar patterns
                a_share_pattern = r"A股代码\s*[：:]\s*(\d{6})"
                match = re.search(a_share_pattern, content)
                if match:
                    return match.group(1)

                # Pattern 6: Handle dual-listed companies (A+B or A+H)
                # Look for patterns like "000028、200028" or "000063/00763"
                dual_listing_pattern = r"(\d{6})[、/](?:\d{6}|\d{5})"
                match = re.search(dual_listing_pattern, content)
                if match:
                    return match.group(1)  # Return A-share code

                # Pattern 7: Handle space-separated codes like "3 0 0 4 9 4"
                space_code_pattern = r"(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)"
                match = re.search(space_code_pattern, content)
                if match:
                    return "".join(match.groups())

                # Pattern 8: Look for SZ/SH format codes
                sz_sh_pattern = r"(?:SZ|SH|sz|sh)\s*[.:]?\s*(\d{6})"
                match = re.search(sz_sh_pattern, content)
                if match:
                    return match.group(1)

                # Pattern 9: Look in specific table cell patterns
                # Handle cases like "300683<br>股票上市"
                cell_pattern = r">(\d{6})<"
                match = re.search(cell_pattern, content)
                if match:
                    return match.group(1)

                # Pattern 10: Handle codes in various table/report formats
                # Like "股票简称 | 蓝宇股份 | 股票代码<br>301585"
                table_code_pattern = r"股票代码[^0-9]{0,20}(\d{6})"
                match = re.search(table_code_pattern, content)
                if match:
                    return match.group(1)

                # Pattern 11: More flexible pattern for any 6 digits that appear after key words
                flexible_pattern = r"(?:股票|证券|代码|简称)[^0-9]{0,50}(\d{6})"
                match = re.search(flexible_pattern, content)
                if match:
                    return match.group(1)

        except Exception as e:
            logger.debug(f"Could not read file {file_path.name} for company code: {e}")

        return None

    async def check_document_state(
        self, file_path: Path
    ) -> tuple[Any | None, DocumentState]:
        """Check document state in database and filesystem."""
        # First get the file hash to check database
        temp_state = DocumentState(file_path)

        async with get_session() as session:
            # Check by file path first - this is the primary check
            stmt = select(SourceDocumentModel).where(
                SourceDocumentModel.file_path == str(file_path.absolute())
            )
            result = await session.execute(stmt)
            db_record = result.scalars().first()

            # If not found by path, check by hash (handles moved files)
            if not db_record:
                stmt = select(SourceDocumentModel).where(
                    SourceDocumentModel.file_hash == temp_state.file_hash
                )
                result = await session.execute(stmt)
                db_record = result.scalars().first()

        # Create DocumentState with db_record info
        doc_state = DocumentState(file_path, db_record)
        return db_record, doc_state

    async def process_document(self, file_path: Path, doc_state: DocumentState) -> bool:
        """Process document through all pipeline stages."""
        try:
            # Double-check if extracted file already exists before processing
            # This handles race conditions in concurrent processing
            path_str = str(file_path)
            if "annual_reports" in path_str or "annual_report" in path_str:
                doc_type = "annual_report"
            elif "research_reports" in path_str or "research_report" in path_str:
                doc_type = "research_report"
            else:
                # Default based on file name patterns
                if "年度报告" in file_path.name or "annual" in file_path.name.lower():
                    doc_type = "annual_report"
                else:
                    doc_type = "research_report"

            output_path = Path(
                f"data/extracted/{doc_type}s/{file_path.stem}_extracted.json"
            )
            if output_path.exists():
                logger.info(
                    f"Extracted file already exists (race condition), skipping: {file_path.name}"
                )
                # Update state to reflect completion
                doc_state.state["stages"]["extraction"]["status"] = "success"
                doc_state.state["stages"]["archive"]["status"] = "success"
                doc_state.state["stages"]["fusion"]["status"] = "success"
                doc_state.state["stages"]["vectorization"]["status"] = "success"
                doc_state._save_checkpoint()
                return True

            # Stage 1: Extraction
            if doc_state.state["stages"]["extraction"]["status"] != "success":
                await self.extract_document(file_path, doc_state)

            # Stage 2: Archive to DB
            if doc_state.state["stages"]["archive"]["status"] != "success":
                await self.archive_document(file_path, doc_state)

            # Stage 3: Fusion
            if doc_state.state["stages"]["fusion"]["status"] != "success":
                doc_id = doc_state.state["stages"]["archive"].get("doc_id")
                if doc_id:
                    await self.run_fusion(doc_id, doc_state)

            # Stage 4: Vectorization
            if doc_state.state["stages"]["vectorization"]["status"] != "success":
                await self.run_vectorization(doc_state)

            return True

        except Exception as e:
            logger.error(f"Pipeline failed for {file_path}: {e}")
            return False

    async def extract_document(self, file_path: Path, doc_state: DocumentState):
        """Extract document with LLM."""
        try:
            # Determine document type based on directory structure
            path_str = str(file_path)
            if "annual_reports" in path_str or "annual_report" in path_str:
                doc_type = "annual_report"
            elif "research_reports" in path_str or "research_report" in path_str:
                doc_type = "research_report"
            else:
                # Default based on file name patterns
                if "年度报告" in file_path.name or "annual" in file_path.name.lower():
                    doc_type = "annual_report"
                else:
                    doc_type = "research_report"
                logger.warning(
                    f"Document type inferred from filename for {file_path.name}: {doc_type}"
                )

            # Check if extracted JSON already exists
            output_dir = Path(f"data/extracted/{doc_type}s")
            output_path = output_dir / f"{file_path.stem}_extracted.json"

            if output_path.exists():
                # Extracted JSON already exists, skip LLM extraction
                logger.info(
                    f"Extracted JSON already exists for {file_path.name}, skipping LLM extraction"
                )
                doc_state.update_stage(
                    "extraction",
                    "success",
                    output_path=str(output_path),
                    skipped_llm=True,
                )
                return

            # Check if company already exists in database (for annual reports)
            if doc_type == "annual_report":
                company_code = self.extract_company_code_from_file(file_path)
                if company_code and company_code in self.existing_companies:
                    # Company already exists, create minimal extraction JSON without LLM
                    logger.info(
                        f"Company {company_code} already exists in database, creating minimal extraction JSON for {file_path.name}"
                    )

                    # Create minimal extraction data with just company code
                    minimal_data = {
                        "document_type": doc_type,
                        "extraction_data": {
                            "company_code": company_code,
                            # Add other minimal fields that might be required
                            "company_name_full": f"Company {company_code}",  # Placeholder, will be updated from DB
                            "company_name_short": f"Company {company_code}",  # Placeholder
                        },
                        "extraction_metadata": {
                            "extraction_method": "existing_company_skip",
                            "llm_skipped": True,
                            "timestamp": now_china().isoformat(),
                            "file_path": str(file_path),
                        },
                    }

                    # Save minimal extraction JSON
                    output_dir.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(minimal_data, f, ensure_ascii=False, indent=2)

                    doc_state.update_stage(
                        "extraction",
                        "success",
                        output_path=str(output_path),
                        skipped_llm=True,
                        existing_company=company_code,
                    )
                    self.stats["llm_skipped"] += 1
                    return

            # No existing extraction, proceed with LLM
            from src.application.use_cases.extract_document_data import (
                ExtractDocumentDataUseCase,
            )
            from src.infrastructure.llm.gemini_llm_adapter import GeminiLLMAdapter
            from src.infrastructure.persistence.postgres.source_document_repository import (
                PostgresSourceDocumentRepository,
            )
            from src.shared.config.settings import Settings

            settings = Settings()
            llm_service = GeminiLLMAdapter(settings)

            async with get_session() as session:
                repository = PostgresSourceDocumentRepository(session)
                use_case = ExtractDocumentDataUseCase(llm_service, repository)

                result = await use_case.execute(
                    file_path, document_type_override=doc_type
                )

                # Save extracted JSON
                output_dir.mkdir(parents=True, exist_ok=True)

                result_data = {
                    "document_type": result.document_type,
                    "extraction_data": result.extraction_data.model_dump(mode="json"),
                    "extraction_metadata": result.extraction_metadata.model_dump(
                        mode="json"
                    ),
                }

                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result_data, f, ensure_ascii=False, indent=2)

                doc_state.update_stage(
                    "extraction", "success", output_path=str(output_path)
                )
                logger.info(f"Extraction successful: {file_path.name}")

        except Exception as e:
            doc_state.update_stage("extraction", "failed", error=str(e))
            raise

    async def archive_document(self, file_path: Path, doc_state: DocumentState):
        """Archive document to database."""
        try:
            # Recalculate file hash to ensure it's current
            # This handles cases where file was modified after being queued
            current_file_hash = doc_state._calculate_hash()
            if current_file_hash != doc_state.file_hash:
                logger.warning(
                    f"File {file_path.name} was modified after being queued. "
                    f"Original hash: {doc_state.file_hash[:16]}..., "
                    f"Current hash: {current_file_hash[:16]}..."
                )
                # Update the DocumentState with current hash
                doc_state.file_hash = current_file_hash
                doc_state.state["file_hash"] = current_file_hash

            # Get extraction result - same logic as extract_document
            path_str = str(file_path)
            if "annual_reports" in path_str or "annual_report" in path_str:
                doc_type = "annual_report"
            elif "research_reports" in path_str or "research_report" in path_str:
                doc_type = "research_report"
            else:
                # Default based on file name patterns
                if "年度报告" in file_path.name or "annual" in file_path.name.lower():
                    doc_type = "annual_report"
                else:
                    doc_type = "research_report"
            extract_path = Path(
                f"data/extracted/{doc_type}s/{file_path.stem}_extracted.json"
            )

            if not extract_path.exists():
                raise FileNotFoundError(f"Extracted JSON not found: {extract_path}")

            # Check if document already exists in database
            async with get_session() as session:
                # First check by file_hash (exact same content)
                stmt = (
                    select(SourceDocumentModel.doc_id)
                    .where(SourceDocumentModel.file_hash == doc_state.file_hash)
                    .order_by(SourceDocumentModel.created_at.desc())
                    .limit(1)
                )

                result = await session.execute(stmt)
                doc_id = result.scalar()

                if doc_id:
                    # Document already in database with same hash
                    doc_state.update_stage("archive", "success", doc_id=str(doc_id))
                    logger.info(
                        f"Document already archived: {file_path.name} -> {doc_id}"
                    )
                    return

                # Check if file_path already exists (file was updated)
                stmt = (
                    select(SourceDocumentModel.doc_id, SourceDocumentModel.file_hash)
                    .where(SourceDocumentModel.file_path == str(file_path))
                    .order_by(SourceDocumentModel.created_at.desc())
                    .limit(1)
                )

                result = await session.execute(stmt)
                row = result.first()

                if row:
                    # File path exists but with different hash - file was updated
                    existing_doc_id, existing_hash = row
                    logger.warning(
                        f"File path already exists with different hash: {file_path.name}\n"
                        f"  Existing hash: {existing_hash[:16]}...\n"
                        f"  New hash: {doc_state.file_hash[:16]}...\n"
                        f"  Skipping re-archive to avoid duplicate file_path"
                    )
                    doc_state.update_stage(
                        "archive",
                        "skipped",
                        reason="file_path_exists_with_different_hash",
                        existing_doc_id=str(existing_doc_id),
                    )
                    return

            # Document not in database, need to import from extracted JSON
            logger.info(f"Importing extracted JSON to database: {file_path.name}")

            # Read extracted JSON
            with open(extract_path, encoding="utf-8") as f:
                data = json.load(f)

            # Import to database using ArchiveExtractionResultUseCase
            # Extract date from filename or use today
            import re

            # Prepare metadata for archiving
            from datetime import date

            from src.application.use_cases.archive_extraction_result import (
                ArchiveExtractionResultUseCase,
            )
            from src.infrastructure.persistence.postgres.source_document_repository import (
                PostgresSourceDocumentRepository,
            )

            date_match = re.search(r"(\d{4})", file_path.name)
            doc_date = (
                date(int(date_match.group(1)), 12, 31) if date_match else date.today()
            )

            # Get company code from extraction data
            company_code = data["extraction_data"].get("company_code", "unknown")

            # Read original content from file
            original_content = None
            try:
                with open(file_path, encoding="utf-8") as f:
                    original_content = f.read()
            except Exception as e:
                logger.warning(f"Could not read original content from {file_path}: {e}")

            metadata = {
                "company_code": company_code,
                "doc_type": doc_type,
                "doc_date": doc_date,
                "report_title": data["extraction_data"].get(
                    "company_name_full", file_path.name
                ),
                "file_path": str(file_path),
                "file_hash": doc_state.file_hash,  # Always use file content hash from DocumentState
                "original_content": original_content,
            }

            # Archive to database
            async with get_session() as session:
                repository = PostgresSourceDocumentRepository(session)
                use_case = ArchiveExtractionResultUseCase(repository)

                # Pass the extraction data as raw_llm_output and metadata separately
                doc_id = await use_case.execute(raw_llm_output=data, metadata=metadata)

                if isinstance(doc_id, UUID):
                    doc_state.update_stage("archive", "success", doc_id=str(doc_id))
                    logger.info(f"Archive successful: {file_path.name} -> {doc_id}")
                else:
                    # For research reports without companies, doc_id might be a warning message
                    doc_state.update_stage("archive", "skipped", reason=str(doc_id))
                    logger.warning(f"Archive skipped: {file_path.name} - {doc_id}")

        except Exception as e:
            doc_state.update_stage("archive", "failed", error=str(e))
            raise

    async def run_fusion(self, doc_id: str, doc_state: DocumentState):
        """Run fusion to update business concepts."""
        try:
            from src.infrastructure.factories import create_standalone_fusion_use_case

            # Get company code from extracted data
            company_code = None
            extract_path = doc_state.state["stages"]["extraction"].get("output_path")
            if extract_path and Path(extract_path).exists():
                with open(extract_path, encoding="utf-8") as f:
                    data = json.load(f)
                    company_code = data["extraction_data"].get("company_code")

            fusion_use_case = await create_standalone_fusion_use_case()
            result = await fusion_use_case.execute(doc_id)

            # Handle dict result from fusion
            if isinstance(result, dict):
                concepts_created = result.get("concepts_created", 0)
                concepts_updated = result.get("concepts_updated", 0)
                total_concepts = result.get("total_concepts", 0)

                doc_state.update_stage(
                    "fusion",
                    "success",
                    concepts=total_concepts,
                    created=concepts_created,
                    updated=concepts_updated,
                    company_code=company_code,
                )
                logger.info(
                    f"Fusion successful for doc {doc_id}: "
                    f"{concepts_created} created, "
                    f"{concepts_updated} updated, "
                    f"{total_concepts} total"
                )
            else:
                # Handle object result (legacy)
                doc_state.update_stage(
                    "fusion",
                    "success",
                    concepts=len(result.concepts_created)
                    + len(result.concepts_updated),
                    company_code=company_code,
                )
                logger.info(
                    f"Fusion successful for doc {doc_id}: "
                    f"{len(result.concepts_created)} created, "
                    f"{len(result.concepts_updated)} updated"
                )

        except Exception as e:
            doc_state.update_stage("fusion", "failed", error=str(e))
            # Don't raise - fusion failure shouldn't stop pipeline
            logger.warning(f"Fusion failed for doc {doc_id}: {e}")

    async def run_vectorization(self, doc_state: DocumentState):
        """Run vectorization for new concepts."""
        try:
            # Get the document ID from archive stage
            doc_id = doc_state.state["stages"]["archive"].get("doc_id")
            if not doc_id:
                logger.warning("No doc_id found, skipping vectorization")
                doc_state.update_stage("vectorization", "skipped", reason="No doc_id")
                return

            # Get company code from fusion stage or archive stage
            company_code = None
            if "company_code" in doc_state.state["stages"].get("fusion", {}):
                company_code = doc_state.state["stages"]["fusion"]["company_code"]
            else:
                # Try to get from extracted data
                extract_path = doc_state.state["stages"]["extraction"].get(
                    "output_path"
                )
                if extract_path and Path(extract_path).exists():
                    with open(extract_path, encoding="utf-8") as f:
                        data = json.load(f)
                        company_code = data["extraction_data"].get("company_code")

            if not company_code:
                logger.warning(
                    f"No company_code found for doc {doc_id}, skipping vectorization"
                )
                doc_state.update_stage(
                    "vectorization", "skipped", reason="No company_code"
                )
                return

            # Import necessary modules for vectorization
            from src.application.use_cases.build_vector_index import (
                BuildVectorIndexUseCase,
            )
            from src.domain.services.vectorization_service import VectorizationService
            from src.infrastructure.llm.qwen.qwen_embedding_adapter import (
                QwenEmbeddingAdapter,
                QwenEmbeddingConfig,
            )
            from src.infrastructure.persistence.postgres.business_concept_master_repository import (
                PostgresBusinessConceptMasterRepository,
            )
            from src.shared.config.settings import Settings

            settings = Settings()

            async with get_session() as session:
                # Initialize repository
                repository = PostgresBusinessConceptMasterRepository(session)

                # Initialize embedding service
                embedding_config = QwenEmbeddingConfig.from_settings(
                    settings.qwen_embedding
                )
                embedding_service = QwenEmbeddingAdapter(config=embedding_config)

                # Initialize vectorization service
                vectorization_service = VectorizationService(
                    embedding_service=embedding_service,
                    qwen_settings=settings.qwen_embedding,
                )

                # Create use case
                use_case = BuildVectorIndexUseCase(
                    repository=repository,
                    embedding_service=embedding_service,
                    vectorization_service=vectorization_service,
                    batch_size=settings.qwen_embedding.qwen_max_batch_size,
                )

                # Build vectors for this specific company
                result = await use_case.execute(
                    rebuild_all=False,
                    company_code=company_code,
                )

                vectors_built = result.get("succeeded", 0)
                doc_state.update_stage(
                    "vectorization",
                    "success",
                    vectors_built=vectors_built,
                    total_concepts=result.get("total_concepts", 0),
                    company_code=company_code,
                )
                logger.info(
                    f"Vectorization completed for {company_code}: {vectors_built} vectors built"
                )

        except Exception as e:
            doc_state.update_stage("vectorization", "failed", error=str(e))
            logger.warning(f"Vectorization failed: {e}")

    async def clear_database_content(self):
        """Clear all database content while preserving table structure."""
        console.print("\n[bold yellow]🗑️  Clearing database content...[/bold yellow]")

        try:
            async with get_session() as session:
                # Disable foreign key checks temporarily
                await session.execute(text("SET session_replication_role = 'replica';"))

                # Clear tables in correct order to respect foreign keys
                tables_to_clear = [
                    "business_concepts_master",  # Has FK to source_documents
                    "source_documents",  # Has FK to companies
                    "companies",  # Base table
                ]

                for table in tables_to_clear:
                    result = await session.execute(text(f"DELETE FROM {table}"))
                    count = result.rowcount
                    console.print(f"  ✓ Cleared {count} rows from {table}")

                # Re-enable foreign key checks
                await session.execute(text("SET session_replication_role = 'origin';"))

                # Commit the transaction
                await session.commit()

                self.stats["db_cleared"] = True
                console.print("[green]✅ Database content cleared successfully[/green]")

        except Exception as e:
            logger.error(f"Failed to clear database: {e}")
            console.print(f"[red]❌ Failed to clear database: {e}[/red]")
            raise

    def clear_checkpoints(self):
        """Clear all checkpoint files."""
        console.print("\n[bold yellow]🗑️  Clearing checkpoints...[/bold yellow]")

        checkpoint_dir = Path("data/temp/checkpoints")
        if checkpoint_dir.exists():
            try:
                shutil.rmtree(checkpoint_dir)
                checkpoint_dir.mkdir(parents=True, exist_ok=True)
                self.stats["checkpoints_cleared"] = True
                console.print("[green]✅ Checkpoints cleared successfully[/green]")
            except Exception as e:
                logger.error(f"Failed to clear checkpoints: {e}")
                console.print(f"[red]❌ Failed to clear checkpoints: {e}[/red]")
                raise
        else:
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            self.stats["checkpoints_cleared"] = True
            console.print("[green]✅ Checkpoint directory created[/green]")

        # Also clear lock files
        lock_dir = Path("data/temp/locks")
        if lock_dir.exists():
            try:
                shutil.rmtree(lock_dir)
                lock_dir.mkdir(parents=True, exist_ok=True)
                console.print("[green]✅ Lock files cleared[/green]")
            except Exception as e:
                logger.warning(f"Failed to clear lock files: {e}")

    async def create_vector_indices(self):
        """Create HNSW vector indices for production."""
        console.print("\n[bold blue]🔨 Creating vector indices...[/bold blue]")

        try:
            # Run the index creation script as a subprocess
            import subprocess

            result = subprocess.run(
                ["python", "scripts/migration/003_create_vector_indices.py"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                self.stats["indices_created"] = True
                console.print("[green]✅ Vector indices created successfully[/green]")
            else:
                logger.warning(f"Failed to create vector indices: {result.stderr}")
        except Exception as e:
            logger.warning(f"Failed to create vector indices: {e}")
            # Non-fatal - indices can be created later

    async def run(
        self,
        annual_reports_dir: Path = Path("data/annual_reports"),
        research_reports_dir: Path = Path("data/research_reports"),
        force_reprocess: bool = False,
        dry_run: bool = False,
        clear_db: bool = False,
        clear_checkpoints: bool = False,
        build_indices: bool = False,
    ):
        """Run the production pipeline with optional database clearing."""

        # Fetch existing companies from database
        await self.fetch_existing_companies()

        # Collect all documents
        all_files = []
        for base_dir, doc_type in [
            (annual_reports_dir, "annual_report"),
            (research_reports_dir, "research_report"),
        ]:
            if base_dir.exists():
                for pattern in ["**/*.md", "**/*.txt"]:
                    all_files.extend(base_dir.glob(pattern))

        self.stats["total_files"] = len(all_files)
        console.print(f"Found {len(all_files)} total files")

        # Check each file
        to_process = []
        for file_path in all_files:
            db_record, doc_state = await self.check_document_state(file_path)

            if force_reprocess or doc_state.needs_reprocessing(
                db_record, self.existing_companies, self.extract_company_code_from_file
            ):
                to_process.append((file_path, doc_state, db_record is not None))
            else:
                self.stats["skipped"] += 1

        console.print(f"\nFiles to process: {len(to_process)}")
        console.print(f"Files to skip: {self.stats['skipped']}")

        if dry_run:
            console.print("\n[yellow]Dry run - no processing performed[/yellow]")

            # Count already extracted files
            already_extracted_count = 0
            for base_dir, doc_type in [
                (annual_reports_dir, "annual_report"),
                (research_reports_dir, "research_report"),
            ]:
                if base_dir.exists():
                    for pattern in ["**/*.md", "**/*.txt"]:
                        for file_path in base_dir.glob(pattern):
                            output_path = Path(
                                f"data/extracted/{doc_type}s/{file_path.stem}_extracted.json"
                            )
                            if output_path.exists():
                                already_extracted_count += 1

            console.print("\n[bold]Overall Statistics:[/bold]")
            console.print(f"  - Total files found: {self.stats['total_files']}")
            console.print(
                f"  - Already extracted (JSON exists): {already_extracted_count}"
            )
            console.print(f"  - Truly need processing: {len(to_process)}")
            console.print(
                f"  - Will skip (already extracted): {self.stats['total_files'] - len(to_process)}"
            )

            # Analyze which files would skip LLM extraction
            skip_llm_count = 0
            need_llm_count = 0
            company_unknown_count = 0

            console.print("\n[bold]Analysis of LLM extraction requirements:[/bold]")

            for file_path, doc_state, is_reprocess in to_process:
                # Try to extract company code
                company_code = self.extract_company_code_from_file(file_path)

                if company_code and company_code in self.existing_companies:
                    skip_llm_count += 1
                elif company_code:
                    need_llm_count += 1
                else:
                    company_unknown_count += 1

            console.print(
                f"  - Files from existing companies (skip LLM): {skip_llm_count}"
            )
            console.print(f"  - Files from new companies (need LLM): {need_llm_count}")
            console.print(
                f"  - Files with unknown company code: {company_unknown_count}"
            )

            # Show sample files
            console.print("\n[bold]Sample files to process:[/bold]")
            sample_count = 0
            for file_path, doc_state, is_reprocess in to_process:
                if sample_count >= 10:
                    break

                company_code = self.extract_company_code_from_file(file_path)
                status = "reprocess" if is_reprocess else "new"

                if company_code and company_code in self.existing_companies:
                    llm_status = "[green]skip LLM[/green]"
                elif company_code:
                    llm_status = "[red]need LLM[/red]"
                else:
                    llm_status = "[yellow]unknown[/yellow]"

                console.print(
                    f"  - {file_path.name} ({status}, {company_code or 'no code'}, {llm_status})"
                )
                sample_count += 1

            if len(to_process) > 10:
                console.print(f"  ... and {len(to_process) - 10} more")
            return

        # Process documents with parallel extraction
        console.print(
            f"\n[bold]Processing with {self.max_concurrent} concurrent extractions[/bold]"
        )

        # Create semaphore for concurrent limit
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def process_with_semaphore(file_path, doc_state, is_reprocess):
            async with semaphore:
                # Try to acquire file lock
                if not await self.file_lock.acquire(file_path):
                    logger.warning(
                        f"Could not acquire lock for {file_path.name}, skipping"
                    )
                    self.stats["locked_skip"] += 1
                    return False

                try:
                    if is_reprocess:
                        self.stats["reprocessed"] += 1

                    success = await self.process_document(file_path, doc_state)

                    if success:
                        self.stats["processed"] += 1
                    else:
                        self.stats["failed"] += 1

                    return success
                finally:
                    # Always release lock
                    self.file_lock.release(file_path)

        # Create tasks for all documents
        tasks = [
            process_with_semaphore(file_path, doc_state, is_reprocess)
            for file_path, doc_state, is_reprocess in to_process
        ]

        # Process with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Processing documents...", total=len(to_process))

            # Use asyncio.as_completed for real-time progress updates
            for coro in asyncio.as_completed(tasks):
                await coro
                progress.advance(task)

        # Display results
        self._display_results()

        # Build vector indices if requested
        if build_indices and not dry_run:
            await self.create_vector_indices()

        # Clean up any remaining locks
        self.file_lock.release_all()

    def _display_results(self):
        """Display processing results."""
        console.print("\n[bold]=== PIPELINE RESULTS ===[/bold]")

        table = Table()
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        if self.stats["db_cleared"]:
            table.add_row("Database Cleared", "✅")
        if self.stats["checkpoints_cleared"]:
            table.add_row("Checkpoints Cleared", "✅")

        table.add_row("Total Files", str(self.stats["total_files"]))
        table.add_row("Processed", str(self.stats["processed"]))
        table.add_row("Reprocessed", str(self.stats["reprocessed"]))
        table.add_row("Skipped", str(self.stats["skipped"]))
        table.add_row("LLM Skipped", str(self.stats["llm_skipped"]))
        table.add_row("Lock Skipped", str(self.stats["locked_skip"]))
        table.add_row("Failed", str(self.stats["failed"]))

        if self.stats["indices_created"]:
            table.add_row("Vector Indices", "✅ Created")

        console.print(table)

        if self.stats["failed"] > 0:
            console.print(
                "\n[red]⚠️  Some documents failed processing. Check logs for details.[/red]"
            )
        else:
            console.print("\n[green]✅ Pipeline completed successfully![/green]")


@click.command()
@click.option(
    "--annual-reports-dir",
    type=click.Path(exists=True),
    default="data/annual_reports/2024",
    help="Annual reports directory (default: data/annual_reports/2024)",
)
@click.option(
    "--research-reports-dir",
    type=click.Path(exists=True),
    default="data/research_reports",
    help="Research reports directory",
)
@click.option(
    "--force-reprocess", is_flag=True, help="Force reprocessing of all documents"
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be processed without executing"
)
@click.option(
    "--clear-db", is_flag=True, help="Clear all database content before processing"
)
@click.option("--clear-checkpoints", is_flag=True, help="Clear all checkpoint files")
@click.option(
    "--build-indices", is_flag=True, help="Build vector indices after processing"
)
@click.option(
    "--full-rebuild",
    is_flag=True,
    help="Complete rebuild: clear DB, checkpoints, force reprocess, and build indices",
)
@click.option(
    "--max-concurrent",
    type=int,
    default=5,
    help="Maximum concurrent LLM extractions (default: 5)",
)
def main(
    annual_reports_dir,
    research_reports_dir,
    force_reprocess,
    dry_run,
    clear_db,
    clear_checkpoints,
    build_indices,
    full_rebuild,
    max_concurrent,
):
    """Production-ready document processing pipeline.

    Examples:
        # Normal incremental processing
        python production_pipeline.py

        # Full rebuild from scratch
        python production_pipeline.py --full-rebuild

        # Clear DB and reprocess everything
        python production_pipeline.py --clear-db --force-reprocess

        # Dry run to see what would be processed
        python production_pipeline.py --dry-run
    """
    pipeline = ProductionPipeline(max_concurrent=max_concurrent)

    # Handle full rebuild flag
    if full_rebuild:
        clear_db = True
        clear_checkpoints = True
        force_reprocess = True
        build_indices = True

    async def run_pipeline():
        # Clear operations if requested
        if clear_db and not dry_run:
            await pipeline.clear_database_content()

        if clear_checkpoints and not dry_run:
            pipeline.clear_checkpoints()

        # Run the main pipeline
        await pipeline.run(
            Path(annual_reports_dir),
            Path(research_reports_dir),
            force_reprocess,
            dry_run,
            clear_db,
            clear_checkpoints,
            build_indices,
        )

    asyncio.run(run_pipeline())


if __name__ == "__main__":
    main()
