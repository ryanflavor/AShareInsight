#!/usr/bin/env python3
"""
修复缺失公司代码的文件
"""

import asyncio
import json
from pathlib import Path

import click
from rich.console import Console

console = Console()

# 手动映射公司名称到股票代码
COMPANY_CODE_MAPPING = {
    "永顺生物": "839729",  # 北交所
    "三友科技": "834475",  # 北交所/新三板
    "奥迪威": "832491",  # 北交所/新三板
}


def fix_extraction_files():
    """修复提取文件中的公司代码"""

    fixed_count = 0

    for company_short_name, company_code in COMPANY_CODE_MAPPING.items():
        # 查找对应的提取文件
        pattern = f"*{company_short_name}*_extracted.json"

        for extract_dir in [
            "data/extracted/annual_reports",
            "data/extracted/annual_report",
        ]:
            extract_path = Path(extract_dir)
            if not extract_path.exists():
                continue

            for json_file in extract_path.glob(pattern):
                console.print(f"\n处理文件: {json_file.name}")

                # 读取JSON
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)

                # 检查是否需要修复
                current_code = data.get("extraction_data", {}).get("company_code", "")
                if not current_code:
                    console.print(f"  当前公司代码为空，修复为: {company_code}")

                    # 修复公司代码
                    if "extraction_data" not in data:
                        data["extraction_data"] = {}
                    data["extraction_data"]["company_code"] = company_code

                    # 保存回文件
                    with open(json_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)

                    fixed_count += 1
                    console.print("  ✅ 已修复")
                else:
                    console.print(f"  公司代码已存在: {current_code}")

    return fixed_count


async def retry_failed_archives():
    """重试失败的归档"""
    import hashlib
    import sys
    from datetime import date

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from src.application.use_cases.archive_extraction_result import (
        ArchiveExtractionResultUseCase,
    )
    from src.infrastructure.factories import create_standalone_fusion_use_case
    from src.infrastructure.persistence.postgres.connection import get_session
    from src.infrastructure.persistence.postgres.source_document_repository import (
        PostgresSourceDocumentRepository,
    )

    success_count = 0

    for company_short_name, company_code in COMPANY_CODE_MAPPING.items():
        # 查找checkpoint文件
        checkpoint_pattern = f"*{company_short_name}*_checkpoint.json"
        checkpoint_dir = Path("data/temp/checkpoints")

        for checkpoint_file in checkpoint_dir.glob(checkpoint_pattern):
            console.print(f"\n处理checkpoint: {checkpoint_file.name}")

            # 读取checkpoint
            with open(checkpoint_file) as f:
                checkpoint_data = json.load(f)

            # 检查状态
            archive_status = (
                checkpoint_data.get("stages", {}).get("archive", {}).get("status")
            )
            if archive_status != "failed":
                console.print(f"  状态不是failed: {archive_status}")
                continue

            # 获取提取文件路径
            extraction_path = (
                checkpoint_data.get("stages", {})
                .get("extraction", {})
                .get("output_path")
            )
            if not extraction_path or not Path(extraction_path).exists():
                console.print("  找不到提取文件")
                continue

            # 读取提取的数据
            with open(extraction_path, encoding="utf-8") as f:
                extracted_data = json.load(f)

            # 确保公司代码已修复
            if not extracted_data.get("extraction_data", {}).get("company_code"):
                console.print("  公司代码仍为空，跳过")
                continue

            # 准备归档
            file_path = Path(checkpoint_data["file_path"])

            # 计算文件哈希
            with open(file_path, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            # 准备metadata
            metadata = {
                "company_code": company_code,
                "doc_type": "annual_report",
                "doc_date": date(2024, 12, 31),
                "report_title": extracted_data["extraction_data"].get(
                    "company_name_full", file_path.name
                ),
                "file_path": str(file_path),
                "file_hash": file_hash,
                "original_content": None,
            }

            try:
                # 归档到数据库
                async with get_session() as session:
                    repository = PostgresSourceDocumentRepository(session)
                    fusion_use_case = await create_standalone_fusion_use_case()

                    archive_use_case = ArchiveExtractionResultUseCase(
                        repository=repository,
                        update_master_data_use_case=fusion_use_case,
                    )

                    doc_id = await archive_use_case.execute(
                        raw_llm_output=extracted_data, metadata=metadata
                    )

                    console.print(f"  ✅ 归档成功: {doc_id}")

                    # 更新checkpoint
                    checkpoint_data["stages"]["archive"]["status"] = "success"
                    checkpoint_data["stages"]["archive"]["doc_id"] = str(doc_id)

                    with open(checkpoint_file, "w") as f:
                        json.dump(checkpoint_data, f, indent=2)

                    success_count += 1

            except Exception as e:
                console.print(f"  ❌ 归档失败: {e}")

    return success_count


@click.command()
@click.option("--fix-only", is_flag=True, help="只修复JSON文件，不重试归档")
def main(fix_only: bool):
    """修复缺失公司代码的文件并重试归档"""

    console.print("[bold]修复缺失的公司代码[/bold]\n")

    # 修复提取文件
    fixed = fix_extraction_files()
    console.print(f"\n总共修复了 {fixed} 个文件")

    if not fix_only:
        # 重试归档
        console.print("\n[bold]重试失败的归档[/bold]")
        success = asyncio.run(retry_failed_archives())
        console.print(f"\n成功归档 {success} 个文件")


if __name__ == "__main__":
    main()
