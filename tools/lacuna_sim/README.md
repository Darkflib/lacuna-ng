# Lacuna Simulator (`lacuna_sim`)

Dry-run simulator for testing Lacuna v2 redirect configurations **without running Caddy**.

## Purpose

The simulator evaluates redirect rules offline to:

- **Test redirect behavior** - Verify which rule matches for given requests
- **Find dead rules** - Identify rules never matched by any test case
- **Generate coverage reports** - Show percentage of rules exercised by tests
- **Validate configs** - Catch issues before deploying to production

## Installation

```bash
# From repository root
uv sync --all-packages

# The lacuna-sim command will be available
uv run lacuna-sim --help
```

## Quick Start

```bash
# Test with cases file
uv run lacuna-sim --yaml examples/domainlist.yaml --cases examples/cases.txt

# Test single request
uv run lacuna-sim --yaml examples/domainlist.yaml --request "prod.example.com /blog"

# Test with query string
uv run lacuna-sim --yaml examples/domainlist.yaml --request "prod.example.com /blog page=2"
```

## How It Works

### Matching Algorithm

The simulator **mirrors Caddy's routing logic** to ensure accurate predictions:

1. **Find matching host** - Match request hostname against config hosts
2. **Sort rules** - Using `lacuna_schema.sort_rules()`:
   - All **exact** match rules first (longest path first)
   - Then all **prefix** match rules (longest path first)
3. **Iterate through rules** in sorted order:
   - **Exact match**: `path == rule.from` → MATCH
   - **Prefix match**: `path.startswith(rule.from)` → MATCH
4. **Build redirect Location header**:
   - **Exact match**: Use `rule.to` as-is
   - **Prefix match**: Strip `rule.from` from path, append remainder to `rule.to`
   - If `keep_query=true` and query exists: append `?{query}`
5. **Return**: `(rule_id, status, location)` or no-match

### Example

Given config:
```yaml
hosts:
  - host: example.com
    rules:
      - id: home
        match: exact
        from: /
        to: https://www.example.org/
        status: 308

      - id: blog
        match: prefix
        from: /blog
        to: https://blog.example.org
        status: 308
        keep_query: true
```

Request: `example.com /blog/post-1 page=2`

**Evaluation**:
1. Host matches: `example.com` ✓
2. Rules sorted: `home` (exact), then `blog` (prefix)
3. Check `home`: `/blog/post-1` != `/` → no match
4. Check `blog`: `/blog/post-1`.startswith(`/blog`) → MATCH
5. Build location:
   - Base: `https://blog.example.org`
   - Remainder: `/post-1` (strip `/blog` from `/blog/post-1`)
   - Result: `https://blog.example.org/post-1`
   - Query: `keep_query=true` → append `?page=2`
   - **Final**: `https://blog.example.org/post-1?page=2`

## CLI Usage

### Options

```
--yaml, -y PATH       Path to YAML config file (required)
--cases, -c PATH      Path to test cases file
--request, -r TEXT    Single request: "HOST PATH [QUERY]"
--coverage / --no-coverage
                      Show coverage report (default: enabled)
--verbose, -v         Verbose output
--help                Show help
```

### Test Cases File Format

Create a `cases.txt` file with one request per line:

```
# Comments start with #
HOST PATH [QUERY]

# Examples:
prod.example.com /
prod.example.com /blog/post-1
prod.example.com /blog/2024/11/article page=2
old.example.com /anything
```

**Format rules**:
- Lines starting with `#` are comments (ignored)
- Empty lines are ignored
- Format: `HOST PATH [QUERY]` (space-separated)
- Query string is optional (everything after second space)

### Output Format

**Results Table**:
```
Simulation Results
┌─────────────────────────────┬───────────────┬────────┬──────────────────────────────┐
│ Request                     │ Rule ID       │ Status │ Location                     │
├─────────────────────────────┼───────────────┼────────┼──────────────────────────────┤
│ prod.example.com /          │ home          │ 308    │ https://www.example.org/     │
│ prod.example.com /blog      │ blog          │ 308    │ https://blog.example.org     │
│ prod.example.com /blog/post │ blog          │ 308    │ https://blog.example.org/post│
└─────────────────────────────┴───────────────┴────────┴──────────────────────────────┘
```

**Coverage Report**:
```
Coverage Report:
✓ 6/6 rules matched (100%)
✓ No dead rules

All test cases passed!
```

**With dead rules**:
```
Coverage Report:
⚠ 4/6 rules matched (66.7%)
✗ Dead rules (never matched):
  - api-v2
  - legacy-redirect

⚠ Some issues found
```

### Exit Codes

- **0** - All tests passed, 100% coverage, no dead rules
- **1** - Dead rules found OR requests didn't match any rule

## Programmatic API

```python
from pathlib import Path
from lacuna_sim import (
    load_config_from_yaml,
    parse_cases_file,
    simulate_batch,
    generate_coverage_report,
    match_request,
    Request
)

# Load config
cfg = load_config_from_yaml(Path("domainlist.yaml"))

# Load test cases from file
requests = parse_cases_file(Path("cases.txt"))

# Or create requests manually
requests = [
    Request(host="example.com", path="/", query=""),
    Request(host="example.com", path="/blog/post-1", query="page=2"),
]

# Simulate all requests
results = simulate_batch(cfg, requests)

# Print results
for result in results:
    if result.matched:
        print(f"{result.request} → {result.status} {result.location}")
    else:
        print(f"{result.request} → NO MATCH")

# Generate coverage report
report = generate_coverage_report(cfg, results)
print(f"Coverage: {report.coverage_percent:.1f}%")
print(f"Dead rules: {report.dead_rules}")

# Test single request
req = Request(host="example.com", path="/blog")
result = match_request(cfg, req)
print(f"Matched rule: {result.rule_id}")
print(f"Location: {result.location}")
```

