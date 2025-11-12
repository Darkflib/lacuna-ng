# Lacuna v2 - Example Configurations

This directory contains example configurations and test cases for Lacuna v2, demonstrating all features of the YAML-based redirect configuration system.

## Files Overview

### Valid Examples

#### `domainlist.yaml` - Comprehensive Example

The primary example file demonstrating all Lacuna v2 features:

**Features Demonstrated:**
- **Multiple hosts**: `prod.example.com`, `old.example.com`, `parked.example.com`
- **Match types**: Both `exact` and `prefix` matches
- **Status codes**: 301, 302, 307, 308 redirects
- **HSTS control**: Enabled for production hosts, disabled for parked domains
- **Query preservation**: Both enabled and disabled query string handling

**Hosts and Rules:**

1. **prod.example.com** (HSTS enabled)
   - `home` - Exact match on `/` → `https://www.example.org/` (308)
   - `blog` - Prefix match on `/blog` → `https://blog.example.org` (308, keeps query)
   - `docs` - Prefix match on `/docs` → `https://docs.example.org` (308, drops query)
   - `api` - Prefix match on `/api` → `https://api.example.org` (307, keeps query)

2. **old.example.com** (HSTS enabled)
   - `catch-all` - Prefix match on `/` → `https://new.example.com` (301, keeps query)

3. **parked.example.com** (HSTS disabled)
   - `parked` - Prefix match on `/` → `https://about.example.com/parked` (302, drops query)

**Expected Behavior Examples:**

```bash
# Exact match - only / matches
prod.example.com/           → 308 → https://www.example.org/
prod.example.com/anything   → (no match from home rule)

# Prefix match with path preservation
prod.example.com/blog/post-1     → 308 → https://blog.example.org/post-1
prod.example.com/api/v1/users    → 307 → https://api.example.org/v1/users

# Query string preservation (keep_query: true)
prod.example.com/blog?page=2     → 308 → https://blog.example.org?page=2
prod.example.com/api?id=123      → 307 → https://api.example.org?id=123

# Query string dropped (keep_query: false)
prod.example.com/docs?search=foo → 308 → https://docs.example.org (no query)

# Catch-all rule
old.example.com/anything/here    → 301 → https://new.example.com/anything/here
```

---

#### `minimal.yaml` - Simplest Valid Config

The absolute minimum valid Lacuna configuration. Useful for:
- Learning the basic structure
- Testing the schema validator
- Quick prototyping
- Understanding required fields

Contains:
- Single host: `example.com`
- Single rule: exact match on `/`
- Permanent redirect (308)
- HSTS enabled

---

#### `cases.txt` - Test Cases for Simulator

Test cases for the `lacuna-sim` simulator tool. These cover all rules in `domainlist.yaml`.

**Format:**
```
HOST PATH [QUERY]
```

**Examples:**
```
prod.example.com /blog
prod.example.com /blog/post-1
prod.example.com /api/v1/users id=123
old.example.com /anything
```

Each line represents a request that will be matched against the compiled rules. Comments indicate expected behavior.

**Usage with simulator:**
```bash
lacuna-sim --json ./vol/config/config.active.json --cases examples/cases.txt
```

Expected output:
- Which rule matched each request
- Resulting status code and Location header
- List of dead rules (rules that never matched)

---

### Invalid Examples (Negative Tests)

The `invalid/` directory contains intentionally broken configurations to test validation:

#### `bad_scheme.yaml`
- **Violation**: Contains `javascript:` URL (invalid scheme)
- **Expected**: Schema validation should reject (only http/https allowed)

#### `templating.yaml`
- **Violation**: Contains `{variable}` in `to` field
- **Expected**: Validation should reject templating characters (`{`, `}`, `$`)

#### `duplicate_ids.yaml`
- **Violation**: Same rule ID used twice within one host
- **Expected**: Duplicate ID detection should fail

#### `bad_status.yaml`
- **Violation**: Uses status code 200 instead of 30x redirect
- **Expected**: Status code validation should fail (only 301/302/303/307/308)

#### `missing_slash.yaml`
- **Violation**: `from` path doesn't start with `/`
- **Expected**: Path validation should fail

---

## Usage Examples

### 1. Validate Configuration

Check if a YAML file is valid:

```bash
# Using the schema checker
python -m lacuna_schema.check examples/domainlist.yaml

# Expected output on success:
# ✓ Config valid
# Hosts: 3
# Total rules: 6
```

Validate an invalid config (should fail):

```bash
python -m lacuna_schema.check examples/invalid/bad_scheme.yaml

# Expected: validation error about invalid scheme
```

---

### 2. Compile to Caddy JSON

Compile YAML to Caddy JSON without reloading:

```bash
lacuna-compiler examples/domainlist.yaml \
  --out-dir ./vol/config \
  --validate-only
```

This creates `./vol/config/config.next.json` but doesn't reload Caddy.

Compile and promote (with Caddy reload):

```bash
lacuna-compiler examples/domainlist.yaml \
  --out-dir ./vol/config
```

This validates, compiles, and reloads Caddy with the new config.

---

### 3. Simulate Requests

Test requests against compiled configuration:

```bash
lacuna-sim \
  --json ./vol/config/config.active.json \
  --cases examples/cases.txt
```

