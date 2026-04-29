"""
End-to-end tests for the dynamic OpenAPI MCP server (rdc_dynamic.py).

Tests the FULL pipeline:
  1. Fetch OpenAPI spec from GitHub (or local file)
  2. Auto-generate MCP tools from spec paths
  3. Invoke tools via call_tool() hitting live Sauce Labs APIs
  4. Return ToolResult with parsed JSON responses

Production code is NOT modified. Issues found are flagged inline.

Run:
  # Offline tests (fast, no credentials)
  pytest tests/test_rdc_dynamic_e2e.py -k "not live" -v

  # All tests including live API calls
  SAUCE_USERNAME=... SAUCE_ACCESS_KEY=... SAUCE_REGION=EU_CENTRAL \\
    pytest tests/test_rdc_dynamic_e2e.py -v

  # Including slow device-allocation tests
  pytest tests/test_rdc_dynamic_e2e.py -v -W ignore::pytest.PytestUnknownMarkWarning
"""

import asyncio
import base64
import json
import os
import tempfile

import httpx
import pytest
import yaml

from sauce_api_mcp.rdc_dynamic import (
    DEFAULT_SPEC_URL,
    DATA_CENTERS,
    EXCLUDED_PATHS,
    create_server,
    fetch_openapi_spec_sync,
    resolve_refs,
    route_map_fn,
)

from tests.conftest import live, HAS_CREDENTIALS, _load_credentials, compat_get_tools, compat_call_tool

USERNAME, ACCESS_KEY, REGION = _load_credentials()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_refs(schema, path="root"):
    """Recursively find all $ref and $defs keys in a schema tree."""
    found = []
    if isinstance(schema, dict):
        if "$ref" in schema:
            found.append(f"{path}.$ref = {schema['$ref']}")
        if "$defs" in schema:
            found.append(f"{path}.$defs present")
        for k, v in schema.items():
            found.extend(_find_refs(v, f"{path}.{k}"))
    elif isinstance(schema, list):
        for i, item in enumerate(schema):
            found.extend(_find_refs(item, f"{path}[{i}]"))
    return found


def _parse_tool_result(result):
    """Extract parsed JSON from a ToolResult."""
    return json.loads(result.content[0].text)


def _get_internal_tools(server):
    """Get raw tool objects from a server, compat across fastmcp 2.x/3.x."""
    # fastmcp 2.x
    if hasattr(server, "_tool_manager") and hasattr(server._tool_manager, "_tools"):
        return server._tool_manager._tools
    # fastmcp 3.x — tools stored in provider
    if hasattr(server, "_local_provider"):
        provider = server._local_provider
        if hasattr(provider, "_tools"):
            return provider._tools
        if hasattr(provider, "tools"):
            return provider.tools
    # Fallback: use the sync list via async helper
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        tools = loop.run_until_complete(compat_get_tools(server))
        return tools
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def spec_from_url():
    """Fetch real OpenAPI spec from GitHub (once per module)."""
    try:
        spec = fetch_openapi_spec_sync(DEFAULT_SPEC_URL)
    except Exception:
        pytest.skip("Could not fetch OpenAPI spec from GitHub")
    return spec