## Integration with CI

Add simulator to your test pipeline to catch config issues:

```yaml
# .github/workflows/ci.yaml
- name: Test redirect configs
  run: |
    uv run lacuna-sim --yaml examples/domainlist.yaml --cases examples/cases.txt
```

The command exits with code 1 if:
- Any dead rules are found
- Any test requests don't match a rule

## Match Logic Details

### Exact Match

**Behavior**: Path must match `rule.from` exactly.

```yaml
- id: home
  match: exact
  from: /
  to: https://www.example.org/
```

| Request | Matches? | Location |
|---------|----------|----------|
| `/` | ✓ | `https://www.example.org/` |
| `/about` | ✗ | - |
| `/?ref=home` | ✓ | `https://www.example.org/?ref=home` (if keep_query=true) |

### Prefix Match

**Behavior**: Path must start with `rule.from`. Remainder is appended to `rule.to`.

```yaml
- id: blog
  match: prefix
  from: /blog
  to: https://blog.example.org
```

| Request | Matches? | Remainder | Location |
|---------|----------|-----------|----------|
| `/blog` | ✓ | `` | `https://blog.example.org` |
| `/blog/` | ✓ | `/` | `https://blog.example.org/` |
| `/blog/post-1` | ✓ | `/post-1` | `https://blog.example.org/post-1` |
| `/docs` | ✗ | - | - |

**Path remainder calculation**:
1. Strip `rule.from` from request path: `remainder = path[len(rule.from):]`
2. Strip trailing `/` from `rule.to`: `base = rule.to.rstrip('/')`
3. Strip leading `/` from remainder: `remainder = remainder.lstrip('/')`
4. Join: `location = f"{base}/{remainder}"` (if remainder non-empty)

### Query String Handling

**`keep_query=true`** (default):
- If request has query string: append `?{query}` to location
- If no query string: location without query

**`keep_query=false`**:
- Query string is always dropped

```yaml
- id: api
  match: prefix
  from: /api
  to: https://api.example.org
  keep_query: true
```

| Request | Location |
|---------|----------|
| `/api/users` | `https://api.example.org/users` |
| `/api/users?id=123` | `https://api.example.org/users?id=123` |

### Rule Ordering (Critical!)

Rules are sorted **before** evaluation to ensure correct behavior:

1. **Exact match rules** (longest path first)
2. **Prefix match rules** (longest path first)

**Why?** More specific rules must be checked before general ones.

**Example**:
```yaml
rules:
  - id: blog-post-1
    match: exact
    from: /blog/post-1
    to: https://special.example.org

  - id: blog
    match: prefix
    from: /blog
    to: https://blog.example.org

  - id: root
    match: prefix
    from: /
    to: https://fallback.example.org
```

Request `/blog/post-1`:
1. Check `blog-post-1` (exact) → MATCH ✓
2. Stop (first match wins)

Request `/blog/other`:
1. Check `blog-post-1` (exact) → no match
2. Check `blog` (prefix) → MATCH ✓
3. Stop

Request `/about`:
1. Check `blog-post-1` (exact) → no match
2. Check `blog` (prefix) → no match
3. Check `root` (prefix) → MATCH ✓

## Testing

Run tests:
```bash
cd tools/lacuna_sim
uv run pytest tests/ -v
```

Run with coverage:
```bash
uv run pytest tests/ -v --cov=lacuna_sim --cov-report=term
```

Type check:
```bash
uv run mypy src/lacuna_sim --strict
```

## Comparison with Caddy

The simulator aims to **predict** Caddy's behavior without running it. Key differences:

| Feature | Simulator | Caddy |
|---------|-----------|-------|
| Matching logic | Subset (exact/prefix only) | Full Caddy routing |
| Performance | Fast (pure Python) | Production-ready (Go) |
| Headers | Shows Location only | Full HTTP response |
| TLS/ACME | Not simulated | Full support |
| Purpose | Testing/validation | Production serving |

**Use simulator for**:
- Pre-deployment testing
- Dead rule detection
- Config validation in CI
- Development feedback loop

**Use Caddy for**:
- Production traffic
- TLS termination
- Performance-critical paths
- Full HTTP compliance

## Limitations

- Only simulates **redirect rules** (exact/prefix matches)
- Does not simulate other Caddy features (reverse proxy, file serving, etc.)
- Does not validate DNS or TLS certificates
- Does not test HSTS headers (only validates config)
- Assumes rules are correctly ordered by `sort_rules()`

## Examples

See `examples/` directory for:
- `domainlist.yaml` - Sample configuration
- `cases.txt` - Sample test cases

Run example:
```bash
uv run lacuna-sim --yaml examples/domainlist.yaml --cases examples/cases.txt
```

Expected output:
```
Simulating 17 requests...

[Table with all 17 test cases]

Coverage Report:
✓ 6/6 rules matched (100%)
✓ No dead rules

✓ All test cases passed!
```

## Contributing

- Code must pass `mypy --strict`
- Add tests for new features
- Update this README for API changes
- Follow existing code style

## License

Part of the Lacuna v2 project.
