---
name: Sauce Labs OpenAPI Spec Guidelines
description: Standards for OpenAPI 3.0 specs for Sauce Labs REST APIs that will be exposed through the MCP platform.
---

# Sauce Labs OpenAPI Spec Guidelines

## When to use this skill

Use this when building or modifying any Sauce Labs REST API service that will be
exposed to AI agents via the MCP platform (sauce-api-mcp). Load this skill into
your AI coding assistant's context when designing endpoints, writing OpenAPI
specs, or reviewing API PRs.

## Core principle

**Do not hand-write OpenAPI YAML.** Specs should be generated from your API
code by your framework, or contract-enforced so drift is impossible.

---

## Required: Expose a live OpenAPI spec endpoint

Every Sauce Labs API must serve its current OpenAPI 3.0 spec at a well-known
URL on the API itself:

```
GET https://api.<your-service>.saucelabs.com/openapi.json
```

This is the source of truth. The MCP platform fetches from this URL at startup
to auto-generate tools. Do not publish the spec as a static YAML in a docs repo.

### Framework recipes

#### FastAPI (Python) — built-in, zero config

```python
from fastapi import FastAPI

app = FastAPI(
    title="Sauce Labs VDC API",
    version="2.0.0",
    description="Virtual Device Cloud API",
)
# /openapi.json is served automatically
```

#### Spring Boot (Java)

```xml
<!-- pom.xml -->
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
</dependency>
```
Serves `/v3/api-docs` automatically. Rename to `/openapi.json` via config.

#### NestJS (TypeScript)

```typescript
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';

const config = new DocumentBuilder()
  .setTitle('Sauce Labs Service')
  .setVersion('1.0.0')
  .build();
const document = SwaggerModule.createDocument(app, config);
SwaggerModule.setup('openapi.json', app, document);
```

#### ASP.NET Core (.NET 9+)

```csharp
builder.Services.AddOpenApi();
app.MapOpenApi(); // serves /openapi/v1.json
```

---

## Required: Every endpoint must have

### `operationId` — camelCase verb-noun

```python
@app.get("/devices", operation_id="listDevices")
async def list_devices(): ...
```

- **Correct:** `listDevices`, `createSession`, `getJobDetails`, `uninstallApp`
- **Wrong:** `get_devices`, `List_Devices`, `devices_get`

Without `operationId`, MCP tool names are auto-generated from summaries and
look like `Forward_a_single_http_DELETE_request_via_a_proxy_running` (truncated).

### `summary` — one-line description

Short, action-oriented. Becomes the tool's short label.
- **Correct:** `"List all device descriptors"`
- **Wrong:** `"Devices endpoint"` or `"GET /devices"`

### `description` — detailed explanation

Tells the LLM *when* to use the tool, *what it returns*, and *what to do next*.
This is often the most important field for LLM tool selection.

```python
description = """
Returns the full device catalog. Use when the user wants to see what devices
are available for testing. Returns an array of DeviceDescriptor objects with
hardware and software specifications. For device availability status, use
listDeviceStatus instead.
"""
```

### Parameter descriptions

Every query/path/body parameter needs a description:

```python
async def list_devices(
    device_id: str | None = Query(
        None,
        description="Filter by device identifier. Supports regex patterns.",
    )
): ...
```

### Response schemas with descriptions

Every property in a response schema needs a description:

```python
class Device(BaseModel):
    descriptor: str = Field(
        ...,
        description="Unique identifier for this device type (e.g., iPhone_15_real)"
    )
    os: Literal["ANDROID", "IOS"] = Field(
        ...,
        description="Operating system of the device"
    )
```

---

## Required: Valid OpenAPI 3.0 structure

### Do not place siblings next to `$ref`

OpenAPI 3.0 silently ignores anything next to a `$ref`.

**Wrong:**
```yaml
schema:
  type: object
  $ref: "#/components/schemas/Device"  # type is ignored
```

**Correct:**
```yaml
schema:
  $ref: "#/components/schemas/Device"  # Device already declares its type
```

### Do not use `oneOf` at the response level

`oneOf` belongs inside `content.<mime-type>.schema`, not at the response object level.

**Wrong:**
```yaml
responses:
  "400":
    oneOf:
      - $ref: "#/components/responses/BadRequest"
      - $ref: "#/components/responses/BundleIdMissing"
```

