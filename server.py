from mcp.server import FastMCP
from typing import Dict, Any, Union  # For type hinting dicts
import httpx
import sys
import logging

from models import (
    TestLog,
    TestAssets,
    TeamConcurrency,
    OrgConcurrency,
    JobDetails,
    RecentJobs,
    TestAnalytics,
    TestMetrics,
    TestTrends,
    AccountInfo,
    AllBuildsAndTests,
    SauceStatus,
)

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
        data_center: str = "us-west-1",
    ):
        sys.stderr.write(">>>>>>>>>>>>Initializing SauceLabsAgent\n")
        self.mcp = mcp_server

        self.username = username
        auth = httpx.BasicAuth(username, access_key)
        base_url = f"https://api.{data_center}.saucelabs.com/"
        self.client = httpx.AsyncClient(base_url=base_url, auth=auth)

        ## Resources
        self.mcp.resource("sauce://account")(self.account_info)

        ## Tools
        ### Accounts
        self.mcp.tool()(self.get_account_info)
        self.mcp.tool()(self.get_org_concurrency)
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

        ### Builds
        self.mcp.tool()(self.get_build_for_job)
        self.mcp.tool()(self.get_build)
        self.mcp.tool()(self.lookup_builds)
        self.mcp.tool()(self.lookup_jobs_in_build)

        ### Insights
        self.mcp.tool()(self.get_test_analytics)
        self.mcp.tool()(self.get_test_trends)
        self.mcp.tool()(self.get_test_metrics)

        ### Platform
        self.mcp.tool()(self.get_sauce_status)

        ### Sauce Connect
        self.mcp.tool()(self.get_tunnels_for_user)
        self.mcp.tool()(self.get_tunnel_information)
        self.mcp.tool()(self.get_tunnel_version_downloads)
        self.mcp.tool()(self.get_current_jobs_for_tunnel)

        ### Storage
        self.mcp.tool()(self.get_storage_files)
        self.mcp.tool()(self.get_storage_groups)
        self.mcp.tool()(self.get_storage_groups_settings)

        # self.mcp.tool()(self.get_all_builds_and_tests)
        # self.mcp.tool()(self.get_network_har_file)
        # self.mcp.tool()(self.get_performance_json_file)
        # self.mcp.tool()(self.get_selenium_log_file)

        logging.info("SauceAPI client initialized and resource manifest loaded.")

    # Not exposed to the Agent
    async def sauce_api_call(
        self, relative_endpoint: str, method: str = "GET"
    ) -> Union[httpx.Response, dict[str, str]]:
        try:
            response = await self.client.request(method, relative_endpoint)
            response.raise_for_status()
            return response

        except httpx.HTTPStatusError as e:
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
    # Not exposed to the Agent. We can register if we need to, but it seems better to use the helper method.
    async def get_asset_url(self, job_id: str, asset_key: str) -> str:
        asset_list = await self.get_test_assets(job_id)
        asset_url = getattr(asset_list, asset_key)
        if isinstance(asset_url, str):
            return f"rest/v1/{self.username}/jobs/{job_id}/assets/" + asset_url
        raise ValueError(f"Asset must be string, {asset_key} is type {type(asset_url)}")

    # This method populates the Resource at sauce://account
    async def account_info(self) -> Union[AccountInfo, Dict[str, str]]:
        """
        Retrieves detailed account information for the user associated with this client.
        Refer to `SauceAPI.resource_manifest['account']['methods']['get_account_info']` for full documentation.
        """
        response = await self.sauce_api_call(
            f"team-management/v1/users?username={self.username}"
        )

        if isinstance(response, httpx.Response):
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

    async def lookup_teams(self, id: str, name: str) -> Dict[str, Any]:
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
        response = await self.sauce_api_call(
            f"team-management/v1/teams?id={id}&name={name}"
        )
        return response.json()

    async def get_team(self, id: str) -> Dict[str, Any]:
        """
        Returns the full profile of the specified team. The ID of the team is the only valid unique identifier.
        :param id: Required. The unique identifier of the team. You can look up the IDs of teams in your organization
            using the Lookup Teams endpoint.
        """
        response = await self.sauce_api_call(f"team-management/v1/teams/{id}")
        return response.json()

    async def list_team_members(self, id: str) -> Dict[str, Any]:
        """
        Returns the number of members in the specified team and lists each member.
        :param id: Required. Identifies the team for which you are requesting the list of members.
        """
        response = await self.sauce_api_call(f"team-management/v1/teams/{id}/members/")
        return response.json()

    async def lookup_users(self, id: str) -> Dict[str, Any]:
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
        response = await self.sauce_api_call("team-management/v1/users/")
        return response.json()

    async def get_user(self, id: str) -> Dict[str, Any]:
        """
        Returns the full profile of the specified user. The ID of the user is the only valid unique identifier.
        :param id: Required. The user's unique identifier. Specific user IDs can be obtained through the lookup_users Tool
        """
        response = await self.sauce_api_call(f"team-management/v1/users/{id}/")
        return response.json()

    async def get_my_active_team(self) -> Dict[str, Any]:
        """
        Retrieves the Sauce Labs active team for the currently authenticated user.
        """
        response = await self.sauce_api_call("team-management/v1/users/me/active-team/")
        return response.json()

    async def lookup_service_accounts(self) -> Dict[str, Any]:
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
        response = await self.sauce_api_call("team-management/v1/service-accounts/")
        return response.json()

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
        return response.json()

    async def get_org_concurrency(
        self, org_id: str
    ) -> Union[OrgConcurrency, Dict[str, str]]:
        """
        Return information about concurrency usage for organization:
        - maximum, minimum concurrency for given granularity (monthly, weekly, daily, hourly),
        - teams' share for the organization maximum concurrency for given granularity (in percentage),
        - current limits.
        :param org_id: Return results only for the specified org_id
        :return: Json report containing org concurrency usage
        """
        response = await self.sauce_api_call(
            f"usage-analytics/v1/concurrency/org?org_id={org_id}"
        )
        if isinstance(response, httpx.Response):
            return OrgConcurrency.model_validate(response.json())
        return response

    async def get_team_concurrency(
        self, org_id: str, team_id: str
    ) -> Union[TeamConcurrency, Dict[str, str]]:
        """
        Return information about concurrency usage for teams:
            - maximum, minimum concurrency for given granularity (monthly, weekly, daily, hourly),
            - current limits.
        Concurrency data is broken down by resource types for:
        - Virtual Cloud:
            - virtual machines,
            - mac virtual machines,
            - mac arm virtual machines,
            - total virtual machines, combining all resource types.
        - Real Device Cloud:
            - private devices,
            - public devices,
            - total virtual machines, combining all resource types.
        :param org_id:
        :param team_id:
        :return: Json report containing team concurrency usage
        """
        response = await self.sauce_api_call(
            f"usage-analytics/v1/concurrency/teams?org_id={org_id}&team_id={team_id}"
        )
        if isinstance(response, httpx.Response):
            return TeamConcurrency.model_validate(response.json())
        return response

    ################################## Jobs endpoints
    # This is exposed to the Agent in case the user wants to see the links that will click through to the Sauce UI
    async def get_test_assets(self, job_id: str) -> Union[TestAssets, Dict[str, str]]:
        """
        Returns the list of all assets for a test, based on the job ID.
        :param job_id: The Sauce Labs Job ID.
        :return: JSON containing a list of assets, from which the URL can be derived.
        """
        response = await self.sauce_api_call(f"rest/v1/jobs/{job_id}/assets")
        if isinstance(response, httpx.Response):
            return TestAssets.model_validate(response.json())
        return response

    async def get_log_json_file(self, job_id: str) -> Union[TestLog, Dict[str, str]]:
        """
        Shows the complete log of a Sauce Labs test, in structured json format.
        """
        asset_url = await self.get_asset_url(job_id, "sauce-log")
        response = await self.sauce_api_call(asset_url)
        if isinstance(response, httpx.Response):
            return TestLog.model_validate(response.json())
        return response

    async def get_selenium_log_file(self, job_id: str) -> Union[str, Dict[str, str]]:
        """
        Shows the complete log of a Sauce Labs test, in unstructured raw format.
        """
        asset_url = await self.get_asset_url(job_id, "selenium-server.log")
        response = await self.sauce_api_call(asset_url)
        if isinstance(response, httpx.Response):
            return response.json()
        return response

    async def get_network_har_file(self, job_id: str) -> Dict[str, str]:
        """
        Returns the HAR file of network traffic gathered during the test, in structured json format.
        """
        asset_url = await self.get_asset_url(job_id, "network.har")
        response = await self.sauce_api_call(asset_url)
        if isinstance(response, httpx.Response):
            return response.json()
        return response

    async def get_performance_json_file(self, job_id: str) -> Dict[str, str]:
        """
        Returns the Performance log of the test, in structured json format.
        """
        asset_url = await self.get_asset_url(job_id, "performance.json")
        response = await self.sauce_api_call(asset_url)
        if isinstance(response, httpx.Response):
            return response.json()
        return response

    async def get_job_details(self, job_id: str) -> Union[JobDetails, Dict[str, str]]:
        """
        Retrieves the execution details of a particular job, by ID.
        """
        response = await self.sauce_api_call(f"rest/v1/{self.username}/jobs/{job_id}")
        if isinstance(response, httpx.Response):
            return JobDetails.model_validate(response.json())
        return response

    async def get_recent_jobs(
        self, limit: int = 5
    ) -> Union[RecentJobs, Dict[str, str]]:
        """
        Retrieves a list of the most recent jobs run on Sauce Labs for the current user.
        Allows specifying the number of jobs to retrieve, up to a maximum.
        Useful for quickly checking the status of recent test runs.
        :param limit: The upper limit (integer) of jobs to retrieve. Max is 100
        """
        response = await self.sauce_api_call(
            f"rest/v1/{self.username}/jobs?limit={limit}"
        )
        if isinstance(response, httpx.Response):
            return RecentJobs.model_validate(response.json())
        return response

    ################################## Builds endpoints

    async def lookup_builds(self, build_source: str) -> Dict[str, Any]:
        """
        Queries the requesting account and returns a summary of each build matching the query, including the ID value,
        which may be a required parameter of other API calls related to a specific build.You can narrow the results of
        your query using any of the optional filtering parameters.
        :param build_source: The type of device for which you are getting builds. Valid values are: 'rdc' - Real Device
            Builds, 'vdc' - Emulator or Simulator Builds
        """
        response = await self.sauce_api_call(f"v2/builds/{build_source}/")
        data = response.json()

        return data

    async def get_build(self, build_source: str, build_id: str) -> Dict[str, Any]:
        """
        Retrieve the details related to a specific build by passing its unique ID in the request.
        :param build_source: Required. The type of device for which you are getting builds. Valid values are: 'rdc' -
            Real Device Builds, 'vdc' - Emulator or Simulator Builds
        :param build_id: Required. The unique identifier of the build to retrieve. You can look up build IDs in your
            organization using the Lookup Builds endpoint.
        """
        response = await self.sauce_api_call(f"v2/builds/{build_source}/{build_id}/")
        data = response.json()

        return data

    async def get_build_for_job(self, build_source: str, job_id: str) -> Dict[str, Any]:
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
        data = response.json()

        return data

    async def lookup_jobs_in_build(
        self, build_source: str, build_id: str
    ) -> Dict[str, Any]:
        """
        Retrieve the details related to a specific build by passing its unique ID in the request.
        :param build_source: Required. The type of device for which you are getting builds. Valid values are: 'rdc'
            (Real Device Builds), 'vdc' (Emulator or Simulator Builds)
        :param build_id: Required. The unique identifier of the build whose jobs you are looking up. You can look up
            build IDs in your organization using the Lookup Builds endpoint.
        """
        response = await self.sauce_api_call(
            f"v2/builds/{build_source}/{build_id}/jobs/"
        )
        data = response.json()

        return data

    ################################## Sauce Connect endpoints

    async def get_tunnels_for_user(self, username) -> Dict[str, Any]:
        """
        Returns Tunnel IDs or Tunnels Info for any currently running tunnels launched by or shared with the specified
        user. The word "tunnel" in this context refers to usage of the Sauce Connect tool.
        It also allows to filter tunnels using an optional "filter" parameter that may take the following values:
        :param username: Required. The authentication username of the user whose tunnels you are requesting.
        """
        response = await self.sauce_api_call(f"rest/v1/{username}/tunnels")
        data = response.json()

        return data

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
        data = response.json()

        return data

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
        response = await self.sauce_api_call(
            f"rest/v1/{username}/tunnels/{tunnel_id}/num_jobs"
        )
        data = response.json()

        return data

    ################################## Insights endpoints
    async def get_test_analytics(
        self, start: str, end: str
    ) -> Union[TestAnalytics, Dict[str, str]]:
        """
        Return run summary data for all tests that match the request criteria. Good for overall analytics about the requested period, not detailed test results
        :param start: The starting date of the period during which the test runs executed, in YYYY-MM-DDTHH:mm:ssZ (UTC) format.
        :param end: The ending date of the period during which the test runs executed, in YYYY-MM-DDTHH:mm:ssZ (UTC) format.
        """
        response = await self.sauce_api_call(
            f"v1/analytics/tests?start={start}&end={end}"
        )
        if isinstance(response, httpx.Response):
            return TestAnalytics.model_validate(response.json())
        return response

    async def get_test_metrics(
        self, start: str, end: str
    ) -> Union[TestMetrics, Dict[str, str]]:
        """
        Return an aggregate of metric values for runs of a specified test during the specified period.
        :param start: The starting date of the period during which the test runs executed, in YYYY-MM-DDTHH:mm:ssZ (UTC) format.
        :param end: The ending date of the period during which the test runs executed, in YYYY-MM-DDTHH:mm:ssZ (UTC) format.
        """
        response = await self.sauce_api_call(
            f"v1/analytics/insights/test-metrics?start={start}&end={end}"
        )
        if isinstance(response, httpx.Response):
            return TestMetrics.model_validate(response.json())
        return response

    async def get_test_trends(
        self, start: str, end: str, interval: str
    ) -> Union[TestTrends, Dict[str, str]]:
        """
        Return a set of data "buckets" representing tests that were run in each time interval defined by the request parameters.
        This shows test trends over the specified time period, and can help understand an organization/team/user's overall test
        execution efficiency.
        :param start: Required. The starting date of the period during which the test runs executed, in YYYY-MM-DDTHH:mm:ssZ (UTC) format. Default should be '7 days ago'
        :param end: Required. The ending date of the period during which the test runs executed, in YYYY-MM-DDTHH:mm:ssZ (UTC) format. Default should be 'today'
        :param time_range: Required. The amount of time backward from the current time that represents the period during which the test runs are executed. Acceptable units include d (day); h (hour); m (minute); s (second).
        :param interval: Required. Relative date filter. Available values are: 1m, 15m, 1h, 6h, 12h, 1d, 7d, 30d. Defaul is 1d
        """
        response = await self.sauce_api_call(
            f"v1/analytics/trends/tests?start={start}&end={end}&interval={interval}"
        )
        if isinstance(response, httpx.Response):
            return TestTrends.model_validate(response.json())
        return response

    async def get_all_builds_and_tests(
        self, start: str, end: str
    ) -> Union[AllBuildsAndTests, Dict[str, str]]:
        """
        Return the set of all tests run in the specified period, grouped by whether each test was part of a build or not.
        :param start: The starting date of the period during which the test runs executed, in YYYY-MM-DDTHH:mm:ssZ (UTC) format.
        :param end: The ending date of the period during which the test runs executed, in YYYY-MM-DDTHH:mm:ssZ (UTC) format.
        """
        response = await self.sauce_api_call(
            f"v1/analytics/trends/builds_tests?start={start}&end={end}"
        )
        if isinstance(response, httpx.Response):
            return AllBuildsAndTests.model_validate(response.json())
        return response

    ################################## Sauce system metrics

    async def get_sauce_status(self) -> Union[SauceStatus, Dict[str, str]]:
        """
        Returns the current (30 second cache) availability of the Sauce Labs platform. This should tell you whether Sauce is 'up' or 'down'
        """
        response = await self.sauce_api_call("rest/v1/info/status")
        if isinstance(response, httpx.Response):
            return SauceStatus.model_validate(response.json())
        return response

    ################################## Storage endpoints

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


# --- Main Application Setup ---
if __name__ == "__main__":
    # Create the FastMCP server instance
    mcp_server_instance = FastMCP("SauceLabsAgent")

    import os

    SAUCE_ACCESS_KEY = os.getenv("SAUCE_ACCESS_KEY")
    if SAUCE_ACCESS_KEY is None:
        raise ValueError("SAUCE_ACCESS_KEY environment variable is not set.")

    SAUCE_USERNAME = os.getenv("SAUCE_USERNAME")
    if SAUCE_USERNAME is None:
        raise ValueError("SAUCE_USERNAME environment variable is not set.")

    sauce_agent = SauceLabsAgent(mcp_server_instance, SAUCE_ACCESS_KEY, SAUCE_USERNAME)

    # Run the FastMCP server instance
    sys.stderr.write(">>>>>>>>>>>>About to run SauceLabsAgent\n")
    mcp_server_instance.run(transport="stdio")
    sys.stderr.write(">>>>>>>>>>>>Finished running SauceLabsAgent\n")
