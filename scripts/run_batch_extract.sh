#!/bin/bash
# Run batch extraction with correct environment

# Set the correct API key
# IMPORTANT: Set your API key as environment variable before running this script
# export GEMINI_API_KEY=<your-api-key-here>
if [ -z "$GEMINI_API_KEY" ]; then
    echo "Error: GEMINI_API_KEY environment variable is not set"
    echo "Please run: export GEMINI_API_KEY=<your-api-key>"
    exit 1
fi

export GEMINI_BASE_URL=https://apius.tu-zi.com

# Run the extraction script
exec uv run python scripts/batch_extract_all.py "$@"