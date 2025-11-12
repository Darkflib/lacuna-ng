# lacuna_schema

**YAML schema validation for Lacuna v2 redirection service**

This package provides Pydantic v2 models for validating Lacuna redirect configurations, along with semantic validators and utilities for safe configuration loading.

## Features

- ✅ **Type-safe models**: Pydantic v2 models with full type annotations
- ✅ **Security validation**: Scheme allowlist (http/https only), no templating characters
- ✅ **Semantic checks**: Duplicate ID detection, path validation, status code validation
- ✅ **Rule sorting**: Optimal evaluation order (exact rules first, longest path first)
- ✅ **CLI validator**: Command-line tool for quick config validation
- ✅ **mypy strict**: Fully typed and checked with `mypy --strict`

## Installation

```bash
# Install from local path (during development)
pip install -e packages/lacuna_schema

# Or with uv (recommended)
uv pip install -e packages/lacuna_schema
```

## CLI Usage

Validate a configuration file:

```bash
# Using python -m
python -m lacuna_schema.check examples/domainlist.yaml

# Or just
python -m lacuna_schema examples/domainlist.yaml
```

**Output on success:**

```
✓ Valid configuration: examples/domainlist.yaml
  Version: 1
  Hosts: 3
  Total rules: 6
  - example.com: 4 rules (2 exact, 2 prefix) 🔒
  - old.example.com: 1 rules (0 exact, 1 prefix) 🔒
  - parked.example.com: 1 rules (0 exact, 1 prefix) 🔓
```

**Output on error:**

```
✗ Validation errors in examples/bad.yaml:
  [hosts → 0 → rules → 0 → to] URL must use http or https scheme (not javascript:, data:, file:, etc.): javascript:alert('XSS')
```

## API Usage

### Load and validate a configuration

```python
from pathlib import Path
from lacuna_schema import load_config

# Load and validate YAML
config = load_config(Path("domainlist.yaml"))

# Access configuration
print(f"Version: {config.version}")
print(f"HSTS default: {config.defaults.hsts}")

for host in config.hosts:
    print(f"{host.host}: {len(host.rules)} rules")
```

### Sort rules for optimal evaluation

```python
from lacuna_schema import sort_rules

# Sort rules: exact (longest first), then prefix (longest first)
sorted_host = sort_rules(host)

for rule in sorted_host.rules:
    print(f"{rule.match:6} {rule.from_:20} -> {rule.to}")
```

### Create models programmatically

```python
from lacuna_schema import Config, Defaults, Host, Rule

config = Config(
    version=1,
    defaults=Defaults(hsts=True, keep_query=True),
    hosts=[
        Host(
            host="example.com",
            rules=[
                Rule(
                    id="home",
                    match="exact",
                    **{"from": "/", "to": "https://www.example.org/", "status": 308}
                )
            ]
        )
    ]
)
```

## YAML Schema

### Complete Example

```yaml
version: 1

defaults:
  hsts: true          # Enable HSTS by default
  keep_query: true    # Preserve query strings by default

hosts:
  - host: example.com
    hsts: true        # Optional: override default
    rules:
      # Exact match: must match path exactly
      - id: home
        match: exact
        from: /
        to: https://www.example.org/
        status: 308
        keep_query: true

      # Prefix match: matches /blog and /blog/*
      - id: blog
        match: prefix
        from: /blog
        to: https://blog.example.org
        status: 308
```

### Field Constraints

#### `version` (integer)
- Must be `1` (only supported version)

#### `defaults` (object)
- `hsts` (boolean): Enable HSTS by default (default: `true`)
- `keep_query` (boolean): Preserve query strings by default (default: `true`)

#### `hosts` (array of objects)
Each host has:
- `host` (string): Domain name without protocol (e.g., `example.com`)
- `hsts` (boolean, optional): Override default HSTS setting
- `rules` (array): List of redirect rules (see below)

#### `rules` (array of objects)
Each rule has:
- `id` (string): **Required**. Unique identifier within the host
  - Pattern: `^[a-z0-9][a-z0-9._-]*$`
  - Must start with lowercase letter or digit
  - Can contain lowercase letters, digits, dots, underscores, hyphens
  - Examples: `home`, `api-v2`, `catch_all`, `rule.v1`

- `match` (string): **Required**. Match type
  - `exact`: Match path exactly (e.g., `/about` matches only `/about`)
  - `prefix`: Match path prefix (e.g., `/blog` matches `/blog`, `/blog/post`, etc.)

