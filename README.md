# Sauce Labs MCP Server

[//]: # (mcp-name: io.github.saucelabs/sauce-api-mcp)

A Model Context Protocol (MCP) server that provides comprehensive integration with the Sauce Labs testing platform. This
package includes two complementary MCP servers enabling AI assistants to interact with Sauce Labs' device cloud, manage
test jobs, analyze builds, and monitor testing infrastructure through natural language conversations.

## Servers

This package provides two separate MCP servers optimized for different use cases:

**sauce-api-mcp** (Core Server) — Full Sauce Labs API integration for account management, device discovery, job
analysis, builds, storage, and tunnels.

**sauce-api-mcp-rdc** (RDC Server) — Real Device Cloud (RDC) focused server. Dynamically generates MCP tools at startup
from the official Sauce Labs OpenAPI spec using [FastMCP](https://github.com/jlowin/fastmcp) with an `OpenAPIProvider`,
so the tool set is always up-to-date without code changes. Includes a small set of handwritten tools for endpoints that
need special handling (binary payloads, session lifecycle, app installation polling).

Both servers can be configured simultaneously in your LLM client for full Sauce Labs coverage.

## Features

### 🚀 Core Capabilities

- **Account Management**: View account details, team information, and user permissions
- **Device Cloud Access**: Browse 300+ real devices (iOS, Android) and virtual machines
- **Test Job Management**: Retrieve recent jobs, analyze test results, and debug failures
- **Build Monitoring**: Track build status, view job collections, and analyze test suites
- **Storage Management**: Manage uploaded apps and test artifacts
- **Tunnel Monitoring**: Check Sauce Connect tunnel status and configuration

### 🔧 Advanced Features

- **Real-time Device Status**: Monitor device availability and usage across data centres
- **Cross-platform Testing**: Support for both Virtual Device Cloud (VDC) and Real Device Cloud (RDC)
- **Test Analytics**: Detailed job information including logs, videos, and performance metrics
- **Team Collaboration**: Multi-team support with proper access controls
- **Dynamic RDC API**: `sauce-api-mcp-rdc` auto-discovers the latest RDC v2 endpoints from the OpenAPI spec at startup;
  the cached spec is used as a fallback when the network is unavailable
- **Response shaping**: Large API list responses are automatically truncated to keep LLM context budget under control (
  configurable via `SAUCE_MCP_MAX_RESPONSE_ITEMS`)
- **File safety**: File push/pull operations on devices are restricted to `~/.sauce-mcp/files/` to prevent path
  traversal

## Prerequisites

- Python 3.10+
- `pip`
- Sauce Labs account with API access
- Claude Desktop, Gemini CLI, Goose, or another MCP-compatible LLM client

## Installation

Install the package from PyPI:

```bash
pip install sauce-api-mcp
```

This installs both servers and registers their command-line entry points:

- `sauce-api-mcp` — core server
- `sauce-api-mcp-rdc` — RDC OpenAPI server

Verify installation:

```bash
which sauce-api-mcp
which sauce-api-mcp-rdc
```

## Configuration for LLM Clients

### Claude Desktop (Mac / Linux / Windows)

1. Locate your Claude Desktop config file:
    - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
    - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
    - **Linux**: `~/.config/Claude/claude_desktop_config.json`

2. Find your Python installation's `bin` directory:
   ```bash
   python3 -c "import sys; print(sys.prefix + '/bin')"
   ```

3. Add both servers to your config:
   ```json
   {
     "mcpServers": {
       "sauce-api-mcp-core": {
         "command": "/path/to/bin/sauce-api-mcp",
         "env": {
           "SAUCE_USERNAME": "your-sauce-username",
           "SAUCE_ACCESS_KEY": "your-sauce-access-key"
         }
       },
       "sauce-api-mcp-rdc": {
         "command": "/path/to/bin/sauce-api-mcp-rdc",
         "env": {
           "SAUCE_USERNAME": "your-sauce-username",
           "SAUCE_ACCESS_KEY": "your-sauce-access-key"
         }
       }
     }
   }
   ```

4. Restart Claude Desktop to load the servers.

### Gemini CLI

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "sauce-api-mcp-core": {
      "command": "/path/to/bin/sauce-api-mcp",
      "env": {
        "SAUCE_USERNAME": "your-sauce-username",
        "SAUCE_ACCESS_KEY": "your-sauce-access-key"
      }
    },
    "sauce-api-mcp-rdc": {
      "command": "/path/to/bin/sauce-api-mcp-rdc",
      "env": {
        "SAUCE_USERNAME": "your-sauce-username",
        "SAUCE_ACCESS_KEY": "your-sauce-access-key"
      }
    }
  }
}
```

### Goose

Add to `~/.config/goose/config.yaml`:

```yaml
sauce-api-mcp-core:
  cmd: /path/to/bin/sauce-api-mcp
  description: Sauce Labs MCP (Core)
  enabled: true
  envs:
    SAUCE_USERNAME: your-sauce-username
    SAUCE_ACCESS_KEY: your-sauce-access-key
  type: stdio

