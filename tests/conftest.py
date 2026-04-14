"""
Shared fixtures for sauce-api-mcp test suite.

Provides both mocked and live agent instances for comprehensive testing.
Live tests require SAUCE_USERNAME and SAUCE_ACCESS_KEY environment variables,
or fall back to .mcp.json credentials.
"""

import json
import os
import pytest
import httpx
from unittest.mock import MagicMock

from mcp.server import FastMCP as MCPFastMCP
from fastmcp import FastMCP as FastMCPLib

from sauce_api_mcp.main import SauceLabsAgent
from sauce_api_mcp.rdc_openapi import SauceLabsRDCAgent


# ---------------------------------------------------------------------------
# fastmcp 2.x / 3.x compatibility
# ---------------------------------------------------------------------------

async def compat_get_tools(server) -> dict:
    """Get tools as a {name: Tool} dict, compatible with fastmcp 2.x and 3.x.

    - fastmcp 2.x: server.get_tools() → dict[str, Tool]
    - fastmcp 3.x: server.list_tools() → list[Tool]  (get_tools removed)
    """
    if hasattr(server, "get_tools"):
        result = await server.get_tools()
        if isinstance(result, dict):
            return result
        # Shouldn't happen in 2.x, but handle it
        return {t.name: t for t in result}
    elif hasattr(server, "list_tools"):
        tools_list = await server.list_tools()
        return {t.name: t for t in tools_list}
    raise AttributeError("Server has neither get_tools() nor list_tools()")


async def compat_call_tool(server, name: str, arguments: dict):
    """Call a tool by name, compatible with fastmcp 2.x and 3.x.

    - fastmcp 2.x: server._tool_manager.call_tool(name, args)
    - fastmcp 3.x: server.call_tool(name, args)
    """
    if hasattr(server, "call_tool") and callable(server.call_tool):
        return await server.call_tool(name, arguments)
    elif hasattr(server, "_tool_manager"):
        return await server._tool_manager.call_tool(name, arguments)
    raise AttributeError("Server has neither call_tool() nor _tool_manager")


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def _load_credentials():
    """Load Sauce Labs credentials from env vars or .mcp.json fallback."""
    username = os.getenv("SAUCE_USERNAME")
    access_key = os.getenv("SAUCE_ACCESS_KEY")
    region = os.getenv("SAUCE_REGION", "EU_CENTRAL")

    if username and access_key:
        return username, access_key, region

    # Fallback: read from .mcp.json in project root
    mcp_json_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), ".mcp.json"
    )
    if os.path.exists(mcp_json_path):
        with open(mcp_json_path) as f:
            config = json.load(f)
        # Try core server config first, then rdc
        for server_key in ["sauce-api-mcp-core", "sauce-api-mcp-rdc"]:
            if server_key in config.get("mcpServers", {}):
                env = config["mcpServers"][server_key].get("env", {})
                username = env.get("SAUCE_USERNAME")
                access_key = env.get("SAUCE_ACCESS_KEY")
                region = env.get("SAUCE_REGION", "EU_CENTRAL")
                if username and access_key:
                    return username, access_key, region

    return None, None, region


USERNAME, ACCESS_KEY, REGION = _load_credentials()
HAS_CREDENTIALS = USERNAME is not None and ACCESS_KEY is not None

# Skip marker for live tests when credentials are unavailable
live = pytest.mark.skipif(
    not HAS_CREDENTIALS,
    reason="SAUCE_USERNAME / SAUCE_ACCESS_KEY not available"
)


# ---------------------------------------------------------------------------
# Mock fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_mcp_server():
    """Create a mock FastMCP server that records tool registrations."""
    server = MagicMock(spec=MCPFastMCP)
    server.tool.return_value = lambda fn: fn
    server.resource.return_value = lambda fn: fn
    return server


@pytest.fixture
def mock_transport():
    """
    Create an httpx.MockTransport that returns configurable responses.
    Default: 200 with empty JSON body.
    """
    def _factory(handler=None):
        if handler is None:
            async def default_handler(request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json={})
            handler = default_handler
        return httpx.MockTransport(handler)
    return _factory


@pytest.fixture
def core_agent_with_mock(mock_mcp_server, mock_transport):
    """
    Factory fixture: returns a SauceLabsAgent whose httpx client uses a MockTransport.
    Usage: agent, requests = core_agent_with_mock(handler_fn)
    """
    def _factory(handler=None):
        captured = []

        async def capturing_handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            if handler:
                return await handler(request)
            return httpx.Response(200, json={})

        agent = SauceLabsAgent(
            mock_mcp_server, "fake_key", "test_user", "US_WEST"
        )
        agent.client._transport = httpx.MockTransport(capturing_handler)
        return agent, captured

    return _factory


@pytest.fixture
def rdc_agent_with_mock(mock_transport):
    """
    Factory fixture: returns a SauceLabsRDCAgent whose httpx client uses a MockTransport.
    """
    def _factory(handler=None):
        captured = []

        async def capturing_handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            if handler:
                return await handler(request)
            return httpx.Response(200, json={})

        mcp = FastMCPLib("TestRDCAgent")
        agent = SauceLabsRDCAgent(mcp, "fake_key", "test_user", "US_WEST")
        agent.client._transport = httpx.MockTransport(capturing_handler)
        return agent, captured

    return _factory


# ---------------------------------------------------------------------------
# Live fixtures (hit real Sauce Labs APIs)
# ---------------------------------------------------------------------------

@pytest.fixture
def live_credentials():
    """Return (username, access_key, region) or skip if unavailable."""
    if not HAS_CREDENTIALS:
        pytest.skip("No Sauce Labs credentials available")
    return USERNAME, ACCESS_KEY, REGION


@pytest.fixture
def live_core_agent(live_credentials):
    """Function-scoped live SauceLabsAgent hitting real APIs.
    Created per-test to avoid event loop issues with httpx.AsyncClient."""
    username, access_key, region = live_credentials
    mcp = MagicMock(spec=MCPFastMCP)
    mcp.tool.return_value = lambda fn: fn
    mcp.resource.return_value = lambda fn: fn
    agent = SauceLabsAgent(mcp, access_key, username, region)
    return agent


@pytest.fixture
def live_rdc_agent(live_credentials):
    """Function-scoped live SauceLabsRDCAgent hitting real APIs."""
    username, access_key, region = live_credentials
    mcp = FastMCPLib("LiveRDCAgent")
    agent = SauceLabsRDCAgent(mcp, access_key, username, region)
    return agent
