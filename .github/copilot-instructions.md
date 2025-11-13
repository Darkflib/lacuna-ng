# GitHub Copilot Instructions for Lacuna v2

This file provides context and guidelines for GitHub Copilot when working in the Lacuna v2 repository.

## Project Overview

Lacuna v2 is a **KISS (Keep It Simple, Stupid) redirection service** powered by Caddy at the edge with static rules compiled from YAML to Caddy JSON using a minimal Python toolchain. No database. No runtime complexity. Just fast, deterministic redirects.

**Key principles:**
- Simple, static, and safe design (no runtime templating)
- Deterministic builds with reproducible output
- Fast failure with early validation
- Observability by default with structured logging

## Tech Stack & Conventions

### Core Technologies
- **Python**: 3.12+ (3.13 recommended)
- **Dependency Manager**: `uv` (workspace mode)
- **Data Modeling**: Pydantic v2
- **CLI Framework**: Typer or stdlib argparse
- **Testing**: pytest with ≥85% coverage goal
- **Type Checking**: mypy --strict (100% compliance required)
- **Formatting**: ruff and black
- **Linting**: ruff
- **Edge Server**: Caddy v2.8.x with JSON config
- **Containers**: Docker/Podman with multi-arch images

### Repository Structure
```
packages/
  ├── lacuna_schema/     # YAML validation with Pydantic models
  ├── lacuna_compiler/   # YAML → Caddy JSON compiler
  └── lacuna_promote/    # Double-buffer promotion with rollback
tools/
  └── lacuna_sim/        # Dry-run simulator for testing
infra/                   # Docker, Compose, Kubernetes manifests
examples/                # Sample configurations
tests/integration/       # End-to-end integration tests
```

This is a **uv workspace** with multiple independent packages. Each package has its own `pyproject.toml` and can be used standalone.

## Code Quality Standards

### Type Safety (Critical)
- **ALL code must pass `mypy --strict`** with zero errors
- Use type annotations for all functions, methods, and variables
- Use `from __future__ import annotations` for forward references
- No `type: ignore` comments without documented justification
- Import types from `typing` module as needed

Example:
```python
from __future__ import annotations
from pathlib import Path
from typing import Optional

def load_config(path: Path, validate: bool = True) -> Config:
    """Load and validate configuration from YAML file."""
    ...
```

### Code Formatting
- **Line length**: 100 characters (black) or 120 (ruff) - follow existing patterns
- Run `make fmt` before committing (runs ruff format + black)
- Follow PEP 8 style guide
- No unused imports or variables

### Code Organization
- Keep functions focused and small
- Use descriptive variable names
- Prefer explicit over implicit
- Add docstrings for all public APIs (Google style)
- Use dataclasses or Pydantic models for structured data

## Security Requirements (Critical)

### Input Validation
- **Scheme allowlist**: Only `http` and `https` are allowed in redirect targets
- **No templating**: Reject any `{`, `}`, or `$` characters in redirect URLs
- **Path validation**: All paths must start with `/`
- **No open redirects**: All targets must be explicitly defined in config

### Validation Checks
When working with redirect configurations:
```python
# Always validate schemes
ALLOWED_SCHEMES = {"http", "https"}
if parsed_url.scheme not in ALLOWED_SCHEMES:
    raise ValidationError(f"Invalid scheme: {parsed_url.scheme}")

# Always reject templating characters
FORBIDDEN_CHARS = {"{", "}", "$"}
if any(char in url for char in FORBIDDEN_CHARS):
    raise ValidationError("Templating characters not allowed")
```

### File Operations
- Use atomic file writes (temp file + fsync + os.replace)
- Never overwrite configs without validation
- Always maintain rollback capability (lastgood.json)

## Testing Requirements

### Coverage & Test Types
- **Minimum coverage**: 85% for all packages
- **Unit tests**: Test individual functions in isolation
- **Integration tests**: Test workflows across components
- **Property tests**: Use Hypothesis for complex logic
- **Golden file tests**: For deterministic output (compiler)

### Test Organization
```python
# Place tests in tests/ subdirectory of each package
packages/lacuna_schema/tests/test_models.py
packages/lacuna_compiler/tests/test_compiler.py
packages/lacuna_promote/tests/test_promote.py
tools/lacuna_sim/tests/test_simulator.py

# Integration tests in root
tests/integration/test_e2e.py
```

### Writing Tests
```python
def test_validation_rejects_bad_scheme():
    """Schema validation should reject non-http(s) schemes."""
    config = {
        "version": 1,
        "hosts": [{
            "host": "example.com",
            "rules": [{
                "id": "bad",
                "match": "exact",
                "from": "/",
                "to": "javascript:alert(1)",
                "status": 308
            }]
        }]
    }
    with pytest.raises(ValidationError, match="Invalid scheme"):
        Config(**config)
```

### Running Tests
```bash
make test              # Run all tests with coverage
pytest -v              # Verbose output
pytest -x              # Stop on first failure
pytest path/to/test.py # Run specific test file
```

## Common Tasks & Commands

### Development Workflow
```bash
# Format code
make fmt

# Type check
make lint

# Run tests
make test

# Validate YAML config
python -m lacuna_schema.check examples/domainlist.yaml

# Compile to Caddy JSON
lacuna-compiler examples/domainlist.yaml --validate-only

# Test with simulator
lacuna-sim --yaml examples/domainlist.yaml

# Run Caddy locally
make compile && make run
```

