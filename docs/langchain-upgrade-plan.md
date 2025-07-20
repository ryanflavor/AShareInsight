# LangChain Upgrade Plan: Best Practices Implementation

## Executive Summary

This document outlines a comprehensive upgrade plan for implementing LangChain best practices in the AShareInsight project. Based on research of current best practices in 2025, we've identified four key areas for improvement that will enhance observability, reliability, and maintainability of our LLM integration.

## 1. LangChain Callbacks Implementation

### Current State
- No custom callback handlers implemented
- Limited observability into LLM execution flow
- Basic logging without structured metrics collection

### Proposed Implementation

#### Phase 1: Basic Callback Handler (Sprint 1)
```python
# src/infrastructure/llm/langchain/callbacks/metrics_handler.py
from langchain_core.callbacks import BaseCallbackHandler
from typing import Any, Dict, List, Optional
import time
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)

@dataclass
class LLMMetrics:
    start_time: float
    end_time: Optional[float] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0
    error: Optional[str] = None

class MetricsCallbackHandler(BaseCallbackHandler):
    """Custom callback handler for metrics collection."""
    
    def __init__(self):
        self.metrics: Dict[str, LLMMetrics] = {}
        
    def on_llm_start(
        self, 
        serialized: Dict[str, Any],
        prompts: List[str],
        run_id: str,
        **kwargs: Any
    ) -> None:
        """Track LLM start time and prompt size."""
        self.metrics[run_id] = LLMMetrics(start_time=time.time())
        logger.info(
            "LLM execution started",
            run_id=run_id,
            model=serialized.get("name", "unknown"),
            prompt_count=len(prompts)
        )
    
    def on_llm_end(
        self,
        response: Any,
        run_id: str,
        **kwargs: Any
    ) -> None:
        """Record completion metrics."""
        if run_id in self.metrics:
            metric = self.metrics[run_id]
            metric.end_time = time.time()
            
            # Extract token usage from response
            if hasattr(response, "llm_output"):
                usage = response.llm_output.get("token_usage", {})
                metric.prompt_tokens = usage.get("prompt_tokens", 0)
                metric.completion_tokens = usage.get("completion_tokens", 0)
            
            duration = metric.end_time - metric.start_time
            logger.info(
                "LLM execution completed",
                run_id=run_id,
                duration_seconds=duration,
                tokens=metric.prompt_tokens + metric.completion_tokens
            )
    
    def on_llm_error(
        self,
        error: Exception,
        run_id: str,
        **kwargs: Any
    ) -> None:
        """Track errors for debugging."""
        if run_id in self.metrics:
            self.metrics[run_id].error = str(error)
        logger.error(
            "LLM execution failed",
            run_id=run_id,
            error=str(error)
        )
```

#### Phase 2: Advanced Features (Sprint 2)
- Streaming token callback support
- Chain and tool execution tracking
- Integration with OpenTelemetry spans
- Custom event support (v0.2.15+ feature)

### Benefits
- Real-time monitoring of LLM performance
- Detailed cost tracking
- Better debugging capabilities
- Foundation for A/B testing different models/prompts

## 2. Modern Memory Management Migration

### Current State
- No conversation memory implementation
- Each extraction is stateless
- ConversationBufferMemory is deprecated (as of v0.3.1)

### Proposed Implementation

#### Option A: LangGraph with Persistence (Recommended)
```python
# src/infrastructure/llm/langchain/memory/langgraph_memory.py
from langgraph.checkpoint import MemorySaver
from langgraph.graph import StateGraph
from typing import TypedDict, List
from langchain_core.messages import BaseMessage

class ConversationState(TypedDict):
    messages: List[BaseMessage]
    context: Dict[str, Any]

class LangGraphMemory:
    """Modern conversation memory using LangGraph."""
    
    def __init__(self):
        self.memory = MemorySaver()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the conversation graph with memory."""
        workflow = StateGraph(ConversationState)
        
        # Add nodes for different conversation stages
        workflow.add_node("process_message", self._process_message)
        workflow.add_node("summarize", self._summarize_if_needed)
        
        # Add edges
        workflow.add_edge("process_message", "summarize")
        workflow.set_entry_point("process_message")
        workflow.set_finish_point("summarize")
        
        return workflow.compile(checkpointer=self.memory)
    
    def _process_message(self, state: ConversationState) -> ConversationState:
        """Process new messages with context."""
        # Implementation for processing messages
        return state
    
    def _summarize_if_needed(self, state: ConversationState) -> ConversationState:
        """Summarize if conversation exceeds token limit."""
        total_tokens = self._count_tokens(state["messages"])
        if total_tokens > 3000:  # Configure based on model
            # Implement summarization logic
            pass
        return state
```

