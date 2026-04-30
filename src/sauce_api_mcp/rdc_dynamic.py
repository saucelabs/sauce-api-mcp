"""
Dynamic OpenAPI-driven MCP server for Sauce Labs RDC v2 API.

Auto-generates MCP tools from the official OpenAPI spec at startup using
FastMCPOpenAPI, so the tool set is always up-to-date without code changes.

A few endpoints are excluded from auto-generation (see EXCLUDED_PATHS and
EXCLUDED_OPERATION_IDS) and hand-written instead:
  - pushFile / takeScreenshot / pullFile: binary/multipart payloads.
  - proxy/http/...: collapsed into a single `proxy_http` tool that takes
    the HTTP verb as a parameter, instead of six separate tools.
  - POST /sessions and GET /sessions/{sessionId}: replaced by a single
    `createSession` tool that creates the session and polls until the
    device is ready, so callers don't have to drive the polling loop.
  - installApp: replaced by a pair of tools (`installApp` +
    `waitForAppInstallation`). `installApp` starts the install and returns
    the installation id; `waitForAppInstallation` polls
    `listAppInstallations` for up to 55s and tells the caller to call it
    again if the install is still pending. App installs can take longer
    than the MCP client's ~60s tool-call ceiling, which is why the wait
    step is a separately callable tool rather than a single blocking call.
"""

import asyncio
import base64
import json as json_mod
import os
import sys
import logging
from typing import Any, Dict, Literal, Optional

import httpx
import yaml

from fastmcp.server.openapi import FastMCPOpenAPI, MCPType
from fastmcp.utilities.openapi import HTTPRoute

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format=">>>>>>>>>>>>%(levelname)s: %(message)s",
)

DATA_CENTERS = {
    "US_WEST": "https://api.us-west-1.saucelabs.com/rdc/v2/",
    "US_EAST": "https://api.us-east-4.saucelabs.com/rdc/v2/",
    "EU_CENTRAL": "https://api.eu-central-1.saucelabs.com/rdc/v2/",
}

DEFAULT_SPEC_URL = (
    "https://raw.githubusercontent.com/saucelabs/sauce-docs/"
    "refs/heads/main/static/oas/real-device-access-api-spec.yaml"
)

# Paths excluded from auto-generation.
# - pushFile/takeScreenshot/pullFile: binary/multipart, need hand-written tools.
# - proxy/http/...: collapsed into a single `proxy_http` tool below instead of
#   six method-specific tools (proxyGet, proxyPost, proxyPut, proxyDelete,
#   proxyHead, proxyOptions).
# - POST /sessions and GET /sessions/{sessionId}: replaced by a single
#   hand-written `create_session` tool that creates the session and polls the
#   backend until the device is ready (or fails), so callers don't have to
#   drive the polling loop themselves.
EXCLUDED_PATHS = {
    "/sessions/{sessionId}/device/pushFile",
    "/sessions/{sessionId}/device/takeScreenshot",
    "/sessions/{sessionId}/device/pullFile",
    "/sessions/{sessionId}/device/proxy/http/{targetHost}/{targetPort}/{targetPath}",
}

# Operation IDs excluded from auto-generation. Used for endpoints where we want
# to suppress a specific HTTP method on a path while keeping others (e.g. we
# hand-roll POST /sessions and GET /sessions/{sessionId} but keep listSessions
# and deleteSession), and for endpoints whose auto-generated shape we want to
# replace with a richer hand-written version (e.g. installApp, which we wrap
# with a companion waitForAppInstallation tool so callers don't have to drive
# the polling loop themselves).
EXCLUDED_OPERATION_IDS = {
    "createSession",
    "getSession",
    "installApp",
}

# Session polling configuration for the hand-written create_session tool.
# The backend transitions a newly created session through PENDING -> CREATING ->
# ACTIVE. If device allocation fails it transitions to ERRORED. We poll until we
# leave the pre-ready states or the timeout elapses.
#
# Timeout is capped at 55s on purpose: common MCP clients (Claude Desktop in
# particular) enforce a hardcoded ~60s ceiling on tool calls, and we need a few
# seconds of headroom for the final response to make it back through the
# transport before the client gives up on us.
SESSION_POLL_INTERVAL_SECONDS = 2.0
SESSION_POLL_TIMEOUT_SECONDS = 55.0
SESSION_PENDING_STATES = {"PENDING", "CREATING"}

# App installation polling configuration for the hand-written
# waitForAppInstallation tool. The backend reports installation progress via
# listAppInstallations with a per-installation ``status`` that starts at
# PENDING and transitions to FINISHED, LAUNCHING, or ERROR. We poll until the
# status leaves PENDING or the per-call timeout elapses. Same 55s cap as
# session polling: an app install can legitimately take longer than a single
# MCP tool call, so when we hit the deadline we hand control back to the LLM
# with guidance to call the tool again rather than blocking past the client's
# ~60s ceiling.
APP_INSTALL_POLL_INTERVAL_SECONDS = 2.0
APP_INSTALL_POLL_TIMEOUT_SECONDS = 55.0
APP_INSTALL_PENDING_STATES = {"PENDING"}

# Safe directory for file operations (push/pull)
SAFE_FILE_DIR = os.path.join(os.path.expanduser("~"), ".sauce-mcp", "files")


def _safe_json(response: httpx.Response) -> Any:
    """Return the response body as parsed JSON, or fall back to text.

    Some error responses use ``application/problem+json``; others may have no
    JSON body at all (e.g. HTML from a gateway). Callers that just want to
    surface the backend's explanation shouldn't have to care.
    """
    try:
        return response.json()
    except Exception:
        return response.text


