# AShareInsight

Enterprise concept retrieval system with PostgreSQL and vector search.

## Overview

AShareInsight is an AI-powered system designed to analyze A-share company annual reports and research reports, extract key business concepts, and provide intelligent search and analysis capabilities.

## Tech Stack

- Python 3.13+
- PostgreSQL 16+ with pgvector
- LangChain & LangGraph
- FastAPI
- Redis for caching
- Docker for containerization

## Quick Start

### Prerequisites

- Python 3.13+
- Docker and Docker Compose
- uv (Python package manager)

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

3. Start the database:
```bash
docker-compose -f docker/docker-compose.yaml up -d
```

4. Run database migrations:
```bash
uv run python scripts/migration/init_db.py
```

### Development

Run tests:
```bash
uv run pytest
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
├── domain/          # Core business logic
├── application/     # Use cases and orchestration
├── infrastructure/  # External integrations
├── interfaces/      # API and CLI
└── shared/         # Cross-cutting concerns
```

## License

Copyright (c) 2025 AShareInsight Team. All rights reserved.