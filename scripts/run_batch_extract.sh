#!/bin/bash
# Run batch extraction with correct environment

# Set the correct API key
export GEMINI_API_KEY=sk-PzX4fMzvcHKxQb4NnfwhJ3mzk9HzleX7MXfaFcFhoIdclEr3
export GEMINI_BASE_URL=https://apius.tu-zi.com

# Run the extraction script
exec uv run python scripts/batch_extract_all.py "$@"