def _validate_path(file_path: str) -> str:
    """Validate that a file path resolves within SAFE_FILE_DIR.

    Returns the resolved absolute path if safe, raises ValueError otherwise.
    """
    os.makedirs(SAFE_FILE_DIR, exist_ok=True)
    resolved = os.path.realpath(os.path.join(SAFE_FILE_DIR, os.path.basename(file_path)))
    if not resolved.startswith(os.path.realpath(SAFE_FILE_DIR)):
        raise ValueError(
            f"Path '{file_path}' resolves outside the safe directory. "
            f"Files are restricted to {SAFE_FILE_DIR}"
        )
    return resolved


SPEC_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".sauce-mcp")
SPEC_CACHE_FILE = os.path.join(SPEC_CACHE_DIR, "rdc-access-api-spec.yaml")
MAX_FETCH_RETRIES = 3


def _cache_spec(spec_text: str) -> None:
    """Save spec text to local cache for fallback."""
    try:
        os.makedirs(SPEC_CACHE_DIR, exist_ok=True)
        with open(SPEC_CACHE_FILE, "w") as f:
            f.write(spec_text)
        logging.info("Cached OpenAPI spec to %s", SPEC_CACHE_FILE)
    except OSError as e:
        logging.warning("Failed to cache spec: %s", e)


def _load_cached_spec() -> dict | None:
    """Load spec from local cache if available."""
    if os.path.exists(SPEC_CACHE_FILE):
        try:
            with open(SPEC_CACHE_FILE) as f:
                spec = yaml.safe_load(f)
            logging.info("Loaded cached OpenAPI spec from %s", SPEC_CACHE_FILE)
            return spec
        except Exception as e:
            logging.warning("Failed to load cached spec: %s", e)
    return None


# Response shaping limits
MAX_RESPONSE_ITEMS = int(os.getenv("SAUCE_MCP_MAX_RESPONSE_ITEMS", "100"))


def shape_response(data):
    """Truncate large API responses to stay within LLM context budget."""
    if isinstance(data, list) and len(data) > MAX_RESPONSE_ITEMS:
        return {
            "items": data[:MAX_RESPONSE_ITEMS],
            "truncated": True,
            "total_count": len(data),
            "message": (
                f"Response truncated to {MAX_RESPONSE_ITEMS} of {len(data)} items. "
                "Use filtering parameters to narrow results."
            ),
        }
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list) and len(value) > MAX_RESPONSE_ITEMS:
                data = dict(data)  # shallow copy
                total = len(value)
                data[key] = value[:MAX_RESPONSE_ITEMS]
                data["truncated"] = True
                data["total_count"] = total
                data["message"] = (
                    f"Response truncated to {MAX_RESPONSE_ITEMS} of {total} items. "
                    "Use filtering parameters to narrow results."
                )
                return data
    return data


def fetch_openapi_spec_sync(spec_url: str) -> dict:
    """Fetch and parse the OpenAPI YAML spec from a URL or local file.

    For remote URLs, retries up to MAX_FETCH_RETRIES times and caches
    the spec locally. Falls back to the cached copy if all retries fail.
    """
    if not spec_url.startswith(("http://", "https://")):
        with open(spec_url) as f:
            return yaml.safe_load(f)

    last_error = None
    for attempt in range(1, MAX_FETCH_RETRIES + 1):
        try:
            response = httpx.get(spec_url, timeout=30.0)
            response.raise_for_status()
            spec = yaml.safe_load(response.text)
            _cache_spec(response.text)
            return spec
        except Exception as e:
            last_error = e
            logging.warning(
                "Spec fetch attempt %d/%d failed: %s",
                attempt, MAX_FETCH_RETRIES, e,
            )

    logging.error(
        "All %d fetch attempts failed. Trying cached spec.", MAX_FETCH_RETRIES
    )
    cached = _load_cached_spec()
    if cached is not None:
        return cached

    raise RuntimeError(
        f"Failed to fetch OpenAPI spec from {spec_url} after "
        f"{MAX_FETCH_RETRIES} retries and no cached copy available. "
        f"Last error: {last_error}"
    )


def resolve_refs(schema: dict) -> dict:
    """Recursively resolve $ref references in a JSON Schema, inlining $defs.

    The Claude API does not support $ref/$defs in tool input schemas.
    This function walks the schema tree and replaces every $ref with the
    resolved definition from $defs, then strips $defs from the result.
    """
    if not isinstance(schema, dict):
        return schema

    defs = schema.get("$defs", {})

    # `seen` tracks refs on the current resolution path (not the whole tree),
    # so sibling branches that reference the same $def are still resolved
    # independently. A ref is only "circular" if it reappears on its own path.
    def _resolve(node, seen):
        if isinstance(node, list):
            return [_resolve(item, seen) for item in node]
        if not isinstance(node, dict):
            return node

        # Merge local $defs into the resolution scope
        local_defs = node.get("$defs", defs)

        if "$ref" in node:
            ref_path = node["$ref"]  # e.g. "#/$defs/TunnelConfiguration"
            if ref_path.startswith("#/$defs/"):
                ref_name = ref_path[len("#/$defs/"):]
                if ref_name in seen:
                    logging.warning(
                        "Circular $ref detected at %s; dropping to avoid "
                        "infinite recursion", ref_path
                    )
                    return {k: _resolve(v, seen) for k, v in node.items()
                            if k not in ("$ref", "$defs")}
                resolved = local_defs.get(ref_name, {})
                # Merge any sibling keys (e.g. "type" next to "$ref")
                merged = {k: v for k, v in node.items()
                          if k not in ("$ref", "$defs")}
                merged.update(_resolve(resolved, seen | {ref_name}))
                return merged
            # Unresolvable $ref — drop it, keep siblings
            return {k: _resolve(v, seen) for k, v in node.items()
                    if k not in ("$ref", "$defs")}

        return {k: _resolve(v, seen) for k, v in node.items() if k != "$defs"}

    resolved = _resolve(schema, frozenset())
    resolved.pop("$defs", None)
    return resolved


def route_map_fn(route: HTTPRoute, mcp_type: MCPType) -> MCPType | None:
    """Exclude binary/multipart endpoints and hand-rolled operations."""
    if route.path in EXCLUDED_PATHS:
        return MCPType.EXCLUDE
    if getattr(route, "operation_id", None) in EXCLUDED_OPERATION_IDS:
        return MCPType.EXCLUDE
    return None


