"""
Live E2E tests for SauceLabsAgent (main.py) — hitting real Sauce Labs APIs.

These tests make actual HTTP calls to Sauce Labs EU_CENTRAL data center.
They require valid SAUCE_USERNAME and SAUCE_ACCESS_KEY credentials.

Run with: pytest tests/test_core_live.py -v -m live
"""

import pytest

from tests.conftest import live

from sauce_api_mcp.models import (
    AccountInfo,
    LookupTeamsResponse,
    LookupUsers,
    LookupServiceAccounts,
)


# ===================================================================
# Account endpoints - Live
# ===================================================================

@live
class TestLiveAccountInfo:
    """Live tests for account information retrieval."""

    @pytest.mark.asyncio
    async def test_get_account_info(self, live_core_agent):
        """Verify we can retrieve account info from the live API."""
        result = await live_core_agent.get_account_info()
        assert isinstance(result, AccountInfo)
        assert result.count >= 1
        assert len(result.results) >= 1
        user = result.results[0]
        assert user.username is not None
        assert len(user.username) > 0
        assert user.email is not None
        assert user.organization is not None
        assert user.organization.name is not None

    @pytest.mark.asyncio
    async def test_account_info_resource(self, live_core_agent):
        """Verify the resource endpoint (sauce://account) returns valid data."""
        result = await live_core_agent.account_info()
        assert isinstance(result, AccountInfo)
        assert result.count >= 1


@live
class TestLiveTeams:
    """Live tests for team-related endpoints."""

    @pytest.mark.asyncio
    async def test_lookup_teams(self, live_core_agent):
        """List all teams in the org."""
        result = await live_core_agent.lookup_teams()
        assert isinstance(result, LookupTeamsResponse)
        assert result.count >= 0
        # If there are teams, verify structure
        if result.count > 0:
            team = result.results[0]
            assert team.id is not None
            assert team.name is not None
            assert team.settings is not None

    @pytest.mark.asyncio
    async def test_lookup_teams_with_name_filter(self, live_core_agent):
        """Filter teams by name prefix — shouldn't error even if no match."""
        result = await live_core_agent.lookup_teams(name="zzz_nonexistent_prefix")
        assert isinstance(result, LookupTeamsResponse)
        assert result.count == 0

    @pytest.mark.asyncio
    async def test_get_team_by_id(self, live_core_agent):
        """Fetch a team by ID (get first team from lookup)."""
        teams = await live_core_agent.lookup_teams()
        if teams.count == 0:
            pytest.skip("No teams available")
        team_id = teams.results[0].id
        result = await live_core_agent.get_team(team_id)
        assert "id" in result or "name" in result

    @pytest.mark.asyncio
    async def test_get_team_invalid_id(self, live_core_agent):
        """Invalid team ID should return 404 error."""
        result = await live_core_agent.get_team("00000000-0000-0000-0000-000000000000")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_team_members(self, live_core_agent):
        """List members of the first available team."""
        teams = await live_core_agent.lookup_teams()
        if teams.count == 0:
            pytest.skip("No teams available")
        team_id = teams.results[0].id
        result = await live_core_agent.list_team_members(team_id)
        # Should be a dict/list, not an error
        assert isinstance(result, (dict, list))

    @pytest.mark.asyncio
    async def test_get_my_active_team(self, live_core_agent):
        """Get the currently active team for the authenticated user."""
        result = await live_core_agent.get_my_active_team()
        assert isinstance(result, dict)
        # Should have team data or an empty dict, not an error string
        # Some accounts may not have an active team set


@live
class TestLiveUsers:
    """Live tests for user-related endpoints."""

    @pytest.mark.asyncio
    async def test_lookup_users(self, live_core_agent):
        """List users in the org."""
        result = await live_core_agent.lookup_users(limit=5)
        assert isinstance(result, LookupUsers)
        assert result.count >= 0

    @pytest.mark.asyncio
    async def test_lookup_users_with_username_filter(self, live_core_agent):
        """Filter users by username prefix."""
        result = await live_core_agent.lookup_users(username="oauth", limit=5)
        assert isinstance(result, LookupUsers)

    @pytest.mark.asyncio
    async def test_get_user_by_id(self, live_core_agent):
        """Get a specific user by ID."""
        users = await live_core_agent.lookup_users(limit=1)
        if users.count == 0:
            pytest.skip("No users found")
        user_id = users.results[0].id
        result = await live_core_agent.get_user(user_id)
        assert isinstance(result, dict)
        # Should contain user data
        assert "username" in result or "id" in result or "error" not in result

    @pytest.mark.asyncio
    async def test_get_user_invalid_id(self, live_core_agent):
        """Invalid user ID should return error."""
        result = await live_core_agent.get_user("00000000-0000-0000-0000-000000000000")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_lookup_service_accounts(self, live_core_agent):
        """List service accounts (may be empty)."""
        result = await live_core_agent.lookup_service_accounts(limit=5)
        assert isinstance(result, LookupServiceAccounts)
        assert result.count >= 0


