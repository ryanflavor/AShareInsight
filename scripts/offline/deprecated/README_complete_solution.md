# Complete Document Processing Solution

This directory contains scripts for offline document processing that fulfill Stories 1.2-1.5.

## Quick Start

```bash
# 1. Process all new documents (20 concurrent LLM calls)
uv run python scripts/offline/end_to_end_pipeline.py

# 2. Check and fill any gaps
uv run python scripts/offline/complete_pipeline.py

# 3. If any raw responses failed parsing, recover them
uv run python scripts/offline/recover_from_raw.py
```

## Overview of Scripts

### 1. `end_to_end_pipeline.py` - Main Processing Pipeline
The primary script that processes new documents through the complete workflow:
- Scans for unprocessed documents
- Extracts data using LLM (Story 1.2)
- Archives to database (Story 1.3)
- Executes fusion to update BusinessConceptsMaster (Story 1.4)
- Automatically vectorizes new concepts (Story 1.5)

**Note**: Raw responses are automatically saved by GeminiLLMAdapter during extraction.

### 2. `complete_pipeline.py` - Gap Filler Script
Ensures all documents complete the full pipeline by:
- Finding documents without extracted JSON
- Finding archived documents without fusion
- Finding concepts without embeddings
- Processing any gaps found

### 3. `process_archived_for_fusion.py` - Fusion Only
Processes archived documents for business concept fusion when needed separately.

### 4. `build_vector_indices.py` - Vectorization Only
Builds embeddings for business concepts when needed separately.

### 5. `recover_from_raw.py` - Raw Response Recovery
Recovers extractions from saved raw LLM responses when parsing fails:
- Extracts JSON from raw responses saved by GeminiLLMAdapter
- Creates extracted JSON files without re-calling LLM
- Useful when LLM response is valid but initial parsing failed

## Recommended Workflow

### Initial Processing
```bash
# 1. Run the main pipeline for all new documents
python scripts/offline/end_to_end_pipeline.py

# 2. Check for and fill any gaps
python scripts/offline/complete_pipeline.py --dry-run  # Check gaps first
python scripts/offline/complete_pipeline.py             # Fill gaps
```

### Verification
```bash
# Check pipeline completion status
python scripts/offline/complete_pipeline.py --dry-run
```

## Current State Analysis

Based on the latest run:
- **Documents**: 64 archived (100% success rate)
- **Companies**: 50 total, but only 17 (34%) have extracted concepts
- **Concepts**: 78 total, all with embeddings (Story 1.5 ✓)
- **Issue**: Many documents archived but fusion not executed

## Key Points

1. **Raw Response Storage**: 
   - Handled automatically by GeminiLLMAdapter
   - Annual reports: `{company_name}_{timestamp}_raw_response.json`
   - Research reports: `research_report_{timestamp}_raw_response.json`

2. **Processing Order**:
   - Annual reports processed first (creates companies)
   - Research reports can only be archived if company exists

3. **Fusion Gap**:
   - Main issue is documents archived without fusion
   - Use `complete_pipeline.py` to fix this

4. **Vectorization**:
   - Working correctly - all concepts have embeddings
   - Automatic after fusion updates

## Troubleshooting

### "No concepts extracted"
- Run `complete_pipeline.py` to ensure fusion runs for all documents
- Check logs for fusion errors

### "Missing embeddings"
- Ensure QWEN_API_KEY is configured
- Run `build_vector_indices.py` manually if needed

### "Document not processed"
- Check if file hash already in database
- Check if extracted JSON already exists
- Verify file format (MD or TXT)

## Story 1.5 Completion

Story 1.5 is successfully implemented:
- ✅ BusinessConceptsMaster updates trigger vectorization
- ✅ All 78 existing concepts have embeddings
- ✅ Automatic process after fusion

To ensure all documents reach Story 1.5:
1. Run `end_to_end_pipeline.py` for new documents
2. Run `complete_pipeline.py` to fill any gaps
3. Verify with DB query that all concepts have embeddings