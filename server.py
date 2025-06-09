from mcp.server import FastMCP
from typing import Dict, Any, Union  # For type hinting dicts
import httpx
import sys
import logging

from models import TestLog, TestAssets, TeamConcurrency, OrgConcurrency, JobDetails, RecentJobs, TestAnalytics, TestMetrics, TestTrends

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
        data_center: str="us-west-1",
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
        self.mcp.tool()(self.get_account_info)
        self.mcp.tool()(self.get_recent_jobs)
        self.mcp.tool()(self.get_job_details)
        self.mcp.tool()(self.get_test_assets)
        self.mcp.tool()(self.get_log_json_file)
        self.mcp.tool()(self.get_org_concurrency)
        self.mcp.tool()(self.get_team_concurrency)
        self.mcp.tool()(self.get_test_analytics)
        self.mcp.tool()(self.get_test_trends)
        self.mcp.tool()(self.get_test_metrics)
        # self.mcp.tool()(self.get_all_builds_and_tests)
        # self.mcp.tool()(self.get_supported_platforms)
        # self.mcp.tool()(self.get_sauce_status)
        # self.mcp.tool()(self.get_network_har_file)
        # self.mcp.tool()(self.get_performance_json_file)
        # self.mcp.tool()(self.get_selenium_log_file)

        logging.info("SauceAPI client initialized and resource manifest loaded.")

    # Not exposed to the Agent
    async def sauce_api_call(self, relative_endpoint: str, method: str="GET") -> Union[httpx.Response, dict[str, str]]:
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

    # Not exposed to the Agent. We can register if we need to, but it seems better to use the helper method.
    async def get_asset_url(self, job_id: str, asset_key: str) -> str:
        asset_list = await self.get_test_assets(job_id)
        asset_url = getattr(asset_list, asset_key)
        if isinstance(asset_url, str):
            return f"rest/v1/{self.username}/jobs/{job_id}/assets/" + asset_url
        raise ValueError(f"Asset must be string, {asset_key} is type {type(asset_url)}")
        
    # This method populates the Resource at sauce://account
    async def account_info(self) -> Dict[str, str]:
        """
        Retrieves detailed account information for the user associated with this client.
        Refer to `SauceAPI.resource_manifest['account']['methods']['get_account_info']` for full documentation.
        """
        endpoint = f"team-management/v1/users?username={self.username}"
        response = await self.sauce_api_call(endpoint)

        if isinstance(response, httpx.Response):
            return response.json()
        return response

    async def get_account_info(self) -> Dict[str, str]:
        """
        Provides the current user's Sauce Labs account information,
        including username, jobs run, minutes used, and overall account status.
        Useful for a quick overview of account activity.
        """
        account_data = await self.account_info()

        return account_data

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

    async def get_selenium_log_file(self, job_id: str) -> str:
        """
        Shows the complete log of a Sauce Labs test, in unstructured raw format.
        """
        asset_url = await self.get_asset_url(job_id, "selenium-server.log")
        response = await self.sauce_api_call(asset_url)
        return response.json()

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
        return response.json()

    async def get_job_details(self, job_id: str) -> Union[JobDetails, Dict[str, str]]:
        """
        Retrieves the execution details of a particular job, by ID.
        """
        response = await self.sauce_api_call(f"rest/v1/{self.username}/jobs/{job_id}")
        if isinstance(response, httpx.Response):
            return JobDetails.model_validate(response.json())
        return response

    async def get_recent_jobs(self, limit: int = 5) -> Union[RecentJobs, Dict[str, str]]:
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

    async def get_supported_platforms(
        self, automation_api: str = "all"
    ) -> Dict[str, Any]:
        """
        Returns the set of supported operating system and browser combinations for the specified automation framework.
        :param automation_api: The framework for which you are requesting supported platforms. Valid values are: 'all', 'appium', and 'webdriver'. Defaults to 'all'.
        """
        response = await self.sauce_api_call(f"rest/v1/info/platforms/{automation_api}")
        data = response.json()

        return data

    ################################## Insights endpoints
    async def get_test_analytics(self, start: str, end: str) -> Union[TestAnalytics, Dict[str, str]]:
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

    async def get_test_metrics(self, start: str, end: str) -> Union[TestMetrics, Dict[str, str]]:
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

    async def get_all_builds_and_tests(self, start: str, end: str) -> Dict[str, str]:
        """
        Return the set of all tests run in the specified period, grouped by whether each test was part of a build or not.
        :param start: The starting date of the period during which the test runs executed, in YYYY-MM-DDTHH:mm:ssZ (UTC) format.
        :param end: The ending date of the period during which the test runs executed, in YYYY-MM-DDTHH:mm:ssZ (UTC) format.
        """
        response = await self.sauce_api_call(
            f"v1/analytics/trends/builds_tests/test-metrics?start={start}&end={end}"
        )
        # data = response.json()

        return response

    ################################## Sauce system metrics
    async def get_sauce_status(self) -> Union[Dict[str, Any], Dict[str, str]]:
        """
        Returns the current (30 second cache) availability of the Sauce Labs platform. This should tell you whether Sauce is 'up' or 'down'
        """
        response = await self.sauce_api_call("rest/v1/info/status")
        if isinstance(response, httpx.Response):
            return response.json()
        else:
            return response

    async def get_org_concurrency(self, org_id: Union[str, None]) -> Union[OrgConcurrency, Dict[str, str]]:
        """
        Return information about concurrency usage for organization:
        - maximum, minimum concurrency for given granularity (monthly, weekly, daily, hourly),
        - teams' share for the organization maximum concurrency for given granularity (in percentage),
        - current limits.
        :param org_id: Return results only for the specified org_id
        :return: Json report containing org concurrency usage
        """
        if org_id is None:
            account_info = await self.account_info()
            org_id = account_info["results"][0]["organization"]["id"]

        response = await self.sauce_api_call(
            f"usage-analytics/v1/concurrency/org?org_id={org_id}"
        )
        if isinstance(response, httpx.Response):
            return OrgConcurrency.model_validate(response.json())
        return response

    async def get_team_concurrency(self, org_id: str, team_id: str) -> Union[TeamConcurrency, Dict[str, str]]:
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
