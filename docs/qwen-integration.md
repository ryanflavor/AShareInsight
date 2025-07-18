# Qwen Embedding Service Integration

This document describes how AShareInsight integrates with the Qwen embedding service for generating high-quality text embeddings.

## Overview

AShareInsight uses the Qwen3-Embedding-4B model to generate 2560-dimensional embeddings for business concepts extracted from financial documents. These embeddings enable semantic search and similarity matching capabilities.

## Architecture

```
┌─────────────────┐     HTTP/REST      ┌──────────────────┐
│   AShareInsight │ ─────────────────> │  Qwen Service    │
│   Application   │                     │  (Port 9547)     │
└─────────────────┘                     └──────────────────┘
        │                                       │
        │                                       │
        ▼                                       ▼
┌─────────────────┐                     ┌──────────────────┐
│  PostgreSQL +   │                     │ Qwen3-Embedding  │
│   pgvector      │                     │      4B Model    │
│  (2560-dim)     │                     │   (GPU: cuda:1)  │
└─────────────────┘                     └──────────────────┘
```

## Configuration

### 1. Database Schema

The database has been configured to support 2560-dimensional vectors:

```sql
-- Business concepts table with 2560-dimensional embeddings
CREATE TABLE business_concepts_master (
    concept_id UUID PRIMARY KEY,
    company_code VARCHAR(10) NOT NULL,
    concept_name VARCHAR(255) NOT NULL,
    embedding VECTOR(2560) NOT NULL,  -- Qwen embedding dimension
    concept_details JSONB,
    -- ... other fields
);

-- HNSW index optimized for 2560 dimensions
CREATE INDEX idx_business_concepts_embedding_hnsw 
ON business_concepts_master 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 32, ef_construction = 128);
```

### 2. Environment Configuration

Create a `.env` file based on `.env.example`:

```bash
# Qwen Embedding Service Configuration
ASHARE_EMBEDDING_SERVICE__BASE_URL=http://localhost:9547
ASHARE_EMBEDDING_SERVICE__TIMEOUT=30.0
ASHARE_EMBEDDING_SERVICE__MAX_RETRIES=3
ASHARE_EMBEDDING_SERVICE__BATCH_SIZE=64
ASHARE_EMBEDDING_SERVICE__NORMALIZE=true
```

### 3. Service Parameters

The Qwen service is configured with:
- **Model**: Qwen3-Embedding-4B
- **Embedding Dimension**: 2560
- **Device**: cuda:1 (GPU 1)
- **Max Length**: 1024 tokens
- **Batch Size**: 64
- **Normalization**: Enabled (L2 norm)

## Usage

### 1. Basic Embedding Generation

```python
from core.embedding_service import get_embedding_service

# Get service instance
service = get_embedding_service()

# Generate single embedding
text = "平安银行的零售银行业务"
embedding = service.generate_single_embedding(text)
# Returns: list[float] with 2560 dimensions

# Generate batch embeddings
texts = ["文本1", "文本2", "文本3"]
embeddings = service.generate_embeddings(texts)
# Returns: list[list[float]], each with 2560 dimensions
```

### 2. Async Embedding Generation

```python
import asyncio
from core.embedding_service import QwenEmbeddingService

async def generate_async():
    service = QwenEmbeddingService()
    embeddings = await service.generate_embeddings_async(texts)
    return embeddings

embeddings = asyncio.run(generate_async())
```

### 3. Database Integration

```python
from core.database import DatabaseOperations
from core.models import BusinessConcept
from core.embedding_service import get_embedding_service

# Initialize services
db = DatabaseOperations(connection_string)
embedding_service = get_embedding_service()

# Generate embedding for concept
concept_text = f"{concept.concept_name}: {concept.description}"
embedding = embedding_service.generate_single_embedding(concept_text)

# Store concept with embedding
concept = BusinessConcept(
    company_code="000001",
    concept_name="零售银行业务",
    embedding=embedding,  # 2560-dimensional vector
    concept_details={...},
    last_updated_from_doc_id=doc_id
)
db.create_business_concept(concept)

# Search similar concepts
query_embedding = embedding_service.generate_single_embedding(query_text)
similar_concepts = db.search_similar_concepts(
    query_embedding=query_embedding,
    company_code="000001",
    limit=10
)
```

## Testing

Run the integration tests to verify the Qwen service connection:

```bash
# Run Qwen integration tests
uv run python tests/integration/test_qwen_embedding_service.py

# Run all compatibility tests
uv run python tests/integration/test_compatibility_validation.py
```

## Performance Considerations

1. **Batch Processing**: Use batch embedding generation for multiple texts to improve throughput
2. **Connection Pooling**: The HTTP client maintains persistent connections for better performance
3. **Retry Logic**: Automatic retries with exponential backoff for resilience
4. **HNSW Index**: Optimized parameters (m=32, ef_construction=128) for 2560-dimensional vectors

## Monitoring

The Qwen service provides monitoring endpoints:

- **Health Check**: `GET http://localhost:9547/health`
- **Statistics**: `GET http://localhost:9547/stats`
- **Admin UI**: `GET http://localhost:9547/admin`

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Ensure Qwen service is running on port 9547
   - Check firewall settings

2. **Dimension Mismatch**
   - Verify database schema uses VECTOR(2560)
   - Check embedding service returns 2560 dimensions

3. **Performance Issues**
   - Increase batch size for bulk operations
   - Check GPU memory usage
   - Monitor service statistics

### Debug Mode

Enable debug logging:

```python
from core.logging_config import setup_logging
setup_logging(level="DEBUG")
```

## Migration from 1024 to 2560 Dimensions

If migrating from the previous 1024-dimensional setup:

```bash
# Run the migration script
psql -U postgres -d ashareinsight -f scripts/update_vector_dimensions.sql
```

This will:
1. Drop the old HNSW index
2. Update the embedding column to VECTOR(2560)
3. Recreate the HNSW index with optimized parameters

Note: Existing embeddings will need to be regenerated using the Qwen service.