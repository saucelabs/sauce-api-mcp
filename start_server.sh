# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
  python3 -m venv venv
  source venv/bin/activate
  pip install -e .
else
  source venv/bin/activate
fi

# Run via the entry point you have installed
sauce-mcp-core