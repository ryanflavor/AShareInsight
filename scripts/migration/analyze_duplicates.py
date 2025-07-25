#!/usr/bin/env python3
"""
分析重复数据的详细情况，帮助决策如何处理
"""

import asyncio
import sys
from pathlib import Path

import structlog
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.infrastructure.persistence.postgres.connection import get_session

logger = structlog.get_logger(__name__)
console = Console()


async def analyze_duplicates():
    """分析重复数据的详细情况"""
    async with get_session() as session:
        # 1. 分析file_path重复的模式
        console.print("\n[bold blue]分析file_path重复模式...[/bold blue]")

        query = text("""
            SELECT 
                file_path,
                COUNT(*) as count,
                MIN(created_at) as first_created,
                MAX(created_at) as last_created,
                ARRAY_AGG(DISTINCT file_hash) as unique_hashes,
                ARRAY_AGG(created_at ORDER BY created_at) as created_times
            FROM source_documents
            WHERE file_path IS NOT NULL
            GROUP BY file_path
            HAVING COUNT(*) > 1
            ORDER BY count DESC, file_path
            LIMIT 20
        """)

        result = await session.execute(query)
        duplicates = result.fetchall()

        # 显示重复模式
        table = Table(title="File Path重复分析（前20个）")
        table.add_column("文件路径", style="cyan", no_wrap=False)
        table.add_column("重复数", style="yellow")
        table.add_column("时间跨度", style="green")
        table.add_column("不同哈希数", style="red")

        for dup in duplicates:
            file_name = Path(dup.file_path).name
            time_diff = dup.last_created - dup.first_created
            unique_hash_count = len(dup.unique_hashes)

            table.add_row(
                file_name, str(dup.count), str(time_diff), str(unique_hash_count)
            )

        console.print(table)

        # 2. 分析创建时间分布
        console.print("\n[bold blue]分析重复创建的时间分布...[/bold blue]")

        time_query = text("""
            WITH time_diffs AS (
                SELECT 
                    file_path,
                    LAG(created_at) OVER (PARTITION BY file_path ORDER BY created_at) as prev_created,
                    created_at,
                    created_at - LAG(created_at) OVER (PARTITION BY file_path ORDER BY created_at) as time_diff
                FROM source_documents
                WHERE file_path IN (
                    SELECT file_path 
                    FROM source_documents 
                    GROUP BY file_path 
                    HAVING COUNT(*) > 1
                )
            )
            SELECT 
                CASE 
                    WHEN time_diff < INTERVAL '1 second' THEN '< 1秒'
                    WHEN time_diff < INTERVAL '1 minute' THEN '< 1分钟'
                    WHEN time_diff < INTERVAL '1 hour' THEN '< 1小时'
                    ELSE '> 1小时'
                END as time_range,
                COUNT(*) as count
            FROM time_diffs
            WHERE time_diff IS NOT NULL
            GROUP BY time_range
            ORDER BY count DESC
        """)

        result = await session.execute(time_query)
        time_dist = result.fetchall()

        console.print("\n重复创建的时间间隔分布：")
        for row in time_dist:
            console.print(f"  {row.time_range}: {row.count} 次")

        # 3. 分析哪些公司受影响最大
        console.print("\n[bold blue]分析受影响的公司...[/bold blue]")

        company_query = text("""
            SELECT 
                company_code,
                COUNT(*) as total_docs,
                COUNT(DISTINCT file_path) as unique_files,
                COUNT(*) - COUNT(DISTINCT file_path) as duplicate_count
            FROM source_documents
            GROUP BY company_code
            HAVING COUNT(*) > COUNT(DISTINCT file_path)
            ORDER BY duplicate_count DESC
            LIMIT 10
        """)

        result = await session.execute(company_query)
        companies = result.fetchall()

        table2 = Table(title="受影响最大的公司（前10个）")
        table2.add_column("公司代码", style="cyan")
        table2.add_column("总文档数", style="yellow")
        table2.add_column("唯一文件数", style="green")
        table2.add_column("重复数", style="red")

        for comp in companies:
            table2.add_row(
                comp.company_code,
                str(comp.total_docs),
                str(comp.unique_files),
                str(comp.duplicate_count),
            )

        console.print(table2)

        # 4. 统计business_concepts_master的引用情况
        console.print(
            "\n[bold blue]分析business_concepts_master引用情况...[/bold blue]"
        )

        ref_query = text("""
            SELECT 
                COUNT(DISTINCT bcm.concept_id) as total_concepts,
                COUNT(DISTINCT bcm.last_updated_from_doc_id) as unique_doc_refs,
                COUNT(DISTINCT sd.doc_id) as total_docs_with_concepts
            FROM business_concepts_master bcm
            LEFT JOIN source_documents sd ON bcm.last_updated_from_doc_id = sd.doc_id
        """)

        result = await session.execute(ref_query)
        ref_stats = result.fetchone()

        console.print("\n业务概念统计：")
        console.print(f"  总概念数: {ref_stats.total_concepts}")
        console.print(f"  引用的唯一文档数: {ref_stats.unique_doc_refs}")
        console.print(f"  有概念的文档数: {ref_stats.total_docs_with_concepts}")

        # 5. 检查是否有孤立的引用
        orphan_query = text("""
            SELECT COUNT(*) as orphan_count
            FROM business_concepts_master bcm
            WHERE bcm.last_updated_from_doc_id NOT IN (
                SELECT doc_id FROM source_documents
            )
        """)

        result = await session.execute(orphan_query)
        orphan_count = result.scalar()

        if orphan_count > 0:
            console.print(f"\n[red]⚠️  发现 {orphan_count} 个孤立的概念引用！[/red]")
        else:
            console.print("\n[green]✅ 没有孤立的概念引用[/green]")


if __name__ == "__main__":
    asyncio.run(analyze_duplicates())
