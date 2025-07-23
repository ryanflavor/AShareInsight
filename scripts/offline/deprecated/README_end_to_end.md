# End-to-End Document Processing Pipeline

This unified script completes the entire workflow from Stories 1.2-1.5 in a single execution.

## Overview

The `end_to_end_pipeline.py` script provides a comprehensive solution that:

1. **Story 1.2**: Reads financial report files and uses LangChain to call LLM API for extraction
2. **Story 1.3**: Archives raw JSON responses for future model retraining  
3. **Story 1.4**: Executes fusion algorithm to update BusinessConceptsMaster table
4. **Story 1.5**: Automatically vectorizes new/updated business concepts

## Key Features

### Intelligent Document Scanning
- Avoids reprocessing documents already in the database (by file hash)
- Skips documents already extracted to JSON files
- Checks for duplicate company/year/type combinations
- Processes annual reports before research reports (ensures companies exist)

### Raw Response Archiving
- GeminiLLMAdapter automatically saves all raw LLM responses to `data/raw_responses/` directory
- Annual reports: Saved with company name in filename (e.g., `华发股份_20241223_143025_raw_response.json`)
- Research reports: Saved with timestamp (e.g., `research_report_20241223_143025_raw_response.json`)
- Preserves original JSON structure for model retraining
- Includes metadata and timestamp information

### Complete Pipeline Integration
- Extraction → Archive → Fusion → Vectorization in one flow
- Automatic error recovery with detailed logging
- Progress tracking with real-time updates
- Comprehensive final summary report

### Smart Error Handling
- Research reports without companies continue processing (extraction completes but archive is skipped)
- Only annual reports can create/update company records
- Retry logic for transient failures
- Detailed error reporting by stage
- Transaction safety for database operations

## Usage

```bash
# Process all new documents (default: 20 concurrent LLM calls)
python scripts/offline/end_to_end_pipeline.py

# Dry run to see what would be processed
python scripts/offline/end_to_end_pipeline.py --dry-run

# Process limited number of documents
python scripts/offline/end_to_end_pipeline.py --limit 10

# Control parallelism (default is 20 for optimal LLM throughput)
python scripts/offline/end_to_end_pipeline.py --parallel-workers 30

# Provide API key via command line
python scripts/offline/end_to_end_pipeline.py --gemini-api-key YOUR_KEY
```

## Environment Requirements

```bash
# Required environment variable (if not provided via CLI)
export GEMINI_API_KEY=your_api_key

# Optional: Qwen API configuration for vectorization
export QWEN_API_KEY=your_qwen_key
export QWEN_BASE_URL=https://your-qwen-endpoint
```

## Output Structure

```
data/
├── raw_responses/          # Raw LLM responses (Story 1.3)
│   ├── annual_reports/
│   │   └── *_raw_response.json
│   └── research_reports/
│       └── *_raw_response.json
├── extracted/              # Processed extractions
│   ├── annual_reports/
│   └── research_reports/
└── metadata/              # Processing metadata
    ├── document_index.json
    └── processing_log.json
```

## Processing Flow

1. **Initialization**
   - Load existing companies from database
   - Cache processed document hashes
   - Prepare raw response directories

2. **Document Discovery**
   - Scan annual_reports/ and research_reports/ directories
   - Filter out already processed documents
   - Order by type (annual reports first - important!)

3. **For Each Document**
   - Extract structured data using LLM
   - Save raw response for retraining
   - Archive to source_documents table
     - Annual reports: Always archived, can create/update companies
     - Research reports: Only archived if company already exists
   - Execute fusion to update master data
   - Build vectors for new/updated concepts

4. **Summary Report**
   - Documents processed by stage
   - Success/failure statistics
   - Error details for troubleshooting

## Important Notes

- **Company Creation**: Only annual reports can create or update company records in the database
- **Research Reports**: Must have an existing company record (from annual reports) to be archived
- **Processing Order**: Annual reports are always processed first to ensure companies exist

## Comparison with Previous Scripts

| Feature | Old Scripts | end_to_end_pipeline.py |
|---------|------------|------------------------|
| LLM Extraction | ✓ | ✓ |
| Raw Response Saving | ✗ | ✓ |
| Archive to DB | ✓ | ✓ |
| Fusion Update | Separate script | ✓ Integrated |
| Vectorization | Separate script | ✓ Integrated |
| Duplicate Detection | Basic | ✓ Advanced |
| Error Recovery | Limited | ✓ Comprehensive |
| Progress Tracking | Basic | ✓ Detailed |

## Performance Considerations

- Default: 20 parallel workers for LLM extraction (optimized for Gemini API throughput)
- Automatic rate limiting between LLM calls
- Batch processing for vectorization (50 concepts per batch)
- Transaction-based database operations for consistency
- Concurrent extraction significantly reduces processing time for large document sets

## Troubleshooting

### Common Issues

1. **"No new documents to process"**
   - Check if documents are already in database
   - Look for extracted JSON files in data/extracted/
   - Verify file paths and patterns

2. **LLM Connection Errors**
   - Verify GEMINI_API_KEY is set correctly
   - Check network connectivity
   - Consider reducing parallel workers

3. **Vectorization Failures**
   - Ensure QWEN_API_KEY is configured
   - Check Qwen service availability
   - Review embedding column type in database

### Debug Mode

For detailed logging:
```bash
export LOG_LEVEL=DEBUG
python scripts/offline/end_to_end_pipeline.py
```

## Migration from Old Scripts

If you have been using the previous scripts, you can safely switch to this unified pipeline:

1. Documents already in the database won't be reprocessed
2. Existing extracted JSON files are detected and skipped
3. Raw responses will be saved for new documents only
4. Fusion and vectorization will catch up automatically

The script is designed to be idempotent - running it multiple times is safe and will only process new documents.