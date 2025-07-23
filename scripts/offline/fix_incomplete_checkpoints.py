#!/usr/bin/env python3
"""
Fix companies that have successful LLM extraction but haven't completed subsequent steps.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.offline.production_pipeline import DocumentState, ProductionPipeline


async def find_incomplete_checkpoints():
    """Find all checkpoints with successful extraction but incomplete processing."""
    checkpoint_dir = Path("data/temp/checkpoints")
    incomplete = []

    for checkpoint_file in checkpoint_dir.glob("*_checkpoint.json"):
        with open(checkpoint_file) as f:
            data = json.load(f)

        stages = data["stages"]
        if stages["extraction"]["status"] == "success" and (
            stages["archive"]["status"] != "success"
            or stages["fusion"]["status"] != "success"
            or stages["vectorization"]["status"] != "success"
        ):
            incomplete.append(
                {
                    "checkpoint_file": checkpoint_file,
                    "file_path": Path(data["file_path"]),
                    "stages": stages,
                }
            )

    return incomplete


async def fix_incomplete_documents(max_concurrent=5):
    """Process documents that have successful extraction but incomplete subsequent steps."""

    # Find incomplete documents
    incomplete_docs = await find_incomplete_checkpoints()
    print(
        f"Found {len(incomplete_docs)} documents with successful extraction but incomplete processing"
    )

    if not incomplete_docs:
        print("No incomplete documents to process")
        return

    # Show summary
    print("\nIncomplete stages summary:")
    archive_pending = sum(
        1 for d in incomplete_docs if d["stages"]["archive"]["status"] != "success"
    )
    fusion_pending = sum(
        1 for d in incomplete_docs if d["stages"]["fusion"]["status"] != "success"
    )
    vector_pending = sum(
        1
        for d in incomplete_docs
        if d["stages"]["vectorization"]["status"] != "success"
    )

    print(f"  Archive pending: {archive_pending}")
    print(f"  Fusion pending: {fusion_pending}")
    print(f"  Vectorization pending: {vector_pending}")

    # Process incomplete documents
    pipeline = ProductionPipeline(max_concurrent=max_concurrent)

    print(f"\nProcessing {len(incomplete_docs)} incomplete documents...")

    success_count = 0
    failed_count = 0

    # Process in batches
    batch_size = max_concurrent
    for i in range(0, len(incomplete_docs), batch_size):
        batch = incomplete_docs[i : i + batch_size]

        tasks = []
        for doc_info in batch:
            file_path = doc_info["file_path"]

            # Load the existing checkpoint
            doc_state = DocumentState(file_path)

            # Process only the incomplete stages
            task = pipeline.process_document(file_path, doc_state)
            tasks.append(task)

        # Wait for batch to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"  ❌ Failed: {batch[idx]['file_path'].name} - {result}")
                failed_count += 1
            elif result:
                print(f"  ✅ Completed: {batch[idx]['file_path'].name}")
                success_count += 1
            else:
                print(f"  ❌ Failed: {batch[idx]['file_path'].name}")
                failed_count += 1

    print("\nProcessing complete:")
    print(f"  Success: {success_count}")
    print(f"  Failed: {failed_count}")


if __name__ == "__main__":
    import click

    @click.command()
    @click.option("--max-concurrent", default=5, help="Maximum concurrent processing")
    def main(max_concurrent):
        """Fix incomplete document processing."""
        asyncio.run(fix_incomplete_documents(max_concurrent))

    main()
