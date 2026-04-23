"""
Dynamic OpenAPI-driven MCP server for Sauce Labs RDC v2 API.

Auto-generates MCP tools from the official OpenAPI spec at startup using
FastMCPOpenAPI, so the tool set is always up-to-date without code changes.

A few endpoints are excluded from auto-generation (see EXCLUDED_PATHS) and
hand-written instead:
  - pushFile / takeScreenshot / pullFile: binary/multipart payloads.
  - proxy/http/...: collapsed into a single `proxy_http` tool that takes
    the HTTP verb as a parameter, instead of six separate tools.
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
# and deleteSession).
EXCLUDED_OPERATION_IDS = {
    "createSession",
    "getSession",
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

    def _resolve(node):
        if isinstance(node, list):
            return [_resolve(item) for item in node]
        if not isinstance(node, dict):
            return node

        # Merge local $defs into the resolution scope
        local_defs = node.get("$defs", defs)

        if "$ref" in node:
            ref_path = node["$ref"]  # e.g. "#/$defs/TunnelConfiguration"
            if ref_path.startswith("#/$defs/"):
                ref_name = ref_path[len("#/$defs/"):]
                resolved = local_defs.get(ref_name, {})
                # Merge any sibling keys (e.g. "type" next to "$ref")
                merged = {k: v for k, v in node.items()
                          if k not in ("$ref", "$defs")}
                merged.update(_resolve(resolved))
                return merged
            # Unresolvable $ref — drop it, keep siblings
            return {k: _resolve(v) for k, v in node.items()
                    if k not in ("$ref", "$defs")}

        return {k: _resolve(v) for k, v in node.items() if k != "$defs"}

    resolved = _resolve(schema)
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

    # --- Manual tools for excluded binary endpoints ---

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
