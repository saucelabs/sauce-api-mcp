# CHANGELOG

<!-- version list -->

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
