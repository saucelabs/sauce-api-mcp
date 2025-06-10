from datetime import datetime
from typing import List, Dict, Optional, Union
from pydantic import BaseModel, Field, RootModel

# --- Nested Models for Request ---


class Browser(BaseModel):
    show_update_promotion_info_bar: bool


class Prefs(BaseModel):
    browser: Browser


class GoogChromeOptionsRequest(BaseModel):
    binary: str
    prefs: Prefs
    args: List[str]


class AlwaysMatch(BaseModel):
    goog_chromeOptions: GoogChromeOptionsRequest = Field(
        ..., alias="goog:chromeOptions"
    )
    browserName: str


class RequestCapabilities(BaseModel):
    alwaysMatch: AlwaysMatch
    # The 'firstMatch' array is empty, so we define it as a list of dictionaries.
    firstMatch: List[Dict[str, str]]


class Request(BaseModel):
    capabilities: RequestCapabilities


# --- Nested Models for Result ---


class GoogChromeOptionsResult(BaseModel):
    debuggerAddress: str


class Timeouts(BaseModel):
    pageLoad: int
    implicit: int
    script: int


class Chrome(BaseModel):
    chromedriverVersion: str
    userDataDir: str


class ResultCapabilities(BaseModel):
    goog_chromeOptions: GoogChromeOptionsResult = Field(..., alias="goog:chromeOptions")
    browserVersion: str
    webauthn_extension_minPinLength: bool = Field(
        ..., alias="webauthn:extension:minPinLength"
    )
    timeouts: Timeouts
    strictFileInteractability: bool
    acceptInsecureCerts: bool
    webauthn_extension_prf: bool = Field(..., alias="webauthn:extension:prf")
    networkConnectionEnabled: bool
    fedcm_accounts: bool = Field(..., alias="fedcm:accounts")
    chrome: Chrome
    browserName: str
    setWindowRect: bool
    # The 'proxy' object is empty, so we define it as an empty dictionary.
    proxy: Dict[str, str]
    webauthn_virtualAuthenticators: bool = Field(
        ..., alias="webauthn:virtualAuthenticators"
    )
    pageLoadStrategy: str
    webauthn_extension_largeBlob: bool = Field(
        ..., alias="webauthn:extension:largeBlob"
    )
    platformName: str
    unhandledPromptBehavior: str
    webauthn_extension_credBlob: bool = Field(..., alias="webauthn:extension:credBlob")


class Result(BaseModel):
    sessionId: str
    capabilities: ResultCapabilities


class TeamShare(BaseModel):
    """
    Represents the concurrency share for a specific team.
    """

    team_id: str
    pct: float
    avg_concurrency: float


class ConcurrencyForOrg(BaseModel):
    """
    Represents the concurrency metrics for a resource.
    """

    max_val: int = Field(..., alias="max")
    min_val: int = Field(..., alias="min")
    max_org_concurrency_team_share: List[TeamShare]


class Concurrency(BaseModel):
    """
    Represents the concurrency metrics for a resource.
    """

    max_val: int = Field(..., alias="max")
    min_val: int = Field(..., alias="min")
    max_org_concurrency_team_share: List[int]


class Limits(BaseModel):
    """
    Represents the concurrency limits for a resource.
    """

    total: int
    resource: int
    total_original: int
    resource_original: int


class OrgValue(BaseModel):
    """
    Represents a specific resource usage data point within a time entry.
    """

    resource_type: str
    concurrency: ConcurrencyForOrg
    limits: Limits


class Value(BaseModel):
    """
    Represents a specific resource usage data point within a time entry.
    """

    resource_type: str
    concurrency: Concurrency
    limits: Limits


class OrgTimeData(BaseModel):
    """
    Represents a timestamped entry containing resource usage values.
    """

    time: datetime
    values: List[OrgValue]


class TimeData(BaseModel):
    """
    Represents a timestamped entry containing resource usage values.
    """

    time: datetime
    values: List[Value]


class TeamData(BaseModel):
    """
    Represents the concurrency data for a specific team.
    """

    team_id: str
    data: List[TimeData]


class ByOrg(BaseModel):
    """
    Represents the concurrency data for a specific organization.
    """

    org_id: str
    data: List[OrgTimeData]


class SauceOptions(BaseModel):
    """
    Represents the 'sauce:options' object within the base configuration.
    """

    name: str
    cyborg: bool = Field(..., alias="_cyborg")
    idle_timeout: int = Field(..., alias="idleTimeout")
    cyborg_start_url: str = Field(..., alias="_cyborg_start_url")
    screen_resolution: str = Field(..., alias="screenResolution")
    avoid_proxy: bool = Field(..., alias="avoidProxy")
    max_duration: int = Field(..., alias="maxDuration")


