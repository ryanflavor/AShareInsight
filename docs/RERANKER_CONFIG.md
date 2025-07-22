# Reranker Configuration Guide

## Overview

The AShareInsight system integrates with Qwen Service via HTTP API for advanced result reranking, improving search relevance through neural re-scoring of initial vector search results. The service runs independently on port 9547.

## Configuration

### Environment Variables

Configure the reranker through environment variables:

```bash
# Enable/disable reranker (default: true)
RERANKER_ENABLED=true

# Service URL for Qwen Service
RERANKER_SERVICE_URL=http://localhost:9547

# Performance settings
RERANKER_TIMEOUT_SECONDS=5.0    # Timeout per request (0.1-30.0)
RERANKER_MAX_RETRIES=2          # Retry attempts (0-5)
```

### Configuration in Code

```python
from src.shared.config import settings

# Access reranker settings
if settings.reranker_enabled:
    print(f"Using reranker at: {settings.reranker_model_path}")
```

## Performance Tuning

### Service Configuration

The Qwen Service handles batch processing internally. Key considerations:

- **Timeout Configuration**: Set based on expected response times and SLA requirements
- **Retry Strategy**: Configure retries for network resilience
- **Connection Pooling**: HTTP client maintains persistent connections

### Service Resource Requirements

- The Qwen Service is configured to use:
  - GPU 0 for reranking model (cuda:0)
  - Batch size of 16 documents
  - Float16 precision for efficiency

## Performance Benchmarks

Expected performance metrics (based on actual service testing):

| Metric | Value |
|--------|-------|
| Service Health Check | <50ms |
| 4 docs rerank | ~170-180ms |
| Network Overhead | ~10-20ms |
| Service Availability | 99%+ |

## Monitoring

Reranking metrics are tracked automatically:

```python
from src.infrastructure.monitoring import get_metrics

metrics = get_metrics()
print(f"Total reranks: {metrics.total_reranks}")
print(f"Average latency: {metrics.get_average_rerank_latency()}ms")
print(f"P95 latency: {metrics.get_rerank_p95_latency()}ms")
```

## Troubleshooting

### Service Connection Failures

```
ModelLoadError: Failed to connect to Qwen Service at http://localhost:9547
```

**Solutions:**
1. Verify Qwen Service is running: `curl http://localhost:9547/health`
2. Check correct port (9547, not 8000)
3. Ensure network connectivity
4. Check service logs in `qwen_rerank/logs/`

### Service Timeout

```
ModelInferenceError: Request timeout
```

**Solutions:**
1. Increase `RERANKER_TIMEOUT_SECONDS`
2. Check service performance metrics
3. Verify service isn't overloaded
4. Consider reducing document count per request

### Slow Performance

If reranking is slower than expected:

1. Check service health:
   ```bash
   curl http://localhost:9547/health | jq .
   ```

2. Monitor service metrics:
   - Check processing time in response stats
   - Verify GPU utilization on service host

3. Network optimization:
   - Ensure low latency between API and service
   - Consider connection pooling settings

### Graceful Degradation

The system automatically falls back to original ranking if reranker fails:

1. Reranker disabled: Original similarity scores used
2. Service connection fails: System continues without reranking
3. HTTP errors or timeouts: Original order preserved, error logged
4. Service returns error: Graceful fallback with logging

## Integration Testing

Test reranker integration:

```bash
# Run integration tests
pytest tests/integration/test_reranker_integration.py -v

# Test with reranker disabled
RERANKER_ENABLED=false pytest tests/integration/ -v
```

## Best Practices

1. **Service Management**
   - Monitor service health endpoint regularly
   - Use systemd or supervisor for service management
   - Implement proper service restart policies

2. **Configuration Management**
   - Use environment-specific service URLs
   - Monitor reranker metrics in production
   - Set appropriate timeouts for your SLA

3. **Error Handling**
   - Always implement graceful degradation
   - Log service failures for monitoring
   - Alert on high failure rates or service downtime

4. **Performance Optimization**
   - Implement connection pooling
   - Monitor network latency
   - Consider caching for repeated queries