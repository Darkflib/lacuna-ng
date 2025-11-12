# lacuna_compiler

**YAML to Caddy JSON compiler for Lacuna v2**

This package compiles validated Lacuna YAML configurations into deterministic Caddy JSON format with proper redirect handling, security headers, and observability features.

## Features

- **Deterministic compilation**: Same input always produces identical output (excluding timestamp/git fields)
- **Two-server architecture**: Separate HTTP (port 80) and HTTPS (port 443) servers
- **SNI routing**: Host-based routing with optimal rule ordering
- **Exact and prefix matching**: Support for both exact path and prefix path matches
- **Query string handling**: Configurable query preservation per rule
- **Security headers**: Automatic HSTS and X-Lacuna-Rule headers
- **Metadata tracking**: Build timestamp, git hash, and content SHA256
- **Atomic writes**: Safe config file writing with fsync

## Installation

```bash
# Install from workspace
uv sync

# Or install directly
pip install lacuna_compiler
```

## CLI Usage

### Basic Usage

```bash
# Compile and validate only (writes config.next.json)
lacuna-compiler examples/domainlist.yaml --validate-only

# Compile with custom output directory
lacuna-compiler config.yaml --out-dir /srv/lacuna/config

# Use default output directory (./vol/config)
lacuna-compiler examples/domainlist.yaml
```

### CLI Options

- `yaml_path` (required): Path to YAML configuration file
- `--out-dir`, `-o`: Output directory for config.next.json (default: `./vol/config`)
- `--validate-only`: Only validate and compile, don't promote (default: `False`)

### Example Output

```
$ lacuna-compiler examples/domainlist.yaml --validate-only

Loading configuration from examples/domainlist.yaml...
✓ Validated: 3 hosts, 6 total rules
Compiling to Caddy JSON...
✓ Written to ./vol/config/config.next.json
✓ Validation complete (--validate-only mode)

Note: Promotion is not yet implemented.
Use 'caddy validate' and 'caddy reload' manually.
```

## API Usage

### Basic Example

```python
from pathlib import Path
from lacuna_schema import load_config
from lacuna_compiler import compile_to_caddy, write_candidate

# Load and validate YAML
config = load_config(Path("domainlist.yaml"))

# Compile to Caddy JSON
caddy_json = compile_to_caddy(config)

# Access the generated structure
print(caddy_json.keys())  # ['_meta', 'apps']
print(caddy_json['apps']['http']['servers'].keys())  # ['http_redirect', 'https']

# Write to file atomically
output_path = write_candidate(config, Path("./vol/config"))
print(f"Written to: {output_path}")
```

### Advanced Example

```python
import json
from pathlib import Path
from lacuna_schema import load_config
from lacuna_compiler import compile_to_caddy

# Load config
config = load_config(Path("domainlist.yaml"))

# Compile
caddy_json = compile_to_caddy(config)

# Inspect metadata
meta = caddy_json["_meta"]
print(f"Built at: {meta['built_at']}")
print(f"Git hash: {meta['git']}")
print(f"Content SHA: {meta['content_sha256']}")

# Inspect servers
servers = caddy_json["apps"]["http"]["servers"]

# HTTP redirect server
http_redirect = servers["http_redirect"]
print(f"HTTP server listens on: {http_redirect['listen']}")

# HTTPS server
https = servers["https"]
print(f"HTTPS server listens on: {https['listen']}")
print(f"Number of host routes: {len(https['routes'])}")

# Save to custom location
with open("custom_output.json", "w") as f:
    json.dump(caddy_json, f, indent=2)
```

## Caddy JSON Structure

The compiler generates Caddy JSON with the following structure:

### Metadata Block

```json
{
  "_meta": {
    "built_at": "2025-11-12T12:34:56Z",
    "git": "abc1234",
    "content_sha256": "sha256_hash_of_apps_block"
  }
}
```

### HTTP → HTTPS Redirect Server (Port 80)

All HTTP traffic is permanently redirected to HTTPS:

```json
{
  "http_redirect": {
    "listen": [":80"],
    "routes": [{
      "handle": [{
        "handler": "static_response",
        "headers": {
          "Location": ["https://{http.request.host}{http.request.uri}"]
        },
        "status_code": 308
      }]
    }]
  }
}
```

