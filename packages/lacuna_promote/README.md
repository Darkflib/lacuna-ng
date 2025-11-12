# lacuna_promote

**Double-buffer config promotion for Lacuna v2** - Safe config promotion with validation, reload, and automatic rollback.

## Overview

`lacuna_promote` implements the operational layer for safely promoting Caddy configurations in production. It uses a double-buffer strategy with three config files:

- `config.next.json` - Candidate config (written by compiler)
- `config.active.json` - Currently active config (used by Caddy)
- `config.lastgood.json` - Backup for rollback

This ensures zero-downtime deployments with instant rollback capability if anything goes wrong.

## Features

- **Atomic file operations** - All writes use temp + fsync + os.replace
- **Pre-promotion validation** - Caddy validates configs before they go live
- **Optional health probes** - Verify sentinel URLs return expected responses
- **Automatic rollback** - Rolls back to lastgood on any failure
- **Clear logging** - Timestamped logs at each step with severity levels
- **Type-safe** - Full mypy --strict compliance

## Installation

```bash
# Install from workspace
cd /path/to/Lacuna-ng
uv sync

# Or install package directly
uv pip install -e packages/lacuna_promote
```

## Quick Start

### Programmatic API

```python
from pathlib import Path
from lacuna_promote import PromoteOptions, compile_and_promote

# Basic promotion
opts = PromoteOptions(out_dir=Path("./vol/config"))
active_path = compile_and_promote(Path("config.yaml"), opts)
print(f"Promoted to {active_path}")

# With sentinel probes
opts = PromoteOptions(
    out_dir=Path("/srv/lacuna/config"),
    sentinel_urls=["http://example.com/health"],
    probe_timeout=10.0
)
active_path = compile_and_promote(Path("config.yaml"), opts)

# Validate only (no promotion)
opts = PromoteOptions(
    out_dir=Path("./vol/config"),
    validate_only=True
)
next_path = compile_and_promote(Path("config.yaml"), opts)
print(f"Validation complete: {next_path}")
```

### CLI Integration

The promotion system integrates with `lacuna-compiler` CLI:

```bash
# Compile and promote (default behavior once lacuna_promote is integrated)
lacuna-compiler examples/domainlist.yaml --out-dir /srv/lacuna/config --promote

# Validate only (no promotion)
lacuna-compiler examples/domainlist.yaml --validate-only

# Custom output directory
lacuna-compiler config.yaml --out-dir ./vol/config --promote
```

## Double-Buffer Algorithm

The promotion system follows this algorithm:

### Step 1: Write Candidate

The compiler writes `config.next.json` using atomic operations:

```
tmp file → fsync → os.replace(config.next.json)
```

### Step 2: Validate Candidate

```bash
caddy validate --config config.next.json
```

If validation fails → abort, exit non-zero.

### Step 3: Optional Health Probes

If sentinel URLs are configured:

```python
response = requests.get(sentinel_url, timeout=5.0, allow_redirects=False)
assert 300 <= response.status_code < 400
```

If probes fail → abort, exit non-zero.

### Step 4: Backup Current Active

If `config.active.json` exists:

```
config.active.json → (atomic copy) → config.lastgood.json
```

If no active config (first deployment) → skip backup.

### Step 5: Reload Caddy

```bash
caddy reload --config config.next.json
```

If reload fails → **ROLLBACK** (see below).

### Step 6: Promote to Active

On successful reload:

```
config.next.json → (atomic copy) → config.active.json
```

Exit 0 (success).

## Rollback Procedure

### Automatic Rollback (on failure)

If `caddy reload` fails, the system automatically:

1. Logs the reload failure with stderr from Caddy
2. Checks if `config.lastgood.json` exists
3. Runs `caddy reload --config config.lastgood.json`
4. If rollback succeeds → exit non-zero (promotion failed but rollback OK)
5. If rollback fails → exit non-zero + log CRITICAL error

### Manual Rollback

If you need to manually rollback to the last good config:

```bash
# Method 1: Using Python API
python3 << 'EOF'
from pathlib import Path
from lacuna_promote import rollback

rollback(Path("/srv/lacuna/config"))
EOF

# Method 2: Manual Caddy commands
cd /srv/lacuna/config
caddy reload --config config.lastgood.json

# Then promote lastgood back to active
cp config.lastgood.json config.active.json
```

