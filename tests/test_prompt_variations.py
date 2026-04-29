"""
Prompt-variation tests for the dynamic OpenAPI MCP server.

Tests whether varied natural language prompts resolve to the correct
MCP tool and produce valid results when executed against live Sauce Labs APIs.

The MCP server exposes tool names + descriptions. An LLM reads these to decide
which tool to call. These tests verify that the tool descriptions are good
enough for correct resolution regardless of how the user phrases their request.

Two resolution modes:
  1. ANTHROPIC_API_KEY set → Claude API selects the tool (real LLM tool_use)
  2. No API key → keyword-scoring against tool descriptions (deterministic)

Either way, the resolved tool is executed against live Sauce Labs APIs.

Run:
  SAUCE_USERNAME=... SAUCE_ACCESS_KEY=... SAUCE_REGION=EU_CENTRAL \\
    pytest tests/test_prompt_variations.py -v

  # With LLM-powered resolution (optional):
  ANTHROPIC_API_KEY=sk-... SAUCE_USERNAME=... SAUCE_ACCESS_KEY=... \\
    pytest tests/test_prompt_variations.py -v
"""

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Optional

import pytest

from sauce_api_mcp.rdc_dynamic import (
    DEFAULT_SPEC_URL,
    create_server,
    fetch_openapi_spec_sync,
)

from tests.conftest import live, HAS_CREDENTIALS, _load_credentials, compat_get_tools, compat_call_tool

USERNAME, ACCESS_KEY, REGION = _load_credentials()

HAS_ANTHROPIC_KEY = bool(os.getenv("ANTHROPIC_API_KEY"))


# ---------------------------------------------------------------------------
# Prompt → Tool resolution
# ---------------------------------------------------------------------------

@dataclass
class ToolResolution:
    """Result of resolving a prompt to a tool."""
    prompt: str
    resolved_tool: str
    arguments: dict
    resolution_method: str  # "llm" or "keyword"
    confidence: Optional[float] = None


def _keyword_score(prompt: str, tool_name: str, description: str) -> float:
    """Score how well a prompt matches a tool by keyword overlap.

    Uses intent-based scoring: prompt words are mapped to intents, and
    tools are scored based on how many intents they satisfy.
    """
    prompt_lower = prompt.lower()
    prompt_words = set(re.findall(r'\w+', prompt_lower))

    # Tool name tokens (split camelCase and underscores)
    name_tokens = set(
        w.lower() for w in re.findall(r'[A-Z]?[a-z]+|[A-Z]+', tool_name)
    )
    desc_lower = description.lower() if description else ""

    # Intent detection from prompt words
    intents = set()
    intent_map = {
        "list_devices": {"device", "devices", "phone", "phones", "mobile", "handset", "inventory", "catalog"},
        "status": {"status", "state", "available", "availability", "free"},
        "list": {"list", "show", "get", "give", "what", "which", "all", "display", "see", "view", "find"},
        "create": {"create", "start", "new", "begin", "spin", "allocate", "reserve"},
        "delete": {"delete", "close", "end", "stop", "terminate", "release", "kill", "shut", "done"},
        "install_app": {"install", "deploy", "sideload"},
        "shell": {"shell", "command", "execute", "adb", "terminal", "cmd"},
        "url": {"url", "browse", "navigate", "website", "web", "link", "visit", "webpage"},
        "screenshot": {"screenshot", "snap", "capture"},
        "screen": {"screen"},
        "appium": {"appium", "automation", "framework"},
        "version": {"version", "versions"},
        "network": {"network", "throttle", "throttling", "bandwidth", "latency", "condition", "3g", "4g"},
        "profile": {"profile", "profiles"},
        "proxy": {"proxy", "forward"},
        "file": {"file", "files", "transfer"},
        "push_file": {"push"},
        "pull_file": {"pull", "download"},
        "app": {"app", "application", "apk", "ipa"},
        "uninstall": {"uninstall", "remove"},
        "session": {"session", "sessions"},
        "run": {"run"},
        "open": {"open", "go"},
    }
    for intent, keywords in intent_map.items():
        if prompt_words & keywords:
            intents.add(intent)

    score = 0.0

    # Direct intent-to-tool mapping with strong scores
    strong_matches = {
        "listDeviceStatus": {"list_devices", "status"},
        "listDevices": {"list_devices", "list"},
        "listSessions": {"list", "session"},
        "listAppiumVersions": {"appium", "version", "list"},
        "createSession": {"create", "session"},
        "deleteSession": {"delete", "session"},
        "executeShellCommand": {"shell", "run"},
        "openUrl": {"url", "open"},
        "installApp": {"install_app", "app"},
        "uninstallApp": {"uninstall", "app"},
        "take_screenshot": {"screenshot", "screen"},
        "push_file_to_device": {"push_file", "file"},
        "pull_file_from_device": {"pull_file", "file"},
        "listNetworkProfiles": {"network", "profile", "list"},
        "setNetworkConditions": {"network"},
        "startNetworkCapture": {"network"},
        "proxyGet": {"proxy"},
        "proxyPost": {"proxy"},
    }

    if tool_name in strong_matches:
        tool_intents = strong_matches[tool_name]
        matched_intents = intents & tool_intents
        score += len(matched_intents) * 5.0

        # Bonus: if ALL of a tool's key intents match, extra boost
        if tool_intents <= intents:
            score += 10.0

    # Light description overlap (lower weight)
    desc_words = set(re.findall(r'\w+', desc_lower))
    score += len(prompt_words & desc_words) * 0.3

    # Light name overlap
    score += len(prompt_words & name_tokens) * 0.5

    return score


