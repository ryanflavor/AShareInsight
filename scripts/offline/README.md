# Offline Pipeline Scripts

This directory contains the production-ready offline data processing pipeline for AShareInsight.

## Overview

The offline pipeline processes annual reports and research reports through multiple stages:
1. **Extraction**: Uses LLM to extract structured data from raw documents
2. **Archival**: Stores documents and extracted data in the database
3. **Fusion**: Creates/updates business concepts in the master data table
4. **Vectorization**: Generates embeddings for semantic search

## Main Scripts

### 🚀 production_pipeline.py

The main production pipeline that orchestrates the entire data processing workflow.

**Features:**
- Checkpoint-based resumable processing
- Concurrent document processing
- Automatic document type detection
- Integrated vectorization
- Database integrity checks
- Comprehensive error handling

**Usage:**
```bash
# Normal incremental processing
uv run python scripts/offline/production_pipeline.py

# Full rebuild from scratch
uv run python scripts/offline/production_pipeline.py --full-rebuild

# Process specific directory
uv run python scripts/offline/production_pipeline.py --annual-reports-dir data/annual_reports/2024

# Dry run to see what would be processed
uv run python scripts/offline/production_pipeline.py --dry-run

# Custom concurrency level
uv run python scripts/offline/production_pipeline.py --max-concurrent 10
```

**Options:**
- `--annual-reports-dir`: Directory containing annual reports (default: data/annual_reports/2024)
- `--research-reports-dir`: Directory containing research reports (default: data/research_reports)
- `--force-reprocess`: Force reprocessing of all documents
- `--dry-run`: Show what would be processed without executing
- `--clear-db`: Clear all database content before processing
- `--clear-checkpoints`: Clear all checkpoint files
- `--build-indices`: Build vector indices after processing
- `--full-rebuild`: Complete rebuild (clears DB, checkpoints, forces reprocess, builds indices)
- `--max-concurrent`: Maximum concurrent LLM extractions (default: 5)

### 🔍 build_vector_indices.py

Standalone script for building or rebuilding vector embeddings for business concepts.

**Features:**
- Batch processing with configurable size
- Checkpoint support for resumable runs
- Company-specific processing
- Dry-run mode
- Progress tracking

**Usage:**
```bash
# Build missing vectors
uv run python scripts/offline/build_vector_indices.py

# Rebuild all vectors
uv run python scripts/offline/build_vector_indices.py --rebuild-all

# Process specific company
uv run python scripts/offline/build_vector_indices.py --company-code 600309

# Dry run
uv run python scripts/offline/build_vector_indices.py --dry-run
```

**Options:**
- `--rebuild-all`: Rebuild all vectors, not just missing ones
- `--company-code`: Process only concepts for a specific company
- `--limit`: Maximum number of concepts to process
- `--batch-size`: Number of concepts per batch (default: 50)
- `--dry-run`: Show what would be done without making changes
- `--parallel-workers`: Number of parallel workers (default: 1)
- `--checkpoint-file`: File to save progress for resuming

## Pipeline Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│   Raw Documents │────▶│  Extraction  │────▶│   Archive   │
│  (.md/.txt)     │     │    (LLM)     │     │ (Database)  │
└─────────────────┘     └──────────────┘     └─────────────┘
                                                     │
                                                     ▼
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│  Vector Index   │◀────│ Vectorization│◀────│   Fusion    │
│   (pgvector)    │     │  (Qwen Emb)  │     │  (Master)   │
└─────────────────┘     └──────────────┘     └─────────────┘
```

## Data Flow

1. **Input**: Documents in `data/annual_reports/` and `data/research_reports/`
2. **Extraction**: LLM extracts structured data, saved to `data/extracted/`
3. **Database**: 
   - Companies table: Company master data
   - Source documents: Original documents and extraction results
   - Business concepts master: Unified business concepts with embeddings
4. **Checkpoints**: Progress saved to `data/temp/checkpoints/`
5. **Raw responses**: LLM outputs saved to `data/raw_responses/` for debugging

## Checkpoint System

The pipeline uses a checkpoint system to track processing stages:

```json
{
  "file_path": "path/to/document.md",
  "file_hash": "sha256_hash",
  "stages": {
    "extraction": {"status": "success", "timestamp": "..."},
    "archive": {"status": "success", "doc_id": "uuid"},
    "fusion": {"status": "success", "concepts": 10},
    "vectorization": {"status": "success", "vectors_built": 10}
  }
}
```

Benefits:
- Resume interrupted processing
- Skip already processed files
- Track processing status per stage
- Handle failures gracefully

## Database Schema

### Companies
- `company_code`: Stock code (primary key)
- `company_name_full`: Full company name
- `company_name_short`: Short name
- `exchange`: Stock exchange

### Source Documents
- `doc_id`: Document UUID
- `company_code`: Foreign key to companies
- `doc_type`: 'annual_report' or 'research_report'
- `file_hash`: SHA256 hash for deduplication
- `extraction_data`: Structured data from LLM

### Business Concepts Master
- `concept_id`: Concept UUID
- `company_code`: Foreign key to companies
- `concept_name`: Name of business concept (unique per company)
- `embedding`: Vector embedding (2560 dimensions)
- `concept_details`: Additional metadata

## Best Practices

1. **Initial Setup**:
   ```bash
   # Run database migrations first
   uv run python scripts/migration/001_initial_schema.py
   uv run python scripts/migration/002_update_models.py
   uv run python scripts/migration/003_create_vector_indices.py
   ```

2. **Production Workflow**:
   ```bash
   # Full rebuild for initial data load
   uv run python scripts/offline/production_pipeline.py --full-rebuild
   
   # Daily incremental updates
   uv run python scripts/offline/production_pipeline.py
   ```

3. **Monitoring**:
   - Check logs for extraction failures
   - Monitor checkpoint files for stuck processes
   - Verify vector coverage with build_vector_indices.py

4. **Troubleshooting**:
   - Use `--dry-run` to preview changes
   - Check `data/temp/checkpoints/` for processing state
   - Review `data/raw_responses/` for LLM outputs
   - Use smaller `--max-concurrent` if hitting rate limits

## Environment Variables

Required in `.env`:
```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db

# LLM Service
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=gemini-2.5-pro-preview-06-05

# Qwen Embedding Service
QWEN_EMBEDDING_URL=http://localhost:11434/v1/embeddings
QWEN_EMBEDDING_MODEL=qwen3-embedding-4b

# Optional
CHUNK_SIZE=10
MAX_CONCURRENT_EXTRACTIONS=5
```

## Performance Considerations

1. **Concurrency**: Adjust `--max-concurrent` based on LLM rate limits
2. **Batch Size**: Larger batches for vectorization improve throughput
3. **Database**: Ensure proper indices are created (run migration 003)
4. **Memory**: Monitor memory usage with large document sets

## Maintenance

### Cleaning Duplicate Records
If duplicate documents are created, use the cleanup scripts:
```bash
# Check for duplicates
uv run python scripts/check_duplicates.py

# Clean duplicates (dry run first)
uv run python scripts/clean_duplicates.py
uv run python scripts/clean_duplicates.py --execute
```

### Deprecated Scripts
Old scripts have been moved to the `deprecated/` folder for reference but should not be used in production.