@pytest.fixture
def spec_from_local_file(spec_from_url):
    """Write spec to temp YAML file and load via local file path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        yaml.dump(spec_from_url, f)
        tmp_path = f.name
    try:
        yield fetch_openapi_spec_sync(tmp_path)
    finally:
        os.unlink(tmp_path)


_offline_server_cache = {}


@pytest.fixture(scope="module")
def offline_server_and_requests(spec_from_url):
    """
    Module-scoped server with mock transport — no live API calls.
    Returns (server, captured_requests_list).
    """
    captured = []

    async def capture_handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"mock": True})

    server = create_server(spec_from_url, "fake_key", "fake_user", "EU_CENTRAL")

    # Replace the httpx client's transport with a mock
    # The client is stored on the server and passed to each OpenAPITool
    internal_tools = _get_internal_tools(server)
    tools_iter = internal_tools.values() if isinstance(internal_tools, dict) else internal_tools
    for tool in tools_iter:
        if hasattr(tool, "_client"):
            tool._client._transport = httpx.MockTransport(capture_handler)
            break

    # Also replace the client used by manual tools (it's in the closure)
    # We access it via the server's client attribute pattern
    # FastMCPOpenAPI stores it as self._client (though it's not publicly documented)
    if hasattr(server, "_client"):
        server._client._transport = httpx.MockTransport(capture_handler)

    return server, captured


@pytest.fixture(scope="module")
def offline_server(offline_server_and_requests):
    return offline_server_and_requests[0]


@pytest.fixture(scope="module")
def captured_requests(offline_server_and_requests):
    return offline_server_and_requests[1]


@pytest.fixture
def live_dynamic_server(live_credentials, spec_from_url):
    """Function-scoped server with real credentials for live API tests."""
    username, access_key, region = live_credentials
    server = create_server(spec_from_url, access_key, username, region)
    return server


# Reuse live_credentials from conftest.py — it skips if no creds


# ===================================================================
# 1. Spec Fetching
# ===================================================================

class TestSpecFetching:
    """Tests for OpenAPI spec download and parsing."""

    def test_fetch_from_github_url(self, spec_from_url):
        """Spec fetched from GitHub is a valid OpenAPI 3.0 dict."""
        assert isinstance(spec_from_url, dict)
        assert "openapi" in spec_from_url
        assert spec_from_url["openapi"].startswith("3.")
        assert "info" in spec_from_url
        assert "paths" in spec_from_url
        assert len(spec_from_url["paths"]) > 0

    def test_fetch_from_local_file(self, spec_from_local_file, spec_from_url):
        """Local file fetch produces same path count as URL fetch."""
        assert isinstance(spec_from_local_file, dict)
        assert len(spec_from_local_file["paths"]) == len(spec_from_url["paths"])

    def test_fetch_invalid_url_raises(self, tmp_path, monkeypatch):
        """With no cache available, fetch failure after retries raises RuntimeError."""
        import sauce_api_mcp.rdc_dynamic as rdc

        def failing_get(*args, **kwargs):
            raise httpx.ConnectError("simulated network failure")

        monkeypatch.setattr(rdc, "SPEC_CACHE_FILE", str(tmp_path / "nonexistent.yaml"))
        monkeypatch.setattr(rdc.httpx, "get", failing_get)
        with pytest.raises(RuntimeError, match="after 3 retries"):
            fetch_openapi_spec_sync("https://example.invalid/spec.yaml")

    def test_fetch_falls_back_to_cache(self, tmp_path, monkeypatch, spec_from_url):
        """When remote fetch fails, a seeded cache file is returned."""
        import sauce_api_mcp.rdc_dynamic as rdc

        def failing_get(*args, **kwargs):
            raise httpx.ConnectError("simulated network failure")

        cache_file = tmp_path / "rdc-access-api-spec.yaml"
        cache_file.write_text(yaml.dump(spec_from_url))
        monkeypatch.setattr(rdc, "SPEC_CACHE_FILE", str(cache_file))
        monkeypatch.setattr(rdc.httpx, "get", failing_get)
        result = fetch_openapi_spec_sync("https://example.invalid/spec.yaml")
        assert result == spec_from_url

    def test_fetch_nonexistent_file_raises(self):
        """Fetching from a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            fetch_openapi_spec_sync("/nonexistent/path/spec.yaml")

    def test_spec_structure(self, spec_from_url):
        """Spec has expected OpenAPI structure."""
        assert "info" in spec_from_url
        assert "title" in spec_from_url["info"]
        assert len(spec_from_url["info"]["title"]) > 0
        assert "servers" in spec_from_url
        assert len(spec_from_url["servers"]) > 0
        # All paths should start with /
        for path in spec_from_url["paths"]:
            assert path.startswith("/"), f"Path '{path}' doesn't start with /"


# ===================================================================
# 2. Tool Generation
# ===================================================================

