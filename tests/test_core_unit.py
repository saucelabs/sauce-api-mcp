"""
Unit tests for SauceLabsAgent (main.py) — core MCP server.

All HTTP calls are intercepted via httpx.MockTransport so no real API
calls are made. Tests verify request construction, response parsing,
error handling, and HAR filtering logic.
"""

import pytest
import httpx

from sauce_api_mcp.main import SauceLabsAgent
from sauce_api_mcp.models import AccountInfo, LookupTeamsResponse, LookupUsers


# ===================================================================
# Initialization
# ===================================================================

class TestAgentInitialization:
    """Tests for SauceLabsAgent construction and configuration."""

    def test_default_region_us_west(self, mock_mcp_server):
        agent = SauceLabsAgent(mock_mcp_server, "key", "user", "US_WEST")
        assert "us-west-1" in str(agent.client.base_url)

    def test_region_us_east(self, mock_mcp_server):
        agent = SauceLabsAgent(mock_mcp_server, "key", "user", "US_EAST")
        assert "us-east-4" in str(agent.client.base_url)

    def test_region_eu_central(self, mock_mcp_server):
        agent = SauceLabsAgent(mock_mcp_server, "key", "user", "EU_CENTRAL")
        assert "eu-central-1" in str(agent.client.base_url)

    def test_invalid_region_raises(self, mock_mcp_server):
        with pytest.raises(KeyError):
            SauceLabsAgent(mock_mcp_server, "key", "user", "INVALID")

    def test_username_stored(self, mock_mcp_server):
        agent = SauceLabsAgent(mock_mcp_server, "key", "myuser", "US_WEST")
        assert agent.username == "myuser"

    def test_har_cache_initialized(self, mock_mcp_server):
        agent = SauceLabsAgent(mock_mcp_server, "key", "user", "US_WEST")
        assert agent._har_cache == {}


# ===================================================================
# sauce_api_call internals
# ===================================================================

