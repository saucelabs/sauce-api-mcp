"""Helpers shared by the Core and RDC MCP servers."""

from importlib.metadata import PackageNotFoundError, version

import httpx


def _package_version() -> str:
    try:
        return version("sauce-api-mcp")
    except PackageNotFoundError:
        return "unknown"


# Identifies requests sent by this open source MCP server.
USER_AGENT = (
    f"sauce-api-mcp/{_package_version()} "
    "(Sauce Labs Open Source MCP Server; +https://github.com/saucelabs/sauce-api-mcp) "
    f"python-httpx/{httpx.__version__}"
)
