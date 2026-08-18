"""
Unit tests for MADAgent (mad.py) — Mobile App Distribution MCP server.

All HTTP calls are intercepted via httpx.MockTransport so no real API
calls are made. Tests verify request construction, auth header, response
parsing, and error passthrough.
"""

import json

import pytest
import httpx

from sauce_api_mcp.mad import MADAgent

BASE_URL = "https://acme.testfairy.com"
API_KEY = "test-api-key"


@pytest.fixture
def mad_agent_with_mock(mock_mcp_server):
    """MADAgent whose httpx client records requests and returns a canned response."""

    def _make(response_json=None, status_code=200):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(status_code, json=response_json if response_json is not None else {"ok": True})

        agent = MADAgent(mock_mcp_server, BASE_URL, API_KEY)
        agent.client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"X-API-Key": API_KEY},
            transport=httpx.MockTransport(handler),
        )
        return agent, requests

    return _make


class TestAgentInitialization:
    def test_base_url_trailing_slash_stripped(self, mock_mcp_server):
        agent = MADAgent(mock_mcp_server, BASE_URL + "/", API_KEY)
        assert str(agent.client.base_url).rstrip("/") == BASE_URL

    def test_api_key_header_set(self, mock_mcp_server):
        agent = MADAgent(mock_mcp_server, BASE_URL, API_KEY)
        assert agent.client.headers["X-API-Key"] == API_KEY


class TestMadApiCall:
    @pytest.mark.asyncio
    async def test_get_returns_parsed_json(self, mad_agent_with_mock):
        agent, requests = mad_agent_with_mock({"projects": []})
        result = await agent.mad_api_call("/api/v3/projects")
        assert result == {"projects": []}
        assert requests[0].method == "GET"

    @pytest.mark.asyncio
    async def test_error_body_passed_through_with_status(self, mad_agent_with_mock):
        agent, requests = mad_agent_with_mock({"error": "Project not found."}, status_code=404)
        result = await agent.mad_api_call("/api/v3/projects/999")
        assert result["error"] == "Project not found."
        assert result["status_code"] == 404

    @pytest.mark.asyncio
    async def test_missing_local_file_reported(self, mad_agent_with_mock):
        agent, requests = mad_agent_with_mock()
        result = await agent.mad_api_call(
            "/api/v3/builds/upload", method="POST", files={"file": "/no/such/file.apk"}
        )
        assert "Local file not found" in result["error"]
        assert requests == []


class TestTools:
    @pytest.mark.asyncio
    async def test_list_builds_url_and_pagination(self, mad_agent_with_mock):
        agent, requests = mad_agent_with_mock({"builds": [], "pagination": {}})
        await agent.list_builds(project_id=7, page=2, per_page=50)
        url = str(requests[0].url)
        assert "/api/v3/projects/7/builds" in url
        assert "page=2" in url
        assert "per_page=50" in url

    @pytest.mark.asyncio
    async def test_update_build_sends_json_body(self, mad_agent_with_mock):
        agent, requests = mad_agent_with_mock({"build": {}})
        await agent.update_build(3, release_notes="Fixed login", tags=["beta"])
        assert requests[0].method == "PUT"
        body = json.loads(requests[0].content)
        assert body == {"release_notes": "Fixed login", "tags": ["beta"]}

    @pytest.mark.asyncio
    async def test_update_build_requires_a_field(self, mad_agent_with_mock):
        agent, requests = mad_agent_with_mock()
        result = await agent.update_build(3)
        assert "error" in result
        assert requests == []

    @pytest.mark.asyncio
    async def test_upload_build_multipart(self, mad_agent_with_mock, tmp_path):
        apk = tmp_path / "app.apk"
        apk.write_bytes(b"fake-apk")
        agent, requests = mad_agent_with_mock({"status": "ok", "build": {"id": 1}}, status_code=201)
        result = await agent.upload_build(str(apk), project_id=7, release_notes="rc1")
        assert result["status"] == "ok"
        req = requests[0]
        assert req.method == "POST"
        assert "/api/v3/builds/upload" in str(req.url)
        assert b"fake-apk" in req.content
        assert b'name="project_id"' in req.content
        assert b'name="release_notes"' in req.content

    @pytest.mark.asyncio
    async def test_notify_testers_posts(self, mad_agent_with_mock):
        agent, requests = mad_agent_with_mock({"status": "queued"}, status_code=202)
        result = await agent.notify_build_testers(11)
        assert result == {"status": "queued"}
        assert requests[0].method == "POST"
        assert "/api/v3/builds/11/notify-testers" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_list_testers_search_param(self, mad_agent_with_mock):
        agent, requests = mad_agent_with_mock({"testers": [], "pagination": {}})
        await agent.list_testers(search="alice")
        assert "search=alice" in str(requests[0].url)


class TestToolRegistration:
    @pytest.mark.asyncio
    async def test_all_mad_tools_registered(self):
        from mcp.server import FastMCP
        from conftest import compat_get_tools

        server = FastMCP("MADAgentTest")
        MADAgent(server, BASE_URL, API_KEY)
        tools = await compat_get_tools(server)
        expected = {
            "list_projects", "get_project",
            "list_builds", "get_build", "upload_build", "update_build",
            "get_build_download_url", "notify_build_testers",
            "list_testers", "list_groups", "list_group_testers",
        }
        assert expected.issubset(set(tools))