#### Option B: RunnableWithMessageHistory (Simpler)
```python
# src/infrastructure/llm/langchain/memory/runnable_memory.py
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import FileChatMessageHistory

def create_memory_chain(base_chain):
    """Wrap chain with message history."""
    return RunnableWithMessageHistory(
        base_chain,
        get_session_history=lambda session_id: FileChatMessageHistory(
            f"./chat_histories/{session_id}.json"
        ),
        input_messages_key="input",
        history_messages_key="history"
    )
```

### Migration Strategy
1. Implement for new features only (no breaking changes)
2. Add optional session_id parameter to extraction methods
3. Use for multi-turn refinement scenarios
4. Consider PostgreSQL storage for production

## 3. Enhanced Output Parsing with Retry Logic

### Current State
- Custom JSON extraction with regex
- Basic retry logic
- No error context passed to retry attempts

### Proposed Implementation

```python
# src/infrastructure/llm/langchain/parsers/robust_parser.py
from langchain.output_parsers import (
    PydanticOutputParser,
    OutputFixingParser,
    RetryWithErrorOutputParser
)
from langchain_core.language_models import BaseLanguageModel
from pydantic import BaseModel
from typing import Type, TypeVar

T = TypeVar('T', bound=BaseModel)

class RobustOutputParser:
    """Production-ready parser with multiple fallback strategies."""
    
    def __init__(
        self,
        pydantic_model: Type[T],
        llm: BaseLanguageModel,
        max_retries: int = 3
    ):
        # Base parser with schema validation
        self.base_parser = PydanticOutputParser(pydantic_object=pydantic_model)
        
        # Layer 1: Fix simple formatting errors
        self.fixing_parser = OutputFixingParser.from_llm(
            parser=self.base_parser,
            llm=llm
        )
        
        # Layer 2: Retry with error context
        self.retry_parser = RetryWithErrorOutputParser.from_llm(
            parser=self.fixing_parser,
            llm=llm,
            max_retries=max_retries
        )
    
    def parse_with_fallbacks(
        self,
        completion: str,
        prompt_value: str = None
    ) -> T:
        """Parse with multiple fallback strategies."""
        try:
            # Try base parser first (fastest)
            return self.base_parser.parse(completion)
        except Exception as e:
            logger.debug(f"Base parser failed: {e}")
            
        try:
            # Try fixing parser (handles format issues)
            return self.fixing_parser.parse(completion)
        except Exception as e:
            logger.debug(f"Fixing parser failed: {e}")
            
        # Final attempt with full context
        if prompt_value:
            return self.retry_parser.parse_with_prompt(
                completion=completion,
                prompt_value=prompt_value
            )
        else:
            return self.retry_parser.parse(completion)
```

### Integration Points
1. Replace current EnhancedOutputParser
2. Add prompt preservation for retry context
3. Configure appropriate retry limits
4. Add cost tracking for retry attempts

## 4. LangSmith Integration for Production Observability

### Current State
- OpenTelemetry integration exists
- No specialized LLM observability
- Limited production debugging capabilities

### Proposed Implementation

