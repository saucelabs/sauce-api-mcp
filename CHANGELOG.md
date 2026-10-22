# CHANGELOG

<!-- version list -->

## v1.3.0 (2026-10-22)

### Bug Fixes

- Return API errors instead of crashing in Core tools
  ([#86](https://github.com/saucelabs/sauce-api-mcp/pull/86),
  [`9fa7191`](https://github.com/saucelabs/sauce-api-mcp/commit/9fa71919d9f9278049631e4792c5967fe8371318))

- **deps**: Adopt mcp 2.x and fastmcp 4.x
  ([#82](https://github.com/saucelabs/sauce-api-mcp/pull/82),
  [`6db1a16`](https://github.com/saucelabs/sauce-api-mcp/commit/6db1a16030562f4ec89964678913804ea8e16e0c))

### Chores

- **deps**: Bump actions/checkout from 6 to 7
  ([#71](https://github.com/saucelabs/sauce-api-mcp/pull/71),
  [`195523d`](https://github.com/saucelabs/sauce-api-mcp/commit/195523d30a64feeeb44175f5b2e0ab7f7bfb49aa))

- **deps**: Bump actions/setup-python from 6 to 7
  ([#74](https://github.com/saucelabs/sauce-api-mcp/pull/74),
  [`9966106`](https://github.com/saucelabs/sauce-api-mcp/commit/99661065499a61ab572b427ec348d5a229599d87))

- **deps**: Bump anyio from 4.12.0 to 4.14.2
  ([#79](https://github.com/saucelabs/sauce-api-mcp/pull/79),
  [`5acdf3a`](https://github.com/saucelabs/sauce-api-mcp/commit/5acdf3a0bd600db9196e0ac411a7cf267b1727bf))

- **deps**: Bump cryptography from 46.0.7 to 48.0.1
  ([#69](https://github.com/saucelabs/sauce-api-mcp/pull/69),
  [`7e336e6`](https://github.com/saucelabs/sauce-api-mcp/commit/7e336e6f9f7f4a5a34f73437b88160ee492f06ff))

- **deps**: Bump cryptography from 48.0.1 to 50.0.0
  ([#75](https://github.com/saucelabs/sauce-api-mcp/pull/75),
  [`5bf91e8`](https://github.com/saucelabs/sauce-api-mcp/commit/5bf91e8c3d5a365609b53dda7d59f8ffc1ceeaa1))

- **deps**: Bump mcp from 1.24.0 to 1.28.1
  ([#73](https://github.com/saucelabs/sauce-api-mcp/pull/73),
  [`d970c2b`](https://github.com/saucelabs/sauce-api-mcp/commit/d970c2b12e5725073e6c8acd9aae15e68f8a6c83))

- **deps**: Bump pydantic-settings from 2.12.0 to 2.14.2
  ([#70](https://github.com/saucelabs/sauce-api-mcp/pull/70),
  [`f4bc35b`](https://github.com/saucelabs/sauce-api-mcp/commit/f4bc35b7f401f8913bfb76dfdebfbfc1e7e32a85))

- **deps**: Bump pyjwt from 2.12.0 to 2.13.0
  ([#66](https://github.com/saucelabs/sauce-api-mcp/pull/66),
  [`c5d40df`](https://github.com/saucelabs/sauce-api-mcp/commit/c5d40dfa0dc356b0a3ccdcd9291614b225582539))

- **deps**: Bump pyjwt from 2.13.0 to 2.15.0
  ([#80](https://github.com/saucelabs/sauce-api-mcp/pull/80),
  [`3b8f5e2`](https://github.com/saucelabs/sauce-api-mcp/commit/3b8f5e2d7e674e13510673d993eaba237b55f6a4))

- **deps**: Bump python-multipart from 0.0.27 to 0.0.31
  ([#67](https://github.com/saucelabs/sauce-api-mcp/pull/67),
  [`17702b2`](https://github.com/saucelabs/sauce-api-mcp/commit/17702b22e6a4c88ee3d840556b1d7065d79917a0))

- **deps**: Bump starlette from 0.50.0 to 1.0.1
  ([#65](https://github.com/saucelabs/sauce-api-mcp/pull/65),
  [`834be75`](https://github.com/saucelabs/sauce-api-mcp/commit/834be75b64c83284e75c9079ba3a153c545c92ca))

- **deps**: Bump starlette from 1.0.1 to 1.3.1
  ([#68](https://github.com/saucelabs/sauce-api-mcp/pull/68),
  [`1a5036d`](https://github.com/saucelabs/sauce-api-mcp/commit/1a5036de0c59dc4b350eba617c16f712f271835f))

- **deps**: Bump urllib3 from 2.7.0 to 2.8.0
  ([#81](https://github.com/saucelabs/sauce-api-mcp/pull/81),
  [`769eba1`](https://github.com/saucelabs/sauce-api-mcp/commit/769eba1d5130eb7f77e2a5413d269b2ea03c78f2))

### Continuous Integration

- Run real-device slow tests one at a time
  ([#83](https://github.com/saucelabs/sauce-api-mcp/pull/83),
  [`1e0dd14`](https://github.com/saucelabs/sauce-api-mcp/commit/1e0dd142893ab55461c255e30e7f982e5c535182))

### Documentation

- Point README readers to the hosted Sauce MCP server
  ([`6105cab`](https://github.com/saucelabs/sauce-api-mcp/commit/6105cabd6344ce3a3ce0627c8d6f3c0b006048ce))

- Simplify tracking module docstring ([#85](https://github.com/saucelabs/sauce-api-mcp/pull/85),
  [`ae49c7c`](https://github.com/saucelabs/sauce-api-mcp/commit/ae49c7c0019bb4cb6835ab0c5ff70a2bd2ea6f42))

### Features

- Add the server version to the User-Agent
  ([#84](https://github.com/saucelabs/sauce-api-mcp/pull/84),
  [`acf5b14`](https://github.com/saucelabs/sauce-api-mcp/commit/acf5b14c2649d9b0fd6d54f06136f6ec0e18d997))

- Send OSS tracking headers on every request
  ([#85](https://github.com/saucelabs/sauce-api-mcp/pull/85),
  [`ae49c7c`](https://github.com/saucelabs/sauce-api-mcp/commit/ae49c7c0019bb4cb6835ab0c5ff70a2bd2ea6f42))

- Set a User-Agent that identifies the MCP server
  ([#84](https://github.com/saucelabs/sauce-api-mcp/pull/84),
  [`acf5b14`](https://github.com/saucelabs/sauce-api-mcp/commit/acf5b14c2649d9b0fd6d54f06136f6ec0e18d997))

- Use "Sauce OSS MCP Server" as the User-Agent
  ([#84](https://github.com/saucelabs/sauce-api-mcp/pull/84),
  [`acf5b14`](https://github.com/saucelabs/sauce-api-mcp/commit/acf5b14c2649d9b0fd6d54f06136f6ec0e18d997))


## v1.2.2 (2026-06-02)

### Bug Fixes

- **registry**: Correct mcp-name org to io.github.saucelabs in README
  ([#64](https://github.com/saucelabs/sauce-api-mcp/pull/64),
  [`17881fa`](https://github.com/saucelabs/sauce-api-mcp/commit/17881fa151abb97cd68857faef1bdab3925de779))


## v1.2.1 (2026-06-02)

### Bug Fixes

- **release**: Attach server.json to stable GitHub release
  ([#62](https://github.com/saucelabs/sauce-api-mcp/pull/62),
  [`551249f`](https://github.com/saucelabs/sauce-api-mcp/commit/551249f4fd0024c7cb0af57c664461e536a8ee01))

- **release**: Generate full changelog from last stable tag on stable releases
  ([#62](https://github.com/saucelabs/sauce-api-mcp/pull/62),
  [`551249f`](https://github.com/saucelabs/sauce-api-mcp/commit/551249f4fd0024c7cb0af57c664461e536a8ee01))

- **release**: Track server.json in PSR assets and fix registry server name
  ([#62](https://github.com/saucelabs/sauce-api-mcp/pull/62),
  [`551249f`](https://github.com/saucelabs/sauce-api-mcp/commit/551249f4fd0024c7cb0af57c664461e536a8ee01))

- **tests**: Handle null asset values in get_asset_url and e2e flow
  ([#62](https://github.com/saucelabs/sauce-api-mcp/pull/62),
  [`551249f`](https://github.com/saucelabs/sauce-api-mcp/commit/551249f4fd0024c7cb0af57c664461e536a8ee01))


## v1.2.0 (2026-05-29)

### Documentation

- Update README to reflect current architecture and tooling
  ([#61](https://github.com/saucelabs/sauce-api-mcp/pull/61),
  [`b925391`](https://github.com/saucelabs/sauce-api-mcp/commit/b925391e61df2b2bbd634d8be7012a905b20b0cc))


## v1.1.1-rc.2 (2026-05-29)

### Bug Fixes

- Update server.json schema and guard MCP Registry publish
  ([#60](https://github.com/saucelabs/sauce-api-mcp/pull/60),
  [`1de3f94`](https://github.com/saucelabs/sauce-api-mcp/commit/1de3f94a466f17b30661725d0846f896acf5f486))


## v1.1.1-rc.1 (2026-05-29)

### Bug Fixes

- Replace deprecated FastMCPOpenAPI with OpenAPIProvider + FastMCP
  ([`f547650`](https://github.com/saucelabs/sauce-api-mcp/commit/f5476506c9b68238ca7bee0f3c85a2bab3cac931))

- Update remaining fastmcp.server.openapi imports to new path
  ([`8c0bc69`](https://github.com/saucelabs/sauce-api-mcp/commit/8c0bc69f76b95d642c8eeb9d1eb4ca02a2d1068c))

### Chores

- Bump build job to Python 3.12 and sync uv.lock with pyproject.toml specifiers
  ([`81e4719`](https://github.com/saucelabs/sauce-api-mcp/commit/81e4719ec007758231bff6a930602dee064ccdb6))

- Enable dependabot updates for GitHub Actions
  ([`483f000`](https://github.com/saucelabs/sauce-api-mcp/commit/483f000a1a7d96fb16ef05ab1d396155dfd8a417))

- Sync pyproject.toml minimum versions with uv.lock
  ([`f1d550d`](https://github.com/saucelabs/sauce-api-mcp/commit/f1d550da1acece1d2386ed7552271f036c27b7d3))

- Update author information in __init__.py and pyproject.toml
  ([`15be385`](https://github.com/saucelabs/sauce-api-mcp/commit/15be385b2e35485f7244e7173bd6d5c947db34f7))

### Continuous Integration

- Add step to create GitHub release after successful semantic release
  ([#59](https://github.com/saucelabs/sauce-api-mcp/pull/59),
  [`815d775`](https://github.com/saucelabs/sauce-api-mcp/commit/815d775f796faa2d1848bcab2c6dcf35b1431ae1))

- Automate releases via workflow_dispatch and python-semantic-release
  ([#59](https://github.com/saucelabs/sauce-api-mcp/pull/59),
  [`815d775`](https://github.com/saucelabs/sauce-api-mcp/commit/815d775f796faa2d1848bcab2c6dcf35b1431ae1))

- Expose SAUCE_USERNAME and SAUCE_ACCESS_KEY secrets to test steps
  ([`08b1241`](https://github.com/saucelabs/sauce-api-mcp/commit/08b1241554d48bde7fbafc0e92cf64bf24407ac1))

- Limit test parallelism to improve stability
  ([`297833e`](https://github.com/saucelabs/sauce-api-mcp/commit/297833eea4aa6f97ca407369fb29419d90cb2009))

- Run full test suite in CI and fix test robustness
  ([`181c2d4`](https://github.com/saucelabs/sauce-api-mcp/commit/181c2d4a5492880472179cbe65d286ea7d35e199))

- Split main.yml test job into integration, live, and slow stages
  ([`a744c2a`](https://github.com/saucelabs/sauce-api-mcp/commit/a744c2a835dfd0ed2e8e3c547ffd9f4c8940d66c))

- Split test job into integration, live, and slow stages
  ([`b9ec740`](https://github.com/saucelabs/sauce-api-mcp/commit/b9ec740dbc80714aa45e605313e6d7b0ebbae8dc))

- Update server.json version automatically on each release
  ([#59](https://github.com/saucelabs/sauce-api-mcp/pull/59),
  [`815d775`](https://github.com/saucelabs/sauce-api-mcp/commit/815d775f796faa2d1848bcab2c6dcf35b1431ae1))

### Documentation

- Update rdc_dynamic module docstring to reflect FastMCP + OpenAPIProvider architecture
  ([`1d33b7d`](https://github.com/saucelabs/sauce-api-mcp/commit/1d33b7d17ece526d4bafcc883f7d38cc4ad7e5c2))

### Testing

- Align RDC dynamic e2e expectations with manual tool contracts
  ([`4c965fe`](https://github.com/saucelabs/sauce-api-mcp/commit/4c965fe486647b6b4528bc6c4cdf7f4ece352641))

- Update rdc dynamic e2e expectations for 7 manual tools
  ([`953e668`](https://github.com/saucelabs/sauce-api-mcp/commit/953e6689c1f11539fc45b19da05290eaf2f760bc))


## v1.1.0 (2025-12-12)


## v1.0.1 (2025-08-13)

- Initial Release