### Inspecting Current State

```bash
# View config files and timestamps
ls -lh /srv/lacuna/config/
# Shows: config.next.json, config.active.json, config.lastgood.json

# Check what's currently loaded in Caddy
curl http://localhost:2019/config/ | jq '._meta'

# Validate a config manually
caddy validate --config /srv/lacuna/config/config.next.json
```

## File Layout

In your output directory (e.g., `/srv/lacuna/config/`):

```
config/
├── config.next.json      # Candidate (written by compiler, validated before use)
├── config.active.json    # Currently active (what Caddy is serving)
└── config.lastgood.json  # Backup (for rollback)
```

**Important**: All three files should be preserved. Do not delete them manually.

## Error Handling

The package defines custom exceptions for clarity:

```python
from lacuna_promote import (
    ValidationError,  # Caddy validation failed
    ProbeError,       # Sentinel probe failed
    ReloadError,      # Caddy reload failed (rollback succeeded)
    RollbackError,    # Rollback failed (CRITICAL)
)

try:
    compile_and_promote(yaml_path, opts)
except ValidationError as e:
    print(f"Config is invalid: {e}")
except ProbeError as e:
    print(f"Health probes failed: {e}")
except ReloadError as e:
    print(f"Reload failed, rolled back: {e}")
except RollbackError as e:
    print(f"CRITICAL: Rollback failed! Manual intervention required: {e}")
```

## Logging

All operations are logged with timestamps:

```
2025-11-12 14:30:00 [INFO] ========================================
2025-11-12 14:30:00 [INFO] Starting config promotion
2025-11-12 14:30:00 [INFO] YAML config: /srv/lacuna/config.yaml
2025-11-12 14:30:00 [INFO] Output dir: /srv/lacuna/config
2025-11-12 14:30:00 [INFO] ========================================
2025-11-12 14:30:01 [INFO] Step 1/8: Loading YAML config
2025-11-12 14:30:01 [INFO] ✓ Loaded: 5 hosts, 23 rules
2025-11-12 14:30:01 [INFO] Step 2/8: Compiling to Caddy JSON
2025-11-12 14:30:01 [INFO] ✓ Compiled and written to: config.next.json
2025-11-12 14:30:01 [INFO] Step 3/8: Validating with Caddy
2025-11-12 14:30:02 [INFO] ✓ Caddy validation passed
2025-11-12 14:30:02 [INFO] Step 4/8: No sentinel URLs configured (skipping)
2025-11-12 14:30:02 [INFO] Step 5/8: Backing up active config
2025-11-12 14:30:02 [INFO] ✓ Backup created: config.lastgood.json
2025-11-12 14:30:02 [INFO] Step 6/8: Reloading Caddy with new config
2025-11-12 14:30:03 [INFO] ✓ Caddy reload succeeded
2025-11-12 14:30:03 [INFO] Step 7/8: Promoting next → active
2025-11-12 14:30:03 [INFO] ✓ Promoted to: config.active.json
2025-11-12 14:30:03 [INFO] Step 8/8: Complete
2025-11-12 14:30:03 [INFO] ========================================
2025-11-12 14:30:03 [INFO] ✓ Config promotion successful in 3.24s
2025-11-12 14:30:03 [INFO] ✓ Active config: config.active.json
2025-11-12 14:30:03 [INFO] ========================================
```

### Rollback Logging

```
2025-11-12 14:35:10 [ERROR] ✗ Caddy reload failed: config.next.json
2025-11-12 14:35:10 [ERROR] Reload stderr: invalid JSON syntax at line 42
2025-11-12 14:35:10 [WARNING] !!! ROLLBACK: Restoring lastgood config
2025-11-12 14:35:11 [INFO] ✓ Rollback succeeded: restored config.lastgood.json
2025-11-12 14:35:11 [ERROR] ========================================
2025-11-12 14:35:11 [ERROR] ✗ Config promotion failed after 1.23s
2025-11-12 14:35:11 [ERROR] ✗ Error: Caddy reload failed, rolled back to lastgood
2025-11-12 14:35:11 [ERROR] ========================================
```

## Testing

### Run Tests

```bash
# From package directory
cd packages/lacuna_promote
pytest tests/ -v

# Run specific test modules
pytest tests/test_promoter.py -v
pytest tests/test_rollback.py -v

# Run with coverage
pytest tests/ --cov=lacuna_promote --cov-report=term
```

