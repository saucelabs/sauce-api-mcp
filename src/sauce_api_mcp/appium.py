#!/usr/bin/env python3
import httpx
from httpx import BasicAuth
from mcp.server import FastMCP
from typing import Dict, Any, Union, Optional, List
import logging
import os
import base64

class AppiumMcpServer:
    def __init__(self, mcp_server: FastMCP):
        self.mcp = mcp_server

        # Register all the tools
        self.mcp.tool()(self.appium_tap)
        self.mcp.tool()(self.appium_swipe)
        self.mcp.tool()(self.appium_type)
        self.mcp.tool()(self.appium_long_press)
        self.mcp.tool()(self.appium_scroll)
        self.mcp.tool()(self.appium_find_element)
        self.mcp.tool()(self.appium_tap_element)
        self.mcp.tool()(self.appium_get_text)

        logging.info("Appium MCP server initialized")

    def _extract_session_id(self, session_url: str) -> str:
        """Extract session ID from Appium session URL"""
        parts = session_url.split('/sessions/')
        if len(parts) > 1:
            session_part = parts[1].split('/')[0]
            return session_part
        raise ValueError("Invalid session URL format")

    async def appium_tap(self, session_url: str, x: int, y: int) -> Dict:
        """Execute tap gesture at coordinates

        Args:
            session_url: Full Appium session URL
            x: X coordinate to tap
            y: Y coordinate to tap

        Returns:
            dict: Appium response with success/error status
        """
        payload = {
            "actions": [{
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pointerUp", "button": 0}
                ]
            }]
        }

        try:
            result = await self._execute_appium_command(session_url, "actions", "POST", payload)
            if "error" in result:
                return {"status": "error", "message": result["error"]}

            return {
                "status": "success",
                "message": f"Successfully tapped at ({x}, {y})",
                "result": result
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def appium_swipe(self, session_url: str, start_x: int, start_y: int,
                           end_x: int, end_y: int, duration: int = 500) -> Dict:
        """Execute swipe gesture between coordinates

        Args:
            session_url: Full Appium session URL
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            end_x: Ending X coordinate
            end_y: Ending Y coordinate
            duration: Duration in milliseconds (default: 500)

        Returns:
            dict: Appium response with success/error status
        """
        session_id = self._extract_session_id(session_url)

        payload = {
            "actions": [{
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0, "x": start_x, "y": start_y},
                    {"type": "pointerDown", "button": 0},
                    {"type": "pointerMove", "duration": duration, "x": end_x, "y": end_y},
                    {"type": "pointerUp", "button": 0}
                ]
            }]
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{session_url.replace('/appium/wd/hub', '')}/session/{session_id}/actions",
                    json=payload
                )
                response.raise_for_status()
                return {
                    "status": "success",
                    "message": f"Successfully swiped from ({start_x}, {start_y}) to ({end_x}, {end_y}) over {duration}ms",
                    "result": response.json()
                }
            except Exception as e:
                return {"status": "error", "message": str(e)}

    async def appium_type(self, session_url: str, text: str) -> Dict:
        """Type text into currently focused element

        Args:
            session_url: Full Appium session URL
            text: Text to type

        Returns:
            dict: Appium response with success/error status
        """
        session_id = self._extract_session_id(session_url)

        payload = {"text": text}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{session_url.replace('/appium/wd/hub', '')}/session/{session_id}/keys",
                    json=payload
                )
                response.raise_for_status()
                return {
                    "status": "success",
                    "message": f"Successfully typed: {text}",
                    "result": response.json()
                }
            except Exception as e:
                return {"status": "error", "message": str(e)}

    async def appium_long_press(self, session_url: str, x: int, y: int, duration: int = 2000) -> dict:
        """Execute long press gesture at coordinates

        Args:
            session_url: Full Appium session URL
            x: X coordinate to long press
            y: Y coordinate to long press
            duration: Hold duration in milliseconds (default: 2000)

        Returns:
            dict: Appium response with success/error status
        """
        actions = [{
            "type": "pointer",
            "id": "finger1",
            "parameters": {"pointerType": "touch"},
            "actions": [
                {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                {"type": "pointerDown", "button": 0},
                {"type": "pause", "duration": duration},
                {"type": "pointerUp", "button": 0}
            ]
        }]

        payload = self._build_w3c_actions_payload(actions)
        result = await self._execute_appium_command(session_url, "actions", "POST", payload)

        if "error" not in result:
            return {"status": "success", "message": f"Long pressed at ({x}, {y}) for {duration}ms"}
        return result

    async def appium_double_tap(self, session_url: str, x: int, y: int, pause_duration: int = 200) -> dict:
        """Execute double tap gesture at coordinates

        Args:
            session_url: Full Appium session URL
            x: X coordinate to double tap
            y: Y coordinate to double tap
            pause_duration: Pause between taps in milliseconds (default: 200)

        Returns:
            dict: Appium response with success/error status
        """

    async def appium_scroll(self, session_url: str, direction: str, distance: int = 300,
                     element_id: str = None) -> dict:
        """Execute scroll gesture in specified direction

        Args:
            session_url: Full Appium session URL
            direction: Scroll direction ('up', 'down', 'left', 'right')
            distance: Scroll distance in pixels (default: 300)
            element_id: Optional element to scroll within (default: None for full screen)

        Returns:
            dict: Appium response with success/error status
        """
        # Get window size first to calculate scroll coordinates
        window_info = await self._execute_appium_command(session_url, "window/rect", "GET")
        if "error" in window_info:
            return window_info

        width = window_info.get("value", {}).get("width", 1280)
        height = window_info.get("value", {}).get("height", 2856)

        center_x = width // 2
        center_y = height // 2

        # Calculate start and end points based on direction
        if direction.lower() == "up":
            start_x, start_y = center_x, center_y + distance // 2
            end_x, end_y = center_x, center_y - distance // 2
        elif direction.lower() == "down":
            start_x, start_y = center_x, center_y - distance // 2
            end_x, end_y = center_x, center_y + distance // 2
        elif direction.lower() == "left":
            start_x, start_y = center_x + distance // 2, center_y
            end_x, end_y = center_x - distance // 2, center_y
        elif direction.lower() == "right":
            start_x, start_y = center_x - distance // 2, center_y
            end_x, end_y = center_x + distance // 2, center_y
        else:
            return {"error": "Invalid direction. Use 'up', 'down', 'left', or 'right'", "status": "failed"}

        return await self.swipe(session_url, start_x, start_y, end_x, end_y, 500)

    async def appium_type_text(self, session_url: str, text: str) -> dict:
        """Type text into currently focused element

        Args:
            session_url: Full Appium session URL
            text: Text to type

        Returns:
            dict: Appium response with success/error status
        """
        payload = {
            "text": text
        }

        result = await self._execute_appium_command(session_url, "keys", "POST", payload)

        if "error" not in result:
            return {"status": "success", "message": f"Typed: {text}"}
        return result

    async def appium_press_key(self, session_url: str, keycode: str) -> dict:
        """Press a key by keycode name

        Args:
            session_url: Full Appium session URL
            keycode: Key name ('ENTER', 'BACK', 'HOME', 'MENU', 'SEARCH', etc.)

        Returns:
            dict: Appium response with success/error status
        """
        keycode_map = {
            "ENTER": 66, "BACK": 4, "HOME": 3, "MENU": 82,
            "SEARCH": 84, "DELETE": 67, "TAB": 61, "SPACE": 62,
            "VOLUME_UP": 24, "VOLUME_DOWN": 25, "POWER": 26
        }

        keycode_num = keycode_map.get(keycode.upper(), keycode)

        payload = {
            "keycode": keycode_num
        }

        result = await self._execute_appium_command(session_url, "appium/device/press_keycode", "POST", payload)

        if "error" not in result:
            return {"status": "success", "message": f"Pressed key: {keycode}"}
        return result

    async def appium_clear_text(self, session_url: str, element_id: str = None) -> dict:
        """Clear text from focused element or specified element

        Args:
            session_url: Full Appium session URL
            element_id: Optional specific element ID to clear (default: None for focused element)

        Returns:
            dict: Appium response with success/error status
        """
        if element_id:
            endpoint = f"element/{element_id}/clear"
        else:
            # Clear currently active element
            endpoint = "keys"
            payload = {"text": ""}  # Send empty text to clear

        result = await self._execute_appium_command(session_url, endpoint, "POST", payload if not element_id else None)

        if "error" not in result:
            return {"status": "success", "message": "Text cleared"}
        return result

    async def appium_go_back(self, session_url: str) -> dict:
        """Navigate back (equivalent to Android back button)

        Args:
            session_url: Full Appium session URL

        Returns:
            dict: Appium response with success/error status
        """
        return await self.press_key(session_url, "BACK")

    async def appium_go_home(self, session_url: str) -> dict:
        """Navigate to home screen

        Args:
            session_url: Full Appium session URL

        Returns:
            dict: Appium response with success/error status
        """
        return await self.press_key(session_url, "HOME")

    async def appium_find_element(self, session_url: str, by: str, value: str) -> dict:
        """Find element using locator strategy

        Args:
            session_url: Full Appium session URL
            by: Locator strategy ('id', 'xpath', 'class name', 'accessibility id', 'android uiautomator', etc.)
            value: Locator value

        Returns:
            dict: Element data with element ID or error
        """
        # Locator strategy mapping
        locator_map = {
            "id": "id",
            "xpath": "xpath",
            "class": "class name",
            "class_name": "class name",
            "accessibility_id": "accessibility id",
            "android_uiautomator": "-android uiautomator",
            "ios_predicate": "-ios predicate string",
            "ios_class_chain": "-ios class chain"
        }

        strategy = locator_map.get(by.lower(), by)

        payload = {
            "using": strategy,
            "value": value
        }

        result = await self._execute_appium_command(session_url, "element", "POST", payload)

        if "error" not in result and "value" in result:
            element_id = result["value"].get("ELEMENT") or result["value"].get("element-6066-11e4-a52e-4f735466cecf")
            return {"status": "success", "element_id": element_id, "message": f"Found element with {by}={value}"}
        return result

    async def appium_find_elements(self, session_url: str, by: str, value: str) -> dict:
        """Find multiple elements using locator strategy

        Args:
            session_url: Full Appium session URL
            by: Locator strategy ('id', 'xpath', 'class name', 'accessibility id', 'android uiautomator', etc.)
            value: Locator value

        Returns:
            dict: List of element data with element IDs or error
        """

    async def appium_tap_element(self, session_url: str, element_id: str) -> dict:
        """Tap on a specific element by its ID

        Args:
            session_url: Full Appium session URL
            element_id: Element ID from find_element response

        Returns:
            dict: Appium response with success/error status
        """
        result = await self._execute_appium_command(session_url, f"element/{element_id}/click", "POST")

        if "error" not in result:
            return {"status": "success", "message": f"Tapped element: {element_id}"}
        return result

    async def appium_get_text(self, session_url: str, element_id: str) -> dict:
        """Get text content from specified element

        Args:
            session_url: Full Appium session URL
            element_id: Element ID from find_element response

        Returns:
            dict: Element text content or error
        """
        async def get_text(self, session_url: str, element_id: str) -> dict:
            """Get text content from specified element"""

            result = await self._execute_appium_command(session_url, f"element/{element_id}/text", "GET")

            if "error" not in result and "value" in result:
                return {"status": "success", "text": result["value"], "message": "Text retrieved successfully"}
            return result

    async def appium_get_attribute(self, session_url: str, element_id: str, attribute_name: str) -> dict:
        """Get attribute value from specified element

        Args:
            session_url: Full Appium session URL
            element_id: Element ID from find_element response
            attribute_name: Attribute name to retrieve ('text', 'enabled', 'displayed', etc.)

        Returns:
            dict: Attribute value or error
        """

    async def appium_get_page_source(self, session_url: str) -> dict:
        """Get current page/screen source XML

        Args:
            session_url: Full Appium session URL

        Returns:
            dict: Page source XML or error
        """
        result = await self._execute_appium_command(session_url, "source", "GET")

        if "error" not in result and "value" in result:
            return {"status": "success", "source": result["value"], "message": "Page source retrieved"}
        return result

    async def appium_take_screenshot(self, session_url: str) -> dict:
        """Take screenshot of current screen

        Args:
            session_url: Full Appium session URL

        Returns:
            dict: Base64 encoded screenshot or error
        """
        result = await self._execute_appium_command(session_url, "screenshot", "GET")

        if "error" not in result and "value" in result:
            return {"status": "success", "screenshot": result["value"], "message": "Screenshot captured (base64)"}
        return result

    async def appium_get_current_activity(self, session_url: str) -> dict:
        """Get current Android activity name

        Args:
            session_url: Full Appium session URL

        Returns:
            dict: Current activity name or error (Android only)
        """

    async def appium_get_current_package(self, session_url: str) -> dict:
        """Get current Android package name

        Args:
            session_url: Full Appium session URL

        Returns:
            dict: Current package name or error (Android only)
        """

    async def appium_open_url(self, session_url: str, url: str) -> dict:
        """Open URL in browser or app

        Args:
            session_url: Full Appium session URL
            url: URL to open (http/https for browser, custom schemes for apps)

        Returns:
            dict: Appium response with success/error status
        """
        payload = {"url": url}
        result = await self._execute_appium_command(session_url, "url", "POST", payload)

        if "error" not in result:
            return {"status": "success", "message": f"Opened URL: {url}"}
        return result

    async def appium_wait_for_element(self, session_url: str, by: str, value: str,
                               timeout: int = 10) -> dict:
        """Wait for element to appear with timeout

        Args:
            session_url: Full Appium session URL
            by: Locator strategy
            value: Locator value
            timeout: Timeout in seconds (default: 10)

        Returns:
            dict: Element data when found or timeout error
        """

    async def appium_get_window_size(self, session_url: str) -> dict:
        """Get current window/screen dimensions

        Args:
            session_url: Full Appium session URL

        Returns:
            dict: Width and height of screen or error
        """
        result = await self._execute_appium_command(session_url, "window/rect", "GET")

        if "error" not in result and "value" in result:
            size = result["value"]
            return {
                "status": "success",
                "width": size.get("width"),
                "height": size.get("height"),
                "message": "Window size retrieved"
            }
        return result

    async def appium_set_implicit_wait(self, session_url: str, timeout: int) -> dict:
        """Set implicit wait timeout for element finding

        Args:
            session_url: Full Appium session URL
            timeout: Timeout in seconds

        Returns:
            dict: Appium response with success/error status
        """


    def _extract_session_id(self, session_url: str) -> str:
        """Extract session ID from Appium session URL"""
        # session_url: https://api.us-west-1.saucelabs.com/rdc/v2/sessions/13b85b71-b6cd-4287-983c-db87cf82bac1/appium/wd/hub
        parts = session_url.split('/sessions/')
        if len(parts) > 1:
            session_part = parts[1].split('/')[0]
            return session_part
        raise ValueError("Invalid session URL format")

    def _get_base_url(self, session_url: str) -> str:
        """Get base URL for Appium commands"""
        # For Sauce RDC, we need to use the standard Appium session format
        # The session_url contains the RDC session ID, but we need to use it
        # in the standard Appium WebDriver protocol format
        session_id = self._extract_session_id(session_url)

        # Keep the original base but use standard Appium session endpoint
        base = session_url.replace('/appium/wd/hub', '')
        return f"{base}/appium/wd/hub/session/{session_id}"

    async def _execute_appium_command(self, session_url: str, endpoint: str,
                                      method: str = "POST", payload: dict = None) -> dict:
        """Execute HTTP request to Appium endpoint"""
        base_url = self._get_base_url(session_url)
        full_url = f"{base_url}/{endpoint.lstrip('/')}"

        # Get Sauce Labs credentials from environment variables
        sauce_username = os.getenv('SAUCE_USERNAME')
        sauce_access_key = os.getenv('SAUCE_ACCESS_KEY')

        if not sauce_username or not sauce_access_key:
            return {"error": "SAUCE_USERNAME and SAUCE_ACCESS_KEY environment variables must be set",
                    "status": "failed"}

        from httpx import BasicAuth
        auth = BasicAuth(sauce_username, sauce_access_key)

        async with httpx.AsyncClient() as client:
            try:
                if method.upper() == "POST":
                    response = await client.post(full_url, json=payload, auth=auth)
                elif method.upper() == "GET":
                    response = await client.get(full_url, auth=auth)
                elif method.upper() == "DELETE":
                    response = await client.delete(full_url, auth=auth)

                response.raise_for_status()
                return response.json()

            except httpx.HTTPError as e:
                return {"error": f"HTTP error: {str(e)}", "status": "failed"}
            except Exception as e:
                return {"error": f"Unexpected error: {str(e)}", "status": "failed"}

    def _build_w3c_actions_payload(self, actions_list: list) -> dict:
        """Build W3C Actions API payload"""
        return {
            "actions": actions_list
        }


def main():
    mcp_server = FastMCP("Sauce Labs Appium MCP")
    appium_server = AppiumMcpServer(mcp_server)
    mcp_server.run()

if __name__ == "__main__":
    main()