"""Helpers shared by the Core and RDC MCP servers."""

from importlib.metadata import PackageNotFoundError, version


def _package_version() -> str:
    try:
        return version("sauce-api-mcp")
    except PackageNotFoundError:
        return "unknown"


# Identifies requests sent by this open source MCP server.
USER_AGENT = f"Sauce OSS MCP Server/{_package_version()}"
