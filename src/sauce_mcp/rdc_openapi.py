import sys
print("RDC OpenAPI server starting...", file=sys.stderr)

import os
import httpx
import yaml
print("yaml imported successfully", file=sys.stderr)

from fastmcp import FastMCP
print("FastMCP imported successfully", file=sys.stderr)

def check_stdio_is_not_tty():
    """Check if running in proper MCP environment"""
    if sys.stdin.isatty() or sys.stdout.isatty() or sys.stderr.isatty():
        print("Error: This server is not meant to be run interactively.", file=sys.stderr)
        return False
    return True

print("About to start server...", file=sys.stderr)

if __name__ == "__main__":
    print("Main block executing...", file=sys.stderr)
    if not check_stdio_is_not_tty():
        sys.exit(1)

    # Create the FastMCP server instance
    mcp_server_instance = FastMCP("Sauce Labs RDC API")

    # Environment variables
    SAUCE_ACCESS_KEY = os.getenv("SAUCE_ACCESS_KEY")
    if SAUCE_ACCESS_KEY is None:
        raise ValueError("SAUCE_ACCESS_KEY environment variable is not set.")

    SAUCE_USERNAME = os.getenv("SAUCE_USERNAME")
    if SAUCE_USERNAME is None:
        raise ValueError("SAUCE_USERNAME environment variable is not set.")

    SAUCE_REGION = os.getenv("SAUCE_REGION")
    if SAUCE_REGION is None:
        SAUCE_REGION = "US_WEST"

    # Download and parse OpenAPI spec
    response = httpx.get("https://raw.githubusercontent.com/saucelabs/real-device-api/refs/heads/main/open_api_specification.yaml?token=GHSAT0AAAAAADE5O5EN3DJ43I7QBBP7TXNA2EJMUEA")
    response.raise_for_status()
    openapi_spec = yaml.safe_load(response.text)

    # Create HTTP client
    client = httpx.Client(
        base_url="https://api.us-west-1.saucelabs.com/v1/rdc",
        auth=(SAUCE_USERNAME, SAUCE_ACCESS_KEY)
    )

    # Generate RDC tools from OpenAPI and register them
    mcp_server_instance = FastMCP.from_openapi(
        openapi_spec=openapi_spec,
        client=client,
        name="temp"
    )
    # Run the server
    mcp_server_instance.run(transport="stdio")