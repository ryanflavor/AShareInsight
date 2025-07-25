#!/usr/bin/env python3
"""
Clean up duplicate documents in source_documents table.

This script identifies and removes duplicate documents based on:
1. file_path duplicates - keeps the oldest (first inserted)
2. company_code + doc_date + doc_type duplicates - keeps the one with valid file_hash
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

import click
import structlog
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.infrastructure.persistence.postgres.connection import get_session

logger = structlog.get_logger(__name__)
console = Console()


async def find_file_path_duplicates(session) -> list[dict[str, Any]]:
    """Find documents with duplicate file_path values."""
    query = text("""
        WITH duplicates AS (
            SELECT 
                file_path,
                COUNT(*) as count,
                MIN(created_at) as first_created,
                ARRAY_AGG(doc_id ORDER BY created_at) as doc_ids,
                ARRAY_AGG(file_hash ORDER BY created_at) as file_hashes,
                ARRAY_AGG(created_at ORDER BY created_at) as created_dates
            FROM source_documents
            WHERE file_path IS NOT NULL
            GROUP BY file_path
            HAVING COUNT(*) > 1
        )
        SELECT * FROM duplicates
        ORDER BY count DESC, file_path
    """)

    result = await session.execute(query)
    return [dict(row._mapping) for row in result]


async def find_logical_duplicates(session) -> list[dict[str, Any]]:
    """Find documents with duplicate (company_code, doc_date, doc_type)."""
    query = text("""
        WITH duplicates AS (
            SELECT 
                company_code,
                doc_date,
                doc_type,
                COUNT(*) as count,
                MIN(created_at) as first_created,
                ARRAY_AGG(doc_id ORDER BY created_at) as doc_ids,
                ARRAY_AGG(file_path ORDER BY created_at) as file_paths,
                ARRAY_AGG(file_hash ORDER BY created_at) as file_hashes,
                ARRAY_AGG(created_at ORDER BY created_at) as created_dates
            FROM source_documents
            GROUP BY company_code, doc_date, doc_type
            HAVING COUNT(*) > 1
        )
        SELECT * FROM duplicates
        ORDER BY count DESC, company_code, doc_date
    """)

    result = await session.execute(query)
    return [dict(row._mapping) for row in result]


async def update_business_concepts_references(
    session, old_doc_ids: list[str], new_doc_id: str
):
    """Update business concepts to reference the kept document."""
    update_query = text("""
        UPDATE business_concepts_master
        SET last_updated_from_doc_id = :new_doc_id
        WHERE last_updated_from_doc_id = ANY(:old_doc_ids)
    """)

    result = await session.execute(
        update_query, {"new_doc_id": new_doc_id, "old_doc_ids": old_doc_ids}
    )
    return result.rowcount


async def delete_duplicate_documents(session, doc_ids_to_delete: list[str]):
    """Delete duplicate documents by their IDs."""
    delete_query = text("""
        DELETE FROM source_documents
        WHERE doc_id = ANY(:doc_ids)
    """)

    result = await session.execute(delete_query, {"doc_ids": doc_ids_to_delete})
    return result.rowcount


async def cleanup_duplicates(dry_run: bool = True, verbose: bool = False):
    """Main cleanup function."""
    async with get_session() as session:
        # Find file_path duplicates
        console.print("\n[bold blue]Finding file_path duplicates...[/bold blue]")
        file_path_dups = await find_file_path_duplicates(session)

        if file_path_dups:
            console.print(f"Found {len(file_path_dups)} file paths with duplicates")

            # Display summary table
            table = Table(title="File Path Duplicates")
            table.add_column("File Path", style="cyan", no_wrap=False)
            table.add_column("Count", style="yellow")
            table.add_column("Keep", style="green")
            table.add_column("Delete", style="red")

            total_to_delete = 0
            docs_to_delete = []
            reference_updates = {}

            for dup in file_path_dups[:10]:  # Show first 10
                keep_id = dup["doc_ids"][0]  # Keep the oldest
                delete_ids = dup["doc_ids"][1:]  # Delete the rest
                total_to_delete += len(delete_ids)
                docs_to_delete.extend(delete_ids)

                # Track reference updates needed
                reference_updates[keep_id] = delete_ids

                file_path = Path(dup["file_path"]).name if dup["file_path"] else "None"
                table.add_row(
                    file_path,
                    str(dup["count"]),
                    f"ID: {str(keep_id)[:8]}...",
                    f"{len(delete_ids)} docs",
                )

                if verbose:
                    console.print(f"\nFile: {dup['file_path']}")
                    for i, doc_id in enumerate(dup["doc_ids"]):
                        status = "KEEP" if i == 0 else "DELETE"
                        console.print(
                            f"  [{status}] {doc_id} - "
                            f"Hash: {dup['file_hashes'][i][:16]}... - "
                            f"Created: {dup['created_dates'][i]}"
                        )

            if len(file_path_dups) > 10:
                console.print(f"\n... and {len(file_path_dups) - 10} more file paths")

            console.print(table)
            console.print(f"\nTotal documents to delete: {total_to_delete}")
        else:
            console.print("[green]No file_path duplicates found![/green]")
            docs_to_delete = []
            reference_updates = {}

        # Find logical duplicates (company + date + type)
        console.print("\n[bold blue]Finding logical duplicates...[/bold blue]")
        logical_dups = await find_logical_duplicates(session)

        if logical_dups:
            console.print(f"Found {len(logical_dups)} logical duplicate groups")

            # For logical duplicates, we need a different strategy
            # Keep the one with a valid file_hash and file_path
            table2 = Table(title="Logical Duplicates (Company + Date + Type)")
            table2.add_column("Company", style="cyan")
            table2.add_column("Date", style="yellow")
            table2.add_column("Type", style="magenta")
            table2.add_column("Count", style="yellow")
            table2.add_column("Resolution", style="green")

            for dup in logical_dups[:5]:
                # Find the best document to keep
                best_idx = 0
                for i, (file_path, file_hash) in enumerate(
                    zip(dup["file_paths"], dup["file_hashes"], strict=False)
                ):
                    if file_path and file_hash:
                        best_idx = i
                        break

                keep_id = dup["doc_ids"][best_idx]
                delete_ids = [
                    doc_id
                    for i, doc_id in enumerate(dup["doc_ids"])
                    if i != best_idx and doc_id not in docs_to_delete
                ]

                if delete_ids:
                    docs_to_delete.extend(delete_ids)
                    if keep_id in reference_updates:
                        reference_updates[keep_id].extend(delete_ids)
                    else:
                        reference_updates[keep_id] = delete_ids

                table2.add_row(
                    dup["company_code"],
                    str(dup["doc_date"]),
                    dup["doc_type"],
                    str(dup["count"]),
                    f"Keep idx {best_idx}, delete {len(delete_ids)}",
                )

            if len(logical_dups) > 5:
                console.print(f"\n... and {len(logical_dups) - 5} more groups")

            console.print(table2)
        else:
            console.print("[green]No logical duplicates found![/green]")

        # Execute cleanup
        if docs_to_delete:
            console.print(
                f"\n[bold]Total unique documents to delete: {len(set(docs_to_delete))}[/bold]"
            )

            if dry_run:
                console.print("\n[yellow]DRY RUN - No changes will be made[/yellow]")
                console.print("\nWould update business concept references:")
                for keep_id, delete_ids in reference_updates.items():
                    console.print(f"  {keep_id} <- {len(delete_ids)} references")
            else:
                if click.confirm("\nProceed with cleanup?", default=False):
                    try:
                        # Update references first
                        console.print(
                            "\n[bold]Updating business concept references...[/bold]"
                        )
                        total_refs_updated = 0
                        for keep_id, delete_ids in reference_updates.items():
                            refs_updated = await update_business_concepts_references(
                                session, delete_ids, keep_id
                            )
                            total_refs_updated += refs_updated

                        console.print(
                            f"✅ Updated {total_refs_updated} business concept references"
                        )

                        # Delete duplicate documents
                        console.print("\n[bold]Deleting duplicate documents...[/bold]")
                        unique_docs_to_delete = list(set(docs_to_delete))
                        deleted_count = await delete_duplicate_documents(
                            session, unique_docs_to_delete
                        )

                        await session.commit()
                        console.print(f"✅ Deleted {deleted_count} duplicate documents")

                        console.print(
                            "\n[green]Cleanup completed successfully![/green]"
                        )

                    except Exception as e:
                        await session.rollback()
                        console.print(f"\n[red]Error during cleanup: {e}[/red]")
                        raise
                else:
                    console.print("\n[yellow]Cleanup cancelled[/yellow]")
        else:
            console.print("\n[green]No duplicates found - database is clean![/green]")


@click.command()
@click.option("--dry-run/--execute", default=True, help="Dry run or execute cleanup")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def main(dry_run: bool, verbose: bool):
    """Clean up duplicate documents in the database.

    This script will:
    1. Find documents with duplicate file_path values
    2. Find documents with duplicate (company_code, doc_date, doc_type)
    3. Update business_concepts_master references to point to kept documents
    4. Delete the duplicate documents

    By default, runs in dry-run mode. Use --execute to actually perform cleanup.
    """
    asyncio.run(cleanup_duplicates(dry_run, verbose))


if __name__ == "__main__":
    main()
