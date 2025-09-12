# Sauce Labs MCP Server

[//]: # (mcp-name: io.github.saucelabs-sample-test-frameworks/sauce-api-mcp)

A Model Context Protocol (MCP) server that provides comprehensive integration with Sauce Labs testing platform. This 
server enables AI assistants (LLM clients) to interact with Sauce Labs' device cloud, manage test jobs, analyze builds, 
and monitor testing infrastructure directly through natural language conversations.

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

### Prerequisites
- Python 3.9+
- `pip`
- Sauce Labs account with API access
- Gemini CLI, Claude Desktop, Goose, or other LLM Client

### For Claude Desktop (Mac/Linux) or Gemini CLI 

1. **Install the MCP server and download the launch script**:

    ```bash
    pip install sauce-api-mcp
   
    curl -o ~/sauce-mcp-launcher.sh https://raw.githubusercontent.com/saucelabs/sauce-api-mcp/refs/heads/main/sauce-mcp-launcher.sh
    chmod +x ~/sauce-mcp-launcher.sh
    ```
 
2. **Configure the Client**:
   
    Edit the config file:

***Claude***

    `~/Library/Application\ Support/Claude/claude_desktop_config.json`

***Gemini CLI***

   `~/.gemini/settings.json`

3. **Add the Sauce Labs MCP server configuration**:

    ```json
    {
      "mcpServers": {
        "sauce-labs": {
        "command": "/path/to/tmp/sauce-mcp-launcher.sh",
          "env": {
            "SAUCE_USERNAME": "your-sauce-username",
            "SAUCE_ACCESS_KEY": "your-sauce-access-key"
          }
        }
      }
    }
    ```
 
   ***Note: if you configure SAUCE_USERNAME and SAUCE_ACCESS_KEY as environment variables, you won't need to add them to the config block. 

4. **Restart the client to load the new MCP server.**

#### [Goose](https://block.github.io/goose/)

First, install the MCP Server from `pip`, and download the launch script:

   ```bash
       pip install sauce-api-mcp
      
       curl -o ~/sauce-mcp-launcher.sh https://raw.githubusercontent.com/saucelabs/sauce-api-mcp/refs/heads/main/sauce-mcp-launcher.sh
       chmod +x ~/sauce-mcp-launcher.sh
   ```

Within your `~/.config/goose/config.yaml` file, add the following extension:

  ```bash
  sauce-api-mcp:
    args: []
    bundled: null
    cmd: /<path>/sauce-mcp-launcher.sh
    description: Sauce Labs MCP for API
    enabled: true
    env_keys: []
    envs: {}
    name: sauce-api-mcp
    timeout: 10
    type: stdio
```
Be sure to edit the <path> to reflect your launch script location.

#### Now you can ask questions like:
* "Show me my recent test failures"
* "Find available iPhone devices for testing"
* "Analyze the performance of my latest build"

## Configuration ##
### Required Environment Variables ###
- SAUCE_USERNAME: Your Sauce Labs username
- SAUCE_ACCESS_KEY: Your Sauce Labs access key (found in Account Settings)

### Optional Configuration ###

SAUCE_REGION: Sauce Labs data center region (default: us-west-1)

# Getting Your Sauce Labs Credentials #

1. Log into your Sauce Labs account
2. Navigate to Account → User Settings
3. Copy your Username and Access Key
4. Add these to your Claude Desktop configuration

### Usage Examples ###
Once configured, you can interact with Sauce Labs through natural language in Claude Desktop:
#### Device Management

```
"Show me all available iPhone devices"
"What Android devices are currently in use?"
"Find me a Samsung Galaxy S24 for testing"
```
#### Test Job Analysis
```
"Show me my recent test jobs"
"Analyze the failed tests from my last build"
"Get details about job ID abc123def456"
```
#### Build Monitoring
```
"What's the status of my latest build?"
"Show me all builds from this week"
"Find builds that have failed tests"
```
#### Storage Management
```
"List my uploaded apps"
"Show me app storage usage"
"Find the iOS demo app"
```
#### Team Collaboration
```
"Who's on my testing team?"
"Show me team device allocations"
"List all users in my organization"
```

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
* 
### Test Assets

* **get_test_assets** - Retrieve test artifacts (logs, videos, screenshots)
* **get_log_json_file** - Get structured test execution logs

## Troubleshooting
### Common Issues

### "MCP server not found"

Ensure the path to the MCP server executable is correct
Verify Python is installed and accessible
Check that all dependencies are installed

### "Authentication failed"

Verify your SAUCE_USERNAME and SAUCE_ACCESS_KEY are correct
Ensure credentials have proper permissions for the requested operations
Check that your Sauce Labs account is active

### "No devices found"

Verify your account has access to the device cloud
Check your team's device allocation settings
Ensure you're querying the correct data center region

### "Job not found"

Verify the job ID is correct and belongs to your account
Check if the job is from VDC vs RDC (different endpoints)
Ensure the job hasn't expired due to retention policies

## Getting Help

- Sauce Labs Documentation: docs.saucelabs.com
- API Reference: docs.saucelabs.com/dev/api
- Support: Contact Sauce Labs support through your account dashboard

# License
This project is licensed under the MIT License - see the LICENSE file for details.

# Roadmap

This roadmap outlines our vision and priorities for the project. It's a living document, and we welcome feedback and contributions from the
community! While we aim to follow this plan, priorities can change based on user feedback and new opportunities.

Want to help? We'd love to have you!

* Check out our **CONTRIBUTING.md** (CONTRIBUTING.md) guide.
* Find an existing issue in our **Issue Tracker** (../issues) that interests you.
* Have a new idea? **Open a new issue** (../issues/new/choose) to discuss it with us.

## 🎯 Short-Term (Next 1-3 Months)
Our immediate focus is on enhancing the core developer experience and improving context management.

## Resources & Tools - Optimizing Model Calls
* Description: Implement Resources comprehensively for model responses. For some prompts, this will reduce latency and cost by returning a
cached result instead of making a new API call.
* Status: Planning

🚀 Mid-Term (3-6 Months)

We plan to focus on adding API endpoints and improving overall interaction with the LLM. We will also maintain the Server to keep up with changes to 
the Sauce Labs API, and to add new product lines as they are introduced.


# Changelog
## v1.0.0
- Initial release with full Sauce Labs API integration
- Support for VDC and RDC platforms
- Comprehensive device management
- Advanced job analysis and build monitoring
- Cross-platform Claude Desktop support

**Made with ❤️ for the testing community**

# Disclaimer of Warranties

THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE 
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR 
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR 
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# Limitation of Liability

IN NO EVENT SHALL SAUCE LABS, INC. BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL 
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR 
BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT 
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE 
POSSIBILITY OF SUCH DAMAGE.

# General Use

The MCP Server is provided as a free and open-source tool to facilitate interaction with publicly available APIs. Users 
are free to modify and distribute the software under the terms of the MIT License.

By using this software, you acknowledge that you are doing so at your own risk and that you are responsible for your 
own compliance with all applicable laws and regulations.

# Indemnification

You agree to indemnify and hold harmless Sauce Labs, inc. ("Sauce Labs"), its officers, directors, employees, and 
agents from and against any and all claims, liabilities, damages, losses, or expenses, including reasonable attorneys' 
fees and costs, arising out of or in any way connected with your access to or use of this software.

This includes, but is not limited to:

* **Your Interaction with Third-Party LLM Providers:** You acknowledge that this software utilizes publicly available APIs for interaction with a Large Language Model (LLM). You are solely responsible for your use of any third-party LLM services. This includes your adherence to the terms and conditions of the LLM provider and any costs associated with your use, such as token fees. Sauce Labs has no control over, and assumes no responsibility for, the content, privacy policies, or practices of any third-party LLM providers.
* **Content Generated by the LLM:** You are solely responsible for the content generated, received, or transmitted through your use of the MCP Server and the underlying LLM. Sauce Labs does not endorse and has no control over the content of communications made by you or any third party through the server.
* **Your Code and Modifications:** Any modifications, enhancements, or derivative works you create based on the MCP Server are your own, and you are solely responsible for their performance and any liabilities that may arise from their use.
