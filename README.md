# AShareInsight

Enterprise concept retrieval system with PostgreSQL and vector search.

## Overview

This project implements a minimal prototype to verify compatibility of key technologies:
- Python 3.13
- PostgreSQL + pgvector extension
- langchain-postgres package
- Pydantic 2.0+

## Setup

```bash
# Create virtual environment
uv venv --python 3.13

# Install dependencies
uv pip install -e .

# Start PostgreSQL container
docker run --name ashareinsight-postgres \
  -e POSTGRES_DB=ashareinsight \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=test123 \
  -p 5432:5432 \
  -d postgres:16
```

## Testing

```bash
# Run tests
pytest

# Run compatibility validation
python packages/core/src/core/compatibility_validation.py
```