### Pre-commit Hooks
Pre-commit hooks run automatically on commit:
- ruff (linting and formatting)
- black (code formatting)
- mypy (type checking)
- yamllint (YAML validation)
- Standard checks (trailing whitespace, EOF, merge conflicts)

## Common Patterns

### Pydantic Models
```python
from pydantic import BaseModel, Field, field_validator

class Rule(BaseModel):
    """Redirect rule definition."""
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    match: Literal["exact", "prefix"]
    from_: str = Field(alias="from", pattern=r"^/.*")
    to: str
    status: int = Field(ge=301, le=308)
    keep_query: bool = True

    @field_validator("to")
    @classmethod
    def validate_scheme(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"Invalid scheme: {parsed.scheme}")
        if any(c in v for c in ["{", "}", "$"]):
            raise ValueError("Templating not allowed")
        return v
```

### Error Handling
```python
# Use specific exception types
from pydantic import ValidationError

try:
    config = load_config(path)
except ValidationError as e:
    logger.error(f"Config validation failed: {e}")
    sys.exit(1)
except FileNotFoundError:
    logger.error(f"Config file not found: {path}")
    sys.exit(1)
```

### Logging
```python
import logging

logger = logging.getLogger(__name__)

# Use structured logging
logger.info(
    "Config loaded successfully",
    extra={
        "hosts": len(config.hosts),
        "total_rules": sum(len(h.rules) for h in config.hosts),
        "file": str(path)
    }
)
```

## Package-Specific Guidelines

### lacuna_schema
- Focus: YAML validation and Pydantic models
- Key: Security validators (schemes, templating, paths)
- Testing: Property tests with Hypothesis

### lacuna_compiler
- Focus: YAML → Caddy JSON compilation
- Key: Deterministic output, metadata tracking
- Testing: Golden file tests for reproducibility

### lacuna_promote
- Focus: Double-buffer promotion with rollback
- Key: Atomic file operations, validation, reload
- Testing: Chaos tests, failure scenarios

### lacuna_sim
- Focus: Offline simulator and coverage analysis
- Key: Request matching without Caddy
- Testing: Rule coverage, dead rule detection

## Documentation Standards

### Docstrings (Google Style)
```python
def compile_to_caddy(cfg: Config) -> dict[str, Any]:
    """
    Compile validated config to Caddy JSON format.

    Args:
        cfg: Validated configuration from lacuna_schema

    Returns:
        Dictionary representing Caddy JSON config with metadata block:
        - _meta: build timestamp, git hash, content checksum
        - apps: Caddy HTTP server configuration

    Raises:
        ValueError: If configuration cannot be compiled
        
    Example:
        >>> config = load_config(Path("config.yaml"))
        >>> caddy_json = compile_to_caddy(config)
        >>> caddy_json["_meta"]["built_at"]
        '2025-11-13T12:00:00Z'
    """
    ...
```

### README Updates
When adding features or making changes:
- Update package README.md for the affected package
- Update root README.md for user-facing changes
- Add examples showing how to use new features
- Update CHANGELOG.md for significant changes

## References

For detailed specifications and architecture:
- **[AGENTS.md](../AGENTS.md)**: Complete technical specs, data contracts, agent prompts
- **[CONTRIBUTING.md](../CONTRIBUTING.md)**: Contribution guidelines and workflow
- **[README.md](../README.md)**: User-facing documentation
- **[PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md)**: Architecture and dependencies
- **[SECURITY.md](../SECURITY.md)**: Security policy and reporting

## Important Notes

### What to Avoid
- ❌ Runtime templating or eval()
- ❌ Schemes other than http/https
- ❌ Breaking changes without documentation
- ❌ Skipping type hints
- ❌ Committing without running tests
- ❌ Ignoring mypy errors
- ❌ Hard-coded file paths (use Path objects)

### What to Prefer
- ✅ Explicit over implicit
- ✅ Type safety with mypy --strict
- ✅ Comprehensive tests (≥85% coverage)
- ✅ Atomic operations (especially file I/O)
- ✅ Clear error messages
- ✅ Structured logging
- ✅ Documentation for public APIs

## Quick Reference

```bash
# Quality checks (run before committing)
make fmt                # Format code
make lint               # Type check with mypy --strict
make test               # Run tests with coverage

# Development
make compile            # Compile example config
make run                # Start Caddy locally
make clean              # Clean build artifacts

# Testing specific packages
pytest packages/lacuna_schema/tests/ -v
pytest packages/lacuna_compiler/tests/ -v
pytest packages/lacuna_promote/tests/ -v
pytest tools/lacuna_sim/tests/ -v

# Integration tests
pytest tests/integration/ -v
```

## Version Requirements

- Python: ≥3.12 (3.13 recommended)
- Caddy: 2.8.x
- mypy: ≥1.8.0
- pytest: ≥8.0.0
- ruff: ≥0.2.0
- black: ≥24.0.0

---

**Remember**: This is a production-ready system. All code must meet strict quality, type safety, and testing standards. When in doubt, refer to [AGENTS.md](../AGENTS.md) for detailed specifications.
