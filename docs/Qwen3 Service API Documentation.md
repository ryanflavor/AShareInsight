# Qwen3 Service API Documentation

## Overview

The Qwen3 Service provides text embedding and document reranking capabilities through a RESTful API. This service is designed for internal network use and offers high-performance NLP operations using Qwen3 models.

**Base URL**: `http://<server-ip>:9547`

## Authentication

Currently, the API does not require authentication by default. This can be configured in `config.yaml` under the `security` section.

## Endpoints

### 1. Text Embedding

Generate embeddings for a list of texts.

**Endpoint**: `POST /embed`

**Request Body**:
```json
{
  "texts": ["text1", "text2", "text3"],
  "normalize": true,
  "batch_size": 32
}
```

**Parameters**:
- `texts` (required): Array of strings to embed. Maximum 1000 texts per request.
- `normalize` (optional): Whether to normalize embeddings. Default: `true`
- `batch_size` (optional): Processing batch size. Default: uses server configuration

**Response**:
```json
{
  "success": true,
  "data": {
    "embeddings": [[0.123, -0.456, ...], [0.789, -0.012, ...], ...],
    "dimensions": 2560,
    "count": 3
  },
  "stats": {
    "processing_time": 0.234,
    "batch_count": 1,
    "tokens_processed": 156
  }
}
```

**Example cURL**:
```bash
curl -X POST http://localhost:9547/embed \
  -H "Content-Type: application/json" \
  -d '{
    "texts": ["Hello world", "This is a test"],
    "normalize": true
  }'
```

### 2. Document Reranking

Rerank documents based on relevance to a query.

**Endpoint**: `POST /rerank`

**Request Body**:
```json
{
  "query": "What is machine learning?",
  "documents": [
    "Machine learning is a subset of AI...",
    "The weather today is sunny...",
    "Deep learning uses neural networks..."
  ],
  "top_k": 2
}
```

**Parameters**:
- `query` (required): The query text
- `documents` (required): Array of documents to rerank. Maximum 500 documents per request.
- `top_k` (optional): Number of top results to return. Default: 10

**Response**:
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "index": 0,
        "score": 0.95,
        "document": "Machine learning is a subset of AI..."
      },
      {
        "index": 2,
        "score": 0.87,
        "document": "Deep learning uses neural networks..."
      }
    ]
  },
  "stats": {
    "processing_time": 0.456,
    "documents_processed": 3,
    "returned": 2
  }
}
```

**Example cURL**:
```bash
curl -X POST http://localhost:9547/rerank \
  -H "Content-Type: application/json" \
  -d '{
    "query": "artificial intelligence applications",
    "documents": ["AI is used in healthcare", "Coffee is a popular beverage", "Machine learning powers recommendation systems"],
    "top_k": 2
  }'
```

### 3. Health Check

Check service health status.

**Endpoint**: `GET /health`

**Response**:
```json
{
  "status": "healthy",
  "timestamp": 1704067200.123,
  "uptime": 3600.5,
  "embedding_service": {
    "status": "healthy",
    "model_loaded": true,
    "device": "cuda:1",
    "requests_processed": 1234
  },
  "reranking_service": {
    "status": "healthy",
    "model_loaded": true,
    "device": "cuda:0",
    "requests_processed": 567
  }
}
```

### 4. Service Statistics

Get detailed service statistics.

**Endpoint**: `GET /stats`

**Response**:
```json
{
  "timestamp": 1704067200.123,
  "embedding_service": {
    "total_requests": 1234,
    "total_texts": 45678,
    "average_batch_size": 28.5,
    "average_processing_time": 0.234,
    "cache_hits": 123,
    "cache_size": 256
  },
  "reranking_service": {
    "total_requests": 567,
    "total_queries": 567,
    "total_documents": 23456,
    "average_documents_per_query": 41.4,
    "average_processing_time": 0.456
  },
  "system": {
    "python_version": "3.13.0",
    "config": { ... }
  }
}
```

## Error Handling

All endpoints return errors in the following format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common HTTP Status Codes**:
- `200`: Success
- `400`: Bad Request (invalid parameters)
- `422`: Unprocessable Entity (validation error)
- `500`: Internal Server Error
- `503`: Service Unavailable (model not loaded)

## Rate Limits & Constraints

- **Maximum texts per embedding request**: 1000
- **Maximum documents per reranking request**: 500
- **Maximum text length**: 8192 characters
- **Maximum request size**: 10MB
- **Concurrent requests**: 10 (configurable)
- **Request timeout**: 300 seconds

## Best Practices

1. **Batch Processing**: For embedding multiple texts, send them in a single request rather than multiple individual requests.

2. **Text Length**: Keep individual texts under 1024 tokens for optimal performance. Longer texts will be truncated.

3. **Error Handling**: Implement retry logic with exponential backoff for 503 errors.

4. **Connection Pooling**: Use HTTP connection pooling for better performance when making multiple requests.

## Example Python Client

```python
import requests
import json

class QwenServiceClient:
    def __init__(self, base_url="http://localhost:9547"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def embed_texts(self, texts, normalize=True):
        response = self.session.post(
            f"{self.base_url}/embed",
            json={"texts": texts, "normalize": normalize}
        )
        response.raise_for_status()
        return response.json()
    
    def rerank_documents(self, query, documents, top_k=10):
        response = self.session.post(
            f"{self.base_url}/rerank",
            json={"query": query, "documents": documents, "top_k": top_k}
        )
        response.raise_for_status()
        return response.json()
    
    def health_check(self):
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

# Usage example
client = QwenServiceClient("http://192.168.1.100:9547")

# Embed texts
result = client.embed_texts(["Hello world", "AI is amazing"])
embeddings = result["data"]["embeddings"]

# Rerank documents
result = client.rerank_documents(
    query="machine learning applications",
    documents=["ML in healthcare", "Coffee brewing", "Neural networks"],
    top_k=2
)
top_docs = result["data"]["results"]
```

## Performance Tips

1. **GPU Memory**: Monitor GPU memory usage through `/admin` interface. Reduce batch_size if OOM errors occur.

2. **Optimal Batch Sizes**:
   - Embedding: 32-64 texts per batch
   - Reranking: 8-16 documents per batch

3. **Caching**: The service implements internal caching. Repeated identical requests will be served from cache.

## Support

- **Admin Interface**: Access `http://<server-ip>:9547/admin` for monitoring and management
- **Logs**: Check `logs/` directory for detailed service logs
- **Configuration**: Modify `config.yaml` for performance tuning