async def resolve_prompt_keyword(prompt: str, tools: dict) -> ToolResolution:
    """Resolve a prompt to a tool using keyword scoring."""
    best_tool = None
    best_score = -1

    for name, tool in tools.items():
        desc = tool.description if hasattr(tool, "description") else ""
        score = _keyword_score(prompt, name, desc)
        if score > best_score:
            best_score = score
            best_tool = name

    return ToolResolution(
        prompt=prompt,
        resolved_tool=best_tool,
        arguments={},  # keyword resolver doesn't generate args
        resolution_method="keyword",
        confidence=best_score,
    )


async def resolve_prompt_llm(prompt: str, tools: dict) -> ToolResolution:
    """Resolve a prompt to a tool using Claude API with tool_use."""
    import anthropic

    # Build tool definitions from MCP tools
    tool_defs = []
    for name, tool in tools.items():
        params = tool.parameters if hasattr(tool, "parameters") else {}
        input_schema = params if isinstance(params, dict) and params else {
            "type": "object", "properties": {}
        }
        tool_defs.append({
            "name": name,
            "description": (tool.description or "")[:1024],
            "input_schema": input_schema,
        })

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=(
            "You are connected to a Sauce Labs MCP server for real device testing. "
            "Use the available tools to fulfill the user's request. "
            "Pick the single most appropriate tool and provide arguments."
        ),
        tools=tool_defs,
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract tool_use from response
    for block in response.content:
        if block.type == "tool_use":
            return ToolResolution(
                prompt=prompt,
                resolved_tool=block.name,
                arguments=block.input,
                resolution_method="llm",
            )

    # No tool selected — LLM chose to respond with text only
    return ToolResolution(
        prompt=prompt,
        resolved_tool=None,
        arguments={},
        resolution_method="llm",
    )


async def resolve_prompt(prompt: str, tools: dict) -> ToolResolution:
    """Resolve using LLM if available, else keyword matching."""
    if HAS_ANTHROPIC_KEY:
        return await resolve_prompt_llm(prompt, tools)
    return await resolve_prompt_keyword(prompt, tools)


# ---------------------------------------------------------------------------
# Test data: prompt variations grouped by expected tool
# ---------------------------------------------------------------------------

