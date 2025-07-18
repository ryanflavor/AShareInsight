# AShareInsight

Enterprise concept retrieval system with PostgreSQL and vector search.

## Overview

This project implements a minimal prototype to verify compatibility of key technologies:
- Python 3.13
- PostgreSQL + pgvector extension (0.7.0+ with halfvec support)
- langchain-postgres package
- Pydantic 2.0+

## Key Features

- **HNSW Vector Search**: Uses pgvector's halfvec type to support 2560-dimensional vectors with HNSW indexing
- **Optimized Storage**: 50% storage reduction using halfvec (2-byte floats)
- **High Performance**: ~30% faster queries compared to standard vector type

## Setup

```bash
# Create virtual environment
uv venv --python 3.13

# Install dependencies
uv pip install -e .

# Start PostgreSQL with pgvector
docker-compose up -d

# Initialize database (creates tables with halfvec support)
uv run python scripts/init_database.py

# Or with sample data
uv run python scripts/init_database.py --sample-data
```

## Testing

```bash
# Run tests
pytest

# Verify database setup
uv run python scripts/init_database.py --verify-only
```

## Database Migration

If you have existing data using VECTOR type and need to migrate to HALFVEC:

```bash
# Run the migration script
psql -h localhost -U postgres -d ashareinsight -f scripts/migrate_to_halfvec.sql
```