class TestToolGeneration:
    """Tests for MCP tool auto-generation from OpenAPI spec."""

    @pytest.mark.asyncio
    async def test_total_tool_count(self, offline_server):
        """Server should have 31 tools (24 auto + 7 manual).

        The 7 manual tools are createSession, installApp,
        waitForAppInstallation, push_file_to_device,
        pull_file_from_device, take_screenshot, and proxy_http.
        proxy_http replaces six method-specific auto-generated tools
        (proxyGet/Post/...). createSession, installApp replace their
        auto-generated counterparts and add waitForAppInstallation.
        """
        tools = await compat_get_tools(offline_server)
        assert len(tools) == 31, (
            f"Expected 31 tools, got {len(tools)}. Names: {sorted(tools.keys())}"
        )

    @pytest.mark.asyncio
    async def test_excluded_paths_not_auto_generated(self, offline_server):
        """The 3 binary endpoints should not appear as auto-generated tools."""
        tools = await compat_get_tools(offline_server)
        for name, tool in tools.items():
            if hasattr(tool, "_route"):
                assert tool._route.path not in EXCLUDED_PATHS, (
                    f"Tool '{name}' maps to excluded path {tool._route.path}"
                )

    @pytest.mark.asyncio
    async def test_manual_tools_registered(self, offline_server):
        """The 7 manual tools should be present."""
        tools = await compat_get_tools(offline_server)
        manual_names = {
            "createSession", "installApp", "waitForAppInstallation",
            "push_file_to_device", "take_screenshot",
            "pull_file_from_device", "proxy_http",
        }
        for name in manual_names:
            assert name in tools, f"Manual tool '{name}' not found in {sorted(tools.keys())}"

    @pytest.mark.asyncio
    async def test_expected_tool_names_present(self, offline_server):
        """Key tool names should be present.

        The six method-specific proxy tools (proxyGet/Post/Put/Delete/Head/
        Options) were collapsed into a single manual `proxy_http` tool, so
        we check for that instead.
        """
        tools = await compat_get_tools(offline_server)
        expected = {
            "listDevices", "listDeviceStatus", "createSession",
            "deleteSession", "listSessions", "executeShellCommand", "launchApp",
            "openUrl", "installApp", "proxy_http", "listAppiumVersions",
            "startAppiumServer", "listAppInstallations", "uninstallApp",
            "waitForAppInstallation",
            "listFiles", "removeFile", "statFile",
            "startNetworkCapture", "stopNetworkCapture",
            "setNetworkConditions", "resetNetworkConditions",
            "listNetworkProfiles", "setNetworkProfile",
        }
        missing = expected - set(tools.keys())
        assert not missing, f"Missing expected tools: {missing}"

    @pytest.mark.asyncio
    async def test_all_tools_have_descriptions(self, offline_server):
        """Every tool should have a non-empty description."""
        tools = await compat_get_tools(offline_server)
        for name, tool in tools.items():
            desc = tool.description if hasattr(tool, "description") else ""
            assert desc and len(desc) > 0, f"Tool '{name}' has no description"

    @pytest.mark.asyncio
    async def test_all_auto_tools_have_object_parameters(self, offline_server):
        """Auto-generated tools should have parameters with type=object."""
        tools = await compat_get_tools(offline_server)
        manual_names = {
            "push_file_to_device", "take_screenshot",
            "pull_file_from_device", "proxy_http",
        }
        for name, tool in tools.items():
            if name in manual_names:
                continue
            params = tool.parameters if hasattr(tool, "parameters") else {}
            if isinstance(params, dict) and params:
                assert params.get("type") == "object", (
                    f"Tool '{name}' parameters type is '{params.get('type')}', expected 'object'"
                )

    @pytest.mark.asyncio
    async def test_no_duplicate_tool_names(self, offline_server):
        """All tool keys should be unique (dict enforces this, but verify count)."""
        tools = await compat_get_tools(offline_server)
        names = list(tools.keys())
        assert len(names) == len(set(names)), "Duplicate tool names found"


# ===================================================================
# 3. Tool Schema Validation
# ===================================================================

class TestToolSchemaValidation:
    """Tests that tool schemas have no $refs and correct parameter shapes."""

    @pytest.mark.asyncio
    async def test_no_refs_in_any_tool_parameters(self, offline_server):
        """No $ref or $defs should remain in any tool's parameter schema."""
        tools = await compat_get_tools(offline_server)
        all_issues = []
        for name, tool in tools.items():
            params = tool.parameters if hasattr(tool, "parameters") else {}
            refs = _find_refs(params, name)
            all_issues.extend(refs)
        assert all_issues == [], (
            f"Found unresolved refs in tool schemas:\n" +
            "\n".join(f"  {r}" for r in all_issues)
        )

    @pytest.mark.asyncio
    async def test_session_tools_require_session_id(self, offline_server):
        """Tools that operate on sessions must have sessionId as required."""
        tools = await compat_get_tools(offline_server)
        session_tools = [
            "getSession", "deleteSession", "executeShellCommand",
            "launchApp", "openUrl", "installApp", "listAppInstallations",
        ]
        for tool_name in session_tools:
            if tool_name not in tools:
                continue
            params = tools[tool_name].parameters
            required = params.get("required", [])
            assert "sessionId" in required, (
                f"Tool '{tool_name}' should require sessionId, "
                f"but required={required}"
            )

    @pytest.mark.asyncio
    async def test_create_session_has_body_params(self, offline_server):
        """createSession should have os and optional deviceName params."""
        tools = await compat_get_tools(offline_server)
        params = tools["createSession"].parameters
        props = params.get("properties", {})
        assert "os" in props, (
            f"createSession params missing 'os'. Has: {list(props.keys())}"
        )

    @pytest.mark.asyncio
    async def test_list_device_status_has_query_params(self, offline_server):
        """listDeviceStatus should have state, privateOnly, deviceName."""
        tools = await compat_get_tools(offline_server)
        params = tools["listDeviceStatus"].parameters
        props = params.get("properties", {})
        assert "state" in props, f"Missing 'state'. Has: {list(props.keys())}"
        assert "deviceName" in props, f"Missing 'deviceName'. Has: {list(props.keys())}"

    @pytest.mark.asyncio
    async def test_proxy_http_has_all_path_params(self, offline_server):
        """proxy_http should require sessionId, method, and all target path params."""
        tools = await compat_get_tools(offline_server)
        assert "proxy_http" in tools, (
            f"proxy_http missing from tools: {sorted(tools.keys())}"
        )
        required = tools["proxy_http"].parameters.get("required", [])
        for param in ["sessionId", "method", "targetHost", "targetPort", "targetPath"]:
            assert param in required, (
                f"Tool 'proxy_http' should require '{param}', required={required}"
            )