def _fix_component_schemas(route: HTTPRoute, component) -> None:
    """Post-process each auto-generated component to inline $ref references."""
    if hasattr(component, "parameters") and isinstance(component.parameters, dict):
        component.parameters = resolve_refs(component.parameters)
    if hasattr(component, "output_schema") and isinstance(component.output_schema, dict):
        component.output_schema = resolve_refs(component.output_schema)


# Returned verbatim by the `get_device_log_streaming_instructions` tool.
# __WS_URL__, __OUT_PATH__, and __SESSION_PLACEHOLDER__ are substituted at
# call time so the playbook is copy-pasteable. Kept as a module-level
# constant so the wording is easy to audit and evolve.
_DEVICE_LOG_PLAYBOOK_TEMPLATE = """# Streaming a Sauce Labs device log to a file

You're running in Claude Code and the user wants to watch logs from an app on a Sauce Labs device — probably to diagnose a crash, ANR, startup bug, or other runtime issue. Capture the device's log WebSocket to a file on disk, then query the file with standard tools.

## Do this

Start the recorder as a background Bash task:

```bash
source ~/.zshrc; websocat --basic-auth "$SAUCE_USERNAME:$SAUCE_ACCESS_KEY" --no-close __WS_URL__ writefile:__OUT_PATH__
```

Invoke via the `Bash` tool with `run_in_background: true`. Do not add `&`. Do not pipe stdout with `>`. Do not add `-u` or `-U`.

The file is newline-delimited JSON, one WebSocket message per line. Read with `Read`, search with `grep`, parse with `jq`.

## Why each piece is there (so you can make good calls at the edges)

**`writefile:/abs/path`, not `> file`.**
The Claude Code sandbox blocks the `fcntl(F_SETFL, O_NONBLOCK)` call that websocat issues when its stdout is a redirected regular file. The refused syscall surfaces as `Invalid argument (os error 22)` right after the WebSocket handshake and websocat exits. `writefile:` opens the file with blocking IO — no `fcntl`, no sandbox trip. Same bytes, same destination, different syscalls.

**`--no-close`.**
With `writefile:` as the sink, websocat still runs bidirectionally by default. The reverse direction (file → server) hits instant EOF because a `writefile:` peer has no read side. When any direction finishes, websocat politely sends a WebSocket close frame to the server. Almost every server reciprocates by closing the whole connection — so without this flag you'd get a burst of messages and then silence. `--no-close` suppresses the frame; the server doesn't know, keeps streaming.

**No `-u` / `-U`.**
These keep only one direction of the websocat pipe. Which direction depends on peer-type inference, so they silently break listeners about half the time. Plain bidirectional mode with `--no-close` is simpler and correct for read-only use.

**`run_in_background: true`, not `cmd &`.**
Shell-level backgrounding inside a foreground Bash tool call does not survive: the harness reaps the whole process group when the tool call returns. `run_in_background: true` registers a proper long-lived task with a handle you can monitor or kill across turns.

**`source ~/.zshrc` with `;` not `&&`.**
Shell state doesn't persist between Bash tool calls, so per-call sourcing is how the credentials become visible. zsh completion init can return non-zero harmlessly; `;` ignores that, `&&` would abort before websocat runs. One-time alternative: move the `SAUCE_*` exports to `~/.zshenv` so every non-interactive shell inherits them automatically.

## Query the captured file

Output is newline-delimited JSON at `__OUT_PATH__`. Typical volume is 100–300 lines/second — most of it iOS/Android system chatter, not the app under test. When you're ready to search, call the **`get_device_log_query_tips`** tool for the message-shape reference, app-filtering recipes, and tuned `jq` / `grep` starters. Do not `cat` the whole file into context.

## Stopping

Use the Claude Code background-task panel, kill the task via its handle, or `pkill -f 'websocat.*__SESSION_PLACEHOLDER__'`. The file stays; nothing further writes to it.

## When things go wrong

- **`Invalid argument (os error 22)` right after handshake** → your command lost `writefile:` and picked up `> file` somewhere. Restore `writefile:`.
- **File has a short burst then stops** → you dropped `--no-close`, or added `-u`/`-U`. Put `--no-close` back; remove `-u`/`-U`.
- **Empty file, websocat exits 1 immediately** → `SAUCE_USERNAME` / `SAUCE_ACCESS_KEY` aren't in this Bash call's shell. Confirm with `echo "USER=${SAUCE_USERNAME:+SET, len=${#SAUCE_USERNAME}}"`. If empty, `source ~/.zshrc` in the command or move exports to `~/.zshenv`.
- **`websocat: command not found`** → `brew install websocat` (or platform equivalent), retry.
- **404 on the WebSocket upgrade** → region mismatch between the URL and the region the session was created in.

Do not wrap the recorder in a `while true` reconnect loop unless the user asked for it. For debug-loop work, a single session plus the option to relaunch is simpler, doesn't mask real disconnects, and avoids runaway reconnect spam filling the file.
"""


def _render_device_log_playbook(
    base_url: str,
    session_id: Optional[str],
) -> str:
    """Fill the playbook template with WS URL, output path, and session id."""
    ws_base = base_url.replace("https://", "wss://").rstrip("/")
    session_placeholder = session_id if session_id else "<session_id>"
    ws_url = f"{ws_base}/socket/companion/{session_placeholder}"
    out_path = f"/tmp/sauce-device-logs/{session_placeholder}.ndjson"
    return (
        _DEVICE_LOG_PLAYBOOK_TEMPLATE
        .replace("__WS_URL__", ws_url)
        .replace("__OUT_PATH__", out_path)
        .replace("__SESSION_PLACEHOLDER__", session_placeholder)
    )


