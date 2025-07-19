# Data Fusion Algorithm Documentation

**Document Version**: 1.0  
**Created Date**: 2025-07-19  
**Author**: System Architecture Team

## Overview

The Fusion Algorithm is the core mechanism that maintains a single, authoritative view of each company's business concepts over time. It intelligently merges new information from recent documents with existing data in the master database.

## Algorithm Process Flow

The fusion process is triggered whenever a new document (annual report or research report) is processed for an existing company.

### Step 1: Concept Matching

For each `business_concept` extracted from the new document:

1. Check if a concept with the same `concept_name` exists in the company's master record
2. If **exists** → proceed to Step 2 (Field-Level Fusion)
3. If **new** → add the entire concept to the master record

### Step 2: Field-Level Fusion Rules

For matching concepts, apply field-specific update rules:

| Field | Fusion Rule | Rationale |
|:------|:------------|:----------|
| `concept_name` | **No Change** | Identifier field, used for matching |
| `concept_category` | **Overwrite** | Category may evolve (e.g., "新兴业务" → "核心业务") |
| `description` | **Overwrite** | Always use the most current description |
| `importance_score` | **Overwrite** | Reflects current strategic importance |
| `development_stage` | **Overwrite** | Tracks progression (e.g., "探索期" → "成长期") |
| `timeline.established` | **Keep Original** | Historical fact, doesn't change |
| `timeline.recent_event` | **Append to History** | Build comprehensive event history |
| `metrics` | **Overwrite** | Financial metrics are time-sensitive |
| `relations.customers` | **Union** | Merge lists, remove duplicates |
| `relations.partners` | **Union** | Merge lists, remove duplicates |
| `relations.subsidiaries` | **Union** | Merge lists, remove duplicates |
| `source_sentences` | **Append** | Accumulate evidence from all sources |

## Implementation Details

### Data Structures

```python
@dataclass
class BusinessConcept:
    concept_name: str
    concept_category: str
    description: str
    importance_score: float
    development_stage: str
    timeline: Timeline
    metrics: Metrics
    relations: Relations
    source_sentences: List[str]

@dataclass
class Timeline:
    established: Optional[str]
    events: List[Event]  # Historical events list

@dataclass
class Relations:
    customers: List[str]
    partners: List[str]
    subsidiaries_or_investees: List[str]
```

### Fusion Service Implementation

```python
class DataFusionService:
    def fuse_company_data(
        self, 
        company_code: str,
        new_concepts: List[BusinessConcept],
        source_doc_id: UUID
    ) -> None:
        """
        Fuses new business concepts with existing master data.
        
        Args:
            company_code: The company's stock code
            new_concepts: Concepts extracted from new document
            source_doc_id: Reference to source document
        """
        # Get existing master record
        master_record = self.repo.get_company_concepts(company_code)
        
        for new_concept in new_concepts:
            existing = self._find_concept_by_name(
                master_record.concepts, 
                new_concept.concept_name
            )
            
            if existing:
                self._update_existing_concept(existing, new_concept)
            else:
                self._add_new_concept(master_record, new_concept)
        
        # Update metadata
        master_record.last_updated_from_doc_id = source_doc_id
        master_record.updated_at = datetime.now()
        
        # Save with version control
        self.repo.save_with_version_check(master_record)
    
    def _update_existing_concept(
        self, 
        existing: BusinessConcept, 
        new: BusinessConcept
    ) -> None:
        """Apply field-level fusion rules."""
        # Overwrite rules
        existing.concept_category = new.concept_category
        existing.description = new.description
        existing.importance_score = new.importance_score
        existing.development_stage = new.development_stage
        existing.metrics = new.metrics
        
        # Append timeline events
        if new.timeline.recent_event:
            existing.timeline.events.append({
                'date': datetime.now(),
                'event': new.timeline.recent_event
            })
        
        # Union relations (with deduplication)
        existing.relations.customers = list(set(
            existing.relations.customers + new.relations.customers
        ))
        existing.relations.partners = list(set(
            existing.relations.partners + new.relations.partners
        ))
        existing.relations.subsidiaries_or_investees = list(set(
            existing.relations.subsidiaries_or_investees + 
            new.relations.subsidiaries_or_investees
        ))
        
        # Append source sentences
        existing.source_sentences.extend(new.source_sentences)
```

## Transaction Management

All fusion operations are wrapped in database transactions to ensure data consistency:

```python
async def execute_fusion(self, company_code: str, new_data: dict):
    async with self.db.transaction():
        try:
            await self._validate_company_exists(company_code)
            await self._apply_fusion_rules(company_code, new_data)
            await self._update_vector_embeddings(company_code)
            await self._log_fusion_event(company_code)
        except Exception as e:
            # Transaction automatically rolls back
            logger.error(f"Fusion failed for {company_code}: {e}")
            raise
```

## Conflict Resolution

### Version Control
- Each update increments the `version` field in `business_concepts_master`
- Optimistic locking prevents concurrent update conflicts

### Duplicate Detection
- Concept names are normalized before matching (lowercase, remove special chars)
- Fuzzy matching with threshold (>0.9 similarity) to catch near-duplicates

## Performance Considerations

1. **Batch Processing**: Process multiple concepts in a single transaction
2. **Indexing**: Ensure indexes on `company_code` and `concept_name`
3. **Async Operations**: Use async/await for I/O operations
4. **Caching**: Cache frequently accessed master records

## Monitoring and Logging

Each fusion operation logs:
- Source document ID
- Number of concepts updated/added
- Execution time
- Any conflicts or errors

```python
logger.info(
    f"Fusion completed for {company_code}: "
    f"{updated_count} updated, {added_count} added, "
    f"duration={duration_ms}ms"
)
```

## Future Enhancements

1. **ML-based Concept Matching**: Use embeddings to match similar concepts with different names
2. **Confidence Scoring**: Track confidence in fused data based on source quality
3. **Temporal Versioning**: Maintain full history of all changes
4. **Conflict UI**: Build interface for manual conflict resolution