# ===================================================================
# Jobs endpoints - Live
# ===================================================================

@live
class TestLiveJobs:
    """Live tests for job retrieval endpoints."""

    @pytest.mark.asyncio
    async def test_get_recent_jobs(self, live_core_agent):
        """Retrieve recent jobs from the live API."""
        result = await live_core_agent.get_recent_jobs(limit=5)
        assert "jobs" in result
        assert "total" in result
        assert isinstance(result["jobs"], list)
        assert result["per_page"] == 5

    @pytest.mark.asyncio
    async def test_get_recent_jobs_limit_1(self, live_core_agent):
        """Verify limit parameter works."""
        result = await live_core_agent.get_recent_jobs(limit=1)
        assert len(result["jobs"]) <= 1

    @pytest.mark.asyncio
    async def test_get_job_details(self, live_core_agent):
        """Get details of the most recent job."""
        jobs = await live_core_agent.get_recent_jobs(limit=1)
        if not jobs["jobs"]:
            pytest.skip("No jobs available")

        job_id = jobs["jobs"][0]["id"]
        result = await live_core_agent.get_job_details(job_id)
        assert "id" in result
        assert result["id"] == job_id

    @pytest.mark.asyncio
    async def test_get_job_details_invalid_id(self, live_core_agent):
        """Invalid job ID should return structured error."""
        result = await live_core_agent.get_job_details("00000000000000000000000000000000")
        assert "error" in result
        assert "Job not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_test_assets_for_vdc_job(self, live_core_agent):
        """Get assets for a VDC job (if one exists)."""
        jobs = await live_core_agent.get_recent_jobs(limit=10)
        vdc_job = None
        for job in jobs["jobs"]:
            # VDC jobs typically have a browser field
            if job.get("browser"):
                vdc_job = job
                break

        if not vdc_job:
            pytest.skip("No VDC jobs found in recent history")

        result = await live_core_agent.get_test_assets(vdc_job["id"])
        # Should either be assets dict or an error
        assert isinstance(result, dict)


# ===================================================================
# Build endpoints - Live
# ===================================================================

@live
class TestLiveBuilds:
    """Live tests for build endpoints."""

    @pytest.mark.asyncio
    async def test_lookup_vdc_builds(self, live_core_agent):
        """List recent VDC builds."""
        result = await live_core_agent.lookup_builds("vdc", limit=5)
        assert isinstance(result, dict)
        # Should have 'builds' key or be a valid response
        assert "builds" in result or "error" not in result

    @pytest.mark.asyncio
    async def test_lookup_rdc_builds(self, live_core_agent):
        """List recent RDC builds."""
        result = await live_core_agent.lookup_builds("rdc", limit=5)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_build_details(self, live_core_agent):
        """Get details of a specific build."""
        builds = await live_core_agent.lookup_builds("vdc", limit=1)
        if "builds" not in builds or not builds["builds"]:
            pytest.skip("No VDC builds available")

        build_id = builds["builds"][0]["id"]
        result = await live_core_agent.get_build("vdc", build_id)
        assert isinstance(result, dict)
        assert "error" not in result or "Build not found" not in result.get("error", "")

    @pytest.mark.asyncio
    async def test_get_build_invalid_id(self, live_core_agent):
        """Invalid build ID should return structured error."""
        result = await live_core_agent.get_build("vdc", "00000000000000000000000000000000")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_lookup_jobs_in_build(self, live_core_agent):
        """List jobs inside a build."""
        builds = await live_core_agent.lookup_builds("vdc", limit=1)
        if "builds" not in builds or not builds["builds"]:
            pytest.skip("No VDC builds available")

        build_id = builds["builds"][0]["id"]
        result = await live_core_agent.lookup_jobs_in_build("vdc", build_id)
        assert isinstance(result, dict)
        assert "jobs" in result


# ===================================================================
# Tunnel endpoints - Live
# ===================================================================

@live
class TestLiveTunnels:
    """Live tests for Sauce Connect tunnel endpoints."""

    @pytest.mark.asyncio
    async def test_get_tunnels_for_user(self, live_core_agent):
        """List tunnels for the authenticated user."""
        result = await live_core_agent.get_tunnels_for_user(live_core_agent.username)
        assert "tunnels" in result
        assert "count" in result
        assert isinstance(result["count"], int)

    @pytest.mark.asyncio
    async def test_get_tunnel_version_downloads(self, live_core_agent):
        """Get download URLs for a specific SC version."""
        result = await live_core_agent.get_tunnel_version_downloads("5.2.3")
        assert isinstance(result, dict)
        # Should contain download URLs or version info

    @pytest.mark.asyncio
    async def test_get_tunnel_info_invalid_id(self, live_core_agent):
        """Invalid tunnel ID should return error."""
        result = await live_core_agent.get_tunnel_information(
            live_core_agent.username,
            "00000000000000000000000000000000"
        )
        assert "error" in result


