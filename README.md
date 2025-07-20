# AShareInsight

Enterprise concept retrieval system with PostgreSQL and vector search.

## Overview

AShareInsight is an AI-powered system designed to analyze A-share company annual reports and research reports, extract key business concepts, and provide intelligent search and analysis capabilities.

This implementation (Story 1.2) focuses on LLM-based data extraction from financial documents using Google Gemini 2.5 Pro.

## Tech Stack

- Python 3.13+
- PostgreSQL 16+ with pgvector
- LangChain & LangGraph
- FastAPI
- Redis for caching
- Docker for containerization
- Google Gemini 2.5 Pro (via OpenAI-compatible API)

## Quick Start

### Prerequisites

- Python 3.13+
- Docker and Docker Compose
- uv (Python package manager)
- Gemini API credentials

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-org/AShareInsight.git
cd AShareInsight
```

2. Install dependencies with uv:
```bash
uv sync --dev
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env and add:
# GEMINI_API_KEY=sk-your-api-key-here
# GEMINI_BASE_URL=https://apius.tu-zi.com
```

4. Start the database:
```bash
docker-compose -f docker/docker-compose.yaml up -d
```

5. Run database migrations:
```bash
uv run python scripts/migration/init_db.py
```

## LLM Data Extraction (Story 1.2)

### Single Document Extraction

Extract structured data from financial documents:

```bash
# Extract annual report
uv run python -m src.interfaces.cli.extract_document \
    reference/inputs/开山股份_2024年年度报告摘要.md \
    --document-type annual_report

# Extract research report with debug mode
uv run python -m src.interfaces.cli.extract_document \
    reference/inputs/艾迪药业-688488-公司信息更新报告.txt \
    --document-type research_report \
    --debug
```

### Batch Processing

Process multiple documents efficiently:

```bash
# Scan documents without processing
uv run python scripts/batch_extract_all.py --dry-run

# Process all documents in data directory
uv run python scripts/batch_extract_all.py

# Process with custom settings
uv run python scripts/batch_extract_all.py \
    --batch-size 10 \
    --rate-limit-delay 60 \
    --max-documents 100
```

### Data Organization

#### Input Structure
```
data/
├── annual_reports/
│   ├── 2024/
│   │   ├── 300257_开山股份_2024_annual_report.md
│   │   └── 300663_科蓝软件_2024_annual_report.md
│   └── ...
├── research_reports/
│   ├── 2024/
│   │   ├── 688488_艾迪药业_20240115_公司信息更新报告.txt
│   │   └── 002747_埃斯顿_20240120_机器人新品发布.txt
│   └── ...
```

#### Output Structure
```
data/
├── extracted/
│   ├── annual_reports/
│   │   └── 300257_开山股份_2024_annual_report_extracted.json
│   └── research_reports/
│       └── 688488_艾迪药业_20240115_公司信息更新报告_extracted.json
├── metadata/
│   ├── company_index.json
│   ├── document_index.json
│   └── processing_log.json
```

### Example Extracted Data

#### Annual Report (开山股份)
```json
{
  "company_name_full": "开山集团股份有限公司",
  "company_name_short": "开山股份",
  "company_code": "300257",
  "exchange": "深圳证券交易所",
  "top_shareholders": [
    {
      "name": "开山控股集团股份有限公司",
      "holding_percentage": 56.98
    }
  ],
  "business_concepts": [
    {
      "concept_name": "螺杆空气压缩机",
      "concept_category": "核心业务",
      "description": "公司主营业务，涵盖螺杆式空气压缩机...",
      "importance_score": 0.95,
      "development_stage": "成熟期",
      "metrics": {
        "revenue": 3926653074.89,
        "revenue_growth_rate": 21.01,
        "gross_margin": 36.31
      }
    }
  ]
}
```

### Performance Metrics

| Document Type | Processing Time | Token Usage | Est. Cost |
|--------------|----------------|-------------|-----------|
| Annual Report | 90-100 seconds | ~50K tokens | ~$0.50 |
| Research Report | 40-45 seconds | ~20K tokens | ~$0.10 |

For 5000+ documents:
- Estimated time: ~75 hours
- Estimated cost: ~$1,700
- Recommendation: Process in batches over multiple days

### Development

Run tests:
```bash
# All tests (124 unit tests)
uv run pytest

# Unit tests only
uv run pytest tests/unit/

# With coverage
uv run pytest --cov=src tests/
```

Format code:
```bash
uv run black src tests
uv run ruff check src tests
```

## Project Structure

The project follows a hexagonal (ports and adapters) architecture:

```
src/
├── domain/              # Core business logic
│   └── entities/        # Company, ResearchReport, etc.
├── application/         # Use cases and orchestration
│   ├── use_cases/       # ExtractDocumentDataUseCase
│   └── ports/           # LLMServicePort interface
├── infrastructure/      # External integrations
│   ├── llm/            # Gemini LLM adapter
│   ├── document_processing/  # Document loaders
│   └── monitoring/      # OpenTelemetry integration
├── interfaces/          # API and CLI
│   └── cli/            # extract_document.py
└── shared/             # Cross-cutting concerns
    ├── config/         # Settings management
    └── exceptions/     # Custom exceptions
```

## Troubleshooting

### 401 Authentication Error
- Verify API key: `echo $GEMINI_API_KEY`
- Check base URL: Should be `https://apius.tu-zi.com`

### Timeout Errors
- Increase timeout in settings: `llm_timeout: int = 240`
- Consider smaller batch sizes for large documents

### JSON Parsing Errors
- System automatically extracts from markdown code blocks
- Numeric strings are converted to proper floats
- Invalid enums mapped to defaults

## Next Steps (Story 1.3)

The extracted structured data will be used for:
1. Creating embeddings using Qwen3-Embedding-4B
2. Storing in PostgreSQL with pgvector (halfvec type)
3. Building similarity search with HNSW indexing
4. Implementing RAG retrieval API

## License

Copyright (c) 2025 AShareInsight Team. All rights reserved.