# ===================================================================
# 4. Ref Resolution
# ===================================================================

class TestRefResolution:
    """Unit tests for the resolve_refs() function."""

    def test_simple_ref(self):
        schema = {
            "$defs": {"Foo": {"type": "string"}},
            "properties": {
                "bar": {"$ref": "#/$defs/Foo"}
            }
        }
        resolved = resolve_refs(schema)
        assert "$ref" not in resolved.get("properties", {}).get("bar", {})
        assert resolved["properties"]["bar"]["type"] == "string"
        assert "$defs" not in resolved

    def test_nested_refs(self):
        schema = {
            "$defs": {
                "Inner": {"type": "integer"},
                "Outer": {"properties": {"val": {"$ref": "#/$defs/Inner"}}},
            },
            "properties": {
                "item": {"$ref": "#/$defs/Outer"}
            }
        }
        resolved = resolve_refs(schema)
        val_schema = resolved["properties"]["item"]["properties"]["val"]
        assert val_schema["type"] == "integer"
        assert _find_refs(resolved) == []

    def test_ref_with_siblings_merged(self):
        schema = {
            "$defs": {"Base": {"type": "object", "properties": {"x": {"type": "int"}}}},
            "allOf": [{"$ref": "#/$defs/Base", "description": "extended"}]
        }
        resolved = resolve_refs(schema)
        entry = resolved["allOf"][0]
        assert "description" in entry
        assert "properties" in entry
        assert "$ref" not in entry

    def test_unresolvable_ref_dropped(self):
        schema = {
            "properties": {
                "val": {"$ref": "#/components/schemas/Unknown", "fallback": True}
            }
        }
        resolved = resolve_refs(schema)
        val = resolved["properties"]["val"]
        assert "$ref" not in val
        assert val.get("fallback") is True

    def test_defs_stripped_from_output(self):
        schema = {"$defs": {"A": {"type": "string"}}, "type": "object"}
        resolved = resolve_refs(schema)
        assert "$defs" not in resolved
        assert resolved["type"] == "object"

    def test_non_dict_passthrough(self):
        assert resolve_refs("not a dict") == "not a dict"
        assert resolve_refs(42) == 42
        assert resolve_refs(None) is None


# ===================================================================
# 5. Manual Tools
# ===================================================================

class TestManualTools:
    """Tests for the manually-registered tools."""

    @pytest.mark.asyncio
    async def test_manual_tool_parameters(self, offline_server):
        """Manual tools have the expected parameter names."""
        tools = await compat_get_tools(offline_server)

        push_params = tools["push_file_to_device"].parameters["properties"]
        assert "sessionId" in push_params
        assert "local_file_path" in push_params
        assert "device_path" in push_params

        screenshot_params = tools["take_screenshot"].parameters["properties"]
        assert "sessionId" in screenshot_params

        pull_params = tools["pull_file_from_device"].parameters["properties"]
        assert "sessionId" in pull_params
        assert "device_file_path" in pull_params
        assert "local_save_path" in pull_params

    @pytest.mark.asyncio
    async def test_manual_tools_not_openapi_tools(self, offline_server):
        """Manual tools should not be OpenAPITool instances."""
        from fastmcp.server.openapi.components import OpenAPITool
        tools = await compat_get_tools(offline_server)
        for name in ["push_file_to_device", "take_screenshot", "pull_file_from_device"]:
            assert not isinstance(tools[name], OpenAPITool), (
                f"'{name}' should be a regular Tool, not OpenAPITool"
            )

    @pytest.mark.asyncio
    async def test_push_file_nonexistent_returns_error(self, offline_server):
        """push_file_to_device with nonexistent file returns error dict."""
        result = await compat_call_tool(offline_server,
            "push_file_to_device",
            {"sessionId": "fake", "local_file_path": "/nonexistent/file.txt"}
        )
        data = _parse_tool_result(result)
        assert "error" in data
        assert "File not found" in data["error"]

    @pytest.mark.asyncio
    async def test_pull_file_has_optional_save_path(self, offline_server):
        """pull_file_from_device's local_save_path should not be required."""
        tools = await compat_get_tools(offline_server)
        required = tools["pull_file_from_device"].parameters.get("required", [])
        assert "local_save_path" not in required


