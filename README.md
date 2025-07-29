# Sauce Labs MCP Server

[//]: # (mcp-name: io.github.saucelabs-sample-test-frameworks/sauce-api-mcp)

A Model Context Protocol (MCP) server that provides comprehensive integration with Sauce Labs testing platform. This package includes two complementary MCP servers enabling AI assistants (LLM clients) to interact with Sauce Labs' device cloud, manage test jobs, analyze builds, and monitor testing infrastructure directly through natural language conversations.

## Servers

This package provides two separate MCP servers optimized for different use cases:

**sauce-api-mcp** (Core Server) - Full Sauce Labs API integration for account management, device discovery, job analysis, builds, storage, and tunnels.

**sauce-api-mcp-rdc** (RDC OpenAPI Server) - Real Device Cloud (RDC) focused server with automated OpenAPI schema discovery and optimized for mobile device testing workflows.

Both servers can be configured simultaneously in your LLM client for comprehensive Sauce Labs integration.

## Features

### 🚀 **Core Capabilities**
- **Account Management**: View account details, team information, and user permissions
- **Device Cloud Access**: Browse 300+ real devices (iOS, Android) and virtual machines
- **Test Job Management**: Retrieve recent jobs, analyze test results, and debug failures
- **Build Monitoring**: Track build status, view job collections, and analyze test suites
- **Storage Management**: Manage uploaded apps and test artifacts
- **Tunnel Monitoring**: Check Sauce Connect tunnel status and configuration

### 🔧 **Advanced Features**
- **Real-time Device Status**: Monitor device availability and usage across data centers
- **Cross-platform Testing**: Support for both Virtual Device Cloud (VDC) and Real Device Cloud (RDC)
- **Test Analytics**: Detailed job information including logs, videos, and performance metrics
- **Team Collaboration**: Multi-team support with proper access controls
- **RDC OpenAPI Integration**: Dynamic API discovery for Real Device Cloud endpoints (sauce-api-mcp-rdc)

## Prerequisites
- Python 3.10+
- `pip`
- Sauce Labs account with API access
- Gemini CLI, Claude Desktop, Goose, or other LLM Client

### For Claude Desktop (Mac/Linux) or Gemini CLI 

Install the package from PyPI:

```bash
pip install sauce-api-mcp
```

This will install both servers and make their command-line entry points available:
- `sauce-api-mcp` (core server)
- `sauce-api-mcp-rdc` (RDC OpenAPI server)

Verify installation:

```bash
which sauce-api-mcp
which sauce-api-mcp-rdc
```

## Configuration for LLM Clients

### Claude Desktop (Mac/Linux/Windows)

1. Locate your Claude Desktop config file:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`

2. Find your Python installation's bin directory:
   ```bash
   python3 -c "import sys; print(sys.prefix + '/bin')"
   ```
   
   On macOS with system Python, this is typically:
   ```
   /Library/Frameworks/Python.framework/Versions/3.12/bin
   ```

3. Add both servers to your config using the full paths from step 2:
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

4. Restart the client to load the servers.

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

Instead of adding credentials to config files, you can set them as environment variables:

```bash
export SAUCE_USERNAME="your-sauce-username"
export SAUCE_ACCESS_KEY="your-sauce-access-key"
```

Then omit the `env` block from your config. Both servers will automatically use these environment variables.

## Troubleshooting Installation

### "Command not found: sauce-api-mcp"

The entry point script isn't in your PATH. Verify installation and use the full path approach above:

```bash
python3 -m pip list | grep sauce-api-mcp
python3 -c "import sys; print(sys.prefix + '/bin/sauce-api-mcp')"
```

### "ENOENT: no such file or directory" in MCP client

The MCP client is using a different Python environment than where you installed the package. Solutions:

1. **Use full absolute path** (recommended): Update your config to use the complete path shown by `python3 -c "import sys; print(sys.prefix + '/bin/sauce-api-mcp')"`, not just `which sauce-api-mcp`

2. **Install in system Python**: If you're using a specific Python installation, ensure `pip install` uses that same Python

3. **Alternative: Module invocation** (less reliable):
   ```json
   "command": "python3",
   "args": ["-m", "sauce_api_mcp.main"]
   ```

## Development Setup

### Prerequisites
- Python 3.10+
- `uv` package manager ([install uv](https://docs.astral.sh/uv/getting-started/installation/))
- Git

### Clone and Setup

```bash
git clone https://github.com/saucelabs/sauce-api-mcp.git
cd sauce-api-mcp
uv sync
```

This creates a virtual environment and installs all dependencies in editable mode.

### Project Structure

```
sauce-api-mcp/
├── src/sauce_api_mcp/
│   ├── __init__.py
│   ├── main.py              # Core server entry point
│   ├── rdc_openapi.py       # RDC OpenAPI server entry point
│   └── shared/              # Shared utilities
├── pyproject.toml           # Package configuration & entry points
├── uv.lock                  # Locked dependencies
└── README.md
```

### Entry Points

The `pyproject.toml` defines two console scripts:

```toml
[project.scripts]
sauce-api-mcp = "sauce_api_mcp.main:main"
sauce-api-mcp-rdc = "sauce_api_mcp.rdc_openapi:main"
```

When you run `uv sync`, these become available as commands in the virtual environment.

### Development Workflow

1. **Activate the virtual environment** (optional, `uv` commands work without it):
   ```bash
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Run the servers locally** (for testing):
   ```bash
   uv run sauce-api-mcp
   uv run sauce-api-mcp-rdc
   ```

   Both will output: `Error: This server is not meant to be run interactively` — this is correct behavior (they're meant to be called by MCP clients).

3. **Run with environment variables**:
   ```bash
   SAUCE_USERNAME=user SAUCE_ACCESS_KEY=key uv run sauce-api-mcp
   ```

4. **Test with your MCP client**:
   ```json
   {
     "command": "/path/to/sauce-api-mcp/.venv/bin/sauce-api-mcp"
   }
   ```

### Running Tests

```bash
uv run pytest
uv run pytest -v  # Verbose
uv run pytest src/sauce_api_mcp/tests/test_main.py  # Specific test
```

### Adding Dependencies

```bash
uv add httpx
uv add --dev pytest-asyncio
```

## Now you can ask questions like:

* "Show me my recent test failures"
* "Find available iPhone devices for testing"
* "Analyze the performance of my latest build"

## Configuration

### Required Environment Variables

- **SAUCE_USERNAME**: Your Sauce Labs username
- **SAUCE_ACCESS_KEY**: Your Sauce Labs access key (found in Account Settings)

### Optional Configuration

- **SAUCE_REGION**: Sauce Labs data center region (default: us-west-1)

## Getting Your Sauce Labs Credentials

1. Log into your Sauce Labs account
2. Navigate to Account → User Settings
3. Copy your Username and Access Key
4. Add these to your Claude Desktop configuration (or set as environment variables)

## Available Tools

### Account & Organization

* **get_account_info** - Retrieve current user account information
* **lookup_users** - Find users in your organization
* **get_user** - Get detailed user information
* **lookup_teams** - Find teams in your organization
* **get_team** - Get team details and member information
* **list_team_members** - List all members of a specific team

### Device Management

* **get_devices_status** - List all available devices and their status
* **get_specific_device** - Get detailed information about a specific device
* **get_private_devices** - List private devices available to your account

### Test Jobs

* **get_recent_jobs** - Retrieve your most recent test jobs
* **get_job_details** - Get comprehensive details about a specific job
* **get_real_device_jobs** - List active jobs on real devices
* **get_specific_real_device_job** - Get details about a specific real device job
* **get_specific_real_device_job_asset** - Download job assets (logs, videos, screenshots)

### Builds

* **lookup_builds** - Search for builds with various filters
* **get_build** - Get detailed information about a specific build
* **lookup_jobs_in_build** - List all jobs within a specific build

### Storage

* **get_storage_files** - List uploaded application files
* **get_storage_groups** - List app storage groups
* **get_storage_groups_settings** - Get settings for specific storage groups

### Tunnels

* **get_tunnels_for_user** - List active Sauce Connect tunnels
* **get_tunnel_information** - Get details about a specific tunnel
* **get_current_jobs_for_tunnel** - See jobs using a specific tunnel

### Test Assets

* **get_test_assets** - Retrieve test artifacts (logs, videos, screenshots)
* **get_log_json_file** - Get structured test execution logs

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Troubleshooting

### "MCP server not found"

Ensure the path to the MCP server executable is correct in your config file. For full paths, run:
```bash
python3 -c "import sys; print(sys.prefix + '/bin')"
```

Verify Python is installed and accessible. Check that all dependencies are installed:
```bash
python3 -m pip list | grep sauce-api-mcp
```

### "Authentication failed"

Verify your SAUCE_USERNAME and SAUCE_ACCESS_KEY are correct. Ensure credentials have proper permissions for the requested operations. Check that your Sauce Labs account is active.

### "No devices found"

Verify your account has access to the device cloud. Check your team's device allocation settings. Ensure you're querying the correct data center region (set SAUCE_REGION if needed).

### "Job not found"

Verify the job ID is correct and belongs to your account. Check if the job is from VDC vs RDC (different endpoints). Ensure the job hasn't expired due to retention policies.

## Getting Help

- Sauce Labs Documentation: [docs.saucelabs.com](https://docs.saucelabs.com)
- API Reference: [docs.saucelabs.com/dev/api](https://docs.saucelabs.com/dev/api)
- Support: Contact Sauce Labs support through your account dashboard
- GitHub Issues: [Report bugs or request features](https://github.com/saucelabs/sauce-api-mcp/issues)

## License

Apache 2.0 (versions 1.1.0+)

Note: Versions prior to 1.0.3 were released under MIT License.

## Roadmap

This roadmap outlines our vision and priorities for the project. It's a living document, and we welcome feedback and contributions from the community! While we aim to follow this plan, priorities can change based on user feedback and new opportunities.

### Short-Term (Next 1-3 Months)

**Resources & Tools - Optimizing Model Calls**
- Implement Resources comprehensively for model responses
- Reduce latency and cost by returning cached results instead of new API calls
- Auto-converting linux time stamps to de-risk incorrect LLM conversions
- Status: Planning

### Mid-Term (3-6 Months)

- Add new API endpoints as Sauce Labs platform evolves
- Improve overall interaction with LLM clients
- Maintain alignment with Sauce Labs API updates
- Add support for new Sauce Labs product lines

## Changelog

### v1.1.0
- Merged sauce-api-mcp and sauce-labs-mcp (RDC OpenAPI) into single monorepo package
- Added sauce-api-mcp-rdc entry point for RDC-focused server
- Updated to use full Python entry points instead of launcher scripts
- Improved installation and configuration documentation
- Locked dependencies with uv.lock for reproducible installs

### v1.0.3
- Updated to use Apache License 2.0 (previously MIT)
- Minor README improvements

### v1.0.2
- Submitted to official MCP Registry
- Added Python 3.9 support

### v1.0.1
- Overhauled and updated README with better install instructions

### v1.0.0
- Initial release with full Sauce Labs API integration
- Support for VDC and RDC platforms
- Comprehensive device management
- Advanced job analysis and build monitoring
- Cross-platform Claude Desktop support

**Made with ❤️ for the testing community**

## Disclaimer of Warranties

THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Limitation of Liability

IN NO EVENT SHALL SAUCE LABS, INC. BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

## General Use

The MCP Server is provided as a free and open-source tool to facilitate interaction with publicly available APIs. Users are free to modify and distribute the software under the terms of the Apache License 2.0.

By using this software, you acknowledge that you are doing so at your own risk and that you are responsible for your own compliance with all applicable laws and regulations.

## Indemnification

You agree to indemnify and hold harmless Sauce Labs, inc. ("Sauce Labs"), its officers, directors, employees, and agents from and against any and all claims, liabilities, damages, losses, or expenses, including reasonable attorneys' fees and costs, arising out of or in any way connected with your access to or use of this software.

This includes, but is not limited to:

- **Your Interaction with Third-Party LLM Providers:** You acknowledge that this software utilizes publicly available APIs for interaction with a Large Language Model (LLM). You are solely responsible for your use of any third-party LLM services, including your adherence to the terms and conditions of the LLM provider and any costs associated with your use, such as token fees. Sauce Labs has no control over, and assumes no responsibility for, the content, privacy policies, or practices of any third-party LLM providers.

- **Content Generated by the LLM:** You are solely responsible for the content generated, received, or transmitted through your use of the MCP Server and the underlying LLM. Sauce Labs does not endorse and has no control over the content of communications made by you or any third party through the server.

- **Your Code and Modifications:** Any modifications, enhancements, or derivative works you create based on the MCP Server are your own, and you are solely responsible for their performance and any liabilities that may arise from their use.
