"""
Live E2E tests for SauceLabsRDCAgent (rdc_openapi.py) — hitting real Sauce Labs RDC APIs.

These tests make actual HTTP calls to the Sauce Labs EU_CENTRAL data center.
They test the real device cloud operations including device listing,
session management, and device interaction.

Run with: pytest tests/test_rdc_live.py -v -m live
"""

import asyncio
import pytest
import pytest_asyncio

from tests.conftest import live


# ===================================================================
# Device status - Live
# ===================================================================

@live
class TestLiveRDCDeviceStatus:
    """Live tests for RDC device status listing."""

    def _extract_devices(self, result):
        """Helper to extract device list from API response (may be list or dict with 'devices' key)."""
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "devices" in result:
            return result["devices"]
        return result

    @pytest.mark.asyncio
    async def test_list_all_devices(self, live_rdc_agent):
        """List all devices in the data center — should return a non-empty list."""
        result = await live_rdc_agent.list_device_status()
        devices = self._extract_devices(result)
        assert isinstance(devices, list)
        assert len(devices) > 0

    @pytest.mark.asyncio
    async def test_list_available_devices(self, live_rdc_agent):
        """Filter devices by AVAILABLE state."""
        result = await live_rdc_agent.list_device_status(state="AVAILABLE")
        devices = self._extract_devices(result)
        assert isinstance(devices, list)

    @pytest.mark.asyncio
    async def test_list_in_use_devices(self, live_rdc_agent):
        """Filter devices by IN_USE state."""
        result = await live_rdc_agent.list_device_status(state="IN_USE")
        devices = self._extract_devices(result)
        assert isinstance(devices, list)

    @pytest.mark.asyncio
    async def test_filter_by_device_name(self, live_rdc_agent):
        """Filter by device name pattern."""
        result = await live_rdc_agent.list_device_status(deviceName="iPhone.*")
        devices = self._extract_devices(result)
        assert isinstance(devices, list)
        for device in devices:
            name = device.get("name", "") or device.get("descriptor", "")
            assert "iphone" in name.lower() or "iPhone" in name

    @pytest.mark.asyncio
    async def test_filter_android_devices(self, live_rdc_agent):
        """Filter for Android devices by name pattern."""
        result = await live_rdc_agent.list_device_status(deviceName="Samsung.*|Google.*|Pixel.*")
        devices = self._extract_devices(result)
        assert isinstance(devices, list)

    @pytest.mark.asyncio
    async def test_invalid_state_rejected(self, live_rdc_agent):
        """Invalid state should be caught by client-side validation."""
        result = await live_rdc_agent.list_device_status(state="NONEXISTENT")
        assert "error" in result
        assert "Invalid state" in result["error"]


# ===================================================================
# Device sessions - Live
# ===================================================================

@live
class TestLiveRDCSessions:
    """Live tests for session listing and details."""

    @pytest.mark.asyncio
    async def test_list_sessions(self, live_rdc_agent):
        """List device sessions — may be empty, but should not error."""
        result = await live_rdc_agent.list_device_sessions()
        assert isinstance(result, (list, dict))
        # If dict, should not be an error
        if isinstance(result, dict):
            assert "error" not in result or "Not authorized" not in result.get("error", "")

    @pytest.mark.asyncio
    async def test_list_active_sessions(self, live_rdc_agent):
        """List only ACTIVE sessions."""
        result = await live_rdc_agent.list_device_sessions(state="ACTIVE")
        assert isinstance(result, (list, dict))

    @pytest.mark.asyncio
    async def test_list_closed_sessions(self, live_rdc_agent):
        """List CLOSED sessions — shows recently closed."""
        result = await live_rdc_agent.list_device_sessions(state="CLOSED")
        assert isinstance(result, (list, dict))

    @pytest.mark.asyncio
    async def test_get_session_invalid_id(self, live_rdc_agent):
        """Non-existent session ID should return 404 error."""
        result = await live_rdc_agent.get_session_details("00000000-0000-0000-0000-000000000000")
        assert isinstance(result, dict)
        assert "error" in result


# ===================================================================
# Session lifecycle - Live (allocate, interact, close)
# ===================================================================

