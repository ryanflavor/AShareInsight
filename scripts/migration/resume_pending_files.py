#!/usr/bin/env python3
"""
恢复处理pending状态的文件
"""

import asyncio
import json
import sys
from pathlib import Path

import click
import structlog
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.infrastructure.persistence.postgres.connection import get_session

logger = structlog.get_logger(__name__)
console = Console()


async def find_pending_files():
    """查找所有pending状态的文件"""
    checkpoint_dir = Path("data/temp/checkpoints")

    # 获取数据库中已存在的文件
    async with get_session() as session:
        result = await session.execute(
            text("""
            SELECT file_path FROM source_documents WHERE file_path IS NOT NULL
        """)
        )
        db_files = {row[0] for row in result}

    pending_files = []
    failed_files = []

    for cp_file in checkpoint_dir.glob("*.json"):
        try:
            with open(cp_file) as f:
                data = json.load(f)

            file_path = data.get("file_path")
            if not file_path or file_path in db_files:
                continue

            stages = data.get("stages", {})
            archive_status = stages.get("archive", {}).get("status", "pending")

            if archive_status == "failed":
                failed_files.append(
                    {
                        "checkpoint": cp_file,
                        "file_path": file_path,
                        "error": stages.get("archive", {}).get(
                            "error", "Unknown error"
                        ),
                    }
                )
            elif archive_status == "pending":
                extraction_status = stages.get("extraction", {}).get(
                    "status", "pending"
                )
                if extraction_status == "success":
                    # 提取成功但归档未完成
                    pending_files.append(
                        {
                            "checkpoint": cp_file,
                            "file_path": file_path,
                            "extracted_json": Path(
                                stages.get("extraction", {}).get("output_path", "")
                            ),
                        }
                    )
        except Exception as e:
            logger.warning(f"读取checkpoint失败 {cp_file}: {e}")

    return pending_files, failed_files


async def resume_pending_file(file_info: dict):
    """恢复处理单个pending文件"""
    try:
        file_path = Path(file_info["file_path"])
        extracted_json = file_info["extracted_json"]

        if not extracted_json.exists():
            logger.warning(f"提取的JSON文件不存在: {extracted_json}")
            return False

        # 读取提取的数据
        with open(extracted_json) as f:
            extracted_data = json.load(f)

        # 准备归档
        # 计算文件哈希
        import hashlib
        from datetime import date

        from src.application.use_cases.archive_extraction_result import (
            ArchiveExtractionResultUseCase,
        )
        from src.infrastructure.factories import create_standalone_fusion_use_case
        from src.infrastructure.persistence.postgres.source_document_repository import (
            PostgresSourceDocumentRepository,
        )

        with open(file_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # 准备metadata
        doc_date = date(2024, 12, 31)  # 默认日期
        company_code = extracted_data["extraction_data"].get("company_code", "unknown")
        doc_type = extracted_data.get("document_type", "annual_report")

        metadata = {
            "company_code": company_code,
            "doc_type": doc_type,
            "doc_date": doc_date,
            "report_title": extracted_data["extraction_data"].get(
                "company_name_full", file_path.name
            ),
            "file_path": str(file_path),
            "file_hash": file_hash,
            "original_content": None,  # 可选
        }

        # 归档到数据库
        async with get_session() as session:
            repository = PostgresSourceDocumentRepository(session)

            # 创建融合用例
            fusion_use_case = await create_standalone_fusion_use_case()

            archive_use_case = ArchiveExtractionResultUseCase(
                repository=repository, update_master_data_use_case=fusion_use_case
            )

            doc_id = await archive_use_case.execute(
                raw_llm_output=extracted_data, metadata=metadata
            )

            if isinstance(doc_id, UUID):
                logger.info(f"成功归档: {file_path.name} -> {doc_id}")

                # 更新checkpoint
                checkpoint = file_info["checkpoint"]
                with open(checkpoint) as f:
                    cp_data = json.load(f)

                cp_data["stages"]["archive"]["status"] = "success"
                cp_data["stages"]["archive"]["doc_id"] = str(doc_id)

                with open(checkpoint, "w") as f:
                    json.dump(cp_data, f, indent=2)

                return True
            else:
                logger.warning(f"归档跳过: {file_path.name} - {doc_id}")
                return False

    except Exception as e:
        logger.error(f"恢复文件失败 {file_info['file_path']}: {e}")
        return False


@click.command()
@click.option("--dry-run", is_flag=True, help="只显示要处理的文件，不实际处理")
@click.option("--limit", default=-1, help="限制处理的文件数量，-1表示全部")
def main(dry_run: bool, limit: int):
    """恢复处理pending状态的文件"""

    async def run():
        pending_files, failed_files = await find_pending_files()

        console.print(f"\n找到 {len(pending_files)} 个pending文件")
        console.print(f"找到 {len(failed_files)} 个失败文件")

        if failed_files:
            console.print("\n[red]失败的文件:[/red]")
            for f in failed_files[:5]:
                console.print(f"  - {Path(f['file_path']).name}: {f['error']}")
            if len(failed_files) > 5:
                console.print(f"  ... 还有 {len(failed_files) - 5} 个")

        if not pending_files:
            console.print("\n[green]没有需要恢复的文件[/green]")
            return

        to_process = pending_files[:limit] if limit > 0 else pending_files

        console.print(f"\n将处理 {len(to_process)} 个文件")

        if dry_run:
            console.print("\n[yellow]DRY RUN - 不会实际处理[/yellow]")
            for f in to_process[:10]:
                console.print(f"  - {Path(f['file_path']).name}")
            if len(to_process) > 10:
                console.print(f"  ... 还有 {len(to_process) - 10} 个")
            return

        # 处理文件
        success_count = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("处理pending文件...", total=len(to_process))

            for file_info in to_process:
                if await resume_pending_file(file_info):
                    success_count += 1
                progress.advance(task)

        console.print(
            f"\n[green]处理完成！成功: {success_count}/{len(to_process)}[/green]"
        )

    asyncio.run(run())


if __name__ == "__main__":
    from uuid import UUID

    main()