class BaseConfig(BaseModel):
    """
    Represents the base configuration for a job.
    """

    sauce_options: SauceOptions = Field(..., alias="sauce:options")
    browser_name: str = Field(..., alias="browserName")
    platform_name: str = Field(..., alias="platformName")
    browser_version: str = Field(..., alias="browserVersion")


class CommandCounts(BaseModel):
    """
    Represents the command counts, using aliases for capitalized keys.
    """

    all_commands: int = Field(..., alias="All")
    error: int = Field(..., alias="Error")


class Job(BaseModel):
    """
    Represents a single recent job object.
    """

    status: str
    base_config: BaseConfig
    command_counts: CommandCounts
    deletion_time: Optional[datetime]
    url: Optional[str]
    org_id: str
    creation_time: datetime
    public: str
    team_id: str
    performance_enabled: Optional[bool]
    assigned_tunnel_id: Optional[str]
    container: bool
    id: str
    breakpointed: Optional[bool]


class TestAnalyticsItem(BaseModel):
    """
    Represents a single test item from the analytics endpoint.
    """

    ancestor: str
    browser: str
    browser_normalized: str
    build: str
    creation_time: datetime
    details_url: str
    duration: int
    end_time: datetime
    error: str
    id: str
    name: str
    org_id: Optional[str] = None
    os: str
    os_normalized: str
    owner: str
    start_time: datetime
    status: str


class Meta(BaseModel):
    """
    Represents the meta object containing response metadata.
    """

    status: int


class RunSummary(BaseModel):
    """
    Represents the summary data for a single test run (e.g., fastest or slowest).
    """

    ancestor: str
    browser: str
    browser_normalized: str
    build: str
    creation_time: datetime
    details_url: str
    duration: int
    end_time: datetime
    error: str
    id: str
    name: str
    org_id: str
    os: str
    os_normalized: str
    owner: str
    start_time: datetime
    status: str


class Statuses(BaseModel):
    """
    Represents the breakdown of test statuses.
    """

    error: int
    failed: int
    passed: int
    complete: Optional[int] = None


class Aggregations(BaseModel):
    """
    Represents the main aggregation data.
    """

    count: int
    fastestRun: RunSummary
    slowestRun: RunSummary
    statuses: Statuses
    totalQueueTime: float
    totalRunTime: float
    avgRunTime: Optional[float] = None


class NameCount(BaseModel):
    """
    A reusable model for objects containing a name and a count.
    """

    name: str
    count: int


class TrendsAggregations(BaseModel):
    """
    Represents the aggregation data within a single bucket.
    """

    browser: List[NameCount]
    browser_error: List[NameCount] = Field(..., alias="browserError")
    browser_fail: List[NameCount] = Field(..., alias="browserFail")
    device: List[NameCount]
    device_error: List[NameCount] = Field(..., alias="deviceError")
    device_fail: List[NameCount] = Field(..., alias="deviceFail")
    error_message: List[NameCount] = Field(..., alias="errorMessage")
    framework: List[NameCount]
    framework_error: List[NameCount] = Field(..., alias="frameworkError")
    framework_fail: List[NameCount] = Field(..., alias="frameworkFail")
    os: List[NameCount]
    os_error: List[NameCount] = Field(..., alias="osError")
    os_fail: List[NameCount] = Field(..., alias="osFail")
    owner: List[NameCount]
    status: List[NameCount]


class Bucket(BaseModel):
    """
    Represents a single time-stamped bucket of data.
    """

    timestamp: int
    datetime: datetime
    count: int
    aggs: TrendsAggregations


class ResultItem(BaseModel):
    """
    Represents a single result item within the account information.
    """

    id: str
    name: str
    # Assuming the settings object can contain various basic value types.
    settings: Dict[str, Union[str, int, bool, None]]
    # Assuming the group object can also contain various basic value types.
    group: Dict[str, Union[str, int, bool, None]]
    is_default: bool
    org_uuid: str
    user_count: int


class Platform(BaseModel):
    """
    Represents a single supported platform configuration.
    """

    short_version: str
    long_name: str
    api_name: str
    long_version: str
    device: str
    latest_stable_version: str
    automation_backend: str
    os: str
    # Optional fields that only appear for certain automation backends
    deprecated_backend_versions: Optional[List[str]] = None
    recommended_backend_version: Optional[str] = None
    supported_backend_versions: Optional[List[str]] = None


class TestItem(BaseModel):
    """
    Represents a single test object.
    """

    id: str
    owner: str
    ancestor: str
    name: str
    creation_time: datetime
    end_time: datetime
    status: str
    error: str
    os: str
    browser: str
    details_url: str