### Test Structure

- `tests/test_promoter.py` - Happy path tests (validation, backup, promotion)
- `tests/test_rollback.py` - Chaos tests (failures, rollback scenarios)

All tests use mocked subprocess calls to `caddy`, so Caddy doesn't need to be installed.

## Failure Scenarios

### 1. Validation Failure

**Scenario**: Config has invalid JSON syntax

**Result**:
- Validation fails
- No backup created
- Active config unchanged
- Exit non-zero
- Clear error logged

**Recovery**: Fix YAML and recompile

### 2. Reload Failure (with lastgood)

**Scenario**: Caddy can't reload new config

**Result**:
- Reload fails
- Automatic rollback triggered
- Lastgood restored
- Exit non-zero
- Rollback logged

**Recovery**: Fix YAML and recompile

### 3. Reload Failure (no lastgood)

**Scenario**: First deployment, Caddy can't reload

**Result**:
- Reload fails
- No lastgood to rollback to
- Exit non-zero
- Clear error logged

**Recovery**: Fix YAML and recompile

### 4. Rollback Failure (CRITICAL)

**Scenario**: Rollback itself fails

**Result**:
- Rollback fails
- CRITICAL error logged
- Exit non-zero
- Manual intervention required

**Recovery**:
```bash
# Manually reload with lastgood
caddy reload --config /srv/lacuna/config/config.lastgood.json

# Or restart Caddy with known-good config
systemctl restart caddy
```

## API Reference

### PromoteOptions

Configuration for promotion behavior:

```python
@dataclass(frozen=True)
class PromoteOptions:
    out_dir: Path                           # Required: output directory
    caddy_bin: str = "caddy"               # Path to caddy binary
    validate_only: bool = False             # Stop after validation
    sentinel_urls: Optional[List[str]] = None  # URLs to probe
    probe_timeout: float = 5.0              # Probe timeout (seconds)
```

### compile_and_promote()

Main entry point for promotion:

```python
def compile_and_promote(yaml_path: Path, opts: PromoteOptions) -> Path:
    """
    Compile YAML and promote with double-buffer.

    Returns: Path to active config on success
    Raises: ValidationError, ProbeError, ReloadError, RollbackError
    """
```

### validate_config()

Validate config with Caddy:

```python
def validate_config(config_path: Path, caddy_bin: str = "caddy") -> bool:
    """
    Validate config with Caddy.

    Returns: True if valid, False otherwise
    """
```

### rollback()

Manual rollback to lastgood:

```python
def rollback(out_dir: Path, caddy_bin: str = "caddy") -> bool:
    """
    Rollback to lastgood config.

    Returns: True if rollback succeeds
    Raises: RollbackError if lastgood missing or reload fails
    """
```

## Security Considerations

- All file writes are atomic (temp + fsync + os.replace)
- No partial writes can corrupt config files
- Rollback ensures service continuity
- Clear logging for audit trails
- Exit codes indicate success/failure clearly

## Integration with lacuna-compiler

Once integrated, the compiler CLI will support:

```bash
# Default: compile and promote
lacuna-compiler config.yaml

# Validate only (no promotion)
lacuna-compiler config.yaml --validate-only

# Explicit promotion (when implemented)
lacuna-compiler config.yaml --promote
```

See `packages/lacuna_compiler/src/lacuna_compiler/cli.py` for integration details.

## Troubleshooting

### "Caddy binary not found"

**Cause**: `caddy` not in PATH or wrong `caddy_bin`

**Solution**:
```python
opts = PromoteOptions(
    out_dir=Path("./vol/config"),
    caddy_bin="/usr/local/bin/caddy"  # Explicit path
)
```

### "Cannot rollback: config.lastgood.json does not exist"

**Cause**: First deployment failed, no previous config

**Solution**: Fix the config and redeploy. No rollback possible on first deployment.

### "Rollback failed - MANUAL INTERVENTION REQUIRED"

**Cause**: Both new config and rollback failed

**Solution**:
1. Check Caddy logs: `journalctl -u caddy`
2. Manually reload: `caddy reload --config /path/to/known-good.json`
3. Investigate root cause
4. Fix config and redeploy

## Contributing

See `AGENTS.md` in the repository root for development guidelines.

## License

Part of the Lacuna v2 project.