sauce-api-mcp-rdc:
  cmd: /path/to/bin/sauce-api-mcp-rdc
  description: Sauce Labs MCP (RDC)
  enabled: true
  envs:
    SAUCE_USERNAME: your-sauce-username
    SAUCE_ACCESS_KEY: your-sauce-access-key
  type: stdio
```

### Environment Variables (Alternative)

Instead of adding credentials to config files, you can export them as environment variables:

```bash
export SAUCE_USERNAME="your-sauce-username"
export SAUCE_ACCESS_KEY="your-sauce-access-key"
```

Then omit the `env` block from your config. Both servers will automatically pick them up.

## Configuration

### Required Environment Variables

| Variable           | Description                                            |
|--------------------|--------------------------------------------------------|
| `SAUCE_USERNAME`   | Your Sauce Labs username                               |
| `SAUCE_ACCESS_KEY` | Your Sauce Labs access key (found in Account Settings) |

### Optional Environment Variables

| Variable                       | Default   | Description                                                |
|--------------------------------|-----------|------------------------------------------------------------|
| `SAUCE_REGION`                 | `US_WEST` | Data centre region: `US_WEST`, `US_EAST`, `EU_CENTRAL`     |
| `SAUCE_MCP_MAX_RESPONSE_ITEMS` | `100`     | Maximum list items returned before truncation (RDC server) |

### Getting Your Sauce Labs Credentials

1. Log into your Sauce Labs account
2. Navigate to **Account → User Settings**
3. Copy your **Username** and **Access Key**

## Troubleshooting Installation

### "Command not found: sauce-api-mcp"

The entry point script isn't in your PATH. Use the full path approach:

```bash
python3 -m pip list | grep sauce-api-mcp
python3 -c "import sys; print(sys.prefix + '/bin/sauce-api-mcp')"
```

### "ENOENT: no such file or directory" in MCP client

The MCP client is using a different Python environment. Solutions:

1. **Use the full absolute path** (recommended) — update your config with the path printed by
   `python3 -c "import sys; print(sys.prefix + '/bin/sauce-api-mcp')"`, not just `which sauce-api-mcp`
2. **Module invocation** (fallback):
   ```json
   "command": "python3",
   "args": ["-m", "sauce_api_mcp.main"]
   ```

## Example Prompts

- *"Show me my recent test failures"*
- *"Find available iPhone 16 devices"*
- *"Analyse the performance of my latest build"*
- *"Open a session on a Samsung device and install my app"*
- *"What tunnels do I have running right now?"*

## Available Tools

### Core Server (`sauce-api-mcp`)

#### Account & Organisation

| Tool                      | Description                                    |
|---------------------------|------------------------------------------------|
| `get_account_info`        | Retrieve current user account information      |
| `lookup_users`            | Find users in your organisation                |
| `get_user`                | Get detailed user information                  |
| `lookup_teams`            | Find teams in your organisation                |
| `get_team`                | Get team details                               |
| `list_team_members`       | List all members of a specific team            |
| `lookup_service_accounts` | List service accounts                          |
| `get_service_account`     | Get service account details                    |
| `get_my_active_team`      | Get the active team for the authenticated user |

#### Device Management

| Tool                  | Description                                      |
|-----------------------|--------------------------------------------------|
| `get_devices_status`  | List all devices and their current status        |
| `get_specific_device` | Get detailed information about a specific device |
| `get_private_devices` | List private devices available to your account   |

#### Test Jobs

| Tool                                 | Description                                     |
|--------------------------------------|-------------------------------------------------|
| `get_recent_jobs`                    | Retrieve your most recent test jobs             |
| `get_job_details`                    | Get comprehensive details about a specific job  |
| `get_real_device_jobs`               | List active jobs on real devices                |
| `get_specific_real_device_job`       | Get details about a specific real device job    |
| `get_specific_real_device_job_asset` | Download job assets (logs, videos, screenshots) |

#### Builds

| Tool                   | Description                                     |
|------------------------|-------------------------------------------------|
| `lookup_builds`        | Search for builds with filters                  |
| `get_build`            | Get detailed information about a specific build |
| `get_build_for_job`    | Get the build associated with a job             |
| `lookup_jobs_in_build` | List all jobs within a build                    |

#### Storage

| Tool                            | Description                                                  |
|---------------------------------|--------------------------------------------------------------|
| `get_storage_files`             | List uploaded application files                              |
| `get_storage_groups`            | List app storage groups                                      |
| `get_storage_groups_settings`   | Get settings for a storage group                             |
| `upload_file_to_storage`        | Upload an app file to Sauce Storage                          |
| `update_storage_group_settings` | Update app group settings (resigning, instrumentation, etc.) |

#### Tunnels

| Tool                           | Description                                  |
|--------------------------------|----------------------------------------------|
| `get_tunnels_for_user`         | List active Sauce Connect tunnels            |
| `get_tunnel_information`       | Get details about a specific tunnel          |
| `get_current_jobs_for_tunnel`  | See how many jobs are using a tunnel         |
| `get_tunnel_version_downloads` | Get download URLs for Sauce Connect versions |

#### Test Assets & Logs

| Tool                   | Description                                                |
|------------------------|------------------------------------------------------------|
| `get_test_assets`      | Retrieve test artifacts for a VDC job                      |
| `get_log_json_file`    | Get structured test execution logs for a VDC job           |
| `get_network_har_file` | Get HAR network capture data with filtering                |
| `filter_har_data`      | Filter cached HAR data efficiently (avoids re-downloading) |

### RDC Server (`sauce-api-mcp-rdc`)

The RDC server auto-generates tools from the Sauce Labs RDC v2 OpenAPI spec. The full tool list varies as the spec
evolves, but the categories below are always present.

#### Session Management

| Tool                  | Description                                                                                  |
|-----------------------|----------------------------------------------------------------------------------------------|
| `createSession`       | Allocate a real device and return an ACTIVE session. Polls until ACTIVE or times out (~55 s) |
| `listSessions`        | List current device sessions with optional filtering                                         |
| `deleteSession`       | Close a session and release the device back to the pool                                      |
| `get_session_details` | Get full details of a specific session                                                       |

#### Device Discovery

| Tool                 | Description                                            |
|----------------------|--------------------------------------------------------|
| `listDevices`        | Browse the full device catalogue with OS/model filters |
| `list_device_status` | Get live availability status of devices                |

#### App Management

| Tool                       | Description                                                        |
|----------------------------|--------------------------------------------------------------------|
| `installApp`               | Start an app installation on a device (returns an installation ID) |
| `waitForAppInstallation`   | Poll installation status — call repeatedly until FINISHED          |
| `launchApp`                | Launch an already-installed app                                    |
| `uninstallApp`             | Remove an app from a device                                        |
| `list_app_installations`   | List ongoing or recent app installations                           |
| `install_app_from_storage` | Install an app from Sauce Storage                                  |

#### Device Interaction

| Tool                    | Description                                        |
|-------------------------|----------------------------------------------------|
| `take_screenshot`       | Capture the current device screen                  |
| `open_url_or_deeplink`  | Open a URL or deep link on the device              |
| `execute_shell_command` | Run an adb shell command (Android)                 |
| `applyDeviceSettings`   | Change device settings (orientation, locale, etc.) |

#### File Operations

| Tool                    | Description                                                             |
|-------------------------|-------------------------------------------------------------------------|
| `push_file_to_device`   | Upload a local file to the device (restricted to `~/.sauce-mcp/files/`) |
| `pull_file_from_device` | Download a file from the device                                         |
| `listFiles`             | List files in a device directory                                        |
| `removeFile`            | Delete a file from the device                                           |
| `statFile`              | Get metadata about a file or directory on the device                    |

#### Network & Proxy

| Tool                                         | Description                                    |
|----------------------------------------------|------------------------------------------------|
| `proxy_http`                                 | Forward HTTP requests through the device proxy |
| `startNetworkCapture` / `stopNetworkCapture` | Capture network traffic                        |
| `setNetworkProfile` / `setNetworkConditions` | Simulate network conditions                    |
| `listNetworkProfiles`                        | List available network profiles                |
| `resetNetworkConditions`                     | Restore normal connectivity                    |

#### Appium

| Tool                      | Description                                             |
|---------------------------|---------------------------------------------------------|
| `startAppiumServer`       | Start a hosted Appium server co-located with the device |
| `getAppiumServerStatus`   | Check if Appium is running and get its endpoint URL     |
| `listAppiumVersions`      | List available Appium versions                          |
| `launchWebDriverAgent`    | Launch WDA on an iOS device                             |
| `getWebDriverAgentStatus` | Check WDA status                                        |

## Development Setup

### Prerequisites

- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) package manager
- Git

### Clone and Setup

```bash
git clone https://github.com/saucelabs/sauce-api-mcp.git
cd sauce-api-mcp
uv sync
```

This creates a virtual environment and installs all dependencies (including test extras) in editable mode.

### Project Structure

```
sauce-api-mcp/
├── src/sauce_api_mcp/
│   ├── main.py              # Core server — hand-written MCP tools
│   ├── rdc_dynamic.py       # RDC server — OpenAPIProvider + hand-written tools
│   ├── models.py            # Pydantic response models
│   └── shared/              # Shared utilities
├── tests/                   # Test suite
├── server.json              # MCP Registry manifest
├── pyproject.toml           # Package config, entry points, PSR release config
└── uv.lock                  # Locked dependencies
```

### Running the Servers Locally

```bash
uv run sauce-api-mcp
uv run sauce-api-mcp-rdc
```

Both will print `Error: This server is not meant to be run interactively` — this is expected (they communicate over
stdio with MCP clients, not the terminal).

To point your MCP client at a local development checkout:

```json
{
  "command": "/path/to/sauce-api-mcp/.venv/bin/sauce-api-mcp"
}
```

### Running Tests

Tests are split into three groups:

```bash
# Integration tests (no live credentials required)
uv run pytest -m "not live and not slow"

