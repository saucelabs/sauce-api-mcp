"""Tracking headers and query params sent with every Sauce Labs request.

The names include "oss" to mark requests from this open source server.
"""

from typing import Awaitable, Callable

import httpx


def tracking_params(api_name: str) -> dict[str, str]:
    return {"ai": f"sauce_mcp_oss_{api_name}"}


def tracking_hook(
    api_name: str, username: str, transport: str = "stdio"
) -> Callable[[httpx.Request], Awaitable[None]]:
    async def _inject(request: httpx.Request) -> None:
        request.headers["X-SAUCE-MCP-SERVER"] = f"sauce-mcp-oss-{api_name}"
        request.headers["X-SAUCE-MCP-TRANSPORT"] = transport
        request.headers["X-SAUCE-MCP-USER"] = username

    return _inject