- `from` (string): **Required**. Source path
  - Must start with `/`
  - Examples: `/`, `/api`, `/blog/posts`

- `to` (string): **Required**. Target URL
  - Must use `http://` or `https://` scheme
  - **Security**: No `{`, `}`, or `$` characters (no templating)
  - Examples: `https://example.com`, `https://api.example.org/v2`

- `status` (integer): **Required**. HTTP redirect status code
  - Must be one of: `301`, `302`, `303`, `307`, `308`
  - `301`: Permanent redirect (cached, changes POST to GET)
  - `302`: Temporary redirect (not cached, changes POST to GET)
  - `303`: See Other (always GET)
  - `307`: Temporary redirect (method preserved)
  - `308`: Permanent redirect (method preserved)

- `keep_query` (boolean, optional): Override default query preservation
  - If not set, inherits from `defaults.keep_query`

## Validation Rules

### Security Rules (enforced)

1. **Scheme allowlist**: Only `http://` and `https://` schemes are allowed
   - ❌ Rejects: `javascript:`, `data:`, `file:`, `ftp:`, etc.

2. **No templating**: Target URLs cannot contain templating characters
   - ❌ Rejects: `{`, `}`, `$` in `to` field
   - This keeps the system simple and prevents injection attacks

### Semantic Rules (enforced)

1. **Rule IDs must be unique** within each host
2. **Paths must start with `/`**
3. **Rule IDs must match pattern** `^[a-z0-9][a-z0-9._-]*$`
4. **Status codes must be valid redirect codes** (301, 302, 303, 307, 308)
5. **Version must be 1** (only supported version)

## Rule Sorting

The `sort_rules()` function orders rules for optimal evaluation:

1. **Exact match rules** (longest path first)
2. **Prefix match rules** (longest path first)

This ensures more specific rules are evaluated before more general ones.

Example:

```python
# Before sorting
rules = [
    Rule(match="prefix", from="/"),           # Catch-all
    Rule(match="exact", from="/about"),       # Specific exact
    Rule(match="prefix", from="/blog/posts"), # Specific prefix
    Rule(match="exact", from="/"),            # Homepage
]

# After sorting
sorted_rules = [
    Rule(match="exact", from="/about"),       # Exact, longest
    Rule(match="exact", from="/"),            # Exact, shorter
    Rule(match="prefix", from="/blog/posts"), # Prefix, longest
    Rule(match="prefix", from="/"),           # Prefix, catch-all
]
```

## Development

### Run tests

```bash
# Run all tests
pytest packages/lacuna_schema/tests/

# Run with coverage
pytest packages/lacuna_schema/tests/ --cov=lacuna_schema --cov-report=html

# Run specific test file
pytest packages/lacuna_schema/tests/test_models.py
```

### Type checking

```bash
# Check types with mypy
mypy packages/lacuna_schema/src/lacuna_schema --strict
```

### Format code

```bash
# Format with ruff and black
ruff check --fix packages/lacuna_schema/
ruff format packages/lacuna_schema/
black packages/lacuna_schema/
```

## Error Messages

The validator provides clear, actionable error messages:

### Invalid scheme
```
[hosts → 0 → rules → 0 → to] URL must use http or https scheme (not javascript:, data:, file:, etc.): javascript:alert('XSS')
```

### Templating characters
```
[hosts → 0 → rules → 0 → to] URL must not contain templating character '{': https://example.com/{user}
```

### Duplicate rule IDs
```
[hosts → 0] Duplicate rule IDs found in host 'example.com': rule1, rule2
```

### Invalid path
```
[hosts → 0 → rules → 0 → from] Path must start with /: api/endpoint
```

### Invalid rule ID
```
[hosts → 0 → rules → 0 → id] String should match pattern '^[a-z0-9][a-z0-9._-]*$'
```

## Architecture

```
lacuna_schema/
├── models.py       # Pydantic v2 models (Config, Host, Rule, Defaults)
├── validators.py   # Validation functions and sorting utilities
├── api.py          # Public API (load_config, sort_rules)
└── __main__.py     # CLI entry point
```

## License

See root repository LICENSE file.

## Related Packages

- `lacuna_compiler`: Compiles validated configs to Caddy JSON
- `lacuna_promote`: Double-buffer promotion with validation and rollback
- `lacuna_sim`: Dry-run simulator for testing rules

## Contributing

See `AGENTS.md` in the root repository for development guidelines and agent instructions.