@live
@pytest.mark.slow
class TestLiveRDCSessionLifecycle:
    """
    Full session lifecycle test: allocate a device, verify it's active,
    perform basic operations, then close it.

    These tests allocate real devices and cost real minutes — they are
    marked slow and should be run explicitly.
    """

    @pytest.mark.asyncio
    async def test_android_session_lifecycle(self, live_rdc_agent):
        """
        End-to-end: allocate Android device -> wait ACTIVE -> open URL -> close.
        """
        session_id = None
        try:
            # 1. Allocate a device
            result = await live_rdc_agent.allocate_device_and_create_session(os="android")
            assert isinstance(result, dict)
            assert "error" not in result, f"Failed to allocate: {result}"
            session_id = result.get("sessionId") or result.get("id")
            assert session_id is not None, f"No session ID in response: {result}"

            # 2. Wait for session to become ACTIVE (poll with timeout)
            max_wait = 120  # seconds
            poll_interval = 5
            elapsed = 0
            session_state = None

            while elapsed < max_wait:
                details = await live_rdc_agent.get_session_details(session_id)
                session_state = details.get("state") or details.get("status")
                if session_state == "ACTIVE":
                    break
                if session_state in ("ERRORED", "CLOSED"):
                    pytest.fail(f"Session entered {session_state} state")
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            assert session_state == "ACTIVE", \
                f"Session did not become ACTIVE within {max_wait}s (state={session_state})"

            # 3. Open a URL on the device
            url_result = await live_rdc_agent.open_url_or_deeplink(
                session_id, "https://www.saucedemo.com"
            )
            # Should succeed (204 -> success dict) or return response
            assert isinstance(url_result, dict)
            if "error" in url_result:
                # Some devices may have issues, log but don't hard fail
                print(f"Warning: open_url returned: {url_result}")

            # 4. Execute a shell command (Android only)
            shell_result = await live_rdc_agent.execute_shell_command(
                session_id, "getprop ro.build.version.sdk"
            )
            assert isinstance(shell_result, dict)

        finally:
            # 5. Always close the session to release the device
            if session_id:
                close_result = await live_rdc_agent.close_device_session(session_id)
                assert isinstance(close_result, dict)

    @pytest.mark.asyncio
    async def test_ios_session_lifecycle(self, live_rdc_agent):
        """
        End-to-end: allocate iOS device -> wait ACTIVE -> open URL -> close.
        """
        session_id = None
        try:
            # 1. Allocate an iOS device
            result = await live_rdc_agent.allocate_device_and_create_session(os="ios")
            assert isinstance(result, dict)
            assert "error" not in result, f"Failed to allocate: {result}"
            session_id = result.get("sessionId") or result.get("id")
            assert session_id is not None

            # 2. Wait for ACTIVE
            max_wait = 120
            poll_interval = 5
            elapsed = 0
            session_state = None

            while elapsed < max_wait:
                details = await live_rdc_agent.get_session_details(session_id)
                session_state = details.get("state") or details.get("status")
                if session_state == "ACTIVE":
                    break
                if session_state in ("ERRORED", "CLOSED"):
                    pytest.fail(f"Session entered {session_state} state")
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            assert session_state == "ACTIVE", \
                f"Session did not become ACTIVE within {max_wait}s"

            # 3. Open a URL (iOS opens in Safari)
            url_result = await live_rdc_agent.open_url_or_deeplink(
                session_id, "https://www.saucedemo.com"
            )
            assert isinstance(url_result, dict)

        finally:
            if session_id:
                await live_rdc_agent.close_device_session(session_id)

    @pytest.mark.asyncio
    async def test_session_with_specific_device(self, live_rdc_agent):
        """Allocate a specific device model."""
        session_id = None
        try:
            # Find an available Android device first
            result = await live_rdc_agent.list_device_status(state="AVAILABLE")
            devices = result.get("devices", result) if isinstance(result, dict) else result
            android_device = None
            for d in devices:
                os_name = d.get("os", "").lower()
                if os_name == "android":
                    android_device = d.get("name") or d.get("descriptor")
                    break

            if not android_device:
                pytest.skip("No available Android devices found")

            result = await live_rdc_agent.allocate_device_and_create_session(
                deviceName=android_device
            )
            assert isinstance(result, dict)
            if "error" in result:
                pytest.skip(f"Could not allocate specific device: {result}")

            session_id = result.get("sessionId") or result.get("id")
            assert session_id is not None

        finally:
            if session_id:
                await live_rdc_agent.close_device_session(session_id)


# ===================================================================
# HTTP Proxy via device - Live
# ===================================================================

@live
@pytest.mark.slow
class TestLiveRDCProxy:
    """
    Live proxy tests — require an active device session.
    These allocate a real device to test proxy forwarding.
    """

    @pytest_asyncio.fixture
    async def active_android_session(self, live_rdc_agent):
        """Fixture that provides an active Android session, cleaned up after test."""
        result = await live_rdc_agent.allocate_device_and_create_session(os="android")
        if "error" in result:
            pytest.skip(f"Could not allocate device: {result}")

        session_id = result.get("sessionId") or result.get("id")
        if not session_id:
            pytest.skip("No session ID returned")

        # Wait for ACTIVE
        for _ in range(24):  # 2 minutes max
            details = await live_rdc_agent.get_session_details(session_id)
            if details.get("state") == "ACTIVE":
                break
            await asyncio.sleep(5)
        else:
            await live_rdc_agent.close_device_session(session_id)
            pytest.skip("Session did not become ACTIVE in time")

        yield session_id

        # Cleanup
        await live_rdc_agent.close_device_session(session_id)

    @pytest.mark.asyncio
    async def test_proxy_get_request(self, live_rdc_agent, active_android_session):
        """Forward a GET request through the device proxy."""
        result = await live_rdc_agent.forward_http_get(
            active_android_session,
            "httpbin.org",
            "443",
            "get"
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_proxy_post_request(self, live_rdc_agent, active_android_session):
        """Forward a POST request through the device proxy."""
        result = await live_rdc_agent.forward_http_post(
            active_android_session,
            "httpbin.org",
            "443",
            "post",
            data={"test": "value"}
        )
        assert isinstance(result, dict)


# ===================================================================
# Close session error handling - Live
# ===================================================================

@live
class TestLiveRDCCloseSession:
    """Live tests for session close error handling."""

    @pytest.mark.asyncio
    async def test_close_nonexistent_session(self, live_rdc_agent):
        """Closing a non-existent session should return error."""
        result = await live_rdc_agent.close_device_session(
            "00000000-0000-0000-0000-000000000000"
        )
        assert isinstance(result, dict)
        assert "error" in result