class TestSauceApiCall:
    """Tests for the internal sauce_api_call method."""

    @pytest.mark.asyncio
    async def test_ai_param_injected(self, core_agent_with_mock):
        agent, requests = core_agent_with_mock()
        await agent.sauce_api_call("test/endpoint")
        assert len(requests) == 1
        assert "ai=mcp" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_get_method_default(self, core_agent_with_mock):
        agent, requests = core_agent_with_mock()
        await agent.sauce_api_call("test/endpoint")
        assert requests[0].method == "GET"

    @pytest.mark.asyncio
    async def test_post_method(self, core_agent_with_mock):
        agent, requests = core_agent_with_mock()
        await agent.sauce_api_call("test/endpoint", method="POST", json_body={"key": "val"})
        assert requests[0].method == "POST"

    @pytest.mark.asyncio
    async def test_params_forwarded(self, core_agent_with_mock):
        agent, requests = core_agent_with_mock()
        await agent.sauce_api_call("test/endpoint", params={"limit": 10})
        url_str = str(requests[0].url)
        assert "limit=10" in url_str
        assert "ai=mcp" in url_str

    @pytest.mark.asyncio
    async def test_404_returns_response(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.sauce_api_call("missing/endpoint")
        # 404 is returned as an httpx.Response, not a dict
        assert isinstance(result, httpx.Response)
        assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_500_returns_response(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(500, json={"error": "server error"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.sauce_api_call("broken/endpoint")
        assert isinstance(result, httpx.Response)
        assert result.status_code == 500

    @pytest.mark.asyncio
    async def test_401_returns_error_dict(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(401, json={"error": "unauthorized"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.sauce_api_call("auth/endpoint")
        assert isinstance(result, dict)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_429_returns_error_dict(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(429, json={"error": "rate limited"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.sauce_api_call("rate/limited")
        assert isinstance(result, dict)
        assert "error" in result


# ===================================================================
# Account endpoints
# ===================================================================

class TestAccountEndpoints:
    """Tests for account-related tools."""

    @pytest.mark.asyncio
    async def test_get_account_info_success(self, core_agent_with_mock):
        account_data = {
            "links": {"next": None, "previous": None, "first": None, "last": None},
            "count": 1,
            "results": [{
                "id": "abc123",
                "email": "test@example.com",
                "username": "test_user",
                "first_name": "Test",
                "last_name": "User",
                "is_active": True,
                "organization": {"id": "org1", "name": "TestOrg"},
                "roles": [{"name": "admin", "role": 1}],
                "teams": [{
                    "id": "team1",
                    "settings": {"live_only": False, "real_devices": 5, "virtual_machines": 10},
                    "group": {"id": "grp1", "name": "Group1"},
                    "is_default": True,
                    "name": "DefaultTeam",
                    "org_uuid": "org1"
                }]
            }]
        }

        async def handler(req):
            return httpx.Response(200, json=account_data)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.get_account_info()
        assert isinstance(result, AccountInfo)
        assert result.count == 1
        assert result.results[0].username == "test_user"
        # Verify correct endpoint called
        assert "team-management/v1/users" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_lookup_teams_with_name_filter(self, core_agent_with_mock):
        teams_data = {
            "links": {"next": None, "previous": None, "first": None, "last": None},
            "count": 1,
            "results": [{
                "id": "team1",
                "settings": {"live_only": False, "real_devices": 5, "virtual_machines": 10},
                "group": {"id": "grp1", "name": "Group1"},
                "is_default": True,
                "name": "SauceTeam",
                "org_uuid": "org1"
            }]
        }

        async def handler(req):
            return httpx.Response(200, json=teams_data)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.lookup_teams(name="Sauce")
        assert isinstance(result, LookupTeamsResponse)
        assert result.count == 1
        assert "name=Sauce" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_get_team_404(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_team("nonexistent_id")
        assert "error" in result
        assert "Team not found" in result["error"]
        assert "suggestions" in result

    @pytest.mark.asyncio
    async def test_get_user_404(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_user("nonexistent_id")
        assert "error" in result
        assert "User not found" in result["error"]

    @pytest.mark.asyncio
    async def test_lookup_users_with_filters(self, core_agent_with_mock):
        users_data = {
            "links": {"next": None, "previous": None, "first": None, "last": None},
            "count": 0,
            "results": []
        }

        async def handler(req):
            return httpx.Response(200, json=users_data)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.lookup_users(
            username="test", roles="1", status="active", limit=5
        )
        assert isinstance(result, LookupUsers)
        url_str = str(requests[0].url)
        assert "username=test" in url_str
        assert "roles=1" in url_str
        assert "status=active" in url_str
        assert "limit=5" in url_str

    @pytest.mark.asyncio
    async def test_get_my_active_team(self, core_agent_with_mock):
        team_data = {"id": "team1", "name": "MyTeam"}

        async def handler(req):
            return httpx.Response(200, json=team_data)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.get_my_active_team()
        assert result["id"] == "team1"
        assert "me/active-team" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_get_service_account_404(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_service_account("fake_id")
        assert "error" in result
        assert "Service account not found" in result["error"]


# ===================================================================
# Jobs endpoints
# ===================================================================

class TestJobEndpoints:
    """Tests for job-related tools."""

    @pytest.mark.asyncio
    async def test_get_recent_jobs_default_limit(self, core_agent_with_mock):
        jobs = [{"id": f"job{i}"} for i in range(5)]

        async def handler(req):
            return httpx.Response(200, json=jobs)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.get_recent_jobs()
        assert result["total"] == 5
        assert result["per_page"] == 5
        assert "limit=5" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_get_recent_jobs_custom_limit(self, core_agent_with_mock):
        jobs = [{"id": f"job{i}"} for i in range(20)]

        async def handler(req):
            return httpx.Response(200, json=jobs)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.get_recent_jobs(limit=20)
        assert result["total"] == 20
        assert "limit=20" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_get_job_details_success(self, core_agent_with_mock):
        job_data = {
            "id": "abc123",
            "status": "passed",
            "browser": "chrome",
            "os": "Windows 11"
        }

        async def handler(req):
            return httpx.Response(200, json=job_data)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.get_job_details("abc123")
        assert result["id"] == "abc123"
        assert result["status"] == "passed"
        assert "jobs/abc123" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_get_job_details_404(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_job_details("nonexistent")
        assert "error" in result
        assert "Job not found" in result["error"]
        assert "suggestions" in result

    @pytest.mark.asyncio
    async def test_get_test_assets_success(self, core_agent_with_mock):
        assets = {
            "sauce-log": "sauce-log.json",
            "video": "video.mp4",
            "selenium-server.log": "selenium-server.log"
        }

        async def handler(req):
            return httpx.Response(200, json=assets)

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_test_assets("job123")
        assert "sauce-log" in result
        assert result["sauce-log"] == "sauce-log.json"

    @pytest.mark.asyncio
    async def test_get_test_assets_404_rdc_hint(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_test_assets("rdc_job_id")
        assert "error" in result
        assert any("Real Device" in r for r in result.get("possible_reasons", []))

    @pytest.mark.asyncio
    async def test_get_test_assets_401(self, core_agent_with_mock):
        """401 is caught by sauce_api_call and returned as an error dict."""
        async def handler(req):
            return httpx.Response(401, json={"error": "unauthorized"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_test_assets("job123")
        assert isinstance(result, dict)
        assert "error" in result


# ===================================================================
# Build endpoints
# ===================================================================

class TestBuildEndpoints:
    """Tests for build-related tools."""

    @pytest.mark.asyncio
    async def test_lookup_builds_vdc(self, core_agent_with_mock):
        builds_data = {"builds": [{"id": "build1", "name": "test-build"}]}

        async def handler(req):
            return httpx.Response(200, json=builds_data)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.lookup_builds("vdc", limit=10)
        assert "builds" in result
        assert "v2/builds/vdc" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_lookup_builds_rdc(self, core_agent_with_mock):
        builds_data = {"builds": []}

        async def handler(req):
            return httpx.Response(200, json=builds_data)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.lookup_builds("rdc")
        assert "v2/builds/rdc" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_get_build_404(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_build("vdc", "nonexistent_build")
        assert "error" in result
        assert "Build not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_build_for_job_404(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_build_for_job("vdc", "nonexistent_job")
        assert "error" in result
        assert "Build not found for job" in result["error"]

    @pytest.mark.asyncio
    async def test_lookup_jobs_in_build_empty(self, core_agent_with_mock):
        jobs_data = {"jobs": []}

        async def handler(req):
            return httpx.Response(200, json=jobs_data)

        agent, _ = core_agent_with_mock(handler)
        result = await agent.lookup_jobs_in_build("vdc", "build123")
        assert result["jobs"] == []
        assert "data_retention_info" in result

    @pytest.mark.asyncio
    async def test_lookup_jobs_in_build_with_filters(self, core_agent_with_mock):
        jobs_data = {"jobs": [{"id": "j1", "passed": True}]}

        async def handler(req):
            return httpx.Response(200, json=jobs_data)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.lookup_jobs_in_build(
            "vdc", "build1", passed=True, running=False
        )
        url_str = str(requests[0].url)
        assert "passed=true" in url_str.lower() or "passed=True" in url_str


# ===================================================================
# Tunnel endpoints
# ===================================================================

class TestTunnelEndpoints:
    """Tests for Sauce Connect tunnel tools."""

    @pytest.mark.asyncio
    async def test_get_tunnels_for_user(self, core_agent_with_mock):
        tunnels = ["tunnel1", "tunnel2"]

        async def handler(req):
            return httpx.Response(200, json=tunnels)

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_tunnels_for_user("test_user")
        assert result["count"] == 2
        assert result["username"] == "test_user"

    @pytest.mark.asyncio
    async def test_get_tunnel_info_404(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(404, json={"error": "not found"})

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_tunnel_information("test_user", "bad_tunnel")
        assert "error" in result
        assert "Tunnel not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_tunnel_version_downloads(self, core_agent_with_mock):
        download_data = {"linux": "url1", "mac": "url2", "windows": "url3"}

        async def handler(req):
            return httpx.Response(200, json=download_data)

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_tunnel_version_downloads("5.2.3")
        assert "linux" in result


# ===================================================================
# Device endpoints
# ===================================================================

class TestDeviceEndpoints:
    """Tests for real device tools."""

    @pytest.mark.asyncio
    async def test_get_devices_status(self, core_agent_with_mock):
        devices = [
            {"descriptor": "iPhone_14", "state": "AVAILABLE"},
            {"descriptor": "Samsung_Galaxy_S23", "state": "IN_USE"}
        ]

        async def handler(req):
            return httpx.Response(200, json=devices)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.get_devices_status()
        assert len(result) == 2
        assert "v1/rdc/devices/status" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_get_specific_device(self, core_agent_with_mock):
        device = {
            "id": "device1",
            "name": "iPhone 14",
            "os": "iOS",
            "osVersion": "16.0"
        }

        async def handler(req):
            return httpx.Response(200, json=device)

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_specific_device("device1")
        assert result["name"] == "iPhone 14"

    @pytest.mark.asyncio
    async def test_get_real_device_jobs(self, core_agent_with_mock):
        jobs_data = {"entities": [{"id": "rdcjob1"}], "totalItemCount": 1}

        async def handler(req):
            return httpx.Response(200, json=jobs_data)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.get_real_device_jobs(limit=10)
        assert "entities" in result
        assert "limit=10" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_get_specific_rdc_job_asset_success(self, core_agent_with_mock):
        async def handler(req):
            return httpx.Response(
                200,
                content=b"fake binary content",
                headers={"content-type": "application/octet-stream"}
            )

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_specific_real_device_job_asset("job1", "deviceLogs")
        assert result["encoding"] == "base64"
        assert result["size"] > 0

    @pytest.mark.asyncio
    async def test_get_private_devices(self, core_agent_with_mock):
        devices = [{"id": "priv1", "name": "Private iPhone"}]

        async def handler(req):
            return httpx.Response(200, json=devices)

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_private_devices()
        assert "devices" in result
        assert len(result["devices"]) == 1


# ===================================================================
# Storage endpoints
# ===================================================================

class TestStorageEndpoints:
    """Tests for storage tools."""

    @pytest.mark.asyncio
    async def test_get_storage_files(self, core_agent_with_mock):
        files_data = {"items": [{"id": "file1", "name": "app.apk"}]}

        async def handler(req):
            return httpx.Response(200, json=files_data)

        agent, requests = core_agent_with_mock(handler)
        result = await agent.get_storage_files()
        assert "items" in result
        assert "v1/storage/files" in str(requests[0].url)

    @pytest.mark.asyncio
    async def test_get_storage_groups(self, core_agent_with_mock):
        groups_data = {"items": [{"id": "grp1", "name": "MyApp"}]}

        async def handler(req):
            return httpx.Response(200, json=groups_data)

        agent, _ = core_agent_with_mock(handler)
        result = await agent.get_storage_groups()
        assert "items" in result

    @pytest.mark.asyncio
    async def test_upload_file_missing_path(self, core_agent_with_mock):
        agent, _ = core_agent_with_mock()
        with pytest.raises(ValueError, match="File not found"):
            await agent.upload_file_to_storage(
                "/nonexistent/path/app.apk",
                "app.apk",
                "test app",
                ["tag1"],
                "project1"
            )


# ===================================================================
# HAR filtering logic
# ===================================================================

class TestHarFiltering:
    """Tests for the HAR filtering helper methods."""

    def _make_agent(self, mock_mcp_server):
        return SauceLabsAgent(mock_mcp_server, "key", "user", "US_WEST")

    def _make_entry(self, url="https://example.com/page", resource_type="Document",
                    status=200, time=500):
        return {
            "request": {"url": url},
            "_resourceType": resource_type,
            "response": {
                "status": status,
                "headers": [
                    {"name": "content-type", "value": "text/html"}
                ]
            },
            "time": time
        }

    def test_analytics_category(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(url="https://www.google-analytics.com/collect")
        assert agent._should_include_entry(entry, "analytics", None, None, None)

    def test_analytics_category_no_match(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(url="https://example.com/api/data")
        assert not agent._should_include_entry(entry, "analytics", None, None, None)

    def test_social_category(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(url="https://facebook.com/share")
        assert agent._should_include_entry(entry, "social", None, None, None)

    def test_api_category_xhr(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(
            url="https://example.com/api/users",
            resource_type="XHR"
        )
        assert agent._should_include_entry(entry, "api", None, None, None)

    def test_fonts_category(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(
            url="https://cdn.example.com/fonts/roboto.woff2",
            resource_type="Font"
        )
        assert agent._should_include_entry(entry, "fonts", None, None, None)

    def test_images_category(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(
            url="https://example.com/hero.jpg",
            resource_type="Image"
        )
        assert agent._should_include_entry(entry, "images", None, None, None)

    def test_scripts_category(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(
            url="https://example.com/app.js",
            resource_type="Script"
        )
        assert agent._should_include_entry(entry, "scripts", None, None, None)

    def test_errors_category(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(status=500)
        assert agent._should_include_entry(entry, "errors", None, None, None)

    def test_errors_category_excludes_200(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(status=200)
        assert not agent._should_include_entry(entry, "errors", None, None, None)

    def test_slow_category(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(time=2500)
        assert agent._should_include_entry(entry, "slow", None, None, None)

    def test_slow_category_excludes_fast(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(time=200)
        assert not agent._should_include_entry(entry, "slow", None, None, None)

    def test_custom_domains_filter(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(url="https://api.mycompany.com/v1/users")
        assert agent._should_include_entry(entry, None, ["mycompany.com"], None, None)

    def test_custom_domains_filter_no_match(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(url="https://api.other.com/v1/users")
        assert not agent._should_include_entry(entry, None, ["mycompany.com"], None, None)

    def test_resource_types_filter(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(resource_type="XHR")
        assert agent._should_include_entry(entry, None, None, ["XHR", "Fetch"], None)

    def test_resource_types_filter_no_match(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(resource_type="Image")
        assert not agent._should_include_entry(entry, None, None, ["XHR"], None)

    def test_status_codes_filter(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(status=404)
        assert agent._should_include_entry(entry, None, None, None, [404, 500])

    def test_status_codes_filter_no_match(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(status=200)
        assert not agent._should_include_entry(entry, None, None, None, [404, 500])

    def test_combined_filters(self, mock_mcp_server):
        """Multiple filters must all match."""
        agent = self._make_agent(mock_mcp_server)
        entry = self._make_entry(
            url="https://api.mycompany.com/data",
            resource_type="XHR",
            status=200
        )
        # All match
        assert agent._should_include_entry(
            entry, None, ["mycompany.com"], ["XHR"], [200]
        )
        # Status doesn't match
        assert not agent._should_include_entry(
            entry, None, ["mycompany.com"], ["XHR"], [404]
        )

    @pytest.mark.asyncio
    async def test_filter_har_data_caching(self, core_agent_with_mock):
        """Second call to filter_har_data should use cached data."""
        har_data = {
            "log": {
                "entries": [
                    {
                        "request": {"url": "https://google-analytics.com/collect"},
                        "_resourceType": "XHR",
                        "response": {"status": 200, "headers": []},
                        "time": 100
                    },
                    {
                        "request": {"url": "https://example.com/api"},
                        "_resourceType": "XHR",
                        "response": {"status": 200, "headers": [
                            {"name": "content-type", "value": "application/json"}
                        ]},
                        "time": 50
                    }
                ]
            }
        }

        call_count = 0

        async def handler(req):
            nonlocal call_count
            call_count += 1
            url_str = str(req.url)
            # get_test_assets call: rest/v1/jobs/{job_id}/assets (no trailing path)
            if "/assets" in url_str and "/assets/" not in url_str:
                return httpx.Response(200, json={"network.har": "network.har"})
            # Download HAR call: rest/v1/{username}/jobs/{job_id}/assets/network.har
            if "network.har" in url_str:
                return httpx.Response(200, json=har_data)
            return httpx.Response(200, json={})

        agent, _ = core_agent_with_mock(handler)

        # First call - should download (2 HTTP calls: get_test_assets + download HAR)
        result1 = await agent.filter_har_data("job1", filter_category="analytics")
        assert "job1" in agent._har_cache
        assert result1["_filter_metadata"]["filtered_request_count"] == 1

        # Second call - should use cache (no new HTTP calls)
        prev_call_count = call_count
        result2 = await agent.filter_har_data("job1", filter_category="api")
        assert call_count == prev_call_count  # No new HTTP calls

    def test_extract_main_domain(self, mock_mcp_server):
        agent = self._make_agent(mock_mcp_server)
        assert agent._extract_main_domain("https://www.example.com/path") == "example.com"
        assert agent._extract_main_domain("https://api.sub.example.com/") == "example.com"