class BuildAggregations(BaseModel):
    """
    Represents the aggregation data for a single build.
    """

    status: List[NameCount]


class BuildItem(BaseModel):
    """
    Represents a single build, including a list of its tests.
    """

    name: str
    tests_count: int
    duration: int
    start_time: datetime
    end_time: datetime
    tests: List[TestItem]
    has_more: Optional[bool] = None
    aggs: BuildAggregations


class Builds(BaseModel):
    """
    Represents the container for build items.
    """

    items: List[BuildItem]
    has_more: bool


class TestsMissingBuild(BaseModel):
    """
    Represents tests that are not associated with any build.
    """

    items: List[TestItem]
    has_more: bool


# --- Main Pydantic Models ---


class TestLog(BaseModel):
    """
    Represents a log entry from a test session.
    """

    screenshot: int
    # 'suggestion_values' is an empty list in the example. Assuming a list of strings.
    # This may need to be adjusted if the actual type is different.
    suggestion_values: List[str]
    start_time: float
    request: Request
    result: Result
    duration: float
    path: str
    hide_from_ui: bool
    # 'between_commands' is null in the example. Assuming it could be a string if not null.
    # This may need to be adjusted based on possible non-null values.
    between_commands: Optional[str]
    visual_command: bool
    HTTPStatus: int
    # 'suggestion' is null in the example. Assuming it could be a string if not null.
    suggestion: Optional[str]
    request_id: str
    in_video_timeline: float
    method: str
    statusCode: int


class TestAssets(BaseModel):
    """
    A Pydantic model to represent the asset files for a test.
    """

    # Use Field with an alias for keys that are not valid Python identifiers
    video_mp4: str = Field(..., alias="video.mp4")
    selenium_log: str = Field(..., alias="selenium-log")
    sauce_log: str = Field(..., alias="sauce-log")

    # Standard field for 'video'
    video: str

    # 'cdp-log' can be null, so it's defined as Optional
    cdp_log: Optional[str] = Field(..., alias="cdp-log")

    # 'screenshots' is a list of strings
    screenshots: List[str]


class TeamConcurrency(BaseModel):
    """
    The main model for the team concurrency report.
    """

    by_team: List[TeamData]


class OrgConcurrency(BaseModel):
    """
    The main model for the organization-level concurrency report.
    """

    by_org: ByOrg


class JobDetails(BaseModel):
    """
    A Pydantic model representing the details of a Sauce Labs job.
    """

    browser_short_version: str
    video_url: str
    creation_time: datetime
    # 'custom-data' can be null and is not a valid Python identifier, so we use an alias.
    # Assuming it's a dictionary of key-value pairs if not null.
    custom_data: Optional[Dict[str, str]] = Field(..., alias="custom-data")
    browser_version: str
    owner: str
    automation_backend: str
    id: str
    collects_automator_log: bool
    record_screenshots: bool
    record_video: bool
    build: Optional[str]
    passed: Optional[bool]
    public: str
    assigned_tunnel_id: Optional[str]
    status: str
    log_url: str
    start_time: datetime
    proxied: bool
    modification_time: datetime
    tags: List[str]
    name: str
    commands_not_successful: int
    consolidated_status: str
    selenium_version: Optional[str]
    manual: bool
    end_time: datetime
    error: Optional[str]
    os: str
    breakpointed: Optional[bool]
    browser: str


class RecentJobs(RootModel[List[Job]]):
    """
    The root model representing a list of recent jobs.
    """

    root: List[Job]


class TestAnalytics(BaseModel):
    """
    The main model for the test analytics response.
    """

    has_more: bool
    items: List[TestAnalyticsItem]
    meta: Meta


class TestMetrics(BaseModel):
    """
    The main model for the test metrics response.
    """

    meta: Meta
    aggs: Aggregations


class TestTrends(BaseModel):
    """
    The main model for the test trends analytics report.
    """

    meta: Meta
    buckets: List[Bucket]
    metrics: Dict[str, Dict[str, int]]


class AccountInfo(BaseModel):
    """
    The main model for the account information response.
    """

    # Assuming links is a dictionary of string keys and URL string values.
    links: Dict[str, str]
    count: int
    results: List[ResultItem]


class SupportedPlatforms(RootModel[List[Platform]]):
    """
    The root model representing a list of supported platforms.
    """

    root: List[Platform]


class AllBuildsAndTests(BaseModel):
    """
    The main model for the builds and tests response.
    """

    meta: Meta
    builds: Builds
    tests_missing_build: TestsMissingBuild


class SauceStatus(BaseModel):
    """
    Represents the basic service status.
    """

    wait_time: float
    service_operational: bool
    status_message: str
