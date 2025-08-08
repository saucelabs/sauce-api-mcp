import base64

from mcp.server import FastMCP
from typing import Dict, Any, Union, Optional, List  # For type hinting dicts
import httpx
import sys
import logging
from urllib.parse import urlencode

from .models import (
    AccountInfo,
    LookupUsers,
    LookupServiceAccounts,
    LookupTeamsResponse,
    ErrorResponse
)

DATA_CENTERS = {
    "US_WEST": "https://api.us-west-1.saucelabs.com/",
    "US_EAST": "https://api.us-east-4.saucelabs.com/",
    "EU_CENTRAL": "https://api.eu-central-1.saucelabs.com/",
}

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format=">>>>>>>>>>>>%(levelname)s: %(message)s",
)

class SauceLabsAgent:
    def __init__(
        self,
        mcp_server: FastMCP,
        access_key: str,
        username: str,
        region: str = "US_WEST",
    ):

        self.mcp = mcp_server

        self.username = username
        auth = httpx.BasicAuth(username, access_key)

        base_url = ""
        if region.upper() == "OTHER":
            base_url = os.getenv("ALTERNATE_URL")
            if not base_url:
                raise ValueError(
                    "Region is 'OTHER', but the URL has not been set."
                )
        else:
            # Fallback to the dictionary for all other regions
            base_url = DATA_CENTERS[region]

        self.client = httpx.AsyncClient(base_url=base_url, auth=auth)

        ## Resources
        self.mcp.resource("sauce://account")(self.account_info)

        ## Tools
        ### Accounts
        self.mcp.tool()(self.get_account_info)
        self.mcp.tool()(self.lookup_teams)
        self.mcp.tool()(self.get_team)
        self.mcp.tool()(self.list_team_members)
        self.mcp.tool()(self.lookup_users)
        self.mcp.tool()(self.get_user)
        self.mcp.tool()(self.get_my_active_team)
        self.mcp.tool()(self.lookup_service_accounts)
        self.mcp.tool()(self.get_service_account)

        ### Jobs
        self.mcp.tool()(self.get_recent_jobs)
        self.mcp.tool()(self.get_job_details)
        self.mcp.tool()(self.get_test_assets)
        self.mcp.tool()(self.get_log_json_file)
        self.mcp.tool()(self.get_network_har_file)

        ### Builds
        self.mcp.tool()(self.get_build_for_job)
        self.mcp.tool()(self.get_build)
        self.mcp.tool()(self.lookup_builds)
        self.mcp.tool()(self.lookup_jobs_in_build)

        ### Sauce Connect
        self.mcp.tool()(self.get_tunnels_for_user)
        self.mcp.tool()(self.get_tunnel_information)
        self.mcp.tool()(self.get_tunnel_version_downloads)
        self.mcp.tool()(self.get_current_jobs_for_tunnel)

        ### Storage
        self.mcp.tool()(self.get_storage_groups)
        self.mcp.tool()(self.get_storage_groups_settings)

        ### Real Devices
        self.mcp.tool()(self.get_specific_device)
        self.mcp.tool()(self.get_devices_status)
        self.mcp.tool()(self.get_real_device_jobs)
        self.mcp.tool()(self.get_specific_real_device_job)
        self.mcp.tool()(self.get_specific_real_device_job_asset)
        self.mcp.tool()(self.get_private_devices)

        logging.info("SauceAPI client initialized and resource manifest loaded.")

    # Not exposed to the Agent
    async def sauce_api_call(
            self, relative_endpoint: str, method: str = "GET", params: Optional[dict] = None
    ) -> Union[httpx.Response, dict[str, str]]:
        try:
            # Always add the ai parameter
            all_params = params or {}
            all_params['ai'] = 'mcp'

            response = await self.client.request(
                method,
                relative_endpoint,
                params=all_params
            )
            response.raise_for_status()
            return response

        except httpx.HTTPStatusError as e:
            if e.response.status_code in [404, 500]:
                return e.response

            sys.stderr.write(
                f">>>>>>>>>>>>HTTP error fetching data from {relative_endpoint}: {e}\n"
            )
            return {
                "error": f"Failed to retrieve from {relative_endpoint}: {e.response.status_code} - {e.response.text}"
            }
        except httpx.RequestError as e:
            sys.stderr.write(
                f">>>>>>>>>>>>Network error fetching data from {relative_endpoint}: {e}\n"
            )
            return {
                "error": f"Network error while fetching data from {relative_endpoint}: {e}"
            }
        except Exception as e:
            sys.stderr.write(
                f">>>>>>>>>>>>An unexpected error occurred from {relative_endpoint}: {e}\n"
            )
            return {
                "error": f"An unexpected error occurred from {relative_endpoint}: {e}"
            }

    async def aclose(self) -> None:
        logging.info("Closing HTTPX client session.")
        await self.client.aclose()

    ################################## Account endpoints
    # This method populates the Resource at sauce://account
    async def account_info(self) -> Union[AccountInfo, Dict[str, str]]:
        """
        Retrieves detailed account information for the user associated with this client.
        Refer to `SauceAPI.resource_manifest['account']['methods']['get_account_info']` for full documentation.
        """
        response = await self.sauce_api_call(
            f"team-management/v1/users",
            params={"username": self.username}
        )

        if isinstance(response, httpx.Response):
            # return response.json()
            return AccountInfo.model_validate(response.json())
        return response

    async def get_account_info(self) -> Union[AccountInfo, Dict[str, str]]:
        """
        Provides the current user's Sauce Labs account information,
        including username, jobs run, minutes used, and overall account status.
        Useful for a quick overview of account activity.
        """
        account_data = await self.account_info()
        return account_data

    async def lookup_teams(
            self,
            id: Optional[str] = None,
            name: Optional[str] = None,
    ) -> Union[LookupTeamsResponse, ErrorResponse]:
        """
        Queries the organization of the requesting account and returns the number of teams matching the query and a
        summary of each team, including the ID value, which may be a required parameter of other API calls related
        to a specific team.You can filter the results of your query using the name parameter below.
        :param id: Optional. Comma-separated team IDs. Allows to receive details of multiple teams at once. For example,
            id=3d60780314724ab8ac688b50aadd9ff9,f9acc7c5b1da4fd0902b184c4f0b6324 would return details of teams with IDs
            included in the provided list.
        :param name: Optional. Returns the set of teams that begin with the specified name value. For example, name=sauce would
            return all teams in the organization with names beginning with "sauce".
        """
        params = {}
        if id:
            params["id"] = id
        if name:
            params["name"] = name

        response = await self.sauce_api_call(
            f"team-management/v1/teams",
            params=params
        )
        if isinstance(response, httpx.Response):
            return LookupTeamsResponse.model_validate(response.json())
        return ErrorResponse(error=response['error'])

    async def get_team(self, id: str) -> Dict[str, Any]:
        """
        Returns the full profile of the specified team. The ID of the team is the only valid unique identifier.
        :param id: Required. The unique identifier of the team. You can look up the IDs of teams in your organization
            using the Lookup Teams endpoint.
        """
        response = await self.sauce_api_call(f"team-management/v1/teams/{id}")
        if response.status_code == 404:
            return {
                "error": f"Team not found: {id}",
                "team_id": id,
                "possible_reasons": [
                    "Team ID does not exist",
                    "Team has been deleted",
                    "Insufficient permissions to access this team"
                ],
                "suggestions": [
                    "Use lookup_teams to find available teams",
                    "Verify team ID is correct",
                    "Check your organization permissions"
                ]
            }
        return response.json()

    async def list_team_members(self, id: str) -> Dict[str, Any]:
        """
        Returns the number of members in the specified team and lists each member.
        :param id: Required. Identifies the team for which you are requesting the list of members.
        """
        response = await self.sauce_api_call(f"team-management/v1/teams/{id}/members/")
        return response.json()

    async def lookup_users(
        self,
        id: Optional[str] = None,
        username: Optional[str] = None,
        teams: Optional[str] = None,
        roles: Optional[str] = None,
        phrase: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> LookupUsers:
        """
        Queries the organization of the requesting account and returns the number of users matching the query and a basic
        profile of each user, including the ID value, which may be a required parameter of other API calls related to a
        specific user. You can narrow the results of your query using any of the following filtering parameters.
        :param id: Optional. Comma-separated user IDs. Allows to receive details of multiple user at once. For example,
            id=3d60780314724ab8ac688b50aadd9ff9,f9acc7c5b1da4fd0902b184c4f0b6324 would return details of users with IDs
            included in the provided list.
        :param username: Optional. Limits the results to usernames that begin with the specified value. For example,
            username=an would return all users in the organization with usernames beginning with "an".
        :param teams: Optional. Limit results to users who belong to the specified team_ids. Specify multiple teams as
            comma-separated values.
        :param roles: Optional. Limit results to users who are assigned certain roles. Valid values are: 1 - Organization Admin,
            4 - Team Admin, 3 - Member. Specify multiple roles as comma-separated values.
        :param phrase: Optional. Limit results to users whose first name, last name, or email address begins with the specified value.
        :param status: Optional. Limit results to users of the specifid status. Valid values are: 'active', 'pending', 'inactive'
        :param limit: Optional. Limit results to a maximum number per page. Default value is 20.
        :param offset: Optional. The starting record number from which to return results.
        """
        params = {}
        if id:
            params["id"] = id
        if username:
            params["username"] = username
        if teams:
            params["teams"] = teams
        if roles:
            params["roles"] = roles
        if phrase:
            params["phrase"] = phrase
        if status:
            params["status"] = status
        if limit:
            params["limit"] = limit
        if offset:
            params["offset"] = offset

        response = await self.sauce_api_call(
            "team-management/v1/users",  # Clean endpoint without query string
            params=params  # Pass parameters as dict
        )
        return LookupUsers.model_validate(response.json())

    async def get_user(self, id: str) -> Dict[str, Any]:
        """
        Returns the full profile of the specified user. The ID of the user is the only valid unique identifier.
        :param id: Required. The user's unique identifier. Specific user IDs can be obtained through the lookup_users Tool
        """
        response = await self.sauce_api_call(f"team-management/v1/users/{id}/")
        if response.status_code == 404:
            return {
                "error": f"User not found: {id}",
                "user_id": id,
                "possible_reasons": [
                    "User ID does not exist",
                    "User has been deleted or deactivated",
                    "Insufficient permissions to access this user"
                ],
                "suggestions": [
                    "Use lookup_users to find available users",
                    "Verify user ID is correct",
                    "Check your organization permissions"
                ]
            }
        return response.json()

    async def get_my_active_team(self) -> Dict[str, Any]:
        """
        Retrieves the Sauce Labs active team for the currently authenticated user.
        """
        response = await self.sauce_api_call("team-management/v1/users/me/active-team/")
        return response.json()

    async def lookup_service_accounts(
        self,
        id: Optional[str] = None,
        username: Optional[str] = None,
        teams: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> LookupServiceAccounts:
        """
        Lists existing service accounts in your organization. You can filter the results using the query parameters below.
        :param id: Optional. Comma-separated service account IDs.
            included in the provided list.
        :param username: Optional. Limits the results to usernames that begin with the specified value. For example,
            username=an would return all service accounts in the organization with usernames beginning with "an".
        :param teams: Optional. Limit results to service account who belong to the specified team_ids. Specify multiple
            teams as comma-separated values.
        :param limit: Optional. Limit results to a maximum number per page. Default value is 20.
        :param offset: Optional. The starting record number from which to return results.
        """
        params = {}
        if id:
            params["id"] = id
        if username:
            params["username"] = username
        if teams:
            params["teams"] = teams
        if limit:
            params["limit"] = limit
        if offset:
            params["offset"] = offset

        response = await self.sauce_api_call(f"team-management/v1/service-accounts", params=params)
        return LookupServiceAccounts.model_validate(response.json())

    async def get_service_account(self, id: str) -> Dict[str, Any]:
        """
        Retrieves details of the specified service account.
        :param id: Required. The unique identifier of the service account. You can find the uuid in the URL of the
            service account details view in the Sauce Labs UI. You can also look up the uuid using the Lookup
            Service Accounts endpoint.
        """
        response = await self.sauce_api_call(
            f"team-management/v1/service-accounts/{id}/"
        )
        if response.status_code == 404:
            return {
                "error": f"Service account not found: {id}",
                "service_account_id": id,
                "possible_reasons": [
                    "Service account ID does not exist",
                    "Service account has been deleted",
                    "Insufficient permissions to access this service account"
                ],
                "suggestions": [
                    "Use lookup_service_accounts to find available service accounts",
                    "Verify service account ID is correct",
                    "Check your organization permissions"
                ]
            }
        return response.json()

    ################################## Jobs endpoints
    # Not exposed to the Agent. We can register if we need to, but it seems better to use the helper method.
    async def get_asset_url(self, job_id: str, asset_key: str) -> str:
        asset_list = await self.get_test_assets(job_id)

        if isinstance(asset_list, dict) and "error" in asset_list:
            raise ValueError(f"Cannot get asset URL: {asset_list['error']}")

        asset_url = asset_list.get(asset_key)
        if asset_url is None:
            raise ValueError(
                f"Asset '{asset_key}' not found in job {job_id}. Available assets: {list(asset_list.keys())}")

        if isinstance(asset_url, str):
            return f"rest/v1/{self.username}/jobs/{job_id}/assets/{asset_url}"
        raise ValueError(f"Asset must be string, {asset_key} is type {type(asset_url)}")

    # This is exposed to the Agent in case the user wants to see the links that will click through to the Sauce UI
    async def get_test_assets(self, job_id: str) -> Dict[str, Any]:
        """
        Returns the list of all assets for a test, based on the job ID.

        IMPORTANT: Only use this method with Virtual Device Cloud (VDC) jobs. This will fail
        with a 404 error for Real Device Cloud (RDC) jobs. If you get an error about
        "Real Device job", use get_specific_real_device_job_asset instead.

        To determine job type: RDC jobs typically have device names like "Samsung Galaxy" or "iPhone 14".
        VDC jobs typically have browser names like "chrome", "firefox", or platform names like "Windows 11".

        :param job_id: The Sauce Labs Job ID (VDC jobs only).
        :return: JSON containing a list of assets, from which the URL can be derived.
        """
        response = await self.sauce_api_call(f"rest/v1/jobs/{job_id}/assets")
        if isinstance(response, httpx.Response):
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                return {
                    "error": f"User not recognized. Please ensure SAUCE_USERNAME and SAUCE_ACCESS_KEY are set",
                }
            elif response.status_code == 404:
                return {
                    "error": f"Assets not found for job: {job_id}",
                    "job_id": job_id,
                    "possible_reasons": [
                        "Job ID does not exist",
                        "Job is a Real Device (RDC) job - use get_specific_real_device_job_asset instead",
                        "Job data may have expired due to retention policies"
                    ],
                    "suggestions": [
                        "Verify job ID is correct",
                        "For RDC jobs, use get_specific_real_device_job_asset with asset types like 'deviceLogs', 'appiumLogs'",
                        "Use get_recent_jobs to find available jobs"
                    ]
                }
        return response

    async def get_log_json_file(self, job_id: str) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """
        Shows the complete log of a Sauce Labs test, in structured json format.

        IMPORTANT: This method only works with Virtual Device Cloud (VDC) jobs. For Real Device
        Cloud (RDC) jobs, use get_specific_real_device_job_asset with asset_type='appiumLogs'
        or 'deviceLogs' instead.

        If this method fails with "asset not found", the job is likely an RDC job - try
        get_specific_real_device_job_asset instead.

        :param job_id: The Sauce Labs Job ID (VDC jobs only).
        :return: Structured JSON log data with test commands, timing, and screenshots.
        """
        asset_url: str = await self.get_asset_url(job_id, "sauce-log")
        sys.stderr.write(
            f"log.json url: {asset_url}\n"
        )
        response = await self.sauce_api_call(asset_url)

        if isinstance(response, httpx.Response):
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"Failed to get logs: {response.status_code}"}
        return {"error": "Invalid response type"}

    # Not published in v1
    async def get_selenium_log_file(self, job_id: str) -> Union[str, Dict[str, str]]:
        """
        Shows the complete log of a Sauce Labs test, in unstructured raw format.
        """
        asset_url = await self.get_asset_url(job_id, "selenium-server.log")
        response = await self.sauce_api_call(asset_url)
        if isinstance(response, httpx.Response):
            return response.json()
        return response

    # Not published in v1
    async def get_network_har_file(self, job_id: str) -> Dict[str, str]:
        """
        Returns the HAR file of network traffic gathered during the test, in structured json format.
        """
        asset_url = await self.get_asset_url(job_id, "network.har")
        response = await self.sauce_api_call(asset_url)
        if isinstance(response, httpx.Response):
            return response.json()
        return response

    # Not published in v1
    async def get_performance_json_file(self, job_id: str) -> Dict[str, str]:
        """
        Returns the Performance log of the test, in structured json format.
        """
        asset_url = await self.get_asset_url(job_id, "performance.json")
        response = await self.sauce_api_call(asset_url)
        if isinstance(response, httpx.Response):
            return response.json()
        return response

    async def get_job_details(self, job_id: str) -> Dict[str, Any]:
        """
        Retrieves the execution details of a particular job, by ID.

        This method works for both Virtual Device Cloud (VDC) and Real Device Cloud (RDC) though
        the returned data structure may vary between platforms.

        Use this method first to understand what type of job you're working with:
            - If 'device_name' contains mobile devices → RDC job → use get_specific_real_device_job_asset for assets
            - If 'browser' field shows web browsers → VDC job → use get_test_assets for assets

        :param job_id: The Sauce Labs Job ID (works for both VDC and RDC jobs).
        :return: Detailed job information including status, timing, configuration, and platform-specific data.
        """
        response = await self.sauce_api_call(f"rest/v1/{self.username}/jobs/{job_id}")
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return {
                "error": f"Job not found: {job_id}",
                "job_id": job_id,
                "possible_reasons": [
                    "Job ID does not exist",
                    "Job data may have expired due to retention policies",
                    "Job may be from RDC platform (different endpoints)",
                    "Insufficient permissions to access this job"
                ],
                "suggestions": [
                    "Verify job ID is correct",
                    "Use get_recent_jobs to find available jobs",
                    "Check if this is a VDC vs RDC job",
                    "Ensure you have access to this job"
                ]
            }
        else:
            return {
                "error": f"API request failed with status {response.status_code}",
                "job_id": job_id,
                "status_code": response.status_code
            }

    async def get_recent_jobs(
        self, limit: int = 5
    ) -> Dict[str, Any]:
        """
        Retrieves a list of the most recent jobs run on Sauce Labs for the current user.
        Allows specifying the number of jobs to retrieve, up to a maximum.
        Useful for quickly checking the status of recent test runs.
        :param limit: The upper limit (integer) of jobs to retrieve. Max is 100
        """
        response = await self.sauce_api_call(
            f"rest/v1/{self.username}/jobs",
            params={"limit": limit}
        )
        if isinstance(response, httpx.Response):
            jobs = response.json()
            return {
                "jobs": jobs,
                "total": len(jobs),
                "page": 1,
                "per_page": limit
            }
        return {"jobs": response, "total": len(response), "page": 1, "per_page": limit}

    ################################## Builds endpoints

    async def lookup_builds(
        self,
        build_source: str,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        group_id: Optional[str] = None,
        team_id: Optional[str] = None,
        status: Optional[List[str]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
        name: Optional[str] = None,
        offset: Optional[int] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Queries the requesting account and returns a summary of each build matching the query, including the ID value,
        which may be a required parameter of other API calls related to a specific build. You can narrow the results of
        your query using any of the optional filtering parameters.
        :param build_source: The type of device for which you are getting builds. Valid values are: \'rdc\' - Real Device
            Builds, \'vdc\' - Emulator or Simulator Builds
        :param user_id: Optional. Returns any builds owned by the specified user that the authenticated user is authorized to view. You can look up the IDs of users in your organization using the Lookup Users endpoint.
        :param org_id: Optional. Returns all builds in the specified organization that the authenticated user is authorized to view.
        :param group_id: Optional. Returns all builds associated with the specified group that the authenticated user is authorized to view.
        :param team_id: Optional. Returns all builds for the specified team that the authenticated user is authorized to view.
        :param status: Optional. Returns only builds where the status matches the list of values specified. Valid values are: running - Any job in the build has a state of running, new, or queued. error - The build is not running and at least one job in the build has a state of errored. failed - The build is not running or error and at least one job in the build has a state of failed. complete - The build is not running, error, or failed, but the number of jobs with a state of finished does not equal the number of jobs marked passed, so at least one job has a state other than passed. success -- All jobs in the build have a state of passed.
        :param start: Optional. Returns only builds where the earliest job ran on or after this Unix timestamp. Note: If experiencing errors, try providing both start and end parameters together.
        :param end: Optional. Returns only builds where the latest job ran on or before this Unix timestamp. Note: If experiencing errors, try providing both start and end parameters together.
        :param limit: Optional. The maximum number of builds to return in the response.
        :param name: Optional. Returns builds with a matching build name.
        :param offset: Optional. Begins the set of results at this index number.
        :param sort: Optional. Sorts the results in alphabetically ascending or descending order. Valid values are: asc - Ascending desc - Descending
        """
        params = {}
        if user_id:
            params["user_id"] = user_id
        if org_id:
            params["org_id"] = org_id
        if group_id:
            params["group_id"] = group_id
        if team_id:
            params["team_id"] = team_id
        if status:
            params["status"] = status
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if limit:
            params["limit"] = limit
        if name:
            params["name"] = name
        if offset:
            params["offset"] = offset
        if sort:
            params["sort"] = sort

        try:
            response = await self.sauce_api_call(f"v2/builds/{build_source}/", params=params)

            if isinstance(response, dict):
                return response
            else:
                return response.json()

        except Exception as e:
            # Check if it's a timestamp-related error
            if ('end' in params and 'start' not in params) or ('start' in params and 'end' not in params):
                raise ValueError(
                    "Time range filtering may require both 'start' and 'end' parameters. "
                    f"Try providing both parameters together. Original error: {e}"
                )
            else:
                raise e

    async def get_build(self, build_source: str, build_id: str) -> Dict[str, Any]:
        """
        Retrieve the details related to a specific build by passing its unique ID in the request.
        :param build_source: Required. The type of device for which you are getting builds. Valid values are: 'rdc' -
            Real Device Builds, 'vdc' - Emulator or Simulator Builds
        :param build_id: Required. The unique identifier of the build to retrieve. You can look up build IDs in your
            organization using the Lookup Builds endpoint.
        """
        response = await self.sauce_api_call(f"v2/builds/{build_source}/{build_id}/")
        if response.status_code == 404:
            return {
                "error": f"Build not found: {build_id}",
                "build_id": build_id,
                "build_source": build_source,
                "possible_reasons": [
                    "Build ID does not exist",
                    "Build data may have expired due to retention policies",
                    "Incorrect build source specified (rdc vs vdc)"
                ],
                "suggestions": [
                    "Use lookup_builds to find available builds",
                    "Verify build ID and build_source are correct",
                    "Try the other build_source (rdc vs vdc)"
                ]
            }
        data = response.json()
        return data

    async def get_build_for_job(self, build_source: str, job_id: str) -> Union[Dict[str, Any], ErrorResponse]:
        """
        Retrieve the details related to a specific build by passing its unique ID in the request.
        :param build_source: Required. The type of device for which you are getting builds. Valid values are: 'rdc'
            (Real Device Builds), 'vdc' (Emulator or Simulator Builds)
        :param job_id: Required. The unique identifier of the job whose build you are looking up. You can look up job
            IDs in your organization using the Get Jobs endpoint.
        """
        response = await self.sauce_api_call(
            f"v2/builds/{build_source}/jobs/{job_id}/build/"
        )
        if isinstance(response, httpx.Response):
            if response.status_code == 404:
                return {
                    "error": f"Build not found for job: {job_id}",
                    "job_id": job_id,
                    "build_source": build_source,
                    "possible_reasons": [
                        "Job ID does not exist",
                        "Job is not associated with a build",
                        "Incorrect build source specified (rdc vs vdc)"
                    ],
                    "suggestions": [
                        "Use get_job_details to verify job exists",
                        "Try the other build_source (rdc vs vdc)",
                        "Some jobs may not be part of a build"
                    ]
                }
            return response.json()
        return ErrorResponse(error=response['error'])

    async def lookup_jobs_in_build(
        self,
        build_source: str,
        build_id: str,
        modified_since: Optional[str] = None,
        completed: Optional[bool] = None,
        errored: Optional[bool] = None,
        failed: Optional[bool] = None,
        finished: Optional[bool] = None,
        new: Optional[bool] = None,
        passed: Optional[bool] = None,
        public: Optional[bool] = None,
        queued: Optional[bool] = None,
        running: Optional[bool] = None,
        faulty: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Returns information about all jobs associated with the specified build. You can limit which jobs are
        returned using any of the optional filtering parameters.
        :param build_source: Required. The type of test device associated with the build and its jobs. Valid values are:
            rdc - Real Device Builds, vdc - Emulator or Simulator Builds
        :param build_id: Required. The unique identifier of the build whose jobs you are looking up. You can look up
            build IDs in your organization using the Lookup Builds endpoint.
        :param modified_since: Optional. Returns only jobs that have been modified after this unicode timestamp.
        :param completed: Optional. Returns jobs based on whether they completed, meaning the tests ran uninterrupted to
            completion: true - Return jobs that have a completed state of true, false - Return jobs that have a
            completed state of false.
        :param errored: Optional. Returns jobs based on their errored state: true - Return jobs that have an errored
            state of true, false - Return jobs that have an errored state of false.
        :param failed: Optional. Returns jobs based on their failed state: true - Return jobs that have a failed state
            of true, false - Return jobs that have a failed state of false.
        :param finished: Optional. Returns jobs based on whether they have finished, meaning they are no longer
            running, but may not have run to completion: true - Return jobs that have a finished state of true, false -
            Return jobs that have a finished state of false.
        :param new: Optional. Returns jobs based on their new state: true - Return jobs that have a new state of true,
            false - Return jobs that have a new state of false.
        :param passed: Optional. Returns jobs based on their passed state: true - Return jobs that have a passed state
            of true, false - Return jobs that have a passed state of false.
        :param public: Optional. Returns jobs based on whether they were run on public devices: true - Return jobs that
            have a public state of true, false - Return jobs that have a public state of false.
        :param queued: Optional. Returns jobs based on whether their current state is queued: true - Return jobs that
            have a queued state of true, false - Return jobs that have a queued state of false.
        :param running: Optional. Returns jobs based on whether they are currently in a running state: true - Return
            jobs that are currently running, false - Return jobs that are not currently running.
        :param faulty: Optional. Returns jobs based on whether they are identified as faulty, meaning either errored or
            failed state is true. true - Return jobs that have a faulty state of true, false - Return jobs that have a
            faulty state of false.
        """
        params = {}
        if modified_since:
            params["modified_since"] = modified_since
        if completed is not None:
            params["completed"] = completed
        if errored is not None:
            params["errored"] = errored
        if failed is not None:
            params["failed"] = failed
        if finished is not None:
            params["finished"] = finished
        if new is not None:
            params["new"] = new
        if passed is not None:
            params["passed"] = passed
        if public is not None:
            params["public"] = public
        if queued is not None:
            params["queued"] = queued
        if running is not None:
            params["running"] = running
        if faulty is not None:
            params["faulty"] = faulty

        response = await self.sauce_api_call(
            f"v2/builds/{build_source}/{build_id}/jobs/", params=params
        )
        if isinstance(response, httpx.Response):
            if response.status_code == 200:
                jobs_data = response.json()

                # Check if we got an empty jobs list and provide context
                if "jobs" in jobs_data and len(jobs_data["jobs"]) == 0:
                    # Add helpful messaging for empty results
                    jobs_data["data_retention_info"] = {
                        "message": "No jobs found for this build. Jobs may no longer be available due to data retention policies.",
                        "note": "Jobs for builds older than ~3 months may have been archived or purged.",
                        "suggestions": [
                            "Try a more recent build ID",
                            "Use get_recent_jobs to find currently available jobs",
                            f"Verify this {build_source} build exists and has associated jobs"
                        ]
                    }

                return jobs_data

            elif response.status_code == 404:
                return {
                    "error": f"Build not found: {build_id}",
                    "build_id": build_id,
                    "build_source": build_source,
                    "possible_reasons": [
                        "Build ID does not exist",
                        "Build data may have expired due to retention policies",
                        "Incorrect build_source parameter (vdc vs rdc)"
                    ],
                    "suggestions": [
                        "Verify build ID is correct using lookup_builds",
                        "Check if build_source should be 'vdc' or 'rdc'",
                        "Try a more recent build"
                    ]
                }

            else:
                return {
                    "error": f"API request failed with status {response.status_code}",
                    "build_id": build_id,
                    "build_source": build_source,
                    "status_code": response.status_code
                }
        return response

    ################################## Sauce Connect endpoints

    async def get_tunnels_for_user(self, username) -> Dict[str, Any]:
        """
        Returns Tunnel IDs or Tunnels Info for any currently running tunnels launched by or shared with the specified
        user. The word "tunnel" in this context refers to usage of the Sauce Connect tool.
        It also allows to filter tunnels using an optional "filter" parameter that may take the following values:
        :param username: Required. The authentication username of the user whose tunnels you are requesting.
        """
        response = await self.sauce_api_call(f"rest/v1/{username}/tunnels")
        if isinstance(response, httpx.Response):
            if response.status_code == 404:
                return {"error": "User not found"}
            elif response.status_code == 403:
                return {"error": "Access denied to user tunnel data"}

            tunnels = response.json()
            return {
                "tunnels": tunnels,
                "count": len(tunnels),
                "username": username
            }

        return {"tunnels": response, "count": len(response), "username": username}

    async def get_tunnel_information(
        self, username: str, tunnel_id: str
    ) -> Dict[str, Any]:
        """
        Returns information about the specified tunnel. The word "tunnel" in this context refers to usage of \
        the Sauce Connect tool.
        :param username: Required. The authentication username of the owner of the requested tunnel.
        :param tunnel_id: Required. The unique identifier of the requested tunnel.
        """
        response = await self.sauce_api_call(f"rest/v1/{username}/tunnels/{tunnel_id}")
        return self.process_tunnel_response(response, tunnel_id, username)

    async def get_tunnel_version_downloads(self, client_version: str) -> Dict[str, Any]:
        """
        Returns the specific paths (URLs) to download specific versions of the SauceConnect tunnel software.
        The word "tunnel" in this context refers to usage of the Sauce Connect tool.
        :param client_version: Optional. Returns download information for the specified Sauce Connect client
            version (For example, '5.2.3').
        """
        response = await self.sauce_api_call(
            f"rest/v1/public/tunnels/info/versions?client_version={client_version}"
        )
        data = response.json()
        return data

    async def get_current_jobs_for_tunnel(
        self, username: str, tunnel_id: str
    ) -> Dict[str, Any]:
        """
        Returns the number of currently running jobs for the specified tunnel. The word "tunnel" in this context refers
        to usage of the Sauce Connect tool.
        :param username: Required. The authentication username of the owner of the requested tunnel.
        :param tunnel_id: Required. The unique identifier of the requested tunnel.
        """
        response = await self.sauce_api_call(f"rest/v1/{username}/tunnels/{tunnel_id}/num_jobs")

        return self.process_tunnel_response(response, tunnel_id, username)

    @staticmethod
    def process_tunnel_response(response, tunnel_id, username):
        if isinstance(response, httpx.Response):
            if response.status_code == 200:
                return response.json()
            elif response.status_code in [404, 500]:
                return {
                    "error": f"Tunnel not found: {tunnel_id}",
                    "tunnel_id": tunnel_id,
                    "username": username,
                    "possible_reasons": [
                        "Tunnel ID does not exist",
                        "Tunnel has been terminated",
                        "Insufficient permissions to access this tunnel"
                    ],
                    "suggestions": [
                        "Use get_tunnels_for_user to find active tunnels",
                        "Verify tunnel ID is correct",
                        "Check if tunnel is still running"
                    ]
                }
            else:
                return {
                    "error": f"API request failed with status {response.status_code}",
                    "tunnel_id": tunnel_id,
                    "status_code": response.status_code
                }
        return response

    ################################## Real Device endpoints
    async def get_specific_device(self, device_id:str) -> Dict[str, Any]:
        """
        Get information about the device specified in the request.
        :param device_id: Required. The unique identifier of a device in the Sauce Labs
            data center. Use the 'descriptor' value from get_devices_status results.
        """
        response = await self.sauce_api_call(f"v1/rdc/devices/{device_id}")
        data = response.json()
        return data

    async def get_devices_status(self) -> Dict[str, Any]:
        """
        Returns a list of devices in the data center along with their current states. Each device is represented by a
        descriptor, indicating its model, and includes information on availability, usage status, and whether it is
        designated as a private device. Note that the inUseBy field is exposed only for private devices
        isPrivateDevice: true. Users can view information about who is currently using the device only if they have
        the required permissions. Lack of permissions will result in the inUseBy field being omitted from the response
        for private devices.

        This tool provides a lightweight overview of all devices. For detailed device specifications, use the
        get_specific_device tool with the descriptor value as the device_id parameter.

        Available States:
            AVAILABLE	Device is available and ready to be allocated
            IN_USE	    Device is currently in use
            CLEANING	Device is being cleaned (only available for private devices)
            MAINTENANCE	Device is in maintenance (only available for private devices)
            REBOOTING	Device is rebooting (only available for private devices)
            OFFLINE	    Device is offline (only available for private devices)

        Note: The 'descriptor' field in each device object is the device identifier that should be used as the
        'device_id' parameter in get_specific_device calls.
        """
        response = await self.sauce_api_call(f"v1/rdc/devices/status")
        data = response.json()
        return data

    ################################## Real Device Jobs endpoints
    async def get_real_device_jobs(self, limit: int = 5, offset: int = 1, type: str = None) -> Dict[str, Any]:
        """
        Get a list of jobs that are actively running on real devices in the data center.
        :param limit: The maximum number of jobs to return.
        :param offset: Limit results to those following this index number. Defaults to 1.
        :param type: Filter results to show manual tests only with LIVE.
        """
        response = await self.sauce_api_call(f"v1/rdc/jobs",
             params={"limit": limit, "offset": offset})
        data = response.json()
        return data

    async def get_specific_real_device_job(self, job_id: str) -> Dict[str, Any]:
        """
        Get information about a specific job running on a real device at the data center.
        :param job_id: Required. The unique identifier of a job running on a real device in the data center. You can
            look up job IDs using the Get Real Device Jobs endpoint.
        """
        response = await self.sauce_api_call(f"v1/rdc/jobs/{job_id}")
        data = response.json()
        return data

    async def get_specific_real_device_job_asset(self, job_id: str, asset_type: str) -> Dict[str, Any]:
        """
        Download a specific asset for a Real Device Cloud (RDC) job.

        USE THIS METHOD WHEN:
        - The job ran on a physical mobile device (iPhone, Android, etc.)
        - get_test_assets returns an error about "Real Device job"
        - get_log_json_file fails with asset not found errors
        - You need logs/videos from mobile app testing

        For web browser testing on virtual machines, use get_test_assets instead.

        :param job_id: Required. The unique identifier of a job running on a real device in the data center. You can look up job
            IDs using the Get Real Device Jobs endpoint.
        :param asset_type: Required. The unique identifier of a job running on a real device in the data center. You can look up job
            IDs using the Get Real Device Jobs endpoint. Possible values are:

            'deviceLogs' - Device Logs | Appium, Espresso, XCUITest
            'appiumLogs' - Appium Logs | Appium
            'appiumRequests' - Appium Requests | Appium
            'junit.xml' - JUnit XML | Espresso, XCUITest
            'xcuitestLogs' - XCUITest Logs | XCUITest
            'video.mp4' - Video | Appium, Espresso, XCUITest
            'screenshots.zip' - Screenshots | Appium, Espresso
            'network.har' - Network Logs | Appium, Espresso, XCUITest
            'insights.json' - Device Vitals | Appium, Espresso, XCUITest
            'crash.json' - Crash Logs | Appium
        """
        response = await self.sauce_api_call(f"v1/rdc/jobs/{job_id}/{asset_type}")
        if response.status_code == 200:
            return {
                "content": base64.b64encode(response.content).decode('utf-8'),
                "encoding": "base64",
                "content_type": response.headers.get("content-type"),
                "filename": f"{job_id}_{asset_type}",
                "size": len(response.content)
            }
        data = response.json()
        return data

    async def get_private_devices(self) -> Dict[str, Any]:
        """
        Get a list of private devices with their device information and settings.
        """
        response = await self.sauce_api_call(f"v1/rdc/device-management/devices")
        data = response.json()
        return {"devices": data}

    ################################## Storage endpoints
    # Not published as of v1
    async def get_storage_files(self) -> Dict[str, Any]:
        """
        Returns the set of files that have been uploaded to Sauce Storage by the requestor.
        """
        response = await self.sauce_api_call("v1/storage/files")
        data = response.json()
        return data

    async def get_storage_groups(self) -> Dict[str, Any]:
        """
        Returns an array of groups (apps containing multiple files) currently in storage for the authenticated requestor.
        """
        response = await self.sauce_api_call("v1/storage/groups")
        data = response.json()
        return data

    async def get_storage_groups_settings(self, group_id: str) -> Dict[str, Any]:
        """
        Returns the settings of an app group with the given ID.
        :param group_id: The unique identifier of the app group. You can look up group IDs using the Get App Storage Groups endpoint.
        """
        response = await self.sauce_api_call(f"v1/storage/groups/{group_id}/settings")
        data = response.json()
        return data

# If run directly from a TTY, this server could be compromised (STDIO hijacking, etc)
def check_stdio_is_not_tty():
    """
    Checks if stdin, stdout, and stderr are not connected to a TTY.
    Returns True if safe, False otherwise.
    """
    if sys.stdin.isatty() or sys.stdout.isatty() or sys.stderr.isatty():
        print("Error: This server is not meant to be run interactively.", file=sys.stderr)
        return False
    return True

def main():
    if not check_stdio_is_not_tty():
        sys.exit(1)

    # Create the FastMCP server instance
    mcp_server_instance = FastMCP("SauceLabsAgent")

    import os

    SAUCE_ACCESS_KEY = os.getenv("SAUCE_ACCESS_KEY")
    if SAUCE_ACCESS_KEY is None:
        raise ValueError("SAUCE_ACCESS_KEY environment variable is not set.")

    SAUCE_USERNAME = os.getenv("SAUCE_USERNAME")
    if SAUCE_USERNAME is None:
        raise ValueError("SAUCE_USERNAME environment variable is not set.")

    SAUCE_REGION = os.getenv("SAUCE_REGION")
    if SAUCE_REGION is None:
        SAUCE_REGION = "US_WEST"

    sauce_agent = SauceLabsAgent(mcp_server_instance, SAUCE_ACCESS_KEY, SAUCE_USERNAME, SAUCE_REGION)

    # Run the FastMCP server instance
    mcp_server_instance.run(transport="stdio")

# --- Main Application Setup ---
if __name__ == "__main__":
    main()