# Returned verbatim by the `get_device_log_query_tips` tool. Kept separate
# from the streaming playbook because the two are consulted at different
# times (streaming: one-shot setup; querying: iterative debugging) and
# evolve on different schedules.
_DEVICE_LOG_QUERY_TIPS = """# Debugging device logs captured via get_device_log_streaming_instructions

The file is newline-delimited JSON: one WebSocket message per line, from a Sauce Labs device session. It's firehose-noisy — typically 100–300 messages/second, most from iOS/Android system processes, not the app under test. Filter first, then look.

## Message shape to rely on

Each `device.log.message` record has stable outer fields — use them, don't regex the raw line:

| Field | Type | Use |
|---|---|---|
| `type` | `"device.log.message"` | Filter out `device.state.update` and `device.har.entry`. |
| `level` | `"INFO"` \\| `"ERROR"` | Coarse triage; outer `level` only has these two values in practice. |
| `processId` | int | Narrow to the app once you know its pid. |
| `timestamp` | `"YYYY-MM-DD HH:MM:SS.000"` (device clock, second granularity) | Time-window filter. |
| `message` | string | Actual content. Internal format: `TS\\tLEVEL:\\tPROC(SUBSYS)[PID] <SEV>: body`. |

Two other message types show up:

- `device.state.update` — session heartbeat, `value.state` is `"ONLINE"` / similar. Confirms the session was alive during a window.
- `device.har.entry` — network HAR entries under `value.event.{request,response,timings}`. Useful for reconstructing what the app called over the network.

The **iOS severity** embedded in `.message` (`<Error>`, `<Fault>`, `<Notice>`, `<Default>`, `<Debug>`) is richer than the outer `level` and not always aligned with it. iOS `<Error>` lines sometimes arrive with outer `level: "INFO"`. Match both if you care about all errors.

## Start narrow, widen only if empty

Biggest single lever: **filter by the app name in the message body**. Most volume is system chatter; the app is a small fraction.

```bash
jq -c 'select(.type=="device.log.message" and (.message | contains("AppName")))' FILE | head -200
```

For iOS, `AppName` matches the process-name prefix shown in the log (e.g. `FakeCounterApp(UIKitCore)[1290]`). For Android, use the package name or tag.

Once you spot the app's pid, pivot to pid for a full process trace:

```bash
jq -c 'select(.processId == 1290)' FILE | head -200
```

## Common recipes

```bash
# Outer-level errors
jq -c 'select(.level=="ERROR")' FILE | head -50

# iOS-level errors and faults (catches what outer-level misses)
jq -c 'select(.message | test("<Error>|<Fault>"))' FILE | head -50

# Anything crash-shaped
jq -c 'select(.message | test("(?i)crash|fatal|exception|abort|sigabrt|sigsegv"))' FILE

# Time window (device clock)
jq -c 'select(.timestamp >= "2026-04-24 03:21:25" and .timestamp <= "2026-04-24 03:21:35")' FILE

# Network requests the app made
jq -c 'select(.type=="device.har.entry") | .value.event.request | {method, url, status: .response.status}' FILE

# Device state heartbeats (did the session stay online?)
jq -c 'select(.type=="device.state.update")' FILE

# Strip the duplicated TS/LEVEL prefix for readability
jq -r 'select(.type=="device.log.message") | .message' FILE | sed -E 's/^[0-9-]+ [0-9:.]+[[:space:]]+[A-Z]+:[[:space:]]+//'
```

## Noise to strip

- `<decode: bad range for [%p] got [...]>` — os_log couldn't decode a pointer format arg. Not a real error. Drop with `grep -v '<decode: bad range'` or `jq 'select(.message | test("<decode: bad range") | not)'`.
- Kernel (`pid 0`), `wifid`, `remoted`, `apsd`-type system processes dominate volume. If you're debugging app behavior, prefer a positive match on the app name over trying to enumerate noisy pids.

## Timestamps: things to know

- `.timestamp` is the **device clock** in the device's timezone (Sauce devices are often on LA time), not your host wall clock. Don't correlate directly; correlate via file ordering or the first `device.state.update`.
- Granularity is **one second** (millis always `.000`). Adjacent messages in the same second are ordered by file position, not timestamp.

## If the file is larger than you want to scan

- Check size first: `wc -l FILE`. Over ~50k lines, narrow before working:
  ```bash
  jq -c 'select(.message | contains("AppName"))' FILE > /tmp/narrowed.ndjson
  ```
  then work from the narrowed file.
- Always `| head -N` at every step. Never pipe the whole file into context.
- If the user knows roughly when the bug happened, a time-window filter is the cheapest first cut.
"""


