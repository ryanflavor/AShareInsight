#!/usr/bin/env python3
"""
安全地清理重复文档 - 分批处理，保留checkpoint信息
"""

import asyncio
import sys
from pathlib import Path

import click
import structlog
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.infrastructure.persistence.postgres.connection import get_session

logger = structlog.get_logger(__name__)
console = Console()


async def analyze_batch(session, limit: int = 100):
    """分析一批重复数据"""
    query = text("""
        WITH duplicates AS (
            SELECT 
                file_path,
                COUNT(*) as count,
                MIN(created_at) as first_created,
                ARRAY_AGG(doc_id ORDER BY created_at) as doc_ids,
                ARRAY_AGG(file_hash ORDER BY created_at) as file_hashes,
                ARRAY_AGG(company_code ORDER BY created_at) as company_codes
            FROM source_documents
            WHERE file_path IS NOT NULL
            GROUP BY file_path
            HAVING COUNT(*) > 1
        )
        SELECT * FROM duplicates
        ORDER BY first_created
        LIMIT :limit
    """)

    result = await session.execute(query, {"limit": limit})
    return [dict(row._mapping) for row in result]


async def cleanup_batch(session, batch_data: list[dict], dry_run: bool = True):
    """清理一批重复数据"""
    docs_to_delete = []
    reference_updates = {}

    for dup in batch_data:
        # 保留最早的文档
        keep_id = dup["doc_ids"][0]
        delete_ids = dup["doc_ids"][1:]

        docs_to_delete.extend(delete_ids)
        reference_updates[keep_id] = delete_ids

    if not dry_run and docs_to_delete:
        # 更新business_concepts_master引用
        for keep_id, delete_ids in reference_updates.items():
            update_query = text("""
                UPDATE business_concepts_master
                SET last_updated_from_doc_id = :keep_id
                WHERE last_updated_from_doc_id = ANY(:delete_ids)
            """)
            await session.execute(
                update_query, {"keep_id": keep_id, "delete_ids": delete_ids}
            )

        # 删除重复文档
        delete_query = text("""
            DELETE FROM source_documents
            WHERE doc_id = ANY(:doc_ids)
        """)
        result = await session.execute(delete_query, {"doc_ids": docs_to_delete})

        await session.commit()
        return result.rowcount

    return len(docs_to_delete)


async def safe_cleanup(
    batch_size: int = 100, dry_run: bool = True, max_batches: int = -1
):
    """安全的批量清理流程"""
    async with get_session() as session:
        total_deleted = 0
        batch_num = 0

        # 获取总重复数
        count_query = text("""
            SELECT COUNT(*) FROM (
                SELECT file_path
                FROM source_documents
                WHERE file_path IS NOT NULL
                GROUP BY file_path
                HAVING COUNT(*) > 1
            ) as dups
        """)
        result = await session.execute(count_query)
        total_duplicates = result.scalar()

        console.print(f"\n[bold]总共有 {total_duplicates} 个文件存在重复[/bold]")

        if dry_run:
            console.print("[yellow]DRY RUN 模式 - 不会实际删除数据[/yellow]\n")
        else:
            console.print("[red]实际执行模式 - 将删除重复数据！[/red]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("处理重复数据...", total=total_duplicates)

            while True:
                batch_num += 1

                # 获取一批重复数据
                batch_data = await analyze_batch(session, batch_size)

                if not batch_data:
                    break

                if max_batches > 0 and batch_num > max_batches:
                    console.print(f"\n达到最大批次限制 ({max_batches})")
                    break

                # 显示批次信息
                console.print(f"\n批次 {batch_num}: 处理 {len(batch_data)} 个重复文件")

                # 清理这批数据
                deleted_count = await cleanup_batch(session, batch_data, dry_run)
                total_deleted += deleted_count

                progress.update(task, advance=len(batch_data))

                if not dry_run:
                    # 实际执行时，每批次后暂停一下
                    await asyncio.sleep(0.5)

        # 显示结果
        console.print("\n[bold]清理完成！[/bold]")
        console.print(f"处理批次数: {batch_num}")
        console.print(f"删除文档数: {total_deleted}")

        # 验证结果
        if not dry_run:
            result = await session.execute(count_query)
            remaining = result.scalar()
            console.print(f"剩余重复文件数: {remaining}")


async def verify_integrity():
    """验证数据完整性"""
    async with get_session() as session:
        # 检查孤立的business_concepts引用
        orphan_query = text("""
            SELECT COUNT(*) 
            FROM business_concepts_master bcm
            WHERE bcm.last_updated_from_doc_id NOT IN (
                SELECT doc_id FROM source_documents
            )
        """)
        result = await session.execute(orphan_query)
        orphan_count = result.scalar()

        if orphan_count > 0:
            console.print(f"[red]⚠️ 发现 {orphan_count} 个孤立的概念引用！[/red]")
        else:
            console.print("[green]✅ 没有孤立的概念引用[/green]")

        # 检查数据统计
        stats_query = text("""
            SELECT 
                (SELECT COUNT(*) FROM source_documents) as total_docs,
                (SELECT COUNT(*) FROM companies) as total_companies,
                (SELECT COUNT(*) FROM business_concepts_master) as total_concepts,
                (SELECT COUNT(DISTINCT company_code) FROM source_documents) as docs_companies
        """)
        result = await session.execute(stats_query)
        stats = result.fetchone()

        table = Table(title="数据库统计")
        table.add_column("指标", style="cyan")
        table.add_column("数量", style="yellow")

        table.add_row("总文档数", str(stats.total_docs))
        table.add_row("总公司数", str(stats.total_companies))
        table.add_row("总概念数", str(stats.total_concepts))
        table.add_row("有文档的公司数", str(stats.docs_companies))

        console.print(table)


@click.command()
@click.option("--batch-size", default=100, help="每批处理的文件数")
@click.option("--dry-run/--execute", default=True, help="是否为演练模式")
@click.option("--max-batches", default=-1, help="最大处理批次数，-1表示全部")
@click.option("--verify", is_flag=True, help="验证数据完整性")
def main(batch_size: int, dry_run: bool, max_batches: int, verify: bool):
    """安全地清理重复文档

    特点：
    1. 分批处理，避免大事务
    2. 保留最早的文档（有checkpoint的）
    3. 自动更新business_concepts_master引用
    4. 支持dry-run模式预览

    使用示例：
        # 预览将要删除的数据
        python safe_cleanup_duplicates.py

        # 实际执行清理（前10批）
        python safe_cleanup_duplicates.py --execute --max-batches 10

        # 清理所有重复数据
        python safe_cleanup_duplicates.py --execute

        # 验证数据完整性
        python safe_cleanup_duplicates.py --verify
    """
    if verify:
        asyncio.run(verify_integrity())
    else:
        asyncio.run(safe_cleanup(batch_size, dry_run, max_batches))


if __name__ == "__main__":
    main()
