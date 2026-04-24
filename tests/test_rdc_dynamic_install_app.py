"""
Tests for the hand-written ``installApp`` and ``waitForAppInstallation``
tools in ``sauce_api_mcp.rdc_dynamic``.

The pair replaces the auto-generated ``installApp`` tool so callers don't
have to drive the ``listAppInstallations`` poll loop themselves. Scenarios
covered:

1. ``installApp`` happy path (PENDING) returns the installation id plus a
   ``next_action`` pointing at ``waitForAppInstallation``.
2. ``installApp`` where the install resolves synchronously to FINISHED —
   no ``next_action`` should be set.
3. ``installApp`` where the backend POST fails — error surfaces with
   details, no ``next_action``.
4. ``waitForAppInstallation`` happy path where the status transitions
   PENDING → FINISHED across polls.
5. ``waitForAppInstallation`` budget exhausted while still PENDING —
   must return ``next_action`` asking the LLM to call the tool again.
6. ``waitForAppInstallation`` ERROR state surfaces a top-level ``error``.
7. ``waitForAppInstallation`` when the installation id isn't in the
   backend's list — returns an error rather than looping forever.
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

    Returns ``(server, captured_requests)``. Handler runs for every outbound
    request; captured requests are recorded in order for post-hoc asserts.
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


async def _call_install_app(server, **kwargs) -> Any:
    tool = await server.get_tool("installApp")
    return await tool.fn(**kwargs)


async def _call_wait_for_install(server, **kwargs) -> Any:
    tool = await server.get_tool("waitForAppInstallation")
    return await tool.fn(**kwargs)


@pytest.fixture(autouse=True)
def _no_sleep():
    """Keep tests fast — skip the real poll interval."""
    async def _instant(_delay):
        return None

    with patch.object(rdc_dynamic.asyncio, "sleep", _instant):
        yield


class TestInstallAppTool:
    @pytest.mark.asyncio
    async def test_pending_response_includes_next_action(self):
        """A PENDING install must direct the LLM to waitForAppInstallation."""
        session_id = "sess-123"
        installation_id = "install-abc"

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path.endswith(
                f"/sessions/{session_id}/device/installApp"
            )
            return httpx.Response(
                200,
                json={
                    "installationId": installation_id,
                    "app": "storage:uuid-abc",
                    "status": "PENDING",
                },
            )

        server, requests = _build_server_with_mock_transport(handler)
        result = await _call_install_app(
            server,
            sessionId=session_id,
            app="storage:uuid-abc",
            enableInstrumentation=True,
            launchAfterInstall=False,
            features={"networkCapture": True},
        )

        assert result["installationId"] == installation_id
        assert result["status"] == "PENDING"
        assert result["sessionId"] == session_id
        assert result["next_action"]["tool"] == "waitForAppInstallation"
        assert result["next_action"]["arguments"] == {
            "sessionId": session_id,
            "installationId": installation_id,
        }
        # POST body should carry the flags the caller set.
        body = json_mod.loads(requests[0].content.decode("utf-8"))
        assert body == {
            "app": "storage:uuid-abc",
            "enableInstrumentation": True,
            "launchAfterInstall": False,
            "features": {"networkCapture": True},
        }

    @pytest.mark.asyncio
    async def test_synchronous_finished_has_no_next_action(self):
        """If the install resolves synchronously, no polling hint is added."""
        session_id = "sess-456"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "installationId": "install-done",
                    "app": "storage:uuid",
                    "status": "FINISHED",
                },
            )

        server, _ = _build_server_with_mock_transport(handler)
        result = await _call_install_app(
            server, sessionId=session_id, app="storage:uuid"
        )

        assert result["status"] == "FINISHED"
        assert result["sessionId"] == session_id
        assert "next_action" not in result

    @pytest.mark.asyncio
    async def test_post_failure_returned_as_error(self):
        """Backend 4xx should short-circuit with an error and no next_action."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "type": "about:blank",
                    "title": "App not found",
                    "detail": "App storage:nope does not exist.",
                },
            )

        server, requests = _build_server_with_mock_transport(handler)
        result = await _call_install_app(
            server, sessionId="sess-789", app="storage:nope"
        )

        assert "error" in result
        assert "400" in result["error"]
        assert result["sessionId"] == "sess-789"
        assert result["details"]["title"] == "App not found"
        assert "next_action" not in result
        assert [r.method for r in requests] == ["POST"]

    @pytest.mark.asyncio
    async def test_defaults_enable_instrumentation_true(self):
        """enableInstrumentation defaults to True and is always on the wire.

        The backend default is also True, but we send it explicitly so the
        tool's behavior doesn't drift if the backend ever changes its
        default. launchAfterInstall and features stay absent unless the
        caller sets them.
        """
        session_id = "sess-min"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "installationId": "id-min",
                    "app": "storage:x",
                    "status": "FINISHED",
                },
            )

        server, requests = _build_server_with_mock_transport(handler)
        await _call_install_app(
            server, sessionId=session_id, app="storage:x"
        )

        body = json_mod.loads(requests[0].content.decode("utf-8"))
        assert body == {
            "app": "storage:x",
            "enableInstrumentation": True,
        }

    @pytest.mark.asyncio
    async def test_explicit_disable_instrumentation_is_respected(self):
        """Explicit enableInstrumentation=False must still be sent."""
        session_id = "sess-no-instr"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "installationId": "id-no-instr",
                    "app": "storage:x",
                    "status": "FINISHED",
                },
            )

        server, requests = _build_server_with_mock_transport(handler)
        await _call_install_app(
            server,
            sessionId=session_id,
            app="storage:x",
            enableInstrumentation=False,
        )

        body = json_mod.loads(requests[0].content.decode("utf-8"))
        assert body == {
            "app": "storage:x",
            "enableInstrumentation": False,
        }

    @pytest.mark.asyncio
    async def test_launch_after_install_flag_is_forwarded(self):
        """Setting launchAfterInstall=True must reach the backend payload.

        The docstring steers the LLM toward this flag instead of a
        follow-up launchApp call, so we want to make sure the wire format
        is correct when it does.
        """
        session_id = "sess-launch-after"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "installationId": "id-launch",
                    "app": "storage:x",
                    "status": "PENDING",
                },
            )

        server, requests = _build_server_with_mock_transport(handler)
        await _call_install_app(
            server,
            sessionId=session_id,
            app="storage:x",
            launchAfterInstall=True,
        )

        body = json_mod.loads(requests[0].content.decode("utf-8"))
        assert body == {
            "app": "storage:x",
            "enableInstrumentation": True,
            "launchAfterInstall": True,
        }