def create_server(
    spec: dict,
    access_key: str,
    username: str,
    region: str = "US_WEST",
) -> FastMCPOpenAPI:
    """Create the FastMCPOpenAPI server with manual tools for binary endpoints."""
    base_url = DATA_CENTERS[region.upper()]

    async def _inject_mcp_headers(request: httpx.Request) -> None:
        request.headers["X-SAUCE-MCP-SERVER"] = "rdc_dynamic"
        request.headers["X-SAUCE-MCP-TRANSPORT"] = "stdio"
        request.headers["X-SAUCE-MCP-USER"] = username

    async def _shape_response(response: httpx.Response) -> None:
        """Intercept large responses and truncate before they reach the LLM."""
        await response.aread()
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type:
            return  # Don't touch binary responses (screenshots, files)
        try:
            data = response.json()
            shaped = shape_response(data)
            if shaped is not data:
                response._content = json_mod.dumps(shaped).encode("utf-8")
        except Exception:
            pass  # If parsing fails, let it through unchanged

    client = httpx.AsyncClient(
        base_url=base_url,
        auth=httpx.BasicAuth(username, access_key),
        params={"ai": "rdc_openapi_mcp"},
        event_hooks={
            "request": [_inject_mcp_headers],
            "response": [_shape_response],
        },
    )

    server = FastMCPOpenAPI(
        openapi_spec=spec,
        client=client,
        name="SauceLabsRDCDynamic",
        route_map_fn=route_map_fn,
        mcp_component_fn=_fix_component_schemas,
    )

    # --- Manual tools for excluded endpoints ---

    @server.tool()
    async def createSession(
        os: Literal["android", "ios"],
        deviceName: Optional[str] = None,
        sessionDuration: Optional[str] = None,
        tunnelName: Optional[str] = None,
        tunnelOwner: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Allocate a real device and return an ACTIVE session ready to use.

        This is the one-shot entry point for starting a real-device session.
        The returned payload contains the ``id``, ``state``, and the URLs
        needed to drive the device (Appium endpoint, live view, websocket
        channels). Use that ``id`` as ``sessionId`` for every subsequent
        tool call, and close it with ``deleteSession`` when finished.

        Mapping the user's request to parameters:

        - The user's device brand or model implies ``os``. Apple hardware
          (``iPhone``, ``iPad``) is always ``"ios"``. Everything else sold
          as a phone or tablet — ``Samsung``, ``Google`` / ``Pixel``,
          ``OnePlus``, ``Xiaomi``, ``Huawei``, ``Motorola``, ``Nokia``,
          ``Sony``, ``LG``, ``Oppo``, ``Vivo``, etc. — is ``"android"``.
          Set ``os`` from the brand when the user names one; only ask the
          user if the request is truly ambiguous (e.g. "a phone").
        - When the user names a brand or family but not a specific model,
          pass a regex in ``deviceName`` that matches any device in that
          family. The backend treats ``deviceName`` as a regex and matches
          it against both the descriptor and the device name, so a broad
          pattern with ``.*`` on each side is the right shape.

        Worked examples:

        - "Open a session on a Samsung device" →
          ``os="android"``, ``deviceName=".*Samsung.*"``.
        - "I need a Pixel" → ``os="android"``, ``deviceName=".*Pixel.*"``.
        - "Start an iPhone 15 session" →
          ``os="ios"``, ``deviceName=".*iPhone.?15.*"``.
        - "Any iOS device is fine" → ``os="ios"``, no ``deviceName``.

        IMPORTANT: ``os`` is required. If the user hasn't named a brand,
        model, or platform at all, stop and ask them — never guess a
        default. Picking a random OS may allocate the wrong device and
        consume the user's quota.

        :param os: Target platform. Must be ``"android"`` or ``"ios"``.
            Required — infer from the brand/model the user named, or ask
            the user if the request is ambiguous.
        :param deviceName: Optional device selector, treated as a regex
            matched against both the device's descriptor and its display
            name. Use a broad regex (``.*<brand>.*``) when the user named
            a brand or family, and a tighter one when they named a
            specific model. Omit this entirely if the user is happy with
            any device of the requested OS. Examples: ``".*Samsung.*"``,
            ``".*Pixel_[78].*"``, ``"iPhone_16_real"``.
        :param sessionDuration: Optional ISO-8601 duration that caps how
            long the session may run. Default 6h, max 24h. Examples:
            ``"PT30M"``, ``"PT2H"``.
        :param tunnelName: Optional Sauce Connect tunnel name. Pass this to
            route device traffic through a tunnel.
        :param tunnelOwner: Optional tunnel owner username. Only needed when
            using a tunnel owned by a different user than the caller.
            Ignored unless ``tunnelName`` is also provided.

        On success returns the Session object (state ``ACTIVE``). On failure
        returns a dict with an ``error`` key: the device couldn't be
        allocated (the backend's explanation is included), or allocation is
        still pending after the internal timeout (suggest retrying or
        choosing a different device).
        """
        device: Dict[str, Any] = {"os": os}
        if deviceName:
            device["deviceName"] = deviceName

        configuration: Dict[str, Any] = {}
        if sessionDuration:
            configuration["sessionDuration"] = sessionDuration
        if tunnelName:
            tunnel: Dict[str, Any] = {"name": tunnelName}
            if tunnelOwner:
                tunnel["owner"] = tunnelOwner
            configuration["tunnel"] = tunnel

        payload: Dict[str, Any] = {"device": device}
        if configuration:
            payload["configuration"] = configuration

        create_response = await client.post("sessions", json=payload)
        if create_response.status_code >= 400:
            return {
                "error": f"Create session failed: {create_response.status_code}",
                "details": _safe_json(create_response),
            }

        created = create_response.json()
        session_id = created.get("id")
        if not session_id:
            return {
                "error": "Create session response missing session id",
                "details": created,
            }

        # Poll GET /sessions/{sessionId} until the session leaves the
        # PENDING/CREATING states, or we hit the timeout.
        loop = asyncio.get_event_loop()
        deadline = loop.time() + SESSION_POLL_TIMEOUT_SECONDS
        last_session: Dict[str, Any] = created
        last_state: Optional[str] = created.get("state")

        while last_state in SESSION_PENDING_STATES:
            if loop.time() >= deadline:
                # Cancel the still-pending allocation so we don't leave an
                # orphaned session draining the user's quota while they
                # decide what to do next. Record whether cleanup succeeded
                # so the caller can surface that if needed.
                cancellation: Dict[str, Any] = {"attempted": True}
                try:
                    cancel_response = await client.delete(
                        f"sessions/{session_id}"
                    )
                    cancellation["status"] = cancel_response.status_code
                    cancellation["succeeded"] = (
                        cancel_response.status_code < 400
                    )
                    if cancel_response.status_code >= 400:
                        cancellation["details"] = _safe_json(cancel_response)
                except Exception as exc:
                    cancellation["succeeded"] = False
                    cancellation["error"] = str(exc)

                return {
                    "error": (
                        "Device allocation timed out after "
                        f"{int(SESSION_POLL_TIMEOUT_SECONDS)} seconds. "
                        "Explain to the user that Sauce Labs could not "
                        "allocate a device in time and the pending "
                        "allocation has been canceled. Offer them two "
                        "choices: (1) try the same request again, or "
                        "(2) change the allocation prompt — a different "
                        "os, a broader deviceName regex, or no deviceName "
                        "at all to pick any available device. Do not "
                        "retry automatically without asking."
                    ),
                    "reason": "allocation_timeout",
                    "sessionId": session_id,
                    "state": last_state,
                    "timeoutSeconds": int(SESSION_POLL_TIMEOUT_SECONDS),
                    "cancellation": cancellation,
                }

            await asyncio.sleep(SESSION_POLL_INTERVAL_SECONDS)

            get_response = await client.get(f"sessions/{session_id}")
            if get_response.status_code >= 400:
                return {
                    "error": (
                        f"Polling session {session_id} failed: "
                        f"{get_response.status_code}"
                    ),
                    "sessionId": session_id,
                    "details": _safe_json(get_response),
                }
            last_session = get_response.json()
            last_state = last_session.get("state")

        if last_state == "ERRORED":
            # Surface whatever the backend told us about the failure. The
            # Session schema doesn't formally carry an error field, but real
            # responses do include one — preserve the whole payload so the
            # caller sees the backend's explanation verbatim.
            error_detail = (
                last_session.get("error")
                or last_session.get("detail")
                or last_session.get("message")
                or "Device could not be allocated. See details for the "
                   "backend response."
            )
            return {
                "error": f"Session {session_id} failed to start: {error_detail}",
                "sessionId": session_id,
                "state": last_state,
                "details": last_session,
            }

        return last_session

    @server.tool()
    async def installApp(
        sessionId: str,
        app: str,
        enableInstrumentation: bool = True,
        launchAfterInstall: Optional[bool] = None,
        features: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Any]:
        """
        Start installing an app on the device in a session, optionally
        launching it once the install completes.

        This kicks off the install asynchronously on the backend and returns
        as soon as Sauce Labs has accepted the request. Installation itself
        can easily take longer than a single MCP tool call — sometimes more
        than a minute — so this tool does NOT wait for the install to
        finish. Instead it returns the ``installationId`` and a pointer to
        the companion ``waitForAppInstallation`` tool, which polls for
        progress in bounded chunks.

        **Preferred way to install-and-launch.** If the user asks to
        install and then launch the app ("install and open it", "install
        and run it", "install and launch", "install this build and start
        it up", etc.), call THIS tool with ``launchAfterInstall=True``.
        Do NOT install first and then call the ``launchApp`` tool as a
        second step — the backend launches the app as part of the install
        flow when you set this flag, which is faster and avoids race
        conditions between install completion and launch. Only fall back
        to ``launchApp`` when the user wants to launch an app that is
        already installed, or re-launch it after it was closed.

        Typical flow:

        1. Call ``installApp`` with the session id and app reference. Set
           ``launchAfterInstall=True`` if the user wants the app to start
           running after install.
        2. If the returned ``status`` is already ``FINISHED``, ``LAUNCHING``,
           or ``ERROR``, the install resolved synchronously and you're done.
        3. Otherwise (``status`` is ``PENDING``), call
           ``waitForAppInstallation`` with the returned ``sessionId`` and
           ``installationId`` and keep calling it until it returns a
           non-pending status.

        :param sessionId: The id of the active device session to install
            the app into.
        :param app: Reference to the app in Sauce Labs App Storage, e.g.
            ``"storage:filename=myapp.apk"`` or
            ``"storage:<uuid>"``. Required.
        :param enableInstrumentation: Enable app instrumentation (includes
            app re-signing on iOS). Required for iOS cloud devices and
            unlocks advanced features (network capture, image injection,
            biometrics interception, etc.) on both platforms. **Defaults
            to True and should almost always stay True.** Only pass
            ``False`` if the user has explicitly asked to disable
            instrumentation for this app — never flip it off on your own
            initiative, even if the install fails, because disabling it
            on iOS will typically break installation outright.
        :param launchAfterInstall: If ``True``, the app launches
            automatically once installation completes. Set this to
            ``True`` whenever the user's request implies they want the
            app running after install (install-and-launch, install-and-
            open, install-and-run, etc.) — prefer this over a follow-up
            ``launchApp`` call. Defaults to ``False`` on the backend when
            omitted.
        :param features: Optional per-feature toggles. Accepts any of:
            ``networkCapture``, ``deviceVitals``, ``imageInjection``,
            ``biometricsInterception``, ``bypassScreenshotRestriction``,
            ``errorReporting``. All default to ``False`` on the backend.

        On success returns a dict with at least ``installationId``,
        ``status``, ``app``, and ``sessionId`` (the latter echoed so the
        caller has everything needed to call ``waitForAppInstallation``).
        When ``status`` is ``PENDING``, ``next_action`` points at the wait
        tool. On failure returns a dict with an ``error`` key.
        """
        # Always include enableInstrumentation on the wire so our tool-side
        # default (True) wins over any backend default drift. The LLM can
        # still override it to False, but only when the user explicitly
        # asks — see the docstring above.
        payload: Dict[str, Any] = {
            "app": app,
            "enableInstrumentation": enableInstrumentation,
        }
        if launchAfterInstall is not None:
            payload["launchAfterInstall"] = launchAfterInstall
        if features:
            payload["features"] = features

        response = await client.post(
            f"sessions/{sessionId}/device/installApp",
            json=payload,
        )
        if response.status_code >= 400:
            return {
                "error": f"Install app failed: {response.status_code}",
                "sessionId": sessionId,
                "details": _safe_json(response),
            }

        installation = response.json() if response.content else {}
        installation_id = installation.get("installationId")
        status = installation.get("status")

        result: Dict[str, Any] = {
            "sessionId": sessionId,
            **installation,
        }

        if status in APP_INSTALL_PENDING_STATES and installation_id:
            result["next_action"] = {
                "tool": "waitForAppInstallation",
                "arguments": {
                    "sessionId": sessionId,
                    "installationId": installation_id,
                },
                "message": (
                    "Installation is still PENDING. Call "
                    "waitForAppInstallation with the sessionId and "
                    "installationId above to wait for it to finish. "
                    "App installs can take longer than 60 seconds, so "
                    "waitForAppInstallation may ask you to call it again "
                    "— keep calling until status is no longer PENDING."
                ),
            }

        return result

    @server.tool()
    async def waitForAppInstallation(
        sessionId: str,
        installationId: str,
    ) -> Dict[str, Any]:
        """
        Poll an in-progress app installation until it leaves the PENDING
        state, or return a "call me again" hint if the per-call budget
        runs out.

        Use this after ``installApp`` returns a PENDING status. This tool
        polls ``listAppInstallations`` on the session every couple of
        seconds looking for the installation with the given
        ``installationId``. It returns as soon as that installation's
        ``status`` transitions to ``FINISHED``, ``LAUNCHING``, or
        ``ERROR``. If the budget (55s — short of the MCP client's ~60s
        tool-call ceiling) elapses while the status is still ``PENDING``,
        the tool returns with ``status: "PENDING"`` and a ``next_action``
        pointing back at itself; when you see that, call
        ``waitForAppInstallation`` again with the same arguments. App
        installations can legitimately take several minutes, so multiple
        iterations are expected for large apps.

        :param sessionId: The id of the device session that owns the
            installation.
        :param installationId: The installation id returned by
            ``installApp``.

        On completion returns the full installation record (at minimum
        ``installationId``, ``app``, ``status``) plus ``sessionId``.
        When status is ``ERROR`` the ``error`` key is also set so the
        caller can surface the failure directly. On timeout returns the
        last observed installation record with ``status: "PENDING"`` and
        a ``next_action`` instructing the LLM to call this tool again.
        On API failure returns a dict with an ``error`` key.
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + APP_INSTALL_POLL_TIMEOUT_SECONDS
        last_installation: Optional[Dict[str, Any]] = None
        last_status: Optional[str] = "PENDING"

        # Poll until status leaves PENDING or we run out of time. We check
        # the status AFTER the request so we always observe at least one
        # fresh snapshot — useful if the install completed between the
        # caller's previous call and now.
        while True:
            response = await client.post(
                f"sessions/{sessionId}/device/listAppInstallations",
            )
            if response.status_code >= 400:
                return {
                    "error": (
                        f"Listing app installations failed: "
                        f"{response.status_code}"
                    ),
                    "sessionId": sessionId,
                    "installationId": installationId,
                    "details": _safe_json(response),
                }

            body = response.json() if response.content else {}
            installations = body.get("appInstallations") or []
            match = next(
                (
                    item
                    for item in installations
                    if item.get("installationId") == installationId
                ),
                None,
            )

            if match is None:
                return {
                    "error": (
                        f"Installation {installationId} not found for "
                        f"session {sessionId}. It may have been cleaned "
                        "up by the backend, or the id is wrong."
                    ),
                    "sessionId": sessionId,
                    "installationId": installationId,
                }

            last_installation = match
            last_status = match.get("status")

            if last_status not in APP_INSTALL_PENDING_STATES:
                break

            if loop.time() >= deadline:
                # Ran out of budget for this call. Hand control back to
                # the LLM with a directive to call us again — the install
                # is still progressing on the backend, we just can't hold
                # the MCP channel open any longer.
                return {
                    "sessionId": sessionId,
                    "installationId": installationId,
                    **(last_installation or {}),
                    "status": last_status or "PENDING",
                    "timeoutSeconds": int(APP_INSTALL_POLL_TIMEOUT_SECONDS),
                    "next_action": {
                        "tool": "waitForAppInstallation",
                        "arguments": {
                            "sessionId": sessionId,
                            "installationId": installationId,
                        },
                        "message": (
                            "Installation is still PENDING after "
                            f"{int(APP_INSTALL_POLL_TIMEOUT_SECONDS)}s. "
                            "Call waitForAppInstallation again with the "
                            "same sessionId and installationId. Keep "
                            "calling until status is no longer PENDING."
                        ),
                    },
                }

            await asyncio.sleep(APP_INSTALL_POLL_INTERVAL_SECONDS)

        result: Dict[str, Any] = {
            "sessionId": sessionId,
            **(last_installation or {}),
        }

        if last_status == "ERROR":
            # Surface a top-level ``error`` so the caller doesn't have to
            # introspect status to realize the install failed. Preserve
            # whatever the backend reported under ``details``.
            error_detail = (
                (last_installation or {}).get("error")
                or (last_installation or {}).get("detail")
                or (last_installation or {}).get("message")
                or "App installation failed. See details for the backend response."
            )
            result["error"] = (
                f"Installation {installationId} failed: {error_detail}"
            )

        return result

    @server.tool()
    async def push_file_to_device(
        sessionId: str,
        local_file_path: str,
        device_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Push a local file to a device in an active session.

        :param sessionId: The id of the device session.
        :param local_file_path: Path to the local file to upload.
            Must be within ~/.sauce-mcp/files/ for security.
        :param device_path: Optional target path on the device.
        """
        try:
            safe_path = _validate_path(local_file_path)
        except ValueError as e:
            return {"error": str(e)}

        if not os.path.exists(safe_path):
            return {"error": f"File not found: {safe_path}"}

        with open(safe_path, "rb") as f:
            files = {"file": (os.path.basename(local_file_path), f)}
            data: Dict[str, str] = {}
            if device_path:
                data["filePath"] = device_path
            response = await client.post(
                f"sessions/{sessionId}/device/pushFile",
                files=files,
                data=data,
            )

        if response.status_code >= 400:
            return {
                "error": f"Push file failed: {response.status_code}",
                "details": response.text,
            }
        return response.json()

    @server.tool()
    async def take_screenshot(sessionId: str) -> Dict[str, Any]:
        """
        Take a screenshot of the device screen. Returns the image as
        a base64-encoded PNG string.

        :param sessionId: The id of the device session.
        """
        response = await client.post(
            f"sessions/{sessionId}/device/takeScreenshot",
        )
        if response.status_code >= 400:
            return {
                "error": f"Screenshot failed: {response.status_code}",
                "details": response.text,
            }
        return {
            "content": base64.b64encode(response.content).decode("utf-8"),
            "encoding": "base64",
            "content_type": response.headers.get("content-type", "image/png"),
            "size": len(response.content),
        }

    @server.tool()
    async def pull_file_from_device(
        sessionId: str,
        device_file_path: str,
        local_save_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Pull a file from a device in an active session and save it locally.

        :param sessionId: The id of the device session.
        :param device_file_path: Path of the file on the device.
        :param local_save_path: Optional local path to save the file.
            Defaults to the filename in ~/.sauce-mcp/files/.
        """
        try:
            safe_path = _validate_path(
                local_save_path if local_save_path else device_file_path
            )
        except ValueError as e:
            return {"error": str(e)}

        response = await client.post(
            f"sessions/{sessionId}/device/pullFile",
            json={"filePath": device_file_path},
        )
        if response.status_code >= 400:
            return {
                "error": f"Pull file failed: {response.status_code}",
                "details": response.text,
            }

        with open(safe_path, "wb") as f:
            f.write(response.content)

        return {
            "saved_to": safe_path,
            "size": len(response.content),
        }

    @server.tool()
    async def proxy_http(
        sessionId: str,
        method: str,
        targetHost: str,
        targetPort: str,
        targetPath: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send an HTTP request from the device under test to a target host,
        tunneled through the Sauce Labs device proxy. Use this to reach
        backends, staging APIs, or local services from the device's network
        context during a session.

        :param sessionId: The id of the active device session.
        :param method: HTTP verb. One of: GET, POST, PUT, DELETE, HEAD, OPTIONS.
        :param targetHost: Hostname or IP the device should connect to.
        :param targetPort: TCP port on the target host (as a string).
        :param targetPath: Request path on the target, without a leading slash.
        :param body: JSON-serializable request body. Only sent for POST and PUT;
            ignored for other verbs.
        """
        verb = method.upper()
        allowed = {"GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"}
        if verb not in allowed:
            return {
                "error": f"Unsupported method '{method}'. "
                         f"Use one of {sorted(allowed)}."
            }

        endpoint = (
            f"sessions/{sessionId}/device/proxy/http/"
            f"{targetHost}/{targetPort}/{targetPath}"
        )
        kwargs: Dict[str, Any] = {}
        if body is not None and verb in {"POST", "PUT"}:
            kwargs["json"] = body

        response = await client.request(verb, endpoint, **kwargs)

        if response.status_code >= 400:
            return {
                "error": f"Proxy {verb} failed: {response.status_code}",
                "details": response.text,
            }

        # HEAD has no body by spec; surface status + headers instead.
        if verb == "HEAD":
            return {
                "status": response.status_code,
                "headers": dict(response.headers),
            }

        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            return response.json()
        return {"status": response.status_code, "text": response.text}

    @server.tool()
    async def get_device_log_streaming_instructions(
        sessionId: Optional[str] = None,
    ) -> str:
        """
        Return a ready-to-use playbook for streaming a device session's log
        WebSocket to a local file on the user's machine, so the logs can be
        grepped, tailed, and parsed with standard Unix tools.

        Use whenever the user wants to debug an app running on a Sauce Labs
        device, asks to inspect/tail/capture/record device logs, is
        investigating a crash, ANR, hang, or runtime bug, or mentions watching
        logcat or os_log output from a device session. The playbook covers the
        exact command to run, why naive setups (shell `>` redirect, `&`
        backgrounding, `-u` flag) fail inside Claude Code's sandbox, and how
        to query the captured file.

        :param sessionId: Optional session ID from createSession. If provided,
            the returned command is pre-filled with it; if omitted, the
            command contains a `<session_id>` placeholder.
        """
        return _render_device_log_playbook(base_url, sessionId)

    @server.tool()
    async def get_device_log_query_tips() -> str:
        """
        Return practical guidance for searching a device-log NDJSON file
        captured via get_device_log_streaming_instructions: the message-shape
        reference, app-name filtering recipes, and tuned jq/grep starter
        queries.

        Use whenever the user wants to inspect, grep, tail, filter, or
        otherwise make sense of the captured log file — for example when
        hunting a crash, ANR, error, or specific event, narrowing to the app
        under test, extracting HAR entries, or reducing a large file to a
        workable slice. The file is firehose-noisy (100-300 msg/sec, mostly
        system chatter), so consulting this tool before searching avoids
        dumping the whole file into context and helps zero in on app signal.
        """
        return _DEVICE_LOG_QUERY_TIPS

    return server


def check_stdio_is_not_tty() -> bool:
    """Check if running in proper MCP environment."""
    if sys.stdin.isatty() or sys.stdout.isatty() or sys.stderr.isatty():
        print(
            "Error: This server is not meant to be run interactively.",
            file=sys.stderr,
        )
        return False
    return True


def main():
    """Main entry point for the dynamic RDC MCP server."""
    if not check_stdio_is_not_tty():
        sys.exit(1)

    access_key = os.getenv("SAUCE_ACCESS_KEY")
    if not access_key:
        raise ValueError("SAUCE_ACCESS_KEY environment variable is not set.")

    username = os.getenv("SAUCE_USERNAME")
    if not username:
        raise ValueError("SAUCE_USERNAME environment variable is not set.")

    region = os.getenv("SAUCE_REGION", "US_WEST")
    spec_url = os.getenv("RDC_OPENAPI_SPEC_URL", DEFAULT_SPEC_URL)

    logging.info("Fetching OpenAPI spec from %s", spec_url)
    spec = fetch_openapi_spec_sync(spec_url)
    logging.info("Loaded %d paths from OpenAPI spec", len(spec.get("paths", {})))

    server = create_server(spec, access_key, username, region)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
