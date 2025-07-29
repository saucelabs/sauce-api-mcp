import sys
from typing import Optional, Dict, Any, Union

import os
import httpx
import yaml
from fastmcp import FastMCP
import logging

DATA_CENTERS = {
    "US_WEST": "https://api.us-west-1.saucelabs.com/",
    "US_EAST": "https://api.us-east-4.saucelabs.com/",
    "EU_CENTRAL": "https://api.eu-central-1.saucelabs.com/",
}

class SauceLabsRDCAgent:
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

        # Device & Session Management
        self.mcp.tool()(self.list_device_status)
        self.mcp.tool()(self.list_device_sessions)
        self.mcp.tool()(self.get_session_details)
        self.mcp.tool()(self.allocate_device_and_create_session)
        self.mcp.tool()(self.close_device_session)

        # Network Proxy - HTTP Methods
        self.mcp.tool()(self.forward_http_get)
        self.mcp.tool()(self.forward_http_post)
        self.mcp.tool()(self.forward_http_put)
        self.mcp.tool()(self.forward_http_delete)
        self.mcp.tool()(self.forward_http_options)
        self.mcp.tool()(self.forward_http_head)

        # App Management
        self.mcp.tool()(self.install_app_from_storage)
        self.mcp.tool()(self.list_app_installations)
        self.mcp.tool()(self.launch_app)

        # Device control
        self.mcp.tool()(self.execute_shell_command)

        # Browser/URL Control
        self.mcp.tool()(self.open_url_or_deeplink)
        logging.info("SauceAPI client initialized and resource manifest loaded.")

    # Not exposed to the Agent
    async def sauce_api_call(
            self,
            relative_endpoint: str,
            method: str = "GET",
            params: Optional[dict] = None,
            json: Optional[dict] = None
    ) -> Union[httpx.Response, dict[str, str]]:
        try:
            # Always add the ai parameter
            all_params = params or {}
            all_params['ai'] = 'rdc_mcp'

            response = await self.client.request(
                method,
                relative_endpoint,
                params=all_params,
                json=json
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

    async def list_device_status(
            self,
            state: Optional[str] = None,
            privateOnly: Optional[bool] = None,
            deviceName: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Lists the current status of all devices. For private devices, additional details are available,
        including the precise state and current user. The data reflects the device state with a maximum
        delay of 1 second at the 99th percentile (p99).

        :param state: Optional. Filter by device state (AVAILABLE, IN_USE, CLEANING, REBOOTING, MAINTENANCE, OFFLINE)
        :param privateOnly: Optional. Show only private devices for the authenticated customer
        :param deviceName: Optional. Filter by device identifier (can be regex pattern)
        """

        # Build query parameters
        params = {}
        if state is not None:
            valid_states = ["AVAILABLE", "IN_USE", "CLEANING", "REBOOTING", "MAINTENANCE", "OFFLINE"]
            if state not in valid_states:
                return {
                    "error": f"Invalid state: {state}",
                    "valid_states": valid_states,
                    "suggestions": [
                        "Use one of the valid state values",
                        "States are case-sensitive",
                        "Leave empty to get all devices"
                    ]
                }
            params["state"] = state

        if privateOnly is not None:
            params["privateOnly"] = str(privateOnly).lower()

        if deviceName is not None:
            params["deviceName"] = deviceName

        response = await self.sauce_api_call("rdc/v2/devices/status", params=params)

        if response.status_code == 401:
            return {
                "error": "Not authorized to access device status",
                "possible_reasons": [
                    "Invalid or expired authentication credentials",
                    "Insufficient permissions for device access",
                    "Account does not have RDC access enabled"
                ],
                "suggestions": [
                    "Verify your Sauce Labs credentials",
                    "Check your account permissions",
                    "Contact support if RDC access is needed"
                ]
            }

        return response.json()

    async def list_device_sessions(
            self,
            state: Optional[str] = None,
            deviceName: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves a list of device sessions, including pending, active and recently closed sessions.

        :param state: Optional. Filter sessions by state (PENDING, CREATING, ACTIVE, CLOSING, CLOSED, ERRORED)
        :param deviceName: Optional. Filter sessions by device identifier (can be regex pattern)
        """

        # Build query parameters
        params = {}
        if state is not None:
            valid_states = ["PENDING", "CREATING", "ACTIVE", "CLOSING", "CLOSED", "ERRORED"]
            if state not in valid_states:
                return {
                    "error": f"Invalid state: {state}",
                    "valid_states": valid_states,
                    "suggestions": [
                        "Use one of the valid session states",
                        "States are case-sensitive",
                        "Leave empty to get all sessions"
                    ]
                }
            params["state"] = state

        if deviceName is not None:
            params["deviceName"] = deviceName

        response = await self.sauce_api_call("rdc/v2/sessions", params=params)

        if isinstance(response, dict):
            return response

        # Handle httpx.Response object
        if response.status_code == 401:
            return {
                "error": "Not authorized to access device sessions",
                "possible_reasons": [
                    "Invalid or expired authentication credentials",
                    "Insufficient permissions for session access",
                    "Account does not have RDC session access enabled"
                ],
                "suggestions": [
                    "Verify your Sauce Labs credentials",
                    "Check your account permissions",
                    "Contact support if RDC session access is needed"
                ]
            }

        return response.json()

    async def get_session_details(self, sessionId: str) -> Dict[str, Any]:
        """
        Get details of a specific device session

        :param sessionId: Required. The id of the device session
        """

        response = await self.sauce_api_call(f"rdc/v2/sessions/{sessionId}")

        if isinstance(response, dict):
            return response

        if response.status_code == 404:
            return {
                "error": f"Session not found: {sessionId}",
                "session_id": sessionId,
                "possible_reasons": [
                    "Session ID does not exist",
                    "Session has been deleted",
                    "Insufficient permissions to access this session"
                ],
                "suggestions": [
                    "Use list_device_sessions to find available sessions",
                    "Verify session ID is correct",
                    "Check if session has expired or been closed"
                ]
            }

        if response.status_code == 401:
            return {
                "error": "Not authorized to access session details",
                "possible_reasons": [
                    "Invalid or expired authentication credentials",
                    "Insufficient permissions for session access"
                ],
                "suggestions": [
                    "Verify your Sauce Labs credentials",
                    "Check your account permissions"
                ]
            }

        return response.json()


    async def forward_http_get(
            self,
            sessionId: str,
            targetHost: str,
            targetPort: str,
            targetPath: str
    ) -> Dict[str, Any]:
        """
        Forward a single GET request via a proxy running on the device. Transparently forwards
        the provided GET request and proxies the response from the server as the proxy in the
        device receives it.

        :param sessionId: Required. The id of the device session
        :param targetHost: Required. The target host to make the request to
        :param targetPort: Required. The port the target host is listening on
        :param targetPath: Required. The path to make the request to (can contain query parameters)
        """

        endpoint = f"rdc/v2/sessions/{sessionId}/device/proxy/http/{targetHost}/{targetPort}/{targetPath}"
        response = await self.sauce_api_call(endpoint, method="GET")

        if isinstance(response, dict):
            return response

        if response.status_code == 400:
            # Try to determine if it's device state vs bad parameters
            try:
                error_details = response.json()
                error_title = error_details.get("title", "").lower()

                if "device not ready" in error_title or "session" in error_title:
                    return {
                        "error": "Device session not ready for proxy requests",
                        "session_id": sessionId,
                        "possible_reasons": [
                            "Device session is in PENDING or CREATING state",
                            "Device is still initializing",
                            "Session has not reached ACTIVE state"
                        ],
                        "suggestions": [
                            "Wait for session to become ACTIVE",
                            "Check session state with get_session_details",
                            "Retry after a few seconds"
                        ]
                    }
                else:
                    return {
                        "error": "Invalid request parameters",
                        "target": f"{targetHost}:{targetPort}{targetPath}",
                        "possible_reasons": [
                            "Invalid host name or IP address",
                            "Port number out of range or invalid",
                            "Malformed target path"
                        ],
                        "suggestions": [
                            "Verify target host is a valid hostname or IP",
                            "Ensure port is between 1-65535",
                            "Check target path format"
                        ]
                    }
            except:
                return {
                    "error": "Bad request - unable to proxy GET request",
                    "session_id": sessionId,
                    "target": f"{targetHost}:{targetPort}{targetPath}"
                }

        if response.status_code == 404:
            return {
                "error": f"Session not found: {sessionId}",
                "session_id": sessionId,
                "possible_reasons": [
                    "Session ID does not exist",
                    "Session has been closed or expired"
                ],
                "suggestions": [
                    "Use list_device_sessions to find active sessions",
                    "Create a new session if needed"
                ]
            }

        if response.status_code == 429:
            return {
                "error": "Too many concurrent proxy requests",
                "possible_reasons": [
                    "Rate limit exceeded for proxy requests",
                    "Too many simultaneous connections to target"
                ],
                "suggestions": [
                    "Wait before making additional requests",
                    "Reduce request frequency",
                    "Use fewer concurrent connections"
                ]
            }

        if response.status_code == 401:
            return {
                "error": "Not authorized for proxy requests",
                "possible_reasons": [
                    "Invalid or expired authentication credentials",
                    "Account does not have proxy access enabled"
                ],
                "suggestions": [
                    "Verify your Sauce Labs credentials",
                    "Check if proxy features are enabled for your account"
                ]
            }

        return response.json()


    async def forward_http_post(
            self,
            sessionId: str,
            targetHost: str,
            targetPort: str,
            targetPath: str,
            data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Forward a single POST request via a proxy running on the device.

        :param sessionId: Required. The id of the device session
        :param targetHost: Required. The target host to make the request to
        :param targetPort: Required. The port the target host is listening on
        :param targetPath: Required. The path to make the request to
        :param data: Optional. JSON data to send in POST body
        """

        endpoint = f"rdc/v2/sessions/{sessionId}/device/proxy/http/{targetHost}/{targetPort}/{targetPath}"
        response = await self.sauce_api_call(endpoint, method="POST", json=data)

        if isinstance(response, dict):
            return response

        if response.status_code == 400:
            try:
                error_details = response.json()
                error_title = error_details.get("title", "").lower()

                if "device not ready" in error_title or "session" in error_title:
                    return {
                        "error": "Device session not ready for proxy requests",
                        "session_id": sessionId,
                        "possible_reasons": [
                            "Device session is in PENDING or CREATING state",
                            "Device is still initializing"
                        ],
                        "suggestions": [
                            "Wait for session to become ACTIVE",
                            "Check session state with get_session_details"
                        ]
                    }
                else:
                    return {
                        "error": "Invalid request parameters or data",
                        "target": f"{targetHost}:{targetPort}{targetPath}",
                        "possible_reasons": [
                            "Invalid host, port, or path",
                            "Malformed JSON data",
                            "Content-Type issues"
                        ],
                        "suggestions": [
                            "Verify target parameters",
                            "Validate JSON data structure",
                            "Check if target endpoint accepts JSON"
                        ]
                    }
            except:
                return {
                    "error": "Bad request - unable to proxy POST request",
                    "session_id": sessionId,
                    "target": f"{targetHost}:{targetPort}{targetPath}"
                }

        # Same 404, 429, 401 handling as GET
        if response.status_code == 404:
            return {
                "error": f"Session not found: {sessionId}",
                "session_id": sessionId,
                "possible_reasons": ["Session ID does not exist", "Session has been closed"],
                "suggestions": ["Use list_device_sessions to find active sessions"]
            }

        if response.status_code == 429:
            return {"error": "Too many concurrent proxy requests"}

        if response.status_code == 401:
            return {"error": "Not authorized for proxy requests"}

        return response.json()

    async def forward_http_put(
            self,
            sessionId: str,
            targetHost: str,
            targetPort: str,
            targetPath: str,
            data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Forward a single PUT request via a proxy running on the device.
        """
        endpoint = f"rdc/v2/sessions/{sessionId}/device/proxy/http/{targetHost}/{targetPort}/{targetPath}"
        response = await self.sauce_api_call(endpoint, method="PUT", json=data)

        if isinstance(response, dict):
            return response

        # Same error handling pattern as POST
        if response.status_code == 400:
            try:
                error_details = response.json()
                error_title = error_details.get("title", "").lower()

                if "device not ready" in error_title or "session" in error_title:
                    return {
                        "error": "Device session not ready for proxy requests",
                        "session_id": sessionId
                    }
                else:
                    return {
                        "error": "Invalid request parameters or data",
                        "target": f"{targetHost}:{targetPort}{targetPath}"
                    }
            except:
                return {"error": "Bad request - unable to proxy PUT request"}

        if response.status_code == 404:
            return {"error": f"Session not found: {sessionId}"}
        if response.status_code == 429:
            return {"error": "Too many concurrent proxy requests"}
        if response.status_code == 401:
            return {"error": "Not authorized for proxy requests"}

        return response.json()


    async def forward_http_delete(
            self,
            sessionId: str,
            targetHost: str,
            targetPort: str,
            targetPath: str
    ) -> Dict[str, Any]:
        """
        Forward a single DELETE request via a proxy running on the device.
        """
        endpoint = f"rdc/v2/sessions/{sessionId}/device/proxy/http/{targetHost}/{targetPort}/{targetPath}"
        response = await self.sauce_api_call(endpoint, method="DELETE")

        if isinstance(response, dict):
            return response

        # Same error handling as GET (no body data)
        if response.status_code == 400:
            try:
                error_details = response.json()
                error_title = error_details.get("title", "").lower()

                if "device not ready" in error_title:
                    return {"error": "Device session not ready for proxy requests"}
                else:
                    return {"error": "Invalid request parameters"}
            except:
                return {"error": "Bad request - unable to proxy DELETE request"}

        if response.status_code == 404:
            return {"error": f"Session not found: {sessionId}"}
        if response.status_code == 429:
            return {"error": "Too many concurrent proxy requests"}
        if response.status_code == 401:
            return {"error": "Not authorized for proxy requests"}

        return response.json()


    async def forward_http_options(
            self,
            sessionId: str,
            targetHost: str,
            targetPort: str,
            targetPath: str
    ) -> Dict[str, Any]:
        """
        Forward a single OPTIONS request via a proxy running on the device.
        """
        endpoint = f"rdc/v2/sessions/{sessionId}/device/proxy/http/{targetHost}/{targetPort}/{targetPath}"
        response = await self.sauce_api_call(endpoint, method="OPTIONS")

        if isinstance(response, dict):
            return response

        # Same error handling as GET
        if response.status_code == 400:
            try:
                error_details = response.json()
                if "device not ready" in error_details.get("title", "").lower():
                    return {"error": "Device session not ready for proxy requests"}
                else:
                    return {"error": "Invalid request parameters"}
            except:
                return {"error": "Bad request - unable to proxy OPTIONS request"}

        if response.status_code == 404:
            return {"error": f"Session not found: {sessionId}"}
        if response.status_code == 429:
            return {"error": "Too many concurrent proxy requests"}
        if response.status_code == 401:
            return {"error": "Not authorized for proxy requests"}

        return response.json()

    async def forward_http_head(
            self,
            sessionId: str,
            targetHost: str,
            targetPort: str,
            targetPath: str
    ) -> Dict[str, Any]:
        """
        Forward a single HEAD request via a proxy running on the device.
        """
        endpoint = f"rdc/v2/sessions/{sessionId}/device/proxy/http/{targetHost}/{targetPort}/{targetPath}"
        response = await self.sauce_api_call(endpoint, method="HEAD")

        if isinstance(response, dict):
            return response

        # Same error handling as GET
        if response.status_code == 400:
            try:
                error_details = response.json()
                if "device not ready" in error_details.get("title", "").lower():
                    return {"error": "Device session not ready for proxy requests"}
                else:
                    return {"error": "Invalid request parameters"}
            except:
                return {"error": "Bad request - unable to proxy HEAD request"}

        if response.status_code == 404:
            return {"error": f"Session not found: {sessionId}"}
        if response.status_code == 429:
            return {"error": "Too many concurrent proxy requests"}
        if response.status_code == 401:
            return {"error": "Not authorized for proxy requests"}

        return response.json()


    async def allocate_device_and_create_session(
            self,
            deviceName: Optional[str] = None,
            os: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a new device session by allocating a device.

        :param deviceName: Optional. Specify a device for the session (can be specific ID or regex pattern)
        :param os: Optional. Filter by operating system (android or ios, case insensitive)
        """

        data = {}
        if deviceName is not None or os is not None:
            device_config = {}
            if deviceName is not None:
                device_config["deviceName"] = deviceName
            if os is not None:
                valid_os = ["android", "ios"]
                if os.lower() not in valid_os:
                    return {
                        "error": f"Invalid OS: {os}",
                        "valid_os": valid_os,
                        "suggestions": [
                            "Use 'android' or 'ios'",
                            "OS parameter is case insensitive",
                            "Leave empty to allow any OS"
                        ]
                    }
                device_config["os"] = os.lower()
            data["device"] = device_config

        response = await self.sauce_api_call("rdc/v2/sessions", method="POST", json=data)

        if isinstance(response, dict):
            return response

        if response.status_code == 400:
            try:
                error_details = response.json()
                error_title = error_details.get("title", "")
                error_detail = error_details.get("detail", "")

                if "does not exist" in error_detail:
                    return {
                        "error": "Device does not exist",
                        "device_name": deviceName,
                        "possible_reasons": [
                            "Device ID or pattern does not match any available devices",
                            "Device is not available in your data center",
                            "Typo in device name"
                        ],
                        "suggestions": [
                            "Use list_device_status to see available devices",
                            "Check device name spelling",
                            "Try a broader device pattern or leave empty for any device"
                        ]
                    }
                else:
                    return {
                        "error": "Bad request for session creation",
                        "details": error_detail,
                        "possible_reasons": [
                            "Invalid device configuration",
                            "No devices available matching criteria",
                            "Account limits exceeded"
                        ],
                        "suggestions": [
                            "Check available devices with list_device_status",
                            "Verify account has available device slots",
                            "Try different device criteria"
                        ]
                    }
            except:
                return {
                    "error": "Bad request - unable to create session",
                    "device_criteria": {"deviceName": deviceName, "os": os}
                }

        if response.status_code == 401:
            return {
                "error": "Not authorized to create device sessions",
                "possible_reasons": [
                    "Invalid or expired authentication credentials",
                    "Account does not have device session creation permissions"
                ],
                "suggestions": [
                    "Verify your Sauce Labs credentials",
                    "Check account permissions for device access"
                ]
            }

        return response.json()


    async def close_device_session(
            self,
            sessionId: str,
            rebootDevice: Optional[bool] = False
    ) -> Dict[str, Any]:
        """
        Close and release a device session

        :param sessionId: Required. The id of the device session
        :param rebootDevice: Optional. Perform a device reboot after session release (only for private devices)
        """

        params = {}
        if rebootDevice is not None:
            params["rebootDevice"] = str(rebootDevice).lower()

        response = await self.sauce_api_call(f"rdc/v2/sessions/{sessionId}", method="DELETE", params=params)

        if isinstance(response, dict):
            return response

        if response.status_code == 400:
            try:
                error_details = response.json()
                error_detail = error_details.get("detail", "")

                if "does not exist" in error_detail:
                    return {
                        "error": "Session does not exist",
                        "session_id": sessionId,
                        "possible_reasons": [
                            "Session ID is invalid",
                            "Session has already been closed"
                        ],
                        "suggestions": [
                            "Verify session ID is correct",
                            "Use list_device_sessions to see active sessions"
                        ]
                    }
                else:
                    return {
                        "error": "Bad request for session closure",
                        "session_id": sessionId,
                        "details": error_detail
                    }
            except:
                return {
                    "error": "Bad request - unable to close session",
                    "session_id": sessionId
                }

        if response.status_code == 404:
            return {
                "error": f"Session not found: {sessionId}",
                "session_id": sessionId,
                "possible_reasons": [
                    "Session ID does not exist",
                    "Session has already been closed or expired"
                ],
                "suggestions": [
                    "Verify session ID is correct",
                    "Use list_device_sessions to see available sessions"
                ]
            }

        return response.json()


    async def install_app_from_storage(
            self,
            sessionId: str,
            app: str,
            enableInstrumentation: bool = True,
            launchAfterInstall: bool = False,
            features: Optional[Dict[str, bool]] = None
    ) -> Dict[str, Any]:
        """
        Install an app on the device from Sauce Labs App Storage. The installation takes place
        in the background. Use list_app_installations to query for status.

        :param sessionId: Required. The id of the device session
        :param app: Required. Location of app in Sauce Labs App Storage (e.g., storage:filename=myapp.apk or storage:uuid)
        :param enableInstrumentation: Optional. Controls app instrumentation and re-signing (default: True)
        :param launchAfterInstall: Optional. Automatically launch app after successful installation (default: False)
        :param features: Optional. Dict of advanced features to enable (biometricsInterception, networkCapture, etc.)
        """

        data = {
            "app": app,
            "enableInstrumentation": enableInstrumentation,
            "launchAfterInstall": launchAfterInstall
        }

        if features is not None:
            # Validate feature flags
            valid_features = [
                "biometricsInterception", "bypassScreenshotRestriction", "deviceVitals",
                "errorReporting", "imageInjection", "networkCapture"
            ]
            invalid_features = [f for f in features.keys() if f not in valid_features]
            if invalid_features:
                return {
                    "error": f"Invalid features: {invalid_features}",
                    "valid_features": valid_features,
                    "suggestions": [
                        "Use only supported feature flags",
                        "Check feature name spelling",
                        "Some features may be platform-specific"
                    ]
                }
            data["features"] = features

        response = await self.sauce_api_call(f"rdc/v2/sessions/{sessionId}/device/installApp", method="POST", json=data)

        if isinstance(response, dict):
            return response

        if response.status_code == 400:
            try:
                error_details = response.json()
                error_detail = error_details.get("detail", "")

                if "Device not ready" in error_detail:
                    return {
                        "error": "Device session not ready for app installation",
                        "session_id": sessionId,
                        "possible_reasons": [
                            "Session is not in ACTIVE state",
                            "Device is still initializing"
                        ],
                        "suggestions": [
                            "Wait for session to become ACTIVE",
                            "Check session state with get_session_details"
                        ]
                    }
                elif "storage:" not in app:
                    return {
                        "error": "Invalid app reference format",
                        "app": app,
                        "possible_reasons": [
                            "App reference must use storage: format",
                            "App may not exist in App Storage"
                        ],
                        "suggestions": [
                            "Use format: storage:filename=myapp.apk",
                            "Or use: storage:uuid-string",
                            "Verify app exists in Sauce Labs App Storage"
                        ]
                    }
                else:
                    return {
                        "error": "Bad request for app installation",
                        "session_id": sessionId,
                        "app": app,
                        "details": error_detail
                    }
            except:
                return {
                    "error": "Bad request - unable to install app",
                    "session_id": sessionId,
                    "app": app
                }

        if response.status_code == 404:
            return {
                "error": f"Session not found: {sessionId}",
                "session_id": sessionId,
                "suggestions": ["Verify session ID and ensure session is active"]
            }

        return response.json()


    async def list_app_installations(self, sessionId: str) -> Dict[str, Any]:
        """
        List ongoing, completed and failed app installations

        :param sessionId: Required. The id of the device session
        """

        response = await self.sauce_api_call(f"rdc/v2/sessions/{sessionId}/device/listAppInstallations")

        if isinstance(response, dict):
            return response

        if response.status_code == 400:
            return {
                "error": "Bad request for app installations list",
                "session_id": sessionId,
                "possible_reasons": [
                    "Session is not in proper state",
                    "Invalid session ID format"
                ],
                "suggestions": [
                    "Check session state with get_session_details",
                    "Verify session ID is correct"
                ]
            }

        if response.status_code == 404:
            return {
                "error": f"Session not found: {sessionId}",
                "session_id": sessionId,
                "suggestions": ["Verify session ID and ensure session exists"]
            }

        return response.json()


    async def launch_app(
            self,
            sessionId: str,
            packageName: Optional[str] = None,
            activityName: Optional[str] = None,
            bundleId: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Launch an app on device

        :param sessionId: Required. The id of the device session
        :param packageName: Optional. Package Name of app to launch (Android)
        :param activityName: Optional. Main Activity Name of app to launch (Android)
        :param bundleId: Optional. Bundle identifier (iOS)
        """

        data = {}

        # Validate platform-specific parameters
        if bundleId and (packageName or activityName):
            return {
                "error": "Cannot specify both iOS (bundleId) and Android (packageName/activityName) parameters",
                "suggestions": [
                    "For iOS: use only bundleId",
                    "For Android: use packageName and optionally activityName"
                ]
            }

        if not bundleId and not packageName:
            return {
                "error": "Must specify either bundleId (iOS) or packageName (Android)",
                "suggestions": [
                    "For iOS apps: provide bundleId (e.g., com.apple.calculator)",
                    "For Android apps: provide packageName (e.g., com.android.calculator)"
                ]
            }

        if packageName:
            data["packageName"] = packageName
        if activityName:
            data["activityName"] = activityName
        if bundleId:
            data["bundleId"] = bundleId

        response = await self.sauce_api_call(f"rdc/v2/sessions/{sessionId}/device/launchApp", method="POST", json=data)

        if isinstance(response, dict):
            return response

        if response.status_code == 400:
            try:
                error_details = response.json()
                error_detail = error_details.get("detail", "")

                if "Device not ready" in error_detail:
                    return {
                        "error": "Device session not ready for app launch",
                        "session_id": sessionId,
                        "possible_reasons": [
                            "Session is not in ACTIVE state",
                            "App is not installed on device"
                        ],
                        "suggestions": [
                            "Ensure session is ACTIVE",
                            "Install app first using install_app_from_storage",
                            "Verify app identifier is correct"
                        ]
                    }
                else:
                    return {
                        "error": "Bad request for app launch",
                        "session_id": sessionId,
                        "app_identifier": bundleId or packageName,
                        "details": error_detail,
                        "possible_reasons": [
                            "App not found on device",
                            "Invalid app identifier",
                            "App launch permissions denied"
                        ],
                        "suggestions": [
                            "Verify app is installed on device",
                            "Check app identifier spelling",
                            "Ensure app has launch permissions"
                        ]
                    }
            except:
                return {
                    "error": "Bad request - unable to launch app",
                    "session_id": sessionId
                }

        if response.status_code == 404:
            return {
                "error": f"Session not found: {sessionId}",
                "session_id": sessionId
            }
        
        # Success returns 204 No Content
        if response.status_code == 204:
            return {
                "success": True,
                "message": "App opened successfully",
                "session_id": sessionId,
                "app": data
            }

        return response.json()


    async def open_url_or_deeplink(
            self,
            sessionId: str,
            url: str
    ) -> Dict[str, Any]:
        """
        Open a URL through browser or a deeplink to an app. Depending on the scheme,
        the OS will decide how to open the URL. 'https:' is usually handled by the browser,
        'tel:' opens the telephone. Custom schemes can open specific apps.
        Note: Currently deeplinking is only supported for iOS; Android opens everything in Chrome.

        :param sessionId: Required. The id of the device session
        :param url: Required. The URL to open (can include custom schemes)
        """

        data = {"url": url}

        # Basic URL validation
        if not url or not isinstance(url, str):
            return {
                "error": "Invalid URL provided",
                "url": url,
                "suggestions": [
                    "Provide a valid URL string",
                    "URLs can use http://, https://, tel:, or custom schemes",
                    "Example: https://example.com or myapp://deeplink"
                ]
            }

        response = await self.sauce_api_call(f"rdc/v2/sessions/{sessionId}/device/openUrl", method="POST", json=data)

        if isinstance(response, dict):
            return response

        if response.status_code == 400:
            try:
                error_details = response.json()
                error_detail = error_details.get("detail", "")

                if "Device not ready" in error_detail:
                    return {
                        "error": "Device session not ready for URL navigation",
                        "session_id": sessionId,
                        "possible_reasons": [
                            "Session is not in ACTIVE state",
                            "Device is still initializing"
                        ],
                        "suggestions": [
                            "Wait for session to become ACTIVE",
                            "Check session state with get_session_details"
                        ]
                    }
                else:
                    return {
                        "error": "Bad request for URL navigation",
                        "session_id": sessionId,
                        "url": url,
                        "details": error_detail,
                        "possible_reasons": [
                            "Malformed URL",
                            "Unsupported URL scheme",
                            "Network connectivity issues"
                        ],
                        "suggestions": [
                            "Verify URL format is correct",
                            "Check URL scheme is supported",
                            "Test URL accessibility from device"
                        ]
                    }
            except:
                return {
                    "error": "Bad request - unable to open URL",
                    "session_id": sessionId,
                    "url": url
                }

        if response.status_code == 404:
            return {
                "error": f"Session not found: {sessionId}",
                "session_id": sessionId
            }

        # Success returns 204 No Content
        if response.status_code == 204:
            return {
                "success": True,
                "message": "URL opened successfully",
                "session_id": sessionId,
                "url": url
            }

        return response.json()
    
    async def execute_shell_command(
            self,
            sessionId: str,
            adbShellCommand: str
    ) -> Dict[str, Any]:
        """
        Execute an adb shell command on an Android device. This command is not available for iOS devices.
        The adbShellCommand should be the shell command executed in the device, for example 'ls /'.

        :param sessionId: Required. The id of the device session
        :param adbShellCommand: Required. The adb command to execute in the Android device.
        """

        data = {"adbShellCommand": adbShellCommand}

        # Basic URL validation
        if not adbShellCommand or not isinstance(adbShellCommand, str):
            return {
                "error": "Invalid adb command provided",
                "command": adbShellCommand,
                "suggestions": [
                    "Provide a valid string with an adb command in it",
                    "Example: ls /"
                ]
            }

        response = await self.sauce_api_call(f"rdc/v2/sessions/{sessionId}/device/executeShellCommand", method="POST", json=data)

        if isinstance(response, dict):
            return response

        if response.status_code == 400:
            try:
                error_details = response.json()
                error_detail = error_details.get("detail", "")

                if "Device not ready" in error_detail:
                    return {
                        "error": "Device session not ready for executing commands",
                        "session_id": sessionId,
                        "possible_reasons": [
                            "Session is not in ACTIVE state",
                            "Device is still initializing"
                        ],
                        "suggestions": [
                            "Wait for session to become ACTIVE",
                            "Check session state with get_session_details"
                        ]
                    }
                else:
                    return {
                        "error": "Invalid request parameters",
                        "session_id": sessionId,
                        "possible_reasons": [
                            "User has no access to this feature",
                            "Invoked on an iOS session instead of Android"
                        ],
                        "suggestions": [
                            "Verify the user plan has access to OpenAPI",
                            "Verify the session is for an Android device "
                        ]
                    }
            except:
                return {
                    "error": "Bad request - unable to open URL",
                    "session_id": sessionId,
                    "command": adbShellCommand
                }

        if response.status_code == 404:
            return {
                "error": f"Session not found: {sessionId}",
                "session_id": sessionId
            }

        return response.json()

def check_stdio_is_not_tty():
    """Check if running in proper MCP environment"""
    if sys.stdin.isatty() or sys.stdout.isatty() or sys.stderr.isatty():
        print("Error: This server is not meant to be run interactively.", file=sys.stderr)
        return False
    return True


def main():
    """Main entry point for the script."""
    if not check_stdio_is_not_tty():
        sys.exit(1)

    # Create the FastMCP server instance
    mcp_server_instance = FastMCP("SauceLabsRDCAgent")

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

    sauce_agent = SauceLabsRDCAgent(mcp_server_instance, SAUCE_ACCESS_KEY, SAUCE_USERNAME, SAUCE_REGION)

    # Run the FastMCP server instance
    mcp_server_instance.run(transport="stdio")


if __name__ == "__main__":
    main()
