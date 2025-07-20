#!/usr/bin/env python3
"""
端到端数据处理管道：从原始文本到数据库
支持增量处理、批量处理、错误恢复等功能

使用方式:
    python scripts/run_end_to_end_pipeline.py              # 处理所有新文件
    python scripts/run_end_to_end_pipeline.py --force      # 强制重新处理所有文件
    python scripts/run_end_to_end_pipeline.py --dry-run    # 仅显示将要处理的文件
    python scripts/run_end_to_end_pipeline.py --type annual_report  # 仅处理年报
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
import structlog
from rich.console import Console
from rich.table import Table
from sqlalchemy import select, text

from src.application.use_cases.batch_extract_documents import (
    BatchExtractDocumentsUseCase,
)
from src.infrastructure.llm import GeminiLLMAdapter
from src.infrastructure.persistence.postgres.connection import get_session
from src.infrastructure.persistence.postgres.models import SourceDocumentModel
from src.shared.config.settings import Settings

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)
console = Console()


class IncrementalPipeline:
    """增量数据处理管道"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.processed_files: set[str] = set()
        self.new_files: list[Path] = []

    async def load_processed_files(self) -> None:
        """从数据库加载已处理文件列表"""
        async with get_session() as session:
            result = await session.execute(
                select(SourceDocumentModel.file_path).distinct()
            )
            self.processed_files = {row[0] for row in result}
            logger.info("loaded_processed_files", count=len(self.processed_files))

    def scan_new_files(
        self, doc_type: str | None = None
    ) -> tuple[list[Path], list[Path]]:
        """扫描新文件

        Returns:
            (annual_reports, research_reports) 两个列表
        """
        annual_reports = []
        research_reports = []

        # 扫描年报
        if doc_type in (None, "annual_report"):
            annual_dir = Path("data/annual_reports/2024")
            for file_path in annual_dir.glob("*.md"):
                if str(file_path) not in self.processed_files:
                    annual_reports.append(file_path)

        # 扫描研报
        if doc_type in (None, "research_report"):
            research_dir = Path("data/research_reports/2024")
            for file_path in research_dir.glob("*.txt"):
                if str(file_path) not in self.processed_files:
                    research_reports.append(file_path)

        return annual_reports, research_reports

    async def process_batch(
        self, files: list[Path], doc_type: str, dry_run: bool = False
    ) -> dict:
        """批量处理文件"""
        if not files:
            return {"processed": 0, "failed": 0}

        if dry_run:
            console.print(
                f"\n[yellow]Would process {len(files)} {doc_type} files:[/yellow]"
            )
            for f in files[:10]:  # 最多显示10个
                console.print(f"  - {f.name}")
            if len(files) > 10:
                console.print(f"  ... and {len(files) - 10} more")
            return {"processed": 0, "failed": 0}

        # 初始化批处理器
        llm_service = GeminiLLMAdapter(self.settings)
        batch_processor = BatchExtractDocumentsUseCase(
            llm_service,
            self.settings,
            None,  # archive_repository will be created per file
        )

        # 执行批处理
        console.print(f"\n[cyan]Processing {len(files)} {doc_type} files...[/cyan]")
        results = await batch_processor.execute(
            file_paths=files, document_type=doc_type, resume=True
        )

        return {"processed": results["successful"], "failed": results["failed"]}

    async def generate_report(self) -> None:
        """生成处理报告"""
        async with get_session() as session:
            # 总体统计
            result = await session.execute(
                text("""
                SELECT 
                    doc_type,
                    COUNT(*) as count,
                    MAX(created_at) as latest
                FROM source_documents
                GROUP BY doc_type
            """)
            )

            table = Table(title="Database Summary")
            table.add_column("Document Type", style="cyan")
            table.add_column("Count", style="green")
            table.add_column("Latest Update", style="yellow")

            total = 0
            for row in result:
                table.add_row(
                    row.doc_type,
                    str(row.count),
                    row.latest.strftime("%Y-%m-%d %H:%M:%S") if row.latest else "N/A",
                )
                total += row.count

            console.print(table)
            console.print(
                f"\n[bold green]Total documents in database: {total}[/bold green]"
            )

            # 最近处理的文档
            cutoff_time = datetime.now() - timedelta(minutes=10)
            result = await session.execute(
                text("""
                SELECT 
                    company_code,
                    doc_type,
                    report_title,
                    created_at
                FROM source_documents
                WHERE created_at > :cutoff_time
                ORDER BY created_at DESC
                LIMIT 10
            """),
                {"cutoff_time": cutoff_time},
            )

            recent = list(result)
            if recent:
                table = Table(title="Recently Processed (last 10 minutes)")
                table.add_column("Time", style="cyan")
                table.add_column("Company", style="green")
                table.add_column("Type", style="yellow")
                table.add_column("Title", style="white")

                for row in recent:
                    table.add_row(
                        row.created_at.strftime("%H:%M:%S"),
                        row.company_code,
                        row.doc_type,
                        row.report_title[:50] + "..."
                        if len(row.report_title) > 50
                        else row.report_title,
                    )

                console.print("\n")
                console.print(table)