#### Phase 1: Basic Integration (Sprint 1)
```python
# src/shared/config/settings.py
class ObservabilitySettings(BaseSettings):
    """Observability configuration."""
    
    langsmith_enabled: bool = Field(default=False)
    langsmith_api_key: str = Field(default="")
    langsmith_project: str = Field(default="ashareinsight-production")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com")
    
    # Feature flags
    trace_all_requests: bool = Field(default=False)
    sample_rate: float = Field(default=0.1)  # 10% sampling in prod

# src/infrastructure/monitoring/langsmith.py
import os
from functools import wraps
from langsmith import Client
from langsmith.run_helpers import traceable

def init_langsmith(settings: ObservabilitySettings):
    """Initialize LangSmith with proper configuration."""
    if not settings.langsmith_enabled:
        return
    
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    
    # For serverless/batch processing
    os.environ["LANGCHAIN_CALLBACKS_BACKGROUND"] = "false"
    
    return Client()

def trace_extraction(name: str = None):
    """Decorator for tracing document extractions."""
    def decorator(func):
        @wraps(func)
        @traceable(
            name=name or func.__name__,
            tags=["extraction", "production"],
            metadata={"version": "1.0.0"}
        )
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

#### Phase 2: Advanced Features (Sprint 2)
1. **Custom Evaluators**
   ```python
   # src/infrastructure/monitoring/evaluators.py
   from langsmith.evaluation import EvaluationResult
   
   def business_concept_completeness(run, example):
       """Evaluate if all business concepts were extracted."""
       output = run.outputs.get("extraction_data", {})
       concepts = output.get("business_concepts", [])
       
       score = len(concepts) / 10.0  # Normalize to 0-1
       return EvaluationResult(
           key="concept_completeness",
           score=score,
           comment=f"Extracted {len(concepts)} business concepts"
       )
   ```

2. **Production Monitoring Dashboard**
   - Track extraction success rates
   - Monitor token usage trends
   - Alert on quality degradation
   - A/B test new prompts safely

3. **Dataset Management**
   ```python
   # Automatically save failed extractions for debugging
   def save_to_dataset(client: Client, run_id: str, error: str):
       client.create_example(
           dataset_name="extraction-errors",
           inputs={"document": "...", "error": error},
           outputs={"expected": "..."},
           metadata={"run_id": run_id}
       )
   ```

### Deployment Considerations
1. **Serverless Environments**: Ensure callbacks complete before function termination
2. **Data Privacy**: Configure PII redaction for sensitive documents
3. **Cost Management**: Use sampling for high-volume production
4. **Self-Hosting Option**: Available for enterprise requirements

## Implementation Timeline

### Sprint 1 (Weeks 1-2)
- [ ] Implement basic MetricsCallbackHandler
- [ ] Set up LangSmith integration
- [ ] Deploy to development environment
- [ ] Create monitoring dashboards

### Sprint 2 (Weeks 3-4)
- [ ] Implement RobustOutputParser
- [ ] Add streaming support to callbacks
- [ ] Create evaluation suite in LangSmith
- [ ] Performance testing

### Sprint 3 (Weeks 5-6)
- [ ] Memory implementation (if needed)
- [ ] Advanced LangSmith features
- [ ] Production deployment
- [ ] Documentation and training

## Success Metrics

1. **Observability**
   - 100% of LLM calls traced
   - < 100ms overhead from callbacks
   - 95% trace retention for debugging

2. **Reliability**
   - 50% reduction in parsing failures
   - 90% success rate with retry logic
   - < 5% of requests need manual intervention

3. **Performance**
   - No latency impact from tracing
   - 30% faster debugging with LangSmith
   - 20% reduction in token usage with better parsing

## Risk Mitigation

1. **Performance Impact**
   - Use async callbacks
   - Implement sampling in production
   - Monitor callback execution time

2. **Cost Management**
   - Set retry limits
   - Track token usage per retry
   - Use LangSmith sampling

3. **Data Security**
   - Review LangSmith data retention policies
   - Implement PII filtering
   - Consider self-hosted option for sensitive data

## Conclusion

This upgrade plan provides a structured approach to implementing LangChain best practices while maintaining production stability. The phased approach allows for incremental improvements with measurable benefits at each stage.

Key benefits:
- Enhanced observability for faster debugging
- Improved reliability with smart retry logic
- Better production monitoring capabilities
- Foundation for future AI improvements

Next steps:
1. Review and approve plan
2. Set up development environment
3. Begin Sprint 1 implementation
4. Schedule weekly progress reviews