# Live tests (require SAUCE_USERNAME + SAUCE_ACCESS_KEY)
uv run pytest -m "live and not slow"

# Slow tests (allocate real devices — takes minutes)
uv run pytest -m "slow"

# Full suite
uv run pytest
```

### Adding Dependencies

```bash
uv add httpx
uv add --dev pytest-asyncio
```

## CI / Release Workflow

### Continuous Integration

Every pull request targeting `main` runs three sequential jobs via `build.yml`:

1. **test** — integration tests across Python 3.10, 3.11, 3.12 (in parallel)
2. **test-live** — live tests on Python 3.12 (after `test`)
3. **test-slow** — slow tests on Python 3.12 (after `test-live`)

### Releases

Releases are triggered manually via the **Release** workflow (`publish.yml`) in GitHub Actions:

1. Go to **Actions → Release → Run workflow**
2. Choose the release type: `patch`, `minor`, `major`, or `prerelease`
3. For pre-releases, optionally set the token (`alpha`, `beta`, `rc`)

The workflow then:

- Bumps the version in `pyproject.toml` **and** `server.json` using [
  `python-semantic-release`](https://python-semantic-release.readthedocs.io/)
- Creates a `v*` git tag and a GitHub Release with auto-generated changelog
- Publishes **stable** releases to [PyPI](https://pypi.org/project/sauce-api-mcp/) and
  the [MCP Registry](https://registry.modelcontextprotocol.io/)
- Publishes **pre-releases** (alpha/beta/rc) to [TestPyPI](https://test.pypi.org/project/sauce-api-mcp/) only

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Getting Help

- Sauce Labs Documentation: [docs.saucelabs.com](https://docs.saucelabs.com)
- API Reference: [docs.saucelabs.com/dev/api](https://docs.saucelabs.com/dev/api)
- Support: Contact Sauce Labs support through your account dashboard
- GitHub Issues: [Report bugs or request features](https://github.com/saucelabs/sauce-api-mcp/issues)

## Changelog

For a full history of releases and changes, see the
[GitHub Releases page](https://github.com/saucelabs/sauce-api-mcp/releases).

### v1.1.0

- Merged `sauce-api-mcp` and `sauce-labs-mcp` (RDC OpenAPI) into single monorepo package
- Added `sauce-api-mcp-rdc` entry point for the RDC-focused server
- Migrated RDC server from deprecated `FastMCPOpenAPI` to `OpenAPIProvider + FastMCP` (fastmcp 3.x)
- Automated release workflow via `workflow_dispatch` with `python-semantic-release`; release type chosen by the author (
  patch/minor/major/prerelease)
- CI split into three sequential stages: integration tests (matrix 3.10–3.12) → live tests → slow tests
- Locked dependencies with `uv.lock` for reproducible installs

### v1.0.3

- Updated to Apache License 2.0 (previously MIT)

### v1.0.2

- Submitted to official MCP Registry
- Added Python 3.9 support

### v1.0.1

- Overhauled README with improved install instructions

### v1.0.0

- Initial release with full Sauce Labs API integration

---

**Made with ❤️ for the testing community**

## License

Apache 2.0 (versions 1.1.0+)

> Versions prior to 1.0.3 were released under the MIT License.

## Disclaimer of Warranties

THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Limitation of Liability

IN NO EVENT SHALL SAUCE LABS, INC. BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (
INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

## General Use

The MCP Server is provided as a free and open-source tool to facilitate interaction with publicly available APIs. Users
are free to modify and distribute the software under the terms of the Apache License 2.0.

By using this software, you acknowledge that you are doing so at your own risk and that you are responsible for your own
compliance with all applicable laws and regulations.

## Indemnification

You agree to indemnify and hold harmless Sauce Labs, Inc. ("Sauce Labs"), its officers, directors, employees, and agents
from and against any and all claims, liabilities, damages, losses, or expenses, including reasonable attorneys' fees and
costs, arising out of or in any way connected with your access to or use of this software.

This includes, but is not limited to:

- **Your Interaction with Third-Party LLM Providers:** You acknowledge that this software utilises publicly available
  APIs for interaction with a Large Language Model (LLM). You are solely responsible for your use of any third-party LLM
  services, including your adherence to the terms and conditions of the LLM provider and any costs associated with your
  use, such as token fees. Sauce Labs has no control over, and assumes no responsibility for, the content, privacy
  policies, or practices of any third-party LLM providers.

- **Content Generated by the LLM:** You are solely responsible for the content generated, received, or transmitted
  through your use of the MCP Server and the underlying LLM. Sauce Labs does not endorse and has no control over the
  content of communications made by you or any third party through the server.

- **Your Code and Modifications:** Any modifications, enhancements, or derivative works you create based on the MCP
  Server are your own, and you are solely responsible for their performance and any liabilities that may arise from
  their use.