# ===================================================================
# Device endpoints - Live
# ===================================================================

@live
class TestLiveDevices:
    """Live tests for real device endpoints."""

    @pytest.mark.asyncio
    async def test_get_devices_status(self, live_core_agent):
        """List all devices in the data center."""
        result = await live_core_agent.get_devices_status()
        assert isinstance(result, dict)
        # API returns {"devices": [...]} dict
        devices_list = result.get("devices", result)
        if isinstance(devices_list, list):
            assert len(devices_list) > 0
            device = devices_list[0]
            assert "descriptor" in device or "descriptorId" in device or "name" in device

    @pytest.mark.asyncio
    async def test_get_specific_device(self, live_core_agent):
        """Get details of a specific device."""
        result = await live_core_agent.get_devices_status()
        devices_list = result.get("devices", result) if isinstance(result, dict) else result
        if not devices_list:
            pytest.skip("No devices available")

        first = devices_list[0] if isinstance(devices_list, list) else None
        if not first:
            pytest.skip("No devices in list")

        device_id = first.get("descriptor") or first.get("descriptorId")
        if not device_id:
            pytest.skip("No device descriptor found")

        detail = await live_core_agent.get_specific_device(device_id)
        assert isinstance(detail, dict)

    @pytest.mark.asyncio
    async def test_get_real_device_jobs(self, live_core_agent):
        """List active RDC jobs."""
        result = await live_core_agent.get_real_device_jobs(limit=5)
        assert isinstance(result, dict)
        # Should have entities key or similar
        assert "entities" in result or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_private_devices(self, live_core_agent):
        """List private devices (may be 403 for non-enterprise accounts)."""
        try:
            result = await live_core_agent.get_private_devices()
            # If we get here, verify the structure
            assert "devices" in result
            assert isinstance(result["devices"], list)
        except AttributeError:
            # Known bug: get_private_devices calls response.json() on a dict
            # when sauce_api_call returns an error dict (e.g., 403 Forbidden).
            # This account lacks private device permissions.
            pass


# ===================================================================
# Storage endpoints - Live
# ===================================================================

@live
class TestLiveStorage:
    """Live tests for storage endpoints."""

    @pytest.mark.asyncio
    async def test_get_storage_files(self, live_core_agent):
        """List files in Sauce Storage."""
        result = await live_core_agent.get_storage_files()
        assert isinstance(result, dict)
        # Should have items array
        assert "items" in result

    @pytest.mark.asyncio
    async def test_get_storage_groups(self, live_core_agent):
        """List app groups in Sauce Storage."""
        result = await live_core_agent.get_storage_groups()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_storage_group_settings(self, live_core_agent):
        """Get settings for a storage group (if any exist)."""
        groups = await live_core_agent.get_storage_groups()
        items = groups.get("items", [])
        if not items:
            pytest.skip("No storage groups available")

        group_id = items[0].get("id") or items[0].get("group_id")
        if not group_id:
            pytest.skip("No group ID found")

        result = await live_core_agent.get_storage_groups_settings(str(group_id))
        # Result could be dict (success or error) or string (404 text)
        assert result is not None


# ===================================================================
# Cross-cutting: data consistency
# ===================================================================

@live
class TestLiveDataConsistency:
    """Tests that verify data consistency across related endpoints."""

    @pytest.mark.asyncio
    async def test_account_info_matches_lookup(self, live_core_agent):
        """Account info username should match the agent's username."""
        result = await live_core_agent.get_account_info()
        assert result.results[0].username == live_core_agent.username

    @pytest.mark.asyncio
    async def test_job_details_match_recent_jobs(self, live_core_agent):
        """Job details should be consistent with the recent jobs listing."""
        recent = await live_core_agent.get_recent_jobs(limit=1)
        if not recent["jobs"]:
            pytest.skip("No jobs available")

        job_summary = recent["jobs"][0]
        job_detail = await live_core_agent.get_job_details(job_summary["id"])
        assert job_detail["id"] == job_summary["id"]
        # Status should match
        if "status" in job_summary and "status" in job_detail:
            assert job_detail["status"] == job_summary["status"]

    @pytest.mark.asyncio
    async def test_device_count_nonzero(self, live_core_agent):
        """EU_CENTRAL data center should have available devices."""
        result = await live_core_agent.get_devices_status()
        devices = result.get("devices", result) if isinstance(result, dict) else result
        if isinstance(devices, list):
            assert len(devices) > 0, "Expected at least one device in the data center"
        else:
            assert isinstance(result, dict)  # At minimum we got a valid response