**Correct:**
```yaml
responses:
  "400":
    content:
      application/problem+json:
        schema:
          oneOf:
            - $ref: "#/components/schemas/BadRequestBody"
            - $ref: "#/components/schemas/BundleIdMissingBody"
```

### Required fields must exist in properties

**Wrong:**
```yaml
required: ["id"]
properties:
  bundleId: { type: string }  # there is no "id"
```

**Correct:** Either remove `required` and document alternatives, or make `id` actually exist.

### Match types to examples

**Wrong:**
```yaml
version:
  type: object
  example: "stable"  # "stable" is a string, not an object
```

**Correct:**
```yaml
version:
  type: string
  example: "stable"
```

---

## Required: Validate the spec in CI

Every PR that modifies the spec (or the code generating it) must pass
[Spectral](https://github.com/stoplightio/spectral) validation.

Standard config:

```yaml
# .spectral.yaml
extends:
  - spectral:oas

rules:
  operation-operationId: error
  operation-description: warn
  operation-operationId-unique: error
  oas3-schema: error
  no-$ref-siblings: error
```

GitHub Action:

```yaml
- name: Lint OpenAPI spec
  uses: stoplightio/spectral-action@latest
  with:
    file_glob: "path/to/spec.yaml"
```

Test locally:
```bash
npx @stoplight/spectral-cli lint <spec-url-or-file>
```

---

## MCP-specific recommendations

### Tag endpoints for MCP exposure

Not every endpoint should become an MCP tool. Internal admin, health checks,
and WebSocket endpoints must be excluded.

Use an OpenAPI tag to opt in:

```python
@app.get("/devices", tags=["mcp"])
async def list_devices(): ...

@app.get("/health", include_in_schema=False)
async def health(): ...
```

The MCP platform filters on the `mcp` tag — untagged endpoints are ignored.

### Avoid returning huge responses

Endpoints that return arrays of 100+ items will overflow the LLM context.
Either:
- **Paginate** — accept `limit` and `offset` parameters
- **Filter** — accept query parameters to narrow results
- **Offer both a summary and detail endpoint** — e.g., `listDevices` returns descriptors only, `getDevice/{id}` returns full details

### Binary content cannot be MCP tools

Endpoints that return binary data (images, files) or accept `multipart/form-data`
cannot be auto-generated into MCP tools. Either:
- Return a URL that the client can fetch separately
- Flag these endpoints for manual MCP tool implementation (the platform team
  handles these case-by-case)

### Long-running operations

MCP tool calls are synchronous. For operations that take more than ~10 seconds:
- Return a job ID immediately from the start endpoint
- Provide a separate poll endpoint (e.g., `getJobStatus`)
- Document the chaining pattern in the description

---

## What NOT to do

- ❌ Hand-write YAML in a docs repo (it will drift from the API)
- ❌ Skip `operationId` (breaks tool naming)
- ❌ Omit descriptions (LLMs can't select tools without them)
- ❌ Return raw arrays (wrap in objects for extensibility)
- ❌ Put `type: object` next to `$ref` (silently ignored in OpenAPI 3.0)
- ❌ Use `oneOf` at response level (not valid OpenAPI 3.0)
- ❌ Assume the MCP platform will work around spec bugs (it won't)

---

## Quick onboarding checklist

Before your API is MCP-ready, verify:

- [ ] `GET /openapi.json` returns a valid OpenAPI 3.0 spec
- [ ] Every endpoint has `operationId`, `summary`, `description`
- [ ] Every schema property has a `description`
- [ ] Endpoints meant for MCP are tagged `mcp`
- [ ] CI runs Spectral and passes with zero errors
- [ ] Auth is Basic Auth (or bridged — coordinate with the platform team)
- [ ] No endpoint returns unbounded list data without pagination/filtering

---

## Reference

- [OpenAPI 3.0 specification](https://spec.openapis.org/oas/v3.0.3)
- [Spectral OpenAPI ruleset](https://docs.stoplight.io/docs/spectral/4dec24461f3af-open-api-rules)
- [sauce-api-mcp repository](https://github.com/saucelabs/sauce-api-mcp)
- [RDC Access API spec](https://raw.githubusercontent.com/saucelabs/sauce-docs/main/static/oas/real-device-access-api-spec.yaml) — reference implementation