# ===================================================================
# 6. Header Injection
# ===================================================================

class TestHeaderInjection:
    """Tests that custom headers, auth, and params are injected into requests."""

    @pytest.mark.asyncio
    async def test_mcp_headers_on_request(self, offline_server, captured_requests):
        """Requests should carry X-SAUCE-MCP-* headers."""
        captured_requests.clear()
        try:
            await compat_call_tool(offline_server,"listDeviceStatus", {})
        except Exception:
            pass  # Mock may not return valid data

        assert len(captured_requests) > 0, "No requests captured"
        req = captured_requests[-1]
        assert req.headers.get("X-SAUCE-MCP-SERVER") == "rdc_dynamic"
        assert req.headers.get("X-SAUCE-MCP-TRANSPORT") == "stdio"
        assert req.headers.get("X-SAUCE-MCP-USER") == "fake_user"

    @pytest.mark.asyncio
    async def test_basic_auth_present(self, offline_server, captured_requests):
        """Requests should include Basic Auth header."""
        captured_requests.clear()
        try:
            await compat_call_tool(offline_server,"listDeviceStatus", {})
        except Exception:
            pass

        assert len(captured_requests) > 0
        req = captured_requests[-1]
        auth_header = req.headers.get("authorization", "")
        assert auth_header.startswith("Basic "), f"Auth header: {auth_header}"
        decoded = base64.b64decode(auth_header.split(" ")[1]).decode()
        assert decoded == "fake_user:fake_key"

    def test_ai_query_param_configured_on_client(self, spec_from_url):
        """The httpx client should have ai=rdc_openapi_mcp in default params."""
        server = create_server(spec_from_url, "key", "user", "EU_CENTRAL")
        internal_tools = _get_internal_tools(server)
        tools_iter = internal_tools.values() if isinstance(internal_tools, dict) else internal_tools
        for tool in tools_iter:
            if hasattr(tool, "_client"):
                client_params = tool._client.params
                assert "ai" in client_params, f"Client params: {dict(client_params)}"
                assert client_params["ai"] == "rdc_openapi_mcp"
                break

    def test_base_url_matches_region(self, spec_from_url):
        """EU_CENTRAL server should use the eu-central-1 base URL."""
        server = create_server(spec_from_url, "key", "user", "EU_CENTRAL")
        internal_tools = _get_internal_tools(server)
        tools_iter = internal_tools.values() if isinstance(internal_tools, dict) else internal_tools
        for tool in tools_iter:
            if hasattr(tool, "_client"):
                base = str(tool._client.base_url)
                assert "eu-central-1" in base, f"Base URL: {base}"
                assert base.endswith("/rdc/v2/"), f"Base URL: {base}"
                break


# ===================================================================
# 7. Live Tool Invocation
# ===================================================================

