#!/bin/bash
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null && python --version 2>&1 | grep -q "Python 3"; then
    PYTHON_CMD="python"
else
    echo "Error: Python 3 not found in PATH" >&2
    exit 1
fi
exec $PYTHON_CMD -m sauce_api_mcp "$@"
