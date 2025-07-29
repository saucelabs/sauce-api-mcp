#!/bin/bash

cd /Users/marcusmerrell/Projects/sauce-api-mcp

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
  echo "Installing dependencies..."
  source venv/bin/activate
  pip install -e .
else
  source venv/bin/activate
fi

python -m sauce_mcp.rdc_openapi