@live
class TestLiveToolInvocation:
    """Live tests invoking auto-generated tools via call_tool()."""

    @pytest.mark.asyncio
    async def test_list_device_status(self, live_dynamic_server):
        """listDeviceStatus returns a JSON dict with devices."""
        result = await compat_call_tool(live_dynamic_server,
            "listDeviceStatus", {}
        )
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        devices = data.get("devices", data.get("result", []))
        assert isinstance(devices, list)
        assert len(devices) > 0, "Expected at least one device"

    @pytest.mark.asyncio
    async def test_list_devices(self, live_dynamic_server):
        """listDevices returns device catalog."""
        result = await compat_call_tool(live_dynamic_server,
            "listDevices", {}
        )
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        # FastMCP wraps non-object arrays in {"result": [...]}
        devices = data.get("result", data.get("devices", []))
        assert isinstance(devices, list)
        assert len(devices) > 0

    @pytest.mark.asyncio
    async def test_list_sessions(self, live_dynamic_server):
        """listSessions returns a sessions dict."""
        result = await compat_call_tool(live_dynamic_server,
            "listSessions", {}
        )
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "sessions" in data

    @pytest.mark.asyncio
    async def test_list_appium_versions(self, live_dynamic_server):
        """listAppiumVersions returns version info."""
        result = await compat_call_tool(live_dynamic_server,
            "listAppiumVersions", {}
        )
        data = _parse_tool_result(result)
        assert isinstance(data, dict)
        assert "versions" in data
        assert len(data["versions"]) > 0

    @pytest.mark.asyncio
    async def test_get_session_invalid_id_raises(self, live_dynamic_server):
        """getSession with invalid ID raises ToolError."""
        from fastmcp.exceptions import ToolError
        with pytest.raises(ToolError, match="404"):
            await compat_call_tool(live_dynamic_server,
                "getSession",
                {"sessionId": "00000000-0000-0000-0000-000000000000"}
            )

    @pytest.mark.asyncio
    async def test_tool_result_structure(self, live_dynamic_server):
        """ToolResult has .content list with TextContent objects."""
        result = await compat_call_tool(live_dynamic_server,
            "listDeviceStatus", {}
        )
        assert hasattr(result, "content")
        assert isinstance(result.content, list)
        assert len(result.content) > 0
        c0 = result.content[0]
        assert hasattr(c0, "text")
        # Should be valid JSON
        json.loads(c0.text)

    @pytest.mark.asyncio
    async def test_list_device_status_with_filter(self, live_dynamic_server):
        """listDeviceStatus with state=AVAILABLE filter works."""
        result = await compat_call_tool(live_dynamic_server,
            "listDeviceStatus", {"state": "AVAILABLE"}
        )
        data = _parse_tool_result(result)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_list_sessions_with_state_filter(self, live_dynamic_server):
        """listSessions with state filter works."""
        result = await compat_call_tool(live_dynamic_server,
            "listSessions", {"state": "CLOSED"}
        )
        data = _parse_tool_result(result)
        assert isinstance(data, dict)


# ===================================================================
# 8. Live Session Lifecycle
# ===================================================================

@live
@pytest.mark.slow
class TestLiveSessionLifecycle:
    """
    Full device session lifecycle via dynamically-generated tools.
    These allocate real devices and cost real minutes.
    """

    @pytest.mark.asyncio
    async def test_android_session_lifecycle(self, live_dynamic_server):
        """
        End-to-end: createSession -> poll getSession -> openUrl ->
        executeShellCommand -> deleteSession -> verify closed.
        """
        session_id = None
        try:
            # Step 1: Create session
            result = await compat_call_tool(live_dynamic_server,
                "createSession",
                {"device": {"os": "android"}}
            )
            data = _parse_tool_result(result)
            session_id = data.get("sessionId") or data.get("id")
            assert session_id is not None, f"No sessionId in response: {data}"

            # Step 2: Poll until ACTIVE
            for _ in range(24):  # 2 min max
                result = await compat_call_tool(live_dynamic_server,
                    "getSession", {"sessionId": session_id}
                )
                session_data = _parse_tool_result(result)
                state = session_data.get("state")
                if state == "ACTIVE":
                    break
                if state in ("ERRORED", "CLOSED"):
                    pytest.fail(f"Session entered {state}")
                await asyncio.sleep(5)
            else:
                pytest.fail("Session did not become ACTIVE within 2 minutes")

            # Step 3: Open a URL
            result = await compat_call_tool(live_dynamic_server,
                "openUrl",
                {"sessionId": session_id, "url": "https://www.saucedemo.com"}
            )
            # openUrl returns 204 No Content, which may be empty or success
            # Just verify it didn't raise

            # Step 4: Execute shell command (Android only)
            result = await compat_call_tool(live_dynamic_server,
                "executeShellCommand",
                {"sessionId": session_id, "adbShellCommand": "echo hello_from_mcp"}
            )
            shell_data = _parse_tool_result(result)
            assert isinstance(shell_data, dict)

        finally:
            # Step 5: Always close the session
            if session_id:
                try:
                    await compat_call_tool(live_dynamic_server,
                        "deleteSession", {"sessionId": session_id}
                    )
                except Exception:
                    pass  # Best-effort cleanup

                # Step 6: Verify session is closed
                await asyncio.sleep(2)
                try:
                    result = await compat_call_tool(live_dynamic_server,
                        "getSession", {"sessionId": session_id}
                    )
                    final_data = _parse_tool_result(result)
                    assert final_data.get("state") != "ACTIVE"
                except Exception:
                    pass  # Session may already be gone

    @pytest.mark.asyncio
    async def test_ios_session_lifecycle(self, live_dynamic_server):
        """
        End-to-end iOS: createSession -> poll -> openUrl -> deleteSession.
        """
        session_id = None
        try:
            result = await compat_call_tool(live_dynamic_server,
                "createSession",
                {"device": {"os": "ios"}}
            )
            data = _parse_tool_result(result)
            session_id = data.get("sessionId") or data.get("id")
            assert session_id is not None

            # Poll until ACTIVE
            for _ in range(24):
                result = await compat_call_tool(live_dynamic_server,
                    "getSession", {"sessionId": session_id}
                )
                session_data = _parse_tool_result(result)
                if session_data.get("state") == "ACTIVE":
                    break
                if session_data.get("state") in ("ERRORED", "CLOSED"):
                    pytest.fail(f"Session entered {session_data['state']}")
                await asyncio.sleep(5)
            else:
                pytest.fail("Session did not become ACTIVE")

            # Open URL
            await compat_call_tool(live_dynamic_server,
                "openUrl",
                {"sessionId": session_id, "url": "https://www.saucedemo.com"}
            )

        finally:
            if session_id:
                try:
                    await compat_call_tool(live_dynamic_server,
                        "deleteSession", {"sessionId": session_id}
                    )
                except Exception:
                    pass