### HTTPS Server (Port 443) with SNI Routing

Each host gets its own route with SNI matching:

```json
{
  "https": {
    "listen": [":443"],
    "routes": [
      {
        "match": [{"host": ["example.com"]}],
        "handle": [{
          "handler": "subroute",
          "routes": [/* rule routes */]
        }],
        "terminal": true
      }
    ]
  }
}
```

## Match Types

### Exact Match

Matches only the exact path specified. The path must match completely.

**YAML:**
```yaml
- id: home
  match: exact
  from: /about
  to: https://example.org/about-us
  status: 308
```

**Generated Caddy JSON:**
```json
{
  "match": [{"path": ["/about"]}],
  "handle": [
    {
      "handler": "headers",
      "response": {
        "set": {
          "X-Lacuna-Rule": ["home"],
          "Strict-Transport-Security": ["max-age=31536000; includeSubDomains; preload"]
        }
      }
    },
    {
      "handler": "static_response",
      "headers": {
        "Location": ["https://example.org/about-us"]
      },
      "status_code": 308
    }
  ]
}
```

### Prefix Match

Matches the specified path and all paths under it. The remainder path is preserved.

**YAML:**
```yaml
- id: blog
  match: prefix
  from: /blog
  to: https://blog.example.com
  status: 308
  keep_query: true
```

**Generated Caddy JSON:**
```json
{
  "match": [{"path": ["/blog*"]}],
  "handle": [
    {
      "handler": "subroute",
      "routes": [{
        "handle": [
          {
            "handler": "rewrite",
            "strip_path_prefix": "/blog"
          },
          {
            "handler": "headers",
            "response": {
              "set": {
                "X-Lacuna-Rule": ["blog"],
                "Strict-Transport-Security": ["max-age=31536000; includeSubDomains; preload"]
              }
            }
          },
          {
            "handler": "static_response",
            "headers": {
              "Location": ["{http.vars.redirect_uri}"]
            },
            "status_code": 308
          }
        ]
      }]
    },
    {
      "handler": "vars",
      "redirect_uri": "https://blog.example.com{http.request.uri.path}{http.request.uri.query}"
    }
  ]
}
```

**Example redirects:**
- `/blog` → `https://blog.example.com/`
- `/blog/post1` → `https://blog.example.com/post1`
- `/blog/post1?page=2` → `https://blog.example.com/post1?page=2`

## Query String Handling

Query strings can be preserved or dropped per rule:

### Keep Query (keep_query: true)

```yaml
- id: api
  match: prefix
  from: /api
  to: https://api.example.com
  keep_query: true  # Preserves query strings
```

**Behavior:**
- `/api/users?page=2` → `https://api.example.com/users?page=2` ✓
- `/api/users` → `https://api.example.com/users` ✓

**Implementation:** Uses Caddy's `vars` handler to construct redirect URI with `{http.request.uri.query}` placeholder.

### Drop Query (keep_query: false)

```yaml
- id: docs
  match: prefix
  from: /docs
  to: https://docs.example.com
  keep_query: false  # Drops query strings
```

**Behavior:**
- `/docs/guide?v=old` → `https://docs.example.com/guide` (query dropped)
- `/docs/guide` → `https://docs.example.com/guide` ✓

**Implementation:** Direct Location header construction without query placeholder.

## Security Headers

### X-Lacuna-Rule Header

Every redirect response includes the `X-Lacuna-Rule` header with the rule ID for observability:

```
X-Lacuna-Rule: blog
```

This enables:
- Request tracing and debugging
- Access log analysis
- Rule coverage monitoring

### HSTS Header

When HSTS is enabled (per host or via defaults), the following header is added:

```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

**Configuration:**

```yaml
defaults:
  hsts: true  # Global default

hosts:
  - host: prod.example.com
    hsts: true  # HSTS enabled

  - host: parked.example.com
    hsts: false  # HSTS disabled (overrides default)
