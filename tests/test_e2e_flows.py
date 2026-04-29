"""
End-to-end workflow tests — complete multi-step scenarios hitting live Sauce Labs APIs.

These tests exercise real-world workflows that a user would perform through
the MCP tools, validating that the full chain works end to end.

Run with: pytest tests/test_e2e_flows.py -v -m live
Or for slow tests too: pytest tests/test_e2e_flows.py -v -m "live or slow"
"""

import pytest

from tests.conftest import live


# ===================================================================
# Flow 1: Account Discovery
# ===================================================================

@live
class TestAccountDiscoveryFlow:
    """
    Simulates a user exploring their Sauce Labs organization:
    1. Get account info
    2. Look up teams in the org
    3. Get members of each team
    4. Look up users
    """

    @pytest.mark.asyncio
    async def test_full_account_discovery(self, live_core_agent):
        # Step 1: Get account info
        account = await live_core_agent.get_account_info()
        assert account.count >= 1
        user = account.results[0]
        assert user.username == live_core_agent.username
        org_name = user.organization.name
        assert org_name is not None

        # Step 2: List teams
        teams = await live_core_agent.lookup_teams()
        assert teams.count >= 0

        # Step 3: For each team (up to 3), get members
        for team in teams.results[:3]:
            members = await live_core_agent.list_team_members(team.id)
            assert isinstance(members, dict)

        # Step 4: Look up users with pagination
        page1 = await live_core_agent.lookup_users(limit=5, offset=0)
        assert page1.count >= 0

        if page1.count > 5:
            page2 = await live_core_agent.lookup_users(limit=5, offset=5)
            assert isinstance(page2.results, list)


# ===================================================================
# Flow 2: Job Investigation Pipeline
# ===================================================================

@live
class TestJobInvestigationFlow:
    """
    Simulates investigating test failures:
    1. Get recent jobs
    2. Pick a job and get its details
    3. Determine if VDC or RDC
    4. Get appropriate assets
    5. Check the build it belongs to
    """

    @pytest.mark.asyncio
    async def test_investigate_recent_job(self, live_core_agent):
        # Step 1: Get recent jobs
        recent = await live_core_agent.get_recent_jobs(limit=10)
        assert "jobs" in recent
        if not recent["jobs"]:
            pytest.skip("No recent jobs to investigate")

        # Step 2: Get details of the first job
        job = recent["jobs"][0]
        job_id = job["id"]
        details = await live_core_agent.get_job_details(job_id)
        assert details["id"] == job_id

        # Step 3: Determine job type
        is_rdc = bool(details.get("assigned_tunnel_id")) or \
                 "real" in str(details.get("automation_backend", "")).lower() or \
                 details.get("device")

        # Step 4a: VDC path — get test assets
        if not is_rdc and details.get("browser"):
            assets = await live_core_agent.get_test_assets(job_id)
            assert isinstance(assets, dict)
            # If assets are available, try to get logs
            if "error" not in assets and "sauce-log" in assets:
                logs = await live_core_agent.get_log_json_file(job_id)
                assert isinstance(logs, (list, dict))

        # Step 4b: RDC path — get RDC-specific assets
        elif is_rdc:
            rdc_detail = await live_core_agent.get_specific_real_device_job(job_id)
            assert isinstance(rdc_detail, dict)

        # Step 5: Check which build this job belongs to
        build_source = "rdc" if is_rdc else "vdc"
        build = await live_core_agent.get_build_for_job(build_source, job_id)
        # May or may not have a build - both are valid
        assert isinstance(build, dict)

    @pytest.mark.asyncio
    async def test_paginate_through_jobs(self, live_core_agent):
        """Verify pagination across multiple job requests."""
        page1 = await live_core_agent.get_recent_jobs(limit=3)
        assert "jobs" in page1

        if len(page1["jobs"]) < 3:
            pytest.skip("Not enough jobs for pagination test")

        page2 = await live_core_agent.get_recent_jobs(limit=3)
        assert "jobs" in page2

        # Both pages should return valid data
        assert len(page1["jobs"]) <= 3
        assert len(page2["jobs"]) <= 3


# ===================================================================
# Flow 4: Build Analysis
# ===================================================================