# ===================================================================
# 9. Error Handling
# ===================================================================

class TestErrorHandling:
    """Tests for error conditions."""

    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self, offline_server):
        """Calling a non-existent tool should raise NotFoundError."""
        from fastmcp.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            await compat_call_tool(offline_server,
                "nonExistentToolName", {}
            )

    def test_invalid_region_raises(self, spec_from_url):
        """Invalid region should raise KeyError."""
        with pytest.raises(KeyError):
            create_server(spec_from_url, "key", "user", "INVALID_REGION")

    @pytest.mark.asyncio
    async def test_empty_spec_only_manual_tools(self):
        """Server with empty spec should only have the 7 manual tools."""
        minimal_spec = {
            "openapi": "3.0.0",
            "info": {"title": "empty", "version": "0.0.1"},
            "paths": {},
        }
        server = create_server(minimal_spec, "key", "user", "US_WEST")
        tools = await compat_get_tools(server)
        manual_names = {
            "createSession", "installApp", "waitForAppInstallation",
            "push_file_to_device", "pull_file_from_device",
            "take_screenshot", "proxy_http",
        }
        assert len(tools) == len(manual_names), (
            f"Expected {len(manual_names)} manual tools, got {len(tools)}: {sorted(tools.keys())}"
        )
        for name in manual_names:
            assert name in tools, f"Manual tool '{name}' missing from {sorted(tools.keys())}"

    @pytest.mark.asyncio
    async def test_route_map_fn_excludes_correctly(self):
        """route_map_fn should return EXCLUDE for binary paths, None otherwise."""
        from fastmcp.server.openapi import MCPType
        from fastmcp.utilities.openapi import HTTPRoute

        for excluded_path in EXCLUDED_PATHS:
            mock_route = HTTPRoute(path=excluded_path, method="POST")
            result = route_map_fn(mock_route, MCPType.TOOL)
            assert result == MCPType.EXCLUDE, (
                f"Path {excluded_path} should be EXCLUDE, got {result}"
            )

        normal_route = HTTPRoute(path="/devices/status", method="GET")
        result = route_map_fn(normal_route, MCPType.TOOL)
        assert result is None, "Normal routes should return None"

    def test_data_centers_dict(self):
        """DATA_CENTERS should have all 3 regions with /rdc/v2/ suffix."""
        assert "US_WEST" in DATA_CENTERS
        assert "US_EAST" in DATA_CENTERS
        assert "EU_CENTRAL" in DATA_CENTERS
        for region, url in DATA_CENTERS.items():
            assert url.endswith("/rdc/v2/"), f"{region} URL doesn't end with /rdc/v2/: {url}"
            assert url.startswith("https://"), f"{region} URL not HTTPS: {url}"


# ===================================================================
# 10. Regression tests for previously flagged production issues
# ===================================================================