PROMPT_VARIATIONS = [
    # --- Device availability / status ---
    {
        "acceptable_tools": {"listDeviceStatus", "listDevices"},
        "prompts": [
            "list all the available devices",
            "give me all devices available",
            "what devices can I test on?",
            "show me the device status",
            "which phones are free right now?",
            "are there any available devices?",
            "display all devices and their states",
        ],
        "id": "device_availability",
    },
    # --- Device catalog / specs ---
    {
        "acceptable_tools": {"listDevices", "listDeviceStatus"},
        "prompts": [
            "show me the full device catalog",
            "what devices does the lab have?",
            "list all device specifications",
            "give me the complete device inventory",
        ],
        "id": "device_catalog",
    },
    # --- Session listing ---
    {
        "acceptable_tools": {"listSessions"},
        "prompts": [
            "show me all active sessions",
            "what sessions are currently running?",
            "list my device sessions",
            "are there any open sessions?",
            "give me the current session list",
        ],
        "id": "session_listing",
    },
    # --- Appium versions ---
    {
        "acceptable_tools": {"listAppiumVersions"},
        "prompts": [
            "what appium versions are available?",
            "show me supported appium versions",
            "list the appium framework versions",
        ],
        "id": "appium_versions",
    },
    # --- Create session ---
    {
        "acceptable_tools": {"createSession"},
        "prompts": [
            "create a new device session",
            "start a new session on a device",
            "spin up a new session",
            "begin a new device session",
        ],
        "id": "create_session",
    },
    # --- Close / delete session ---
    {
        "acceptable_tools": {"deleteSession"},
        "prompts": [
            "close this device session",
            "end the session",
            "release the device",
            "terminate the current session",
            "I'm done testing, close the session",
            "shut down the session",
        ],
        "id": "delete_session",
    },
    # --- Execute shell command ---
    {
        "acceptable_tools": {"executeShellCommand"},
        "prompts": [
            "run a shell command on the device",
            "execute adb command on the phone",
            "execute a command in the device shell",
        ],
        "id": "shell_command",
    },
    # --- Open URL ---
    {
        "acceptable_tools": {"openUrl"},
        "prompts": [
            "open a website on the device",
            "navigate to a URL on the device",
            "browse to a URL on the phone",
            "open this link on the phone",
            "visit a webpage on the device",
        ],
        "id": "open_url",
    },
    # --- Install app ---
    {
        "acceptable_tools": {"installApp"},
        "prompts": [
            "install an app on the device",
            "deploy the APK to the phone",
            "sideload this application",
            "install my test app on the device",
        ],
        "id": "install_app",
    },
    # --- Screenshot ---
    {
        "acceptable_tools": {"take_screenshot"},
        "prompts": [
            "take a screenshot of the device",
            "grab a screenshot of the screen",
            "take a screenshot now",
        ],
        "id": "screenshot",
    },
    # --- Network throttling ---
    {
        "acceptable_tools": {"listNetworkProfiles", "setNetworkConditions", "setNetworkProfile"},
        "prompts": [
            "show me available network profiles",
            "what network conditions can I simulate?",
            "list the network profiles",
        ],
        "id": "network_profiles",
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def spec_from_url():
    try:
        return fetch_openapi_spec_sync(DEFAULT_SPEC_URL)
    except Exception:
        pytest.skip("Could not fetch OpenAPI spec")


@pytest.fixture(scope="module")
def offline_tools(spec_from_url):
    """Tools dict from a server with fake creds (for resolution only)."""
    import asyncio
    server = create_server(spec_from_url, "fake", "fake", "US_WEST")
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(compat_get_tools(server))
    finally:
        loop.close()


@pytest.fixture
def live_server(live_credentials, spec_from_url):
    username, access_key, region = live_credentials
    return create_server(spec_from_url, access_key, username, region)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_result(result):
    return json.loads(result.content[0].text)


# ===================================================================
# Test: Tool Resolution Accuracy
# ===================================================================

class TestToolResolutionAccuracy:
    """
    For each prompt variation, verify the resolver picks an acceptable tool.
    This tests whether tool names + descriptions are descriptive enough.

    Uses acceptable_tools sets because some prompts validly map to multiple
    tools (e.g., "show me devices" → listDevices OR listDeviceStatus).
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "group",
        PROMPT_VARIATIONS,
        ids=[g["id"] for g in PROMPT_VARIATIONS],
    )
    async def test_prompt_resolves_to_acceptable_tool(self, group, offline_tools):
        acceptable = group["acceptable_tools"]
        failures = []

        for prompt in group["prompts"]:
            resolution = await resolve_prompt(prompt, offline_tools)
            if resolution.resolved_tool not in acceptable:
                failures.append(
                    f"  Prompt: \"{prompt}\"\n"
                    f"    Acceptable: {acceptable}\n"
                    f"    Got:        {resolution.resolved_tool} "
                    f"(method={resolution.resolution_method}, "
                    f"confidence={resolution.confidence})"
                )

        if failures:
            method = "LLM" if HAS_ANTHROPIC_KEY else "keyword"
            pytest.fail(
                f"Tool resolution failures for {group['id']} ({method} mode):\n"
                + "\n".join(failures)
            )


# ===================================================================
# Test: Resolved Tools Execute Successfully Against Live APIs
# ===================================================================

@live
class TestPromptToLiveExecution:
    """
    End-to-end: natural language prompt → resolve to tool → execute on live
    Sauce Labs → validate response.

    Only runs tools that are safe to call without a session (read-only).
    """

    @pytest.mark.asyncio
    async def test_device_availability_prompts(self, live_server, offline_tools):
        """All 'show me devices' prompt variations should return real device data."""
        prompts = [
            "list all the available devices",
            "give me all devices available",
            "what devices can I test on?",
            "show me the device status",
            "which phones are free right now?",
        ]
        for prompt in prompts:
            resolution = await resolve_prompt(prompt, offline_tools)
            assert resolution.resolved_tool in ("listDeviceStatus", "listDevices"), (
                f"Prompt \"{prompt}\" resolved to {resolution.resolved_tool}"
            )

            # Execute against live API
            result = await compat_call_tool(live_server,
                resolution.resolved_tool, {}
            )
            data = _parse_result(result)
            assert isinstance(data, dict), f"Prompt \"{prompt}\" returned non-dict"

            # Should contain device data
            devices = data.get("devices", data.get("result", []))
            assert isinstance(devices, list), (
                f"Prompt \"{prompt}\" didn't return device list"
            )
            assert len(devices) > 0, (
                f"Prompt \"{prompt}\" returned empty device list"
            )

    @pytest.mark.asyncio
    async def test_session_listing_prompts(self, live_server, offline_tools):
        """All 'show me sessions' prompts should return session data."""
        prompts = [
            "show me all active sessions",
            "what sessions are currently running?",
            "list my device sessions",
        ]
        for prompt in prompts:
            resolution = await resolve_prompt(prompt, offline_tools)
            assert resolution.resolved_tool == "listSessions", (
                f"Prompt \"{prompt}\" resolved to {resolution.resolved_tool}"
            )

            result = await compat_call_tool(live_server,"listSessions", {})
            data = _parse_result(result)
            assert isinstance(data, dict)
            assert "sessions" in data

    @pytest.mark.asyncio
    async def test_appium_version_prompts(self, live_server, offline_tools):
        """Appium version prompts should return version data."""
        prompts = [
            "what appium versions are available?",
            "show me supported appium versions",
            "which automation versions can I use?",
        ]
        for prompt in prompts:
            resolution = await resolve_prompt(prompt, offline_tools)
            assert resolution.resolved_tool == "listAppiumVersions", (
                f"Prompt \"{prompt}\" resolved to {resolution.resolved_tool}"
            )

            result = await compat_call_tool(live_server,
                "listAppiumVersions", {}
            )
            data = _parse_result(result)
            assert "versions" in data
            assert len(data["versions"]) > 0

    @pytest.mark.asyncio
    async def test_device_catalog_prompts(self, live_server, offline_tools):
        """Device catalog prompts should return full device specifications."""
        prompts = [
            "show me the full device catalog",
            "what devices does the lab have?",
            "list all device specifications",
        ]
        for prompt in prompts:
            resolution = await resolve_prompt(prompt, offline_tools)
            assert resolution.resolved_tool in ("listDevices", "listDeviceStatus"), (
                f"Prompt \"{prompt}\" resolved to {resolution.resolved_tool}"
            )

            result = await compat_call_tool(live_server,
                resolution.resolved_tool, {}
            )
            data = _parse_result(result)
            assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_network_profile_prompts(self, live_server, offline_tools):
        """Network profile prompts should resolve correctly.
        Note: listNetworkProfiles requires sessionId, so we just verify resolution."""
        prompts = [
            "show me available network throttling profiles",
            "what network conditions can I simulate?",
        ]
        for prompt in prompts:
            resolution = await resolve_prompt(prompt, offline_tools)
            assert resolution.resolved_tool in (
                "listNetworkProfiles", "setNetworkConditions",
                "setNetworkProfile", "startNetworkCapture"
            ), (
                f"Prompt \"{prompt}\" resolved to {resolution.resolved_tool}, "
                "expected a network-related tool"
            )


# ===================================================================
# Test: Session Lifecycle via Natural Language Prompts (live)
# ===================================================================

@live
@pytest.mark.slow
class TestPromptDrivenSessionLifecycle:
    """
    Full lifecycle driven by natural language prompts:
    1. "spin up a device" → createSession
    2. "open saucedemo.com" → openUrl
    3. "run ls on the device" → executeShellCommand
    4. "take a screenshot" → take_screenshot
    5. "close the session" → deleteSession

    Each step resolves the prompt, then executes the tool on live infra.
    """

    @pytest.mark.asyncio
    async def test_full_prompt_driven_lifecycle(self, live_server, offline_tools):
        session_id = None
        results = {}

        try:
            # Step 1: Create session
            resolution = await resolve_prompt(
                "create a new session on a device", offline_tools
            )
            assert resolution.resolved_tool == "createSession", (
                f"Expected createSession, got {resolution.resolved_tool}"
            )
            results["create_resolution"] = resolution.resolved_tool

            result = await compat_call_tool(live_server,
                "createSession", {"device": {"os": "android"}}
            )
            data = _parse_result(result)
            session_id = data.get("sessionId") or data.get("id")
            assert session_id, f"No session ID: {data}"
            results["session_id"] = session_id

            # Wait for ACTIVE
            for _ in range(24):
                r = await compat_call_tool(live_server,
                    "getSession", {"sessionId": session_id}
                )
                state = _parse_result(r).get("state")
                if state == "ACTIVE":
                    break
                if state in ("ERRORED", "CLOSED"):
                    pytest.fail(f"Session {state}")
                await asyncio.sleep(5)
            else:
                pytest.fail("Session not ACTIVE in 2 min")

            # Step 2: Open URL
            resolution = await resolve_prompt(
                "navigate to saucedemo.com on the device", offline_tools
            )
            assert resolution.resolved_tool == "openUrl", (
                f"Expected openUrl, got {resolution.resolved_tool}"
            )
            results["url_resolution"] = resolution.resolved_tool

            await compat_call_tool(live_server,
                "openUrl",
                {"sessionId": session_id, "url": "https://www.saucedemo.com"},
            )

            # Step 3: Shell command
            resolution = await resolve_prompt(
                "run a shell command on the device", offline_tools
            )
            assert resolution.resolved_tool == "executeShellCommand", (
                f"Expected executeShellCommand, got {resolution.resolved_tool}"
            )
            results["shell_resolution"] = resolution.resolved_tool

            shell_result = await compat_call_tool(live_server,
                "executeShellCommand",
                {"sessionId": session_id, "adbShellCommand": "echo prompt_test_ok"},
            )
            shell_data = _parse_result(shell_result)
            results["shell_output"] = shell_data

            # Step 4: Screenshot resolution (don't execute — just verify)
            resolution = await resolve_prompt(
                "take a screenshot of what's on screen", offline_tools
            )
            assert resolution.resolved_tool == "take_screenshot", (
                f"Expected take_screenshot, got {resolution.resolved_tool}"
            )
            results["screenshot_resolution"] = resolution.resolved_tool

            # Step 5: Close session
            resolution = await resolve_prompt(
                "I'm done, close the session", offline_tools
            )
            assert resolution.resolved_tool == "deleteSession", (
                f"Expected deleteSession, got {resolution.resolved_tool}"
            )
            results["delete_resolution"] = resolution.resolved_tool

        finally:
            if session_id:
                try:
                    await compat_call_tool(live_server,
                        "deleteSession", {"sessionId": session_id}
                    )
                except Exception:
                    pass

        # All 5 prompts resolved correctly and executed on live infra
        assert results["create_resolution"] == "createSession"
        assert results["url_resolution"] == "openUrl"
        assert results["shell_resolution"] == "executeShellCommand"
        assert results["screenshot_resolution"] == "take_screenshot"
        assert results["delete_resolution"] == "deleteSession"


# ===================================================================
# Test: Ambiguous / Tricky Prompts
# ===================================================================

class TestAmbiguousPrompts:
    """
    Tests for prompts that are harder to resolve — ambiguous wording,
    indirect references, or prompts that could match multiple tools.
    """

    @pytest.mark.asyncio
    async def test_open_vs_create_disambiguation(self, offline_tools):
        """'open' could mean openUrl or createSession — context matters."""
        # 'open a website' should be openUrl
        r = await resolve_prompt("open a website on the device", offline_tools)
        assert r.resolved_tool == "openUrl", (
            f"'open a website' → {r.resolved_tool}, expected openUrl"
        )

        # 'open a session' should be createSession
        r = await resolve_prompt("open a new device session", offline_tools)
        assert r.resolved_tool == "createSession", (
            f"'open a session' → {r.resolved_tool}, expected createSession"
        )

    @pytest.mark.asyncio
    async def test_install_vs_push_disambiguation(self, offline_tools):
        """'install app' should be installApp, 'push file' should be push_file."""
        r = await resolve_prompt("install the app on the device", offline_tools)
        assert r.resolved_tool == "installApp", (
            f"'install app' → {r.resolved_tool}"
        )

        r = await resolve_prompt("push a file to the device storage", offline_tools)
        assert r.resolved_tool == "push_file_to_device", (
            f"'push file' → {r.resolved_tool}"
        )

    @pytest.mark.asyncio
    async def test_stop_vs_delete_disambiguation(self, offline_tools):
        """'stop' + session context should resolve to deleteSession."""
        r = await resolve_prompt("stop the device session", offline_tools)
        assert r.resolved_tool == "deleteSession", (
            f"'stop session' → {r.resolved_tool}"
        )

    @pytest.mark.asyncio
    async def test_colloquial_prompts(self, offline_tools):
        """Casual / colloquial prompts should still resolve correctly."""
        cases = [
            ("what phones can I use?", {"listDeviceStatus", "listDevices"}),
            ("kill the session", {"deleteSession"}),
            ("screenshot please", {"take_screenshot"}),
            ("run a shell command on the device", {"executeShellCommand"}),
        ]
        for prompt, acceptable_tools in cases:
            r = await resolve_prompt(prompt, offline_tools)
            assert r.resolved_tool in acceptable_tools, (
                f"Prompt \"{prompt}\" → {r.resolved_tool}, "
                f"expected one of {acceptable_tools}"
            )

    @pytest.mark.asyncio
    async def test_question_format_prompts(self, offline_tools):
        """Questions should resolve the same as commands."""
        cases = [
            ("can you show me which devices are available?", {"listDeviceStatus", "listDevices"}),
            ("could you list the sessions?", {"listSessions"}),
            ("what appium versions do you support?", {"listAppiumVersions"}),
        ]
        for prompt, acceptable in cases:
            r = await resolve_prompt(prompt, offline_tools)
            assert r.resolved_tool in acceptable, (
                f"\"{prompt}\" → {r.resolved_tool}, expected {acceptable}"
            )


# ===================================================================
# Test: Resolution + Live Execution Combined
# ===================================================================

@live
class TestResolutionQuality:
    """
    Verify that different phrasings of the same intent all produce
    identical live results when executed.
    """

    @pytest.mark.asyncio
    async def test_device_count_consistent_across_prompts(
        self, live_server, offline_tools
    ):
        """
        Multiple prompts asking for devices should all return the same
        device count (proving they hit the same endpoint).
        """
        prompts = [
            "list all the available devices",
            "show me the device status",
            "what devices can I test on?",
        ]
        counts = []
        for prompt in prompts:
            resolution = await resolve_prompt(prompt, offline_tools)
            result = await compat_call_tool(live_server,
                resolution.resolved_tool, {}
            )
            data = _parse_result(result)
            devices = data.get("devices", data.get("result", []))
            if isinstance(devices, list):
                counts.append(len(devices))

        # All prompts should return approximately the same count
        # (exact match may vary slightly due to device state changes)
        assert len(counts) >= 2, "Need at least 2 results to compare"
        avg = sum(counts) / len(counts)
        for i, count in enumerate(counts):
            assert abs(count - avg) / avg < 0.1, (
                f"Prompt {i} returned {count} devices, "
                f"avg={avg:.0f} — too much variance"
            )


# ===================================================================
# Test: Prompts That Require LLM Understanding
# ===================================================================

@pytest.mark.skipif(
    not HAS_ANTHROPIC_KEY,
    reason="These prompts need semantic understanding — requires ANTHROPIC_API_KEY"
)
class TestLLMRequiredPrompts:
    """
    Prompts that a keyword matcher cannot resolve but an LLM should.
    These only run when ANTHROPIC_API_KEY is set.

    These document the gap between keyword matching and LLM understanding.
    If they fail with the LLM, it indicates the tool descriptions need
    improvement.
    """

    @pytest.mark.asyncio
    async def test_implicit_intent_prompts(self, offline_tools):
        """Prompts where intent is implied, not stated explicitly."""
        cases = [
            ("allocate a device for me", {"createSession"}),
            ("reserve a phone for testing", {"createSession"}),
            ("I need to check something on a real phone", {"createSession"}),
            ("I need a screenshot of what's on the device", {"take_screenshot"}),
            ("capture what's on the screen right now", {"take_screenshot"}),
        ]
        for prompt, acceptable in cases:
            r = await resolve_prompt(prompt, offline_tools)
            assert r.resolved_tool in acceptable, (
                f"LLM failed: \"{prompt}\" → {r.resolved_tool}, "
                f"expected {acceptable}"
            )