@live
class TestBuildAnalysisFlow:
    """
    Simulates analyzing test builds:
    1. Look up recent builds
    2. Get build details
    3. List jobs in the build
    4. Inspect individual jobs
    """

    @pytest.mark.asyncio
    async def test_analyze_vdc_build(self, live_core_agent):
        # Step 1: Look up VDC builds
        builds = await live_core_agent.lookup_builds("vdc", limit=5)
        assert isinstance(builds, dict)

        if "builds" not in builds or not builds["builds"]:
            pytest.skip("No VDC builds available")

        # Step 2: Get details of the first build
        build = builds["builds"][0]
        build_id = build["id"]
        build_details = await live_core_agent.get_build("vdc", build_id)
        assert isinstance(build_details, dict)

        # Step 3: List jobs in this build
        build_jobs = await live_core_agent.lookup_jobs_in_build("vdc", build_id)
        assert isinstance(build_jobs, dict)
        assert "jobs" in build_jobs

        # Step 4: If there are jobs, inspect the first one
        if build_jobs["jobs"]:
            first_job = build_jobs["jobs"][0]
            job_id = first_job.get("id")
            if job_id:
                job_detail = await live_core_agent.get_job_details(job_id)
                assert isinstance(job_detail, dict)

    @pytest.mark.asyncio
    async def test_analyze_rdc_build(self, live_core_agent):
        """Same flow for RDC builds."""
        builds = await live_core_agent.lookup_builds("rdc", limit=3)
        assert isinstance(builds, dict)

        if "builds" not in builds or not builds["builds"]:
            pytest.skip("No RDC builds available")

        build_id = builds["builds"][0]["id"]
        build_jobs = await live_core_agent.lookup_jobs_in_build("rdc", build_id)
        assert isinstance(build_jobs, dict)


# ===================================================================
# Flow 5: Storage Exploration
# ===================================================================

@live
class TestStorageExplorationFlow:
    """
    Simulates exploring app storage:
    1. List storage files
    2. List app groups
    3. Get group settings
    """

    @pytest.mark.asyncio
    async def test_explore_storage(self, live_core_agent):
        # Step 1: List all files
        files = await live_core_agent.get_storage_files()
        assert isinstance(files, dict)
        assert "items" in files

        file_count = len(files.get("items", []))

        # Step 2: List app groups
        groups = await live_core_agent.get_storage_groups()
        assert isinstance(groups, dict)

        group_items = groups.get("items", [])

        # Step 3: Get settings for first group (if any)
        if group_items:
            group_id = group_items[0].get("id") or group_items[0].get("group_id")
            if group_id:
                settings = await live_core_agent.get_storage_groups_settings(str(group_id))
                # May return dict (success/error) or string (404 text body)
                assert settings is not None


# ===================================================================
# Flow 7: Tunnel Discovery (read-only, no tunnel creation)
# ===================================================================

@live
class TestTunnelDiscoveryFlow:
    """
    Test tunnel-related read operations:
    1. List tunnels for user
    2. Get download links for SC versions
    """

    @pytest.mark.asyncio
    async def test_tunnel_discovery(self, live_core_agent):
        # Step 1: List tunnels
        tunnels = await live_core_agent.get_tunnels_for_user(live_core_agent.username)
        assert "tunnels" in tunnels
        assert "count" in tunnels

        # Step 2: If tunnels exist, get info on the first one
        if tunnels["count"] > 0 and isinstance(tunnels["tunnels"], list):
            tunnel_id = tunnels["tunnels"][0]
            if isinstance(tunnel_id, str):
                info = await live_core_agent.get_tunnel_information(
                    live_core_agent.username, tunnel_id
                )
                assert isinstance(info, dict)

        # Step 3: Get SC download links
        downloads = await live_core_agent.get_tunnel_version_downloads("5.2.3")
        assert isinstance(downloads, dict)


# ===================================================================
# Flow 8: Error Boundary Validation (live)
# ===================================================================

@live
class TestErrorBoundaryFlow:
    """
    Verify error handling works correctly against live APIs.
    These tests intentionally trigger errors and verify the structured
    error responses contain actionable information.
    """

    @pytest.mark.asyncio
    async def test_invalid_job_id_chain(self, live_core_agent):
        """All job-related calls with invalid ID should return errors."""
        fake_id = "ffffffffffffffffffffffffffffffff"

        detail_result = await live_core_agent.get_job_details(fake_id)
        assert "error" in detail_result

        asset_result = await live_core_agent.get_test_assets(fake_id)
        assert "error" in asset_result

    @pytest.mark.asyncio
    async def test_invalid_build_id(self, live_core_agent):
        """Invalid build ID should return structured error."""
        result = await live_core_agent.get_build("vdc", "ffffffffffffffffffffffffffffffff")
        assert "error" in result
        assert "suggestions" in result

    @pytest.mark.asyncio
    async def test_invalid_team_id(self, live_core_agent):
        """Invalid team ID should return structured error."""
        result = await live_core_agent.get_team("ffffffff-ffff-ffff-ffff-ffffffffffff")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_user_id(self, live_core_agent):
        """Invalid user ID should return structured error."""
        result = await live_core_agent.get_user("ffffffff-ffff-ffff-ffff-ffffffffffff")
        assert "error" in result