class TestProductionCodeIssues:
    """Regression tests for bugs originally flagged during the PR #26 review."""

    def test_resolve_refs_breaks_circular_ref(self):
        """resolve_refs() must not recurse infinitely on circular $refs.

        Originally flagged in PR #26 — a schema where A → B → A used to
        raise RecursionError. resolve_refs now drops the cycle and returns
        a finite schema.
        """
        schema = {
            "$defs": {
                "A": {"type": "object", "properties": {"b": {"$ref": "#/$defs/B"}}},
                "B": {"type": "object", "properties": {"a": {"$ref": "#/$defs/A"}}},
            },
            "properties": {"x": {"$ref": "#/$defs/A"}},
        }
        result = resolve_refs(schema)

        assert "$defs" not in result
        # Serializing proves the output is finite (no recursive structure).
        assert isinstance(json.dumps(result), str)

    def test_resolve_refs_self_reference(self):
        """A $def that references itself is handled without recursion."""
        schema = {
            "$defs": {"Node": {"type": "object",
                               "properties": {"child": {"$ref": "#/$defs/Node"}}}},
            "properties": {"root": {"$ref": "#/$defs/Node"}},
        }
        result = resolve_refs(schema)

        assert "$defs" not in result
        assert json.dumps(result)  # finite

    def test_resolve_refs_sibling_refs_still_resolve(self):
        """Two siblings referencing the same $def are both resolved (not
        incorrectly treated as a cycle)."""
        schema = {
            "$defs": {"X": {"type": "string", "format": "uuid"}},
            "properties": {
                "a": {"$ref": "#/$defs/X"},
                "b": {"$ref": "#/$defs/X"},
            },
        }
        result = resolve_refs(schema)

        assert result["properties"]["a"] == {"type": "string", "format": "uuid"}
        assert result["properties"]["b"] == {"type": "string", "format": "uuid"}

    def test_validate_path_rejects_traversal(self):
        """Path traversal attempts are coerced inside SAFE_FILE_DIR via basename strip."""
        from sauce_api_mcp.shared.file_utils import validate_path, SAFE_FILE_DIR
        resolved = validate_path("../../etc/passwd")
        assert resolved.startswith(os.path.realpath(SAFE_FILE_DIR))
        assert resolved.endswith("passwd")
        assert "/etc/passwd" not in resolved

    def test_validate_path_accepts_plain_filename(self):
        """Plain filenames resolve to SAFE_FILE_DIR/<name>."""
        from sauce_api_mcp.shared.file_utils import validate_path, SAFE_FILE_DIR
        resolved = validate_path("app.apk")
        assert resolved == os.path.realpath(os.path.join(SAFE_FILE_DIR, "app.apk"))

    @pytest.mark.asyncio
    async def test_launch_app_schema_mismatch(self, offline_server):
        """
        ISSUE: The launchApp tool's required field includes 'id' but the
        OpenAPI spec defines bundleId (iOS) and packageName (Android).

        This means calling launchApp with just bundleId or packageName
        would fail validation because 'id' is required.
        """
        tools = await compat_get_tools(offline_server)
        if "launchApp" not in tools:
            pytest.skip("launchApp not in tools")

        params = tools["launchApp"].parameters
        required = params.get("required", [])
        props = list(params.get("properties", {}).keys())

        # Flag if 'id' is required but doesn't exist as a property
        if "id" in required and "id" not in props:
            pytest.xfail(
                "ISSUE: launchApp requires 'id' but it's not a property. "
                f"Required={required}, Properties={props}. "
                "The OpenAPI spec uses bundleId/packageName, not 'id'."
            )

    @pytest.mark.asyncio
    async def test_excluded_paths_match_spec_binary_endpoints(self, spec_from_url):
        """
        Verify EXCLUDED_PATHS covers all binary endpoints in the spec.
        If the spec adds new binary endpoints, this test will catch the drift.
        """
        # Known binary endpoints from the spec (multipart/form-data or
        # binary response bodies)
        spec_binary_paths = set()
        for path, methods in spec_from_url.get("paths", {}).items():
            for method, details in methods.items():
                if method not in ("get", "post", "put", "delete", "patch"):
                    continue
                # Check request body for multipart/form-data
                req_body = details.get("requestBody", {})
                content = req_body.get("content", {})
                if "multipart/form-data" in content:
                    spec_binary_paths.add(path)
                # Check response for binary content types
                for status, resp in details.get("responses", {}).items():
                    resp_content = resp.get("content", {})
                    if any(ct.startswith("image/") or ct == "application/octet-stream"
                           for ct in resp_content):
                        spec_binary_paths.add(path)

        # Check that EXCLUDED_PATHS covers all spec binary endpoints
        uncovered = spec_binary_paths - EXCLUDED_PATHS
        if uncovered:
            # PRODUCTION CODE ISSUE: New binary endpoints in spec not excluded
            pytest.xfail(
                f"ISSUE: Binary endpoints in spec not in EXCLUDED_PATHS: {uncovered}"
            )
