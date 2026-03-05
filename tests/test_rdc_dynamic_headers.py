import httpx
import pytest
from unittest.mock import patch

from sauce_api_mcp.rdc_dynamic import create_server


MINIMAL_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "test", "version": "0.0.1"},
    "paths": {},
}


class TestMcpHeaders:
    """Verify that outbound requests carry X-SAUCE-MCP-* headers."""

    @pytest.mark.asyncio
    async def test_inject_mcp_headers(self):
        # Capture the httpx.AsyncClient instance created inside create_server
        captured_client = None
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            nonlocal captured_client
            original_init(self, *args, **kwargs)
            captured_client = self

        with patch.object(httpx.AsyncClient, "__init__", patched_init):
            create_server(
                spec=MINIMAL_SPEC,
                access_key="fake_key",
                username="alice",
            )

        assert captured_client is not None

        captured_requests: list[httpx.Request] = []

        async def capture_handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(200, json={})

        captured_client._transport = httpx.MockTransport(capture_handler)

        await captured_client.get("/test")

        assert len(captured_requests) == 1
        req = captured_requests[0]
        assert req.headers["X-SAUCE-MCP-SERVER"] == "rdc_dynamic"
        assert req.headers["X-SAUCE-MCP-TRANSPORT"] == "stdio"
        assert req.headers["X-SAUCE-MCP-USER"] == "alice"
