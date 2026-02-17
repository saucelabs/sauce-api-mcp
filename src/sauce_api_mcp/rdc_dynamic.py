"""
Dynamic OpenAPI-driven MCP server for Sauce Labs RDC v2 API.

Auto-generates MCP tools from the official OpenAPI spec at startup using
FastMCPOpenAPI, so the tool set is always up-to-date without code changes.

Three binary/multipart endpoints (pushFile, takeScreenshot, pullFile) are
excluded from auto-generation and implemented manually.
"""

import base64
import os
import sys
import logging
from typing import Any, Dict, Optional

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

# Paths that involve binary/multipart and can't be auto-generated
EXCLUDED_PATHS = {
    "/sessions/{sessionId}/device/pushFile",
    "/sessions/{sessionId}/device/takeScreenshot",
    "/sessions/{sessionId}/device/pullFile",
}


def fetch_openapi_spec_sync(spec_url: str) -> dict:
    """Fetch and parse the OpenAPI YAML spec from a URL or local file."""
    if spec_url.startswith(("http://", "https://")):
        response = httpx.get(spec_url, timeout=30.0)
        response.raise_for_status()
        return yaml.safe_load(response.text)
    else:
        with open(spec_url) as f:
            return yaml.safe_load(f)


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
    """Exclude binary/multipart endpoints from auto-generation."""
    if route.path in EXCLUDED_PATHS:
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

    client = httpx.AsyncClient(
        base_url=base_url,
        auth=httpx.BasicAuth(username, access_key),
        params={"ai": "rdc_openapi_mcp"},
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
    async def push_file_to_device(
        sessionId: str,
        local_file_path: str,
        device_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Push a local file to a device in an active session.

        :param sessionId: The id of the device session.
        :param local_file_path: Path to the local file to upload.
        :param device_path: Optional target path on the device.
        """
        if not os.path.exists(local_file_path):
            return {"error": f"File not found: {local_file_path}"}

        with open(local_file_path, "rb") as f:
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
            Defaults to the filename in the current directory.
        """
        response = await client.post(
            f"sessions/{sessionId}/device/pullFile",
            json={"filePath": device_file_path},
        )
        if response.status_code >= 400:
            return {
                "error": f"Pull file failed: {response.status_code}",
                "details": response.text,
            }

        if local_save_path is None:
            local_save_path = os.path.basename(device_file_path)

        with open(local_save_path, "wb") as f:
            f.write(response.content)

        return {
            "saved_to": os.path.abspath(local_save_path),
            "size": len(response.content),
        }

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