@click.command()
@click.option("--force", is_flag=True, help="Force reprocess all files")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be processed without actually processing",
)
@click.option(
    "--type",
    "doc_type",
    type=click.Choice(["annual_report", "research_report"]),
    help="Process only specific document type",
)
def main(force: bool, dry_run: bool, doc_type: str | None):
    """端到端数据处理管道：从原始文本到数据库"""

    async def run_pipeline():
        settings = Settings()

        # 检查API密钥
        if not settings.llm.gemini_api_key.get_secret_value():
            console.print("[red]Error: GEMINI_API_KEY not set[/red]")
            console.print("Please set: export GEMINI_API_KEY=<your-api-key>")
            sys.exit(1)

        pipeline = IncrementalPipeline(settings)

        # 加载已处理文件（除非强制重新处理）
        if not force:
            with console.status(
                "[cyan]Loading processed files from database...[/cyan]"
            ):
                await pipeline.load_processed_files()
        else:
            console.print("[yellow]Force mode: Will reprocess all files[/yellow]")
            pipeline.processed_files = set()

        # 扫描新文件
        console.print("\n[cyan]Scanning for files...[/cyan]")
        annual_reports, research_reports = pipeline.scan_new_files(doc_type)

        total_new = len(annual_reports) + len(research_reports)
        if total_new == 0:
            console.print("[green]No new files to process![/green]")
            if not force:
                console.print("Use --force to reprocess existing files")
        else:
            console.print(f"\n[bold]Found {total_new} new files:[/bold]")
            if annual_reports:
                console.print(f"  - {len(annual_reports)} annual reports")
            if research_reports:
                console.print(f"  - {len(research_reports)} research reports")

        # 处理文件
        total_processed = 0
        total_failed = 0

        if annual_reports:
            results = await pipeline.process_batch(
                annual_reports, "annual_report", dry_run
            )
            total_processed += results["processed"]
            total_failed += results["failed"]

        if research_reports:
            results = await pipeline.process_batch(
                research_reports, "research_report", dry_run
            )
            total_processed += results["processed"]
            total_failed += results["failed"]

        # 生成报告
        if not dry_run and (total_processed > 0 or force):
            console.print("\n[cyan]Generating report...[/cyan]")
            await pipeline.generate_report()

        # 总结
        if not dry_run:
            console.print("\n" + "=" * 60)
            console.print("[bold]Pipeline Summary:[/bold]")
            console.print(f"  Files processed: {total_processed}")
            if total_failed > 0:
                console.print(f"  Files failed: [red]{total_failed}[/red]")
            console.print("=" * 60)

    # 运行异步管道
    asyncio.run(run_pipeline())


if __name__ == "__main__":
    main()
