# sauce-api-mcp
An MCP Server for the Sauce Labs API

## Overview
Sauce-API-MCP is an MCP Server that serves as a wrapper for the Sauce 
Labs Public API. With proper credentials and access, any Sauce Labs 
customer can use this

## Installation

To install this, you'll need to add it to your LLM Client (Goose, Langchain, Claude for Desktop, etc.)

### Claude for Desktop config

```json
{
    "mcpServers": {
        "sauce-mcp": {
            "type": "stdio",
            "command": "<path-to-server>/start_server.sh",
            "env": {
                "SAUCE_USERNAME": "<SAUCE_USERNAME>",
                "SAUCE_ACCESS_KEY": "<SAUCE_ACCESS_KEY>"
            },
            "note": "Sauce Labs API"
        }
    }
}
```