class TestWaitForAppInstallationTool:
    @pytest.mark.asyncio
    async def test_pending_then_finished(self):
        """Poll transitions PENDING → FINISHED and returns the final record."""
        session_id = "sess-wait-1"
        installation_id = "install-wait-1"
        statuses = iter(["PENDING", "FINISHED"])

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path.endswith(
                f"/sessions/{session_id}/device/listAppInstallations"
            )
            status = next(statuses)
            return httpx.Response(
                200,
                json={
                    "appInstallations": [
                        {
                            "installationId": installation_id,
                            "app": "storage:uuid",
                            "status": status,
                        },
                        # An unrelated installation in the same session; the
                        # tool must pick the one with the matching id.
                        {
                            "installationId": "other-install",
                            "app": "storage:other",
                            "status": "FINISHED",
                        },
                    ]
                },
            )

        server, requests = _build_server_with_mock_transport(handler)
        result = await _call_wait_for_install(
            server,
            sessionId=session_id,
            installationId=installation_id,
        )

        assert result["installationId"] == installation_id
        assert result["status"] == "FINISHED"
        assert result["sessionId"] == session_id
        assert "next_action" not in result
        assert "error" not in result
        # One poll saw PENDING, the next saw FINISHED.
        assert len(requests) == 2

    @pytest.mark.asyncio
    async def test_launching_status_is_terminal(self):
        """LAUNCHING counts as "done enough" — don't keep polling."""
        session_id = "sess-launch"
        installation_id = "install-launch"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "appInstallations": [
                        {
                            "installationId": installation_id,
                            "app": "storage:uuid",
                            "status": "LAUNCHING",
                        }
                    ]
                },
            )

        server, requests = _build_server_with_mock_transport(handler)
        result = await _call_wait_for_install(
            server,
            sessionId=session_id,
            installationId=installation_id,
        )

        assert result["status"] == "LAUNCHING"
        assert "next_action" not in result
        assert len(requests) == 1

    @pytest.mark.asyncio
    async def test_timeout_returns_next_action_call_again(self):
        """Budget exhausted while PENDING must hand control back to the LLM."""
        session_id = "sess-timeout"
        installation_id = "install-timeout"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "appInstallations": [
                        {
                            "installationId": installation_id,
                            "app": "storage:uuid",
                            "status": "PENDING",
                        }
                    ]
                },
            )

        server, _ = _build_server_with_mock_transport(handler)

        # asyncio.sleep is already no-op'd; zero the deadline too so the
        # deadline branch fires after the first observation.
        with patch.object(
            rdc_dynamic, "APP_INSTALL_POLL_TIMEOUT_SECONDS", 0.0
        ):
            result = await _call_wait_for_install(
                server,
                sessionId=session_id,
                installationId=installation_id,
            )

        assert result["status"] == "PENDING"
        assert result["sessionId"] == session_id
        assert result["installationId"] == installation_id
        assert result["next_action"]["tool"] == "waitForAppInstallation"
        assert result["next_action"]["arguments"] == {
            "sessionId": session_id,
            "installationId": installation_id,
        }
        assert "call" in result["next_action"]["message"].lower()

    @pytest.mark.asyncio
    async def test_error_status_surfaces_top_level_error(self):
        """ERROR status must set a top-level ``error`` for the caller."""
        session_id = "sess-err"
        installation_id = "install-err"
        backend_detail = "APK signature verification failed."

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "appInstallations": [
                        {
                            "installationId": installation_id,
                            "app": "storage:uuid",
                            "status": "ERROR",
                            "error": backend_detail,
                        }
                    ]
                },
            )

        server, _ = _build_server_with_mock_transport(handler)
        result = await _call_wait_for_install(
            server,
            sessionId=session_id,
            installationId=installation_id,
        )

        assert result["status"] == "ERROR"
        assert "error" in result
        assert backend_detail in result["error"]
        assert result["installationId"] == installation_id

    @pytest.mark.asyncio
    async def test_installation_not_found_returns_error(self):
        """If listAppInstallations doesn't include our id, error out."""
        session_id = "sess-missing"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "appInstallations": [
                        {
                            "installationId": "someone-else",
                            "app": "storage:other",
                            "status": "FINISHED",
                        }
                    ]
                },
            )

        server, requests = _build_server_with_mock_transport(handler)
        result = await _call_wait_for_install(
            server,
            sessionId=session_id,
            installationId="install-ghost",
        )

        assert "error" in result
        assert "install-ghost" in result["error"]
        assert result["sessionId"] == session_id
        # One lookup, then give up.
        assert len(requests) == 1

    @pytest.mark.asyncio
    async def test_list_failure_returned_as_error(self):
        """A 5xx on listAppInstallations is surfaced as an error."""
        session_id = "sess-5xx"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                500,
                json={"type": "about:blank", "title": "Internal Server Error"},
            )

        server, _ = _build_server_with_mock_transport(handler)
        result = await _call_wait_for_install(
            server,
            sessionId=session_id,
            installationId="any",
        )

        assert "error" in result
        assert "500" in result["error"]
        assert result["sessionId"] == session_id


class TestInstallAppToolSchema:
    @pytest.mark.asyncio
    async def test_install_app_required_params(self):
        """``sessionId`` and ``app`` must both be required in the schema."""
        handler = lambda _r: httpx.Response(200, json={})  # noqa: E731
        server, _ = _build_server_with_mock_transport(handler)

        tool = await server.get_tool("installApp")
        schema = tool.parameters
        required = set(schema.get("required", []))
        assert {"sessionId", "app"}.issubset(required), (
            f"sessionId and app must be required, got required={required}"
        )

    @pytest.mark.asyncio
    async def test_wait_for_app_installation_required_params(self):
        """``sessionId`` and ``installationId`` must both be required."""
        handler = lambda _r: httpx.Response(200, json={})  # noqa: E731
        server, _ = _build_server_with_mock_transport(handler)

        tool = await server.get_tool("waitForAppInstallation")
        schema = tool.parameters
        required = set(schema.get("required", []))
        assert {"sessionId", "installationId"}.issubset(required), (
            "sessionId and installationId must both be required, "
            f"got required={required}"
        )
