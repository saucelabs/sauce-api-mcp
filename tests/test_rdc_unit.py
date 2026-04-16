"""
Unit tests for SauceLabsRDCAgent (rdc_openapi.py) — RDC MCP server.

All HTTP calls are intercepted via httpx.MockTransport.
Tests verify request construction, response parsing, error handling,
and input validation for all RDC tools.
"""

import pytest
import httpx


# ===================================================================
# Initialization
# ===================================================================

class TestRDCAgentInit:
    """Tests for SauceLabsRDCAgent construction."""

    def test_default_region(self, rdc_agent_with_mock):
        agent, _ = rdc_agent_with_mock()
        assert "us-west-1" in str(agent.client.base_url)

    def test_username_stored(self, rdc_agent_with_mock):
        agent, _ = rdc_agent_with_mock()
        assert agent.username == "test_user"


# ===================================================================
# sauce_api_call
# ===================================================================

class TestRDCSauceApiCall:
    """Tests for the RDC agent's internal sauce_api_call."""

    @pytest.mark.asyncio
    async def test_ai_param_is_rdc_mcp(self, rdc_agent_with_mock):
        agent, requests = rdc_agent_with_mock()
        await agent.sauce_api_call("test/endpoint")
        assert "ai=rdc_mcp" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_404_returns_response_object(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = rdc_agent_with_mock(handler)
        result = await agent.sauce_api_call("missing")
        assert isinstance(result, httpx.Response)

    @pytest.mark.asyncio
    async def test_401_returns_error_dict(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(401, json={"error": "unauthorized"})

        agent, _ = rdc_agent_with_mock(handler)
        result = await agent.sauce_api_call("auth")
        assert isinstance(result, dict)
        assert "error" in result


# ===================================================================
# Device status
# ===================================================================

class TestListDeviceStatus:
    """Tests for list_device_status tool."""

    @pytest.mark.asyncio
    async def test_list_all_devices(self, rdc_agent_with_mock):
        devices = [
            {"id": "d1", "state": "AVAILABLE"},
            {"id": "d2", "state": "IN_USE"}
        ]

        async def handler(req):
            return httpx.Response(200, json=devices)

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.list_device_status()
        assert len(result) == 2
        assert "rdc/v2/devices/status" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_filter_by_state(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json=[])

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.list_device_status(state="AVAILABLE")
        assert "state=AVAILABLE" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_invalid_state_returns_error(self, rdc_agent_with_mock):
        agent, _ = rdc_agent_with_mock()
        result = await agent.list_device_status(state="INVALID_STATE")
        assert "error" in result
        assert "Invalid state" in result["error"]
        assert "valid_states" in result

    @pytest.mark.asyncio
    async def test_private_only_filter(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json=[])

        agent, requests = rdc_agent_with_mock(handler)
        await agent.list_device_status(privateOnly=True)
        assert "privateOnly=true" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_device_name_filter(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json=[])

        agent, requests = rdc_agent_with_mock(handler)
        await agent.list_device_status(deviceName="iPhone.*")
        assert "deviceName=iPhone" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_401_unauthorized(self, rdc_agent_with_mock):
        """
        401 is caught by sauce_api_call and returned as a dict.
        list_device_status then tries response.status_code on the dict,
        raising AttributeError — this is a known bug in the production code
        where the isinstance(response, dict) guard is missing.
        """
        async def handler(req):
            return httpx.Response(401, json={"error": "unauthorized"})

        agent, _ = rdc_agent_with_mock(handler)
        with pytest.raises(AttributeError, match="status_code"):
            await agent.list_device_status()


# ===================================================================
# Device sessions
# ===================================================================

class TestDeviceSessions:
    """Tests for session management tools."""

    @pytest.mark.asyncio
    async def test_list_sessions(self, rdc_agent_with_mock):
        sessions = [{"id": "s1", "state": "ACTIVE"}]

        async def handler(req):
            return httpx.Response(200, json=sessions)

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.list_device_sessions()
        assert len(result) == 1
        assert "rdc/v2/sessions" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_list_sessions_filter_state(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json=[])

        agent, requests = rdc_agent_with_mock(handler)
        await agent.list_device_sessions(state="ACTIVE")
        assert "state=ACTIVE" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_list_sessions_invalid_state(self, rdc_agent_with_mock):
        agent, _ = rdc_agent_with_mock()
        result = await agent.list_device_sessions(state="BOGUS")
        assert "error" in result
        assert "Invalid state" in result["error"]

    @pytest.mark.asyncio
    async def test_get_session_details_success(self, rdc_agent_with_mock):
        session = {"id": "s1", "state": "ACTIVE", "device": {"name": "iPhone 14"}}

        async def handler(req):
            return httpx.Response(200, json=session)

        agent, _ = rdc_agent_with_mock(handler)
        result = await agent.get_session_details("s1")
        assert result["id"] == "s1"
        assert result["state"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_get_session_details_404(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = rdc_agent_with_mock(handler)
        result = await agent.get_session_details("nonexistent")
        assert "error" in result
        assert "Session not found" in result["error"]

    @pytest.mark.asyncio
    async def test_allocate_session_success(self, rdc_agent_with_mock):
        session = {"id": "new-session", "state": "PENDING"}

        async def handler(req):
            return httpx.Response(200, json=session)

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.allocate_device_and_create_session(
            deviceName="iPhone.*", os="ios"
        )
        assert result["id"] == "new-session"
        assert requests[0].method == "POST"

    @pytest.mark.asyncio
    async def test_allocate_session_invalid_os(self, rdc_agent_with_mock):
        agent, _ = rdc_agent_with_mock()
        result = await agent.allocate_device_and_create_session(os="windows")
        assert "error" in result
        assert "Invalid OS" in result["error"]

    @pytest.mark.asyncio
    async def test_close_session_success(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json={"status": "closed"})

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.close_device_session("s1")
        assert requests[0].method == "DELETE"

    @pytest.mark.asyncio
    async def test_close_session_404(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = rdc_agent_with_mock(handler)
        result = await agent.close_device_session("nonexistent")
        assert "error" in result
        assert "Session not found" in result["error"]


# ===================================================================
# HTTP Proxy forwarding
# ===================================================================

class TestHttpProxy:
    """Tests for HTTP proxy forwarding tools."""

    @pytest.mark.asyncio
    async def test_forward_get(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json={"data": "response"})

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.forward_http_get("s1", "example.com", "443", "api/data")
        assert result["data"] == "response"
        assert requests[0].method == "GET"
        assert "proxy/http/example.com/443/api/data" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_forward_post(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json={"created": True})

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.forward_http_post(
            "s1", "api.example.com", "443", "v1/items",
            data={"name": "test"}
        )
        assert requests[0].method == "POST"

    @pytest.mark.asyncio
    async def test_forward_put(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json={"updated": True})

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.forward_http_put(
            "s1", "api.example.com", "443", "v1/items/1",
            data={"name": "updated"}
        )
        assert requests[0].method == "PUT"

    @pytest.mark.asyncio
    async def test_forward_delete(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json={"deleted": True})

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.forward_http_delete("s1", "api.example.com", "443", "v1/items/1")
        assert requests[0].method == "DELETE"

    @pytest.mark.asyncio
    async def test_forward_options(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json={})

        agent, requests = rdc_agent_with_mock(handler)
        await agent.forward_http_options("s1", "example.com", "443", "api")
        assert requests[0].method == "OPTIONS"

    @pytest.mark.asyncio
    async def test_forward_head(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json={})

        agent, requests = rdc_agent_with_mock(handler)
        await agent.forward_http_head("s1", "example.com", "443", "api")
        assert requests[0].method == "HEAD"

    @pytest.mark.asyncio
    async def test_proxy_session_not_found(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = rdc_agent_with_mock(handler)
        result = await agent.forward_http_get("bad_session", "example.com", "443", "path")
        assert "error" in result
        assert "Session not found" in result["error"]

    @pytest.mark.asyncio
    async def test_proxy_rate_limited(self, rdc_agent_with_mock):
        """429 is caught by sauce_api_call and returned as generic error dict."""
        async def handler(req):
            return httpx.Response(429, json={})

        agent, _ = rdc_agent_with_mock(handler)
        result = await agent.forward_http_get("s1", "example.com", "443", "path")
        assert isinstance(result, dict)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_proxy_device_not_ready(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(400, json={"title": "Device not ready"})

        agent, _ = rdc_agent_with_mock(handler)
        result = await agent.forward_http_get("s1", "example.com", "443", "path")
        assert "error" in result
        assert "not ready" in result["error"]


# ===================================================================
# App management
# ===================================================================

class TestAppManagement:
    """Tests for app install/launch tools."""

    @pytest.mark.asyncio
    async def test_install_app_success(self, rdc_agent_with_mock):
        install_data = {"installationId": "inst1", "status": "PENDING"}

        async def handler(req):
            return httpx.Response(200, json=install_data)

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.install_app_from_storage(
            "s1", "storage:filename=app.apk"
        )
        assert result["installationId"] == "inst1"
        assert requests[0].method == "POST"
        assert "installApp" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_install_app_with_features(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json={"status": "ok"})

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.install_app_from_storage(
            "s1", "storage:uuid123",
            enableInstrumentation=True,
            launchAfterInstall=True,
            features={"networkCapture": True, "biometricsInterception": False}
        )
        assert "status" in result

    @pytest.mark.asyncio
    async def test_install_app_invalid_features(self, rdc_agent_with_mock):
        agent, _ = rdc_agent_with_mock()
        result = await agent.install_app_from_storage(
            "s1", "storage:uuid",
            features={"invalidFeature": True}
        )
        assert "error" in result
        assert "Invalid features" in result["error"]

    @pytest.mark.asyncio
    async def test_list_app_installations(self, rdc_agent_with_mock):
        installations = [{"id": "i1", "status": "COMPLETED"}]

        async def handler(req):
            return httpx.Response(200, json=installations)

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.list_app_installations("s1")
        assert len(result) == 1
        assert requests[0].method == "POST"

    @pytest.mark.asyncio
    async def test_launch_app_android(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(204)

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.launch_app("s1", packageName="com.example.app")
        assert result["success"] is True
        assert requests[0].method == "POST"

    @pytest.mark.asyncio
    async def test_launch_app_ios(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(204)

        agent, _ = rdc_agent_with_mock(handler)
        result = await agent.launch_app("s1", bundleId="com.example.app")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_launch_app_both_platforms_error(self, rdc_agent_with_mock):
        agent, _ = rdc_agent_with_mock()
        result = await agent.launch_app(
            "s1", packageName="com.example", bundleId="com.example"
        )
        assert "error" in result
        assert "Cannot specify both" in result["error"]

    @pytest.mark.asyncio
    async def test_launch_app_no_identifier_error(self, rdc_agent_with_mock):
        agent, _ = rdc_agent_with_mock()
        result = await agent.launch_app("s1")
        assert "error" in result
        assert "Must specify" in result["error"]


# ===================================================================
# Shell command & URL
# ===================================================================

class TestDeviceControl:
    """Tests for shell command and URL tools."""

    @pytest.mark.asyncio
    async def test_execute_shell_command(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(200, json={"output": "/\ndata\nsystem"})

        agent, requests = rdc_agent_with_mock(handler)
        result = await agent.execute_shell_command("s1", "ls /")
        assert "output" in result
        assert "executeShellCommand" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_execute_shell_command_empty(self, rdc_agent_with_mock):
        agent, _ = rdc_agent_with_mock()
        result = await agent.execute_shell_command("s1", "")
        assert "error" in result
        assert "Invalid adb command" in result["error"]

    @pytest.mark.asyncio
    async def test_open_url_success(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(204)

        agent, _ = rdc_agent_with_mock(handler)
        result = await agent.open_url_or_deeplink("s1", "https://example.com")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_open_url_empty(self, rdc_agent_with_mock):
        agent, _ = rdc_agent_with_mock()
        result = await agent.open_url_or_deeplink("s1", "")
        assert "error" in result
        assert "Invalid URL" in result["error"]

    @pytest.mark.asyncio
    async def test_open_deeplink(self, rdc_agent_with_mock):
        async def handler(req):
            return httpx.Response(204)

        agent, _ = rdc_agent_with_mock(handler)
        result = await agent.open_url_or_deeplink("s1", "myapp://home/settings")
        assert result["success"] is True
