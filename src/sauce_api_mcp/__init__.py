"""Sauce Labs MCP Server.

A Model Context Protocol (MCP) server for interacting with Sauce Labs APIs.
Provides tools for managing jobs, builds, teams, users, and test assets.
"""

# Version information
__version__ = "0.1.0.beta5"
__author__ = "Marcus Merrell"
__email__ = "marcus.merrell@saucelabs.com"

# Import main classes/functions that users should access
from .main import SauceLabsAgent
from .models import (
    AccountInfo,
    LookupUsers,
    LookupServiceAccounts,
    LookupTeamsResponse,
    ErrorResponse
)
# Define what gets imported with "from sauce_api_mcp import *"
__all__ = [
    "SauceLabsAgent",
    "AccountInfo",
    "LookupUsers",
    "LookupServiceAccounts",
    "LookupTeamsResponse",
    "ErrorResponse"
]

# Optional: Set up logging
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())