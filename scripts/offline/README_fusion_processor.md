# Master Data Fusion Processor

This script processes archived documents in the database to perform business concept fusion updates.

## Overview

The `process_archived_for_fusion.py` script:
- Scans the `source_documents` table for archived documents
- Identifies documents that haven't been processed for business concept fusion
- Executes the fusion algorithm to create or update business concepts in the `business_concepts_master` table
- Provides comprehensive progress tracking and error handling

## Usage

```bash
# Process all unprocessed documents
uv run python scripts/offline/process_archived_for_fusion.py

# Dry run - see what would be processed without executing
uv run python scripts/offline/process_archived_for_fusion.py --dry-run

# Process a limited number of documents
uv run python scripts/offline/process_archived_for_fusion.py --limit 10
```

## Features

- **Smart Detection**: Automatically identifies documents that need fusion processing
- **Batch Processing**: Processes documents in batches for optimal performance
- **Progress Tracking**: Real-time progress bar with detailed status updates
- **Error Handling**: Robust error handling with transaction rollback on failures
- **Comprehensive Reporting**: Detailed summary of processing results including:
  - Total documents processed
  - New concepts created
  - Existing concepts updated
  - Skipped documents
  - Failed documents with error details

## Database Changes Required

During development, the following database adjustments were made:
1. Changed `embedding` column from `halfvec` to `TEXT` type (temporary until Story 1.5)
2. Updated `concept_category` constraint to accept Chinese values: '核心业务', '新兴业务', '战略布局'
3. Removed `development_stage` constraint to allow flexible values

## Integration with Existing Pipeline

This script can be run:
- After bulk document extraction to process historical data
- As a scheduled job to process newly archived documents
- Manually to reprocess specific documents after updates

## Error Recovery

The script handles errors gracefully:
- Individual concept failures don't affect other concepts in the same document
- Transaction rollback ensures data consistency
- Detailed error logging for troubleshooting

## Performance Considerations

- Default batch size: 50 concepts per transaction
- Concurrent document processing with semaphore limit
- Small delays between batches to prevent resource exhaustion