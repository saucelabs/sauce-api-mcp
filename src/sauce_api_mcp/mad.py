"""MCP server for Sauce Labs Mobile App Distribution (MAD / TestFairy).

Unlike the core Sauce Labs API, every MAD customer runs on their own
instance (e.g. https://acme.testfairy.com), so the server is configured
with the instance base URL plus a MAD API key:

    MAD_BASE_URL  e.g. https://acme.testfairy.com
    MAD_API_KEY   the user's API key (Settings -> API Key in MAD)

Tools wrap the stable /api/v3 REST API and are scoped to whatever the
API key's organization membership allows.

Over an HTTP transport the caller may instead send its own `X-API-Key`
header per request, which takes precedence over MAD_API_KEY. This lets one
server process serve many users, each scoped to their own MAD permissions;
MAD_API_KEY is then only a fallback and may be omitted entirely.
"""

import argparse
import os
import sys
import logging

from mcp.server import FastMCP
from typing import Any, Dict, List, Optional, Union
import httpx

from .main import check_stdio_is_not_tty

try:
    from fastmcp.server.dependencies import get_http_headers
except ImportError:  # pragma: no cover - older fastmcp without HTTP transports
    def get_http_headers(*_args, **_kwargs) -> Dict[str, str]:
        return {}

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format=">>>>>>>>>>>>%(levelname)s: %(message)s",
)


class MADAgent:
    def __init__(
        self,
        mcp_server: FastMCP,
        base_url: str,
        api_key: Optional[str] = None,
    ):
        self.mcp = mcp_server

        # Fallback only. The key is attached per request so a single process can
        # serve callers who each supply their own X-API-Key.
        self.default_api_key = api_key

        # Uploads can be hundreds of MB; the default 5s timeout is far too short.
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(30.0, read=600.0, write=600.0),
        )

        ## Tools
        ### Projects (apps)
        self.mcp.tool()(self.list_projects)
        self.mcp.tool()(self.get_project)

        ### Builds
        self.mcp.tool()(self.list_builds)
        self.mcp.tool()(self.get_build)
        self.mcp.tool()(self.upload_build)
        self.mcp.tool()(self.update_build)
        self.mcp.tool()(self.get_build_download_url)
        self.mcp.tool()(self.notify_build_testers)

        ### Testers & groups
        self.mcp.tool()(self.list_testers)
        self.mcp.tool()(self.list_groups)
        self.mcp.tool()(self.list_group_testers)

        logging.info("MAD API client initialized for %s.", base_url)

    # Not exposed to the Agent
    def resolve_api_key(self) -> Optional[str]:
        """Return the MAD API key for the call in flight.

        An `X-API-Key` header on the inbound MCP request wins, so each caller is
        scoped to its own MAD permissions. Outside an HTTP transport there are no
        request headers and the configured key is used.
        """
        headers = get_http_headers(include={"x-api-key"})
        return headers.get("x-api-key") or self.default_api_key

    # Not exposed to the Agent
    async def mad_api_call(
        self,
        relative_endpoint: str,
        method: str = "GET",
        params: Optional[dict] = None,
        files: Optional[dict] = None,
        form_data: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Perform one /api/v3 request and always return a JSON-serializable dict.

        On HTTP errors the API's own JSON error body is passed through (plus
        the status code) so the model sees the real reason, not a stack trace.
        """
        api_key = self.resolve_api_key()
        if not api_key:
            return {
                "error": (
                    "No MAD API key for this request. Send an X-API-Key header "
                    "with the MCP request, or set MAD_API_KEY on the server."
                ),
                "status_code": 401,
            }
        auth = {"X-API-Key": api_key}

        try:
            if files or form_data:
                request_files = {}
                try:
                    for key, file_path in (files or {}).items():
                        request_files[key] = open(file_path, "rb")
                    response = await self.client.request(
                        method,
                        relative_endpoint,
                        params=params,
                        files=request_files,
                        data=form_data or {},
                        headers=auth,
                    )
                finally:
                    for file_handle in request_files.values():
                        file_handle.close()
            else:
                response = await self.client.request(
                    method,
                    relative_endpoint,
                    params=params,
                    json=json_body,
                    headers=auth,
                )

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            try:
                body = e.response.json()
            except ValueError:
                body = {"error": e.response.text[:500]}
            body["status_code"] = e.response.status_code
            return body
        except FileNotFoundError as e:
            return {"error": f"Local file not found: {e.filename}"}
        except httpx.RequestError as e:
            return {"error": f"Network error while calling {relative_endpoint}: {e}"}
        except Exception as e:
            return {"error": f"Unexpected error while calling {relative_endpoint}: {e}"}

    async def aclose(self) -> None:
        logging.info("Closing HTTPX client session.")
        await self.client.aclose()

    ################################## Projects (apps)

    async def list_projects(
        self,
        page: int = 1,
        per_page: int = 25,
    ) -> Dict[str, Any]:
        """
        Lists the mobile apps (called "projects") in the organization, sorted by
        name, with pagination info. Each project includes its ID, which other
        tools (list_builds, upload_build) take as project_id.
        :param page: Optional. Page number, starting at 1.
        :param per_page: Optional. Results per page, max 100 (default 25).
        """
        return await self.mad_api_call(
            "/api/v3/projects",
            params={"page": page, "per_page": per_page},
        )

    async def get_project(self, project_id: int) -> Dict[str, Any]:
        """
        Returns the full details of one project (mobile app): name, package
        name, platform, team, and latest-version info.
        :param project_id: Required. The project ID, from list_projects.
        """
        return await self.mad_api_call(f"/api/v3/projects/{project_id}")

    ################################## Builds

    async def list_builds(
        self,
        project_id: int,
        page: int = 1,
        per_page: int = 25,
    ) -> Dict[str, Any]:
        """
        Lists the builds of a project, newest first, with pagination info.
        Each build includes version, platform, release notes, install URL and
        install count.
        :param project_id: Required. The project ID, from list_projects.
        :param page: Optional. Page number, starting at 1.
        :param per_page: Optional. Results per page, max 100 (default 25).
        """
        return await self.mad_api_call(
            f"/api/v3/projects/{project_id}/builds",
            params={"page": page, "per_page": per_page},
        )

    async def get_build(self, build_id: int) -> Dict[str, Any]:
        """
        Returns the full details of one build: version, version code, platform,
        package name, release notes, file size, tags, install count and
        install URL.
        :param build_id: Required. The build ID, from list_builds.
        """
        return await self.mad_api_call(f"/api/v3/builds/{build_id}")

    async def upload_build(
        self,
        file_path: str,
        project_id: Optional[int] = None,
        team_id: Optional[int] = None,
        version: Optional[str] = None,
        version_code: Optional[str] = None,
        release_notes: Optional[str] = None,
        symbols_file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Uploads a mobile app build (APK, AAB or IPA file) from the local
        filesystem to MAD. Returns the created build with its ID and install
        URL. Version and version code are auto-detected from the binary when
        omitted. Provide project_id to upload into a known app; otherwise
        team_id is REQUIRED and the app is auto-matched by package name inside
        that team (or created there).
        :param file_path: Required. Absolute local path of the .apk/.aab/.ipa file.
        :param project_id: Optional. Target project ID (from list_projects).
        :param team_id: Optional. Target team ID; required when project_id is omitted.
        :param version: Optional. Version string override.
        :param version_code: Optional. Version code override.
        :param release_notes: Optional. Release notes for this build.
        :param symbols_file_path: Optional. Local path of a debug-symbols file
            (iOS dSYM .zip or Android mapping.txt); attached best-effort.
        """
        form_data = {}
        if project_id is not None:
            form_data["project_id"] = str(project_id)
        if team_id is not None:
            form_data["team_id"] = str(team_id)
        if version:
            form_data["version"] = version
        if version_code:
            form_data["version_code"] = version_code
        if release_notes:
            form_data["release_notes"] = release_notes

        files = {"file": file_path}
        if symbols_file_path:
            files["symbols_file"] = symbols_file_path

        return await self.mad_api_call(
            "/api/v3/builds/upload",
            method="POST",
            files=files,
            form_data=form_data,
        )

    async def update_build(
        self,
        build_id: int,
        release_notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Updates a build's release notes and/or tags. Only the provided fields
        change; the rest of the build is untouched.
        :param build_id: Required. The build ID, from list_builds.
        :param release_notes: Optional. New release notes text.
        :param tags: Optional. Full replacement list of tags, e.g. ["beta", "rc1"].
        """
        body: Dict[str, Any] = {}
        if release_notes is not None:
            body["release_notes"] = release_notes
        if tags is not None:
            body["tags"] = tags
        if not body:
            return {"error": "Provide release_notes and/or tags to update."}

        return await self.mad_api_call(
            f"/api/v3/builds/{build_id}",
            method="PUT",
            json_body=body,
        )

    async def get_build_download_url(self, build_id: int) -> Dict[str, Any]:
        """
        Returns a pre-signed, time-limited URL to download a build's binary
        file directly. Useful to hand the artifact to another system.
        :param build_id: Required. The build ID, from list_builds.
        """
        return await self.mad_api_call(f"/api/v3/builds/{build_id}/download")

    async def notify_build_testers(self, build_id: int) -> Dict[str, Any]:
        """
        Queues email notifications to every tester assigned to the build's
        project, inviting them to install this build. Returns immediately with
        status "queued"; emails are sent asynchronously. Fails with 409 if the
        build is not installable, and requires admin rights on the project.
        :param build_id: Required. The build ID, from list_builds.
        """
        return await self.mad_api_call(
            f"/api/v3/builds/{build_id}/notify-testers",
            method="POST",
        )

    ################################## Testers & groups

    async def list_testers(
        self,
        page: int = 1,
        per_page: int = 25,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Lists the testers in the organization with pagination info. Each tester
        includes their ID, email, name, groups and blocked status.
        :param page: Optional. Page number, starting at 1.
        :param per_page: Optional. Results per page, max 100 (default 25).
        :param search: Optional. Filters testers by name or email substring.
        """
        params: Dict[str, Any] = {"page": page, "per_page": per_page}
        if search:
            params["search"] = search
        return await self.mad_api_call("/api/v3/testers", params=params)

    async def list_groups(
        self,
        page: int = 1,
        per_page: int = 25,
    ) -> Dict[str, Any]:
        """
        Lists the tester groups in the organization, sorted by name, with
        pagination info. Groups bundle testers for distribution; use
        list_group_testers to see a group's members.
        :param page: Optional. Page number, starting at 1.
        :param per_page: Optional. Results per page, max 100 (default 25).
        """
        return await self.mad_api_call(
            "/api/v3/groups",
            params={"page": page, "per_page": per_page},
        )

    async def list_group_testers(self, group_id: int) -> Dict[str, Any]:
        """
        Lists the testers that belong to one group.
        :param group_id: Required. The group ID, from list_groups.
        """
        return await self.mad_api_call(f"/api/v3/groups/{group_id}/testers")


def main():
    parser = argparse.ArgumentParser(prog="sauce-api-mcp-mad")
    parser.add_argument(
        "--transport",
        default=os.getenv("MAD_MCP_TRANSPORT", "stdio"),
        choices=["stdio", "streamable-http", "sse"],
        help="stdio for a local MCP client; streamable-http to serve many callers over HTTP.",
    )
    parser.add_argument("--host", default=os.getenv("MAD_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MAD_MCP_PORT", "9000")))
    args = parser.parse_args()

    # Only the stdio transport speaks over the terminal's own pipes.
    if args.transport == "stdio" and not check_stdio_is_not_tty():
        sys.exit(1)

    mcp_server_instance = FastMCP("MADAgent", host=args.host, port=args.port)

    MAD_BASE_URL = os.getenv("MAD_BASE_URL")
    if MAD_BASE_URL is None:
        raise ValueError("MAD_BASE_URL environment variable is not set (e.g. https://acme.testfairy.com).")

    # Over HTTP each caller supplies its own X-API-Key, so a server-wide key is
    # optional there; stdio has no request headers and needs one.
    MAD_API_KEY = os.getenv("MAD_API_KEY")
    if MAD_API_KEY is None and args.transport == "stdio":
        raise ValueError("MAD_API_KEY environment variable is not set.")

    MADAgent(mcp_server_instance, MAD_BASE_URL, MAD_API_KEY)

    mcp_server_instance.run(transport=args.transport)


if __name__ == "__main__":
    main()
