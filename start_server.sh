#!/bin/bash

cd /Users/marcusmerrell/Projects/sauce-api-mcp/src/sauce_mcp

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
  echo "Installing dependencies..."
  source venv/bin/activate
  pip install httpx pydantic mcp  # Add more dependencies as needed
else
  source venv/bin/activate
fi

python server.py
