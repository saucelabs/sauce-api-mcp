"""
Tests for the hand-written ``createSession`` tool in
``sauce_api_mcp.rdc_dynamic``.

These cover the three shapes the tool must handle:
1. Happy path: POST /sessions returns PENDING, polling transitions through
   CREATING and lands on ACTIVE. Tool returns the final Session payload.
2. Timeout: session stays PENDING past the configured timeout. Tool returns
   an error explaining it took too long.
3. Backend error: polling observes ERRORED state. Tool surfaces the backend
   error explanation.
"""

from __future__ import annotations

import json as json_mod
from typing import Any, Callable, Dict, List
from unittest.mock import patch

import httpx
import pytest

from sauce_api_mcp import rdc_dynamic
from sauce_api_mcp.rdc_dynamic import create_server


MINIMAL_SPEC: Dict[str, Any] = {
    "openapi": "3.0.0",
    "info": {"title": "test", "version": "0.0.1"},
    "paths": {},
}


def _build_server_with_mock_transport(
    handler: Callable[[httpx.Request], httpx.Response],
):
    """Create an RDC server and swap its httpx client transport for a mock.

    Returns ``(server, captured_requests)``. The handler is called for every
    outbound request and should return an ``httpx.Response``. Captured
    requests are recorded in order for post-hoc assertions.
    """
    captured_client: List[httpx.AsyncClient] = []
    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        captured_client.append(self)

    with patch.object(httpx.AsyncClient, "__init__", patched_init):
        server = create_server(
            spec=MINIMAL_SPEC,
            access_key="fake_key",
            username="alice",
        )

    assert captured_client, "create_server did not instantiate an httpx client"
    client = captured_client[0]

    captured_requests: List[httpx.Request] = []

    async def wrapper(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return handler(request)

    client._transport = httpx.MockTransport(wrapper)
    return server, captured_requests


async def _call_create_session(server, **kwargs) -> Any:
    """Resolve and invoke the ``createSession`` tool by name."""
    tool = await server.get_tool("createSession")
    return await tool.fn(**kwargs)


@pytest.fixture(autouse=True)
def _no_sleep():
    """Keep tests fast — skip the real 2-second poll interval."""
    async def _instant(_delay):
        return None

    with patch.object(rdc_dynamic.asyncio, "sleep", _instant):
        yield


class TestCreateSessionTool:
    @pytest.mark.asyncio
    async def test_happy_path_returns_active_session(self):
        """POST returns PENDING, two polls show CREATING then ACTIVE."""
        session_id = "123e4567-e89b-12d3-a456-426614174000"
        states = iter(["CREATING", "ACTIVE"])
        active_session = {
            "id": session_id,
            "state": "ACTIVE",
            "device": {"descriptor": "iPhone_16_real", "os": "IOS"},
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST" and request.url.path.endswith("/sessions"):
                return httpx.Response(
                    200, json={"id": session_id, "state": "PENDING"}
                )
            if (
                request.method == "GET"
                and request.url.path.endswith(f"/sessions/{session_id}")
            ):
                next_state = next(states)
                if next_state == "ACTIVE":
                    return httpx.Response(200, json=active_session)
                return httpx.Response(
                    200, json={"id": session_id, "state": next_state}
                )
            raise AssertionError(f"unexpected request: {request.method} {request.url}")

        server, requests = _build_server_with_mock_transport(handler)
        result = await _call_create_session(
            server,
            os="ios",
            deviceName="iPhone_16_real",
        )

        assert result == active_session
        # 1 POST + 2 GETs (first: CREATING, second: ACTIVE)
        assert [r.method for r in requests] == ["POST", "GET", "GET"]
        # And the POST body should nest our flat params under device/.
        post_body = json_mod.loads(requests[0].content.decode("utf-8"))
        assert post_body == {
            "device": {"os": "ios", "deviceName": "iPhone_16_real"}
        }

    @pytest.mark.asyncio
    async def test_timeout_cancels_pending_session(self):
        """Timeout path must DELETE the pending session and flag it.

        The LLM-facing error message should explain what happened and steer
        the model toward asking the user what to do (retry vs. change the
        request), not toward an automatic retry.
        """
        session_id = "timeout-session-id"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(
                    200, json={"id": session_id, "state": "PENDING"}
                )
            if request.method == "GET":
                return httpx.Response(
                    200, json={"id": session_id, "state": "PENDING"}
                )
            if request.method == "DELETE":
                return httpx.Response(
                    200, json={"sessionId": session_id, "state": "CLOSING"}
                )
            raise AssertionError(f"unexpected request: {request.method}")

        server, requests = _build_server_with_mock_transport(handler)

        # Shrink the timeout so we can exercise the deadline branch without
        # actually waiting. asyncio.sleep is already no-op'd by the fixture,
        # but loop.time() is real, so we also need the deadline to be short.
        with patch.object(rdc_dynamic, "SESSION_POLL_TIMEOUT_SECONDS", 0.0):
            result = await _call_create_session(server, os="android")

        assert "error" in result
        assert result["reason"] == "allocation_timeout"
        assert result["sessionId"] == session_id
        assert result["state"] == "PENDING"
        assert result["cancellation"]["attempted"] is True
        assert result["cancellation"]["succeeded"] is True
        # The LLM-facing message should mention both choices we want the
        # model to surface to the user.
        assert "try the same request again" in result["error"]
        assert "change the allocation prompt" in result["error"]
        # And the DELETE should have actually been issued against the
        # session we created.
        delete_requests = [r for r in requests if r.method == "DELETE"]
        assert len(delete_requests) == 1
        assert delete_requests[0].url.path.endswith(f"/sessions/{session_id}")

    @pytest.mark.asyncio
    async def test_timeout_records_failed_cancellation(self):
        """If DELETE fails, that's captured in the cancellation block.

        We still return the timeout error — the session is the backend's
        problem at that point — but we don't lie about cleanup having
        worked.
        """
        session_id = "timeout-session-cleanup-fail"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(
                    200, json={"id": session_id, "state": "PENDING"}
                )
            if request.method == "GET":
                return httpx.Response(
                    200, json={"id": session_id, "state": "PENDING"}
                )
            if request.method == "DELETE":
                return httpx.Response(
                    500,
                    json={
                        "type": "about:blank",
                        "title": "Internal Server Error",
                    },
                )
            raise AssertionError(f"unexpected request: {request.method}")

        server, _requests = _build_server_with_mock_transport(handler)
        with patch.object(rdc_dynamic, "SESSION_POLL_TIMEOUT_SECONDS", 0.0):
            result = await _call_create_session(server, os="ios")

        assert result["reason"] == "allocation_timeout"
        assert result["cancellation"]["attempted"] is True
        assert result["cancellation"]["succeeded"] is False
        assert result["cancellation"]["status"] == 500

    @pytest.mark.asyncio
    async def test_errored_state_surfaces_backend_error(self):
        """ERRORED state should be returned with the backend's explanation."""
        session_id = "errored-session-id"
        backend_detail = "No matching device available in the requested pool."
        errored_payload = {
            "id": session_id,
            "state": "ERRORED",
            "error": backend_detail,
        }

        polled = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(
                    200, json={"id": session_id, "state": "PENDING"}
                )
            polled["count"] += 1
            return httpx.Response(200, json=errored_payload)

        server, _requests = _build_server_with_mock_transport(handler)
        result = await _call_create_session(server, os="ios")

        assert "error" in result
        assert backend_detail in result["error"]
        assert result["sessionId"] == session_id
        assert result["state"] == "ERRORED"
        assert result["details"] == errored_payload
        assert polled["count"] == 1

    @pytest.mark.asyncio
    async def test_create_post_failure_returned_as_error(self):
        """A 400 from POST /sessions short-circuits without polling."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            return httpx.Response(
                400,
                json={
                    "type": "about:blank",
                    "title": "Device does not exist.",
                    "detail": "The deviceId \"Samsung XR\" does not exist.",
                },
            )

        server, requests = _build_server_with_mock_transport(handler)
        result = await _call_create_session(
            server, os="android", deviceName="Samsung XR"
        )

        assert "error" in result
        assert "400" in result["error"]
        assert result["details"]["title"] == "Device does not exist."
        # No polling should have happened.
        assert [r.method for r in requests] == ["POST"]

    @pytest.mark.asyncio
    async def test_tunnel_and_duration_are_nested_into_configuration(self):
        """Flat tunnel/duration params should be packed into configuration."""
        session_id = "tunnel-session-id"
        active_session = {"id": session_id, "state": "ACTIVE"}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(
                    200, json={"id": session_id, "state": "PENDING"}
                )
            return httpx.Response(200, json=active_session)

        server, requests = _build_server_with_mock_transport(handler)
        await _call_create_session(
            server,
            os="android",
            sessionDuration="PT30M",
            tunnelName="staging-tunnel",
            tunnelOwner="other-user",
        )

        post_body = json_mod.loads(requests[0].content.decode("utf-8"))
        assert post_body == {
            "device": {"os": "android"},
            "configuration": {
                "sessionDuration": "PT30M",
                "tunnel": {"name": "staging-tunnel", "owner": "other-user"},
            },
        }

    @pytest.mark.asyncio
    async def test_tool_schema_marks_os_as_required(self):
        """LLM-facing schema should force ``os`` to be provided."""
        handler = lambda _r: httpx.Response(200, json={})  # noqa: E731
        server, _requests = _build_server_with_mock_transport(handler)

        tool = await server.get_tool("createSession")
        schema = tool.parameters
        assert "os" in schema.get("required", []), (
            f"'os' must be required in the tool schema, got: {schema}"
        )
        os_prop = schema["properties"]["os"]
        # The enum may sit under `enum` directly or inside an `anyOf`; accept
        # either shape as long as android/ios are the only allowed values.
        allowed = os_prop.get("enum") or next(
            (b.get("enum") for b in os_prop.get("anyOf", []) if "enum" in b),
            None,
        )
        assert allowed is not None, f"'os' schema missing enum: {os_prop}"
        assert set(allowed) == {"android", "ios"}
