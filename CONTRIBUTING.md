# Contributing to Lacuna v2

Thank you for your interest in contributing to Lacuna v2! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Code Standards](#code-standards)
- [Testing Guidelines](#testing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Documentation Guidelines](#documentation-guidelines)
- [Architecture Overview](#architecture-overview)

## Code of Conduct

Be respectful, constructive, and collaborative. We're all here to build something great together.

## Getting Started

### Prerequisites

- **Python 3.12+** (3.13 recommended)
- **uv** - Fast Python package manager ([Install uv](https://docs.astral.sh/uv/))
- **Docker or Podman** - For running Caddy locally
- **Git** - Version control
- **Text editor or IDE** - VS Code, PyCharm, or similar

### First-Time Contributors

1. **Read the documentation**:
   - [README.md](README.md) - Project overview
   - [AGENTS.md](AGENTS.md) - Technical specifications
   - [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - Architecture

2. **Look for good first issues**:
   - Check GitHub issues tagged with `good-first-issue`
   - Start small to familiarize yourself with the codebase

3. **Ask questions**:
   - Open a discussion on GitHub
   - Comment on issues you're interested in

## Development Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/Lacuna-ng.git
cd Lacuna-ng

# Add upstream remote
git remote add upstream https://github.com/ORIGINAL_OWNER/Lacuna-ng.git
```

### 2. Install Dependencies

```bash
# Option 1: Using Make (recommended)
make install

# Option 2: Manual installation
uv sync --all-extras --dev
uv run pre-commit install
```

**What this does:**
- Installs all Python packages in the workspace
- Sets up development dependencies (pytest, mypy, ruff, etc.)
- Configures pre-commit hooks for automatic code quality checks

### 3. Verify Setup

```bash
# Run all tests to ensure everything works
make test

# Expected output: All tests pass
# ===== 141 passed in 3.45s =====

# Verify type checking works
make lint

# Expected output: Success: no issues found
```

### 4. Create a Branch

```bash
# Create a new branch for your feature or fix
git checkout -b feature/my-awesome-feature

# Or for bug fixes
git checkout -b fix/issue-123
```

## Development Workflow

### Standard Development Loop

```bash
# 1. Make your changes
vim packages/lacuna_schema/src/lacuna_schema/models.py

# 2. Run formatters
make fmt
# Runs: ruff format

# 3. Run type checks
make lint
# Runs: mypy --strict

# 4. Run tests
make test
# Runs: pytest with coverage

# 5. Test specific package
pytest packages/lacuna_schema/tests/ -v

# 6. Commit changes (pre-commit hooks run automatically)
git add .
git commit -m "feat: add new validation rule"

# 7. Push to your fork
git push origin feature/my-awesome-feature

# 8. Create Pull Request on GitHub
```

### Common Tasks

#### Run a Specific Package's Tests

```bash
# Schema tests
pytest packages/lacuna_schema/tests/ -v

# Compiler tests
pytest packages/lacuna_compiler/tests/ -v

# Promotion tests
pytest packages/lacuna_promote/tests/ -v

# Simulator tests
pytest tools/lacuna_sim/tests/ -v
```

#### Run Tests with Coverage

```bash
# All packages
pytest --cov --cov-report=html

# Specific package
pytest packages/lacuna_schema/tests/ --cov=lacuna_schema --cov-report=term
```

#### Test Configuration Changes

```bash
# 1. Validate YAML
python -m lacuna_schema.check examples/domainlist.yaml

# 2. Compile to JSON
lacuna-compiler examples/domainlist.yaml --validate-only

# 3. Test with simulator
lacuna-sim --yaml examples/domainlist.yaml --cases examples/cases.txt
```

#### Run Caddy Locally

```bash
# Compile configuration
make compile

# Start Caddy with Docker Compose
make run

# In another terminal, test
curl -v http://localhost -H "Host: example.com"
```

## Code Standards

All code must meet these standards before being merged:

### Type Safety

- **All code must pass `mypy --strict`** with no errors
- All functions must have type annotations
- Use `from __future__ import annotations` for forward references
- No `type: ignore` comments without justification

**Example:**

```python
from __future__ import annotations
from pathlib import Path
from typing import Optional

def load_config(path: Path, validate: bool = True) -> Config:
    """Load and validate configuration from YAML file."""
    ...
```

### Code Formatting

- **Use `ruff`** for consistent formatting
- Line length: 100 characters
- Run `make fmt` before committing

### Code Quality

- **Pass `ruff check`** with no warnings
- No unused imports
- No undefined variables
- Follow PEP 8 style guide

### Testing Requirements

- **Test coverage ≥85%** for new code
- Unit tests for all new functions
- Integration tests for workflows
- Property tests (Hypothesis) for complex logic

### Documentation Requirements

- **Docstrings for all public APIs** using Google style
- Update README.md for user-facing changes
- Add inline comments for complex logic
- Update CHANGELOG.md for significant changes

**Example docstring:**

```python
def compile_to_caddy(cfg: Config) -> dict[str, Any]:
    """
    Compile validated config to Caddy JSON format.

    Args:
        cfg: Validated configuration from lacuna_schema

    Returns:
        Dictionary representing Caddy JSON config with metadata

    Raises:
        ValueError: If configuration is invalid
    """
    ...
```

## Testing Guidelines

### Writing Good Tests

#### Unit Tests

Test individual functions in isolation:

```python
def test_sort_rules_exact_first():
    """Exact match rules should be sorted before prefix rules."""
    host = Host(
        host="example.com",
        rules=[
            Rule(id="prefix1", match="prefix", from_="/api", ...),
            Rule(id="exact1", match="exact", from_="/", ...),
        ]
    )
    sorted_host = sort_rules(host)
    assert sorted_host.rules[0].match == "exact"
    assert sorted_host.rules[1].match == "prefix"
```

#### Integration Tests

Test workflows across multiple components:

```python
def test_compile_and_promote_workflow(tmp_path):
    """Test complete workflow from YAML to active config."""
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(sample_yaml)

    opts = PromoteOptions(out_dir=tmp_path, validate_only=True)
    result = compile_and_promote(yaml_path, opts)

    assert result.exists()
    assert json.loads(result.read_text())["apps"]["http"]
```

#### Property Tests

Use Hypothesis for testing properties:

```python
from hypothesis import given, strategies as st

@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",))))
def test_path_validation(path: str):
    """Any path should either validate or reject consistently."""
    try:
        validated = validate_path(path)
        assert validated.startswith("/")
    except ValidationError:
        pass  # Expected for invalid paths
```

### Test Organization

- Place tests in `tests/` subdirectory of each package
- Name test files `test_<module>.py`
- Name test functions `test_<behavior>`
- Use fixtures for common setup
- Mock external dependencies (Caddy, file system when appropriate)

### Running Tests

```bash
# Fast test run (no coverage)
pytest -q

# With coverage
pytest --cov --cov-report=term

# Verbose output
pytest -v

# Stop on first failure
pytest -x

# Run specific test
pytest packages/lacuna_schema/tests/test_models.py::test_exact_match
```

## Pull Request Process

### Before Submitting

Ensure your PR meets these requirements:

- [ ] **Code is formatted**: Run `make fmt`
- [ ] **Type checks pass**: Run `make lint`
- [ ] **All tests pass**: Run `make test`
- [ ] **Coverage maintained**: New code has ≥85% coverage
- [ ] **Tests added**: New features have tests
- [ ] **Documentation updated**: READMEs and docstrings updated
- [ ] **No breaking changes**: Or clearly documented
- [ ] **Commit messages clear**: Follow commit message guidelines
- [ ] **Branch is up to date**: Rebased on latest main

### Checklist Template

When creating a PR, include this checklist:

```markdown
## Pull Request Checklist

- [ ] Code formatted (`make fmt`)
- [ ] Type checks pass (`make lint`)
- [ ] Tests pass (`make test`)
- [ ] New tests added for changes
- [ ] Documentation updated
- [ ] CHANGELOG updated (if applicable)
- [ ] No breaking changes (or documented)
```

### PR Description

Include in your PR description:

1. **What**: What changes does this PR make?
2. **Why**: Why are these changes needed?
3. **How**: How do the changes work?
4. **Testing**: How did you test the changes?
5. **Screenshots**: If UI changes, include screenshots

**Example:**

```markdown
## Add support for regex path matching

### What
Adds regex support to path matching in addition to exact and prefix.

### Why
Users need more flexible path matching for complex redirect rules.

### How
- Added `match: regex` option to Rule model
- Implemented regex compilation and caching
- Added validation to reject unsafe patterns

### Testing
- Added 15 unit tests for regex matching
- Added property tests for regex safety
- Tested with real-world regex patterns
```

### Review Process

1. **CI must pass**: All checks must be green
2. **Review required**: At least one maintainer review
3. **Address feedback**: Respond to all review comments
4. **Squash commits**: Clean up commit history if requested
5. **Merge**: Maintainer will merge when approved

## Commit Message Guidelines

Follow Conventional Commits format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

### Examples

```bash
# Good commit messages
feat(schema): add regex validation for rule IDs
fix(compiler): handle empty query strings correctly
docs(readme): update quick start guide
test(promote): add rollback failure tests

# With body
feat(schema): add support for regex path matching

Add a new 'regex' match type to Rule model that allows
regex patterns for path matching. Includes validation to
reject unsafe patterns.

Closes #123
```

### Breaking Changes

Prefix the commit message with `BREAKING CHANGE:` in the footer:

```
feat(schema): change default HSTS setting

BREAKING CHANGE: HSTS is now enabled by default for all hosts.
Users must explicitly set hsts=false to disable it.
```

## Documentation Guidelines

### When to Update Documentation

Update documentation when:
- Adding a new feature
- Changing existing behavior
- Fixing a significant bug
- Adding new CLI options
- Changing configuration format

### What to Update

1. **Package README**: Update the relevant package README.md
2. **Root README**: Update if it affects overall usage
3. **AGENTS.md**: Update for architectural changes
4. **CHANGELOG.md**: Add entry for the change
5. **Docstrings**: Update function/class documentation
6. **Examples**: Update or add examples if needed

### Documentation Style

- Use clear, concise language
- Include code examples
- Show expected output
- Link to related documentation
- Keep examples up to date

## Architecture Overview

For detailed architecture, see [AGENTS.md](AGENTS.md) and [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

### Key Components

1. **lacuna_schema**: YAML validation and models
   - Pydantic v2 models
   - Security validators
   - Rule sorting logic

2. **lacuna_compiler**: YAML → Caddy JSON
   - Deterministic compilation
   - Metadata tracking
   - Header injection

3. **lacuna_promote**: Config promotion
   - Double-buffer logic
   - Validation and rollback
   - Atomic file operations

4. **lacuna_sim**: Offline simulator
   - Request matching logic
   - Coverage reporting
   - Dead rule detection

### Design Principles

- **KISS**: Keep It Simple, Stupid
- **Type safety**: Full mypy --strict compliance
- **Deterministic**: Same input → same output
- **Fail fast**: Validate early, fail clearly
- **Observable**: Log everything, track all operations

## Getting Help

- **Questions**: Open a GitHub Discussion
- **Bugs**: File a GitHub Issue
- **Architecture**: See AGENTS.md
- **Slack/Discord**: (If available, add link here)

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (MIT or Apache 2.0).

## Thank You!

Thank you for contributing to Lacuna v2! Your contributions help make this project better for everyone.