```

**Security implications:**
- **Enable** for production domains with valid HTTPS certificates
- **Disable** for parked/development domains or HTTP-only testing

## Deterministic Builds

The compiler produces deterministic output for reproducible builds:

### Stable Content

For the same input YAML, the `apps` block is always identical:
- Rule ordering is deterministic (via `lacuna_schema.sort_rules`)
- JSON structure is stable
- Field ordering is consistent

### Content SHA256

The metadata includes a SHA256 hash of the `apps` block:

```json
{
  "_meta": {
    "content_sha256": "cad3dc0d611cd42831f58e5c71571e2d50e926dd0d3f94898ab27156f5d687de"
  }
}
```

This enables:
- Change detection (did the config actually change?)
- Build verification
- Audit trails

### Variable Fields

Only these fields vary between compilations:
- `_meta.built_at`: Timestamp of compilation
- `_meta.git`: Git commit hash (if in repo)

## Testing

### Run Unit Tests

```bash
# Run all tests
pytest packages/lacuna_compiler/tests/

# Run with coverage
pytest packages/lacuna_compiler/tests/ --cov=lacuna_compiler

# Run specific test file
pytest packages/lacuna_compiler/tests/test_compiler.py

# Run golden file tests
pytest packages/lacuna_compiler/tests/test_golden.py
```

### Golden File Tests

Golden file tests ensure deterministic output by comparing compiled results against known-good reference files:

```bash
# Run golden tests
pytest packages/lacuna_compiler/tests/test_golden.py -v

# Update golden file (after intentional changes)
python -c "
from pathlib import Path
from lacuna_schema import load_config
from lacuna_compiler import compile_to_caddy
import json

config = load_config(Path('examples/domainlist.yaml'))
result = compile_to_caddy(config)
result['_meta']['built_at'] = '2025-11-12T00:00:00Z'
result['_meta']['git'] = 'test'

with open('packages/lacuna_compiler/tests/golden/domainlist.json', 'w') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
"
```

## Type Safety

The package is fully typed and compatible with `mypy --strict`:

```bash
# Run type checks
mypy packages/lacuna_compiler/src/
```

All public APIs have complete type annotations for IDE support and static analysis.

## Integration with Caddy

### Manual Validation

```bash
# Compile config
lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config --validate-only

# Validate with Caddy
caddy validate --config ./vol/config/config.next.json

# Run Caddy
caddy run --config ./vol/config/config.next.json
```

### Testing Redirects

```bash
# Start Caddy
caddy run --config ./vol/config/config.next.json

# Test HTTP → HTTPS redirect
curl -I http://prod.example.com/

# Test exact match
curl -I https://prod.example.com/

# Test prefix match with path preservation
curl -I https://prod.example.com/blog/my-post

# Test query preservation
curl -I https://prod.example.com/blog/my-post?page=2
```

### Response Headers to Expect

All redirects include:
- `Location`: Target URL
- `X-Lacuna-Rule`: Rule ID that matched
- `Strict-Transport-Security`: HSTS header (if enabled)

## Development

### Project Structure

```
packages/lacuna_compiler/
├── src/
│   └── lacuna_compiler/
│       ├── __init__.py       # Public API exports
│       ├── api.py            # Public API functions
│       ├── compiler.py       # Core compilation logic
│       ├── cli.py            # CLI interface
│       └── py.typed          # Type marker
├── tests/
│   ├── test_compiler.py      # Unit tests
│   ├── test_golden.py        # Golden file tests
│   └── golden/
│       └── domainlist.json   # Expected output
├── pyproject.toml            # Package metadata
└── README.md                 # This file
```

### Dependencies

- `lacuna_schema`: Pydantic models and validation
- `typer`: CLI framework
- `pyyaml`: YAML parsing

### Contributing

1. Ensure all tests pass: `pytest packages/lacuna_compiler/tests/`
2. Ensure type checks pass: `mypy packages/lacuna_compiler/src/`
3. Format code: `ruff format . && black .`
4. Update golden files if Caddy JSON structure changes intentionally

## See Also

- [lacuna_schema](../lacuna_schema/README.md): YAML validation and models
- [AGENTS.md](../../AGENTS.md): Full project specification
- [Caddy JSON Config](https://caddyserver.com/docs/json/): Caddy configuration reference