Expected output (table format):
```
┌──────────────────────┬─────────────────┬────────┬────────┬────────────────────────────────┐
│ Host                 │ Path            │ Query  │ Rule   │ Location                       │
├──────────────────────┼─────────────────┼────────┼────────┼────────────────────────────────┤
│ prod.example.com     │ /               │        │ home   │ https://www.example.org/       │
│ prod.example.com     │ /blog           │        │ blog   │ https://blog.example.org       │
│ prod.example.com     │ /blog/post-1    │        │ blog   │ https://blog.example.org/...   │
│ ...                  │ ...             │ ...    │ ...    │ ...                            │
└──────────────────────┴─────────────────┴────────┴────────┴────────────────────────────────┘

Coverage: 6/6 rules matched (100%)
Dead rules: (none)
```

---

### 4. Run Locally with Docker Compose

Full stack with Caddy:

```bash
# First, compile the config
lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config

# Copy active config for Caddy
cp ./vol/config/config.next.json ./vol/config/config.active.json

# Start Caddy
docker compose up

# Test a redirect (in another terminal)
curl -v http://prod.example.com/blog
```

---

### 5. Development Workflow

Typical development loop:

```bash
# 1. Edit configuration
vi examples/domainlist.yaml

# 2. Validate
python -m lacuna_schema.check examples/domainlist.yaml

# 3. Compile without reload (dry run)
lacuna-compiler examples/domainlist.yaml \
  --out-dir ./vol/config \
  --validate-only

# 4. Inspect generated JSON
jq '._meta' ./vol/config/config.next.json
jq '.apps.http.servers' ./vol/config/config.next.json | head -20

# 5. Simulate requests
lacuna-sim \
  --json ./vol/config/config.next.json \
  --cases examples/cases.txt

# 6. If all looks good, promote (reload Caddy)
lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config
```

---

## Schema Reference

### YAML Structure

```yaml
version: 1                    # Schema version (required)

defaults:                     # Global defaults (required)
  hsts: true                  # Enable HSTS headers (bool)
  keep_query: true            # Preserve query strings (bool)

hosts:                        # List of hosts (required, min 1)
  - host: example.com         # Domain name (required)
    hsts: true                # Override default HSTS (optional)
    rules:                    # List of redirect rules (required, min 1)
      - id: rule-name         # Unique ID per host (required)
        match: exact          # "exact" or "prefix" (required)
        from: /path           # Path to match, starts with / (required)
        to: https://dest.com  # Target URL (required, http/https only)
        status: 308           # HTTP status (301/302/303/307/308)
        keep_query: true      # Override default (optional)
```

### Field Constraints

- **id**: `^[a-z0-9][a-z0-9._-]*$` (lowercase, alphanumeric, dots, dashes)
- **match**: Must be `exact` or `prefix`
- **from**: Must start with `/`, no templating chars
- **to**: Must be valid URL with `http://` or `https://` scheme only
- **status**: One of 301, 302, 303, 307, 308
- **keep_query**: Boolean, defaults to `defaults.keep_query`
- **hsts**: Boolean, defaults to `defaults.hsts`

### Security Rules

- **No templating**: `to` field cannot contain `{`, `}`, or `$` characters
- **Scheme allowlist**: Only `http://` and `https://` schemes allowed
- **No open redirects**: All targets are static, no user-driven redirects
- **HSTS policy**: Enabled by default for production, can be disabled for parked/dev domains

---

## Testing Invalid Configs

To test validation error handling:

```bash
# Test each invalid example
for f in examples/invalid/*.yaml; do
  echo "Testing: $f"
  python -m lacuna_schema.check "$f" 2>&1 | head -5
  echo "---"
done
```

Expected: Each should fail with a specific, actionable error message.

---

## Contributing New Examples

When adding new example configs:

1. **Valid examples**: Should demonstrate a real-world use case
2. **Invalid examples**: Should violate exactly ONE validation rule
3. **Test cases**: Update `cases.txt` to cover new rules
4. **Documentation**: Update this README with expected behavior

---

## References

- **AGENTS.md**: Full technical specification
- **PROJECT_STRUCTURE.md**: Repository structure and dependencies
- **Caddy JSON config docs**: https://caddyserver.com/docs/json/
- **HTTP status codes**: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status

---

## Quick Start Checklist

- [ ] Install dependencies: `uv sync --all-extras --dev`
- [ ] Validate example: `python -m lacuna_schema.check examples/domainlist.yaml`
- [ ] Compile config: `lacuna-compiler examples/domainlist.yaml --out-dir ./vol/config`
- [ ] Run simulator: `lacuna-sim --json ./vol/config/config.next.json --cases examples/cases.txt`
- [ ] Start Caddy: `docker compose up`
- [ ] Test redirect: `curl -v http://localhost/` (update /etc/hosts first)

---

## Troubleshooting

**Q: Validation fails with "scheme not allowed"**
A: Ensure all `to` URLs use `http://` or `https://` only. No `ftp://`, `file://`, etc.

**Q: Validation fails with "templating characters"**
A: Remove `{`, `}`, or `$` from the `to` field. Lacuna v2 doesn't support templating.

**Q: Duplicate ID error**
A: Rule IDs must be unique within each host. Use different IDs like `blog-main` and `blog-archive`.

**Q: Path validation error**
A: Ensure `from` paths start with `/`. Use `/path` not `path`.

**Q: Caddy won't start**
A: Check `config.active.json` exists in `./vol/config/`. Run compiler first to generate it.

---

## License

Lacuna v2 is part of the Lacuna project. See repository root for license information.
