# Integration Tests

End-to-end integration tests for Lacuna v2. These tests verify that all components work correctly together, from YAML validation through compilation, simulation, and promotion.

## Test Structure

```
tests/
├── integration/
│   ├── __init__.py
│   ├── conftest.py              # Shared pytest fixtures
│   ├── test_e2e_workflow.py     # Full workflow tests
│   ├── test_caddy_integration.py # Caddy validation/reload tests
│   └── test_cli_integration.py  # CLI tool integration tests
├── fixtures/
│   ├── test_config.yaml         # Simple test configuration
│   ├── test_cases.txt           # Test cases for simulator
│   └── expected_caddy.json      # Reference Caddy output
└── README.md                    # This file
```

## Running Tests

### Run All Integration Tests

```bash
# From project root
pytest tests/integration/ -v

# With coverage
pytest tests/integration/ --cov=packages --cov=tools

# Parallel execution (faster)
pytest tests/integration/ -n auto
```

### Run Specific Test Files

```bash
# Workflow tests only
pytest tests/integration/test_e2e_workflow.py -v

# Caddy integration tests only
pytest tests/integration/test_caddy_integration.py -v

# CLI integration tests only
pytest tests/integration/test_cli_integration.py -v
```

### Run Tests by Marker

```bash
# Run all integration tests
pytest -m integration -v

# Run only tests that require Caddy
pytest -m requires_caddy -v

# Run all except slow tests
pytest -m "not slow" -v

# Skip tests that require Caddy binary
pytest -m "not requires_caddy" -v
```

## Test Categories

### 1. End-to-End Workflow Tests (`test_e2e_workflow.py`)

Tests the complete pipeline from YAML to deployed configuration:

- **Full compilation workflow**: YAML → Config → Caddy JSON → Simulation
- **Complete test coverage**: All rules matched using cases.txt
- **Promotion workflow**: Double-buffer promotion with mocked Caddy
- **Validate-only mode**: Test compilation without deployment
- **Rollback scenarios**: Test rollback when reload fails
- **Double-buffer pattern**: Multiple promotions in sequence
- **Metadata verification**: Check _meta block in compiled JSON

### 2. Caddy Integration Tests (`test_caddy_integration.py`)

Tests Caddy validation and reload operations:

- **Validation tests**: Good and bad configs (requires Caddy binary)
- **Mocked validation**: Test validation logic without Caddy
- **Reload tests**: Success and failure scenarios
- **Rollback tests**: With and without lastgood config
- **Atomic writes**: Verify write_candidate atomicity
- **Binary not found**: Handle missing Caddy binary gracefully

### 3. CLI Integration Tests (`test_cli_integration.py`)

Tests all command-line tools:

- **Schema checker**: `python -m lacuna_schema.check`
- **Compiler**: `lacuna-compiler` with various options
- **Simulator**: `lacuna-sim` with YAML/JSON input
- **Coverage reports**: Simulator coverage generation
- **Help messages**: All tools have working --help
- **Pipeline integration**: Tools work together end-to-end

## Pytest Fixtures

Common fixtures defined in `conftest.py`:

### Path Fixtures

- `test_config_path`: Path to examples/domainlist.yaml
- `minimal_config_path`: Path to examples/minimal.yaml
- `test_cases_path`: Path to examples/cases.txt
- `fixture_config_path`: Path to tests/fixtures/test_config.yaml
- `temp_output_dir`: Temporary directory for output files

### Compiled Config Fixtures

- `compiled_config`: Pre-compiled config.next.json in temp directory

### Mock Fixtures

- `mock_caddy_success`: Mock all Caddy commands to succeed
- `mock_caddy_failure`: Mock all Caddy commands to fail
- `mock_caddy_validate_success_reload_fail`: Mixed success/failure

### Detection Fixtures

- `caddy_available`: Boolean indicating if Caddy binary exists

## Test Markers

Pytest markers for categorizing tests:

- `@pytest.mark.integration`: All integration tests
- `@pytest.mark.requires_caddy`: Tests requiring Caddy binary
- `@pytest.mark.slow`: Slow-running tests (can be skipped)

## Mock Strategy

### When to Mock Caddy

Most tests mock Caddy commands to avoid requiring Caddy installation:

```python
def test_promotion_mocked(temp_output_dir, mock_caddy_success):
    """Test with mocked Caddy - no binary required."""
    opts = PromoteOptions(out_dir=temp_output_dir)
    active_path = compile_and_promote(yaml_path, opts)
    assert active_path.exists()
```

### When to Use Real Caddy

Tests marked with `@pytest.mark.requires_caddy` use the actual Caddy binary:

```python
@pytest.mark.requires_caddy
def test_caddy_validate_real(compiled_config, caddy_available):
    """Test with real Caddy - validates actual JSON."""
    if not caddy_available:
        pytest.skip("Caddy not installed")

    is_valid = validate_config(compiled_config, "caddy")
    assert is_valid is True
```

### Custom Mock Behaviors

For complex scenarios, create custom mocks:

```python
def test_rollback_scenario(temp_output_dir, monkeypatch):
    """Test rollback with custom mock."""
    call_count = 0

    def mock_run(cmd, **kwargs):
        nonlocal call_count
        if "validate" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if "reload" in cmd:
            call_count += 1
            if call_count == 1:
                return subprocess.CompletedProcess(cmd, 1, "", "Failed")
            return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", mock_run)
    # Test logic here...
```

## Test Fixtures

### test_config.yaml

Simple configuration with basic rules:

- 1 host (test.example.com)
- 3 rules: exact match (home), prefix with query (api), prefix without query (static)
- Tests all core features with minimal complexity

### test_cases.txt

Test cases covering all rules in test_config.yaml:

- Format: `HOST PATH [QUERY]`
- Should achieve 100% rule coverage

### expected_caddy.json

Reference Caddy JSON output (simplified):

- Shows expected structure
- Useful for understanding compilation output
- Note: Actual output includes _meta block with timestamps

## CI Integration

These integration tests run in CI pipeline:

```yaml
# .github/workflows/ci.yaml
- name: Run integration tests
  run: |
    pytest tests/integration/ -v -m "not requires_caddy"
```

Tests requiring Caddy binary are skipped in CI unless Caddy is installed.

## Writing New Tests

### Adding a New Integration Test

1. Choose the appropriate test file:
   - Workflow tests → `test_e2e_workflow.py`
   - Caddy operations → `test_caddy_integration.py`
   - CLI tools → `test_cli_integration.py`

2. Use appropriate fixtures from `conftest.py`

3. Add pytest markers:
   ```python
   @pytest.mark.integration
   def test_my_feature(temp_output_dir, test_config_path):
       """Test description."""
       # Test implementation
   ```

4. Mock Caddy unless testing real validation:
   ```python
   @pytest.mark.integration
   def test_with_mock(temp_output_dir, mock_caddy_success):
       """Uses mocked Caddy."""
       # Test implementation
   ```

### Adding a New Fixture

Add to `conftest.py`:

```python
@pytest.fixture
def my_fixture(temp_output_dir):
    """Description of fixture."""
    # Setup
    value = create_test_data()
    yield value
    # Teardown (optional)
```

## Debugging Tests

### Run with verbose output

```bash
pytest tests/integration/test_e2e_workflow.py::test_name -v -s
```

### Run with pdb on failure

```bash
pytest tests/integration/ --pdb
```

### See print statements

```bash
pytest tests/integration/ -v -s
```

### Run single test

```bash
pytest tests/integration/test_e2e_workflow.py::test_full_compilation_workflow -v
```

## Coverage Reports

Generate coverage reports:

```bash
# Terminal report
pytest tests/integration/ --cov=packages --cov=tools --cov-report=term

# HTML report
pytest tests/integration/ --cov=packages --cov=tools --cov-report=html

# Open HTML report
open htmlcov/index.html
```

## Common Issues

### Issue: "Caddy not found"

**Solution**: Either install Caddy or skip tests requiring it:
```bash
pytest -m "not requires_caddy"
```

### Issue: "FileNotFoundError: config.yaml"

**Solution**: Run pytest from project root:
```bash
cd /home/user/Lacuna-ng
pytest tests/integration/ -v
```

### Issue: "Import error: No module named 'lacuna_schema'"

**Solution**: Install packages in development mode:
```bash
uv sync --all-extras --dev
```

### Issue: Tests fail with "No such file or directory"

**Solution**: Ensure you're using absolute paths in tests or run from project root.

## Test Maintenance

### When to Update Tests

- **Schema changes**: Update test fixtures if YAML schema changes
- **Compiler changes**: Update expected outputs if compilation logic changes
- **CLI changes**: Update CLI tests if command-line interfaces change
- **New features**: Add new tests for new functionality

### Keeping Tests Fast

- Use mocks instead of real Caddy when possible
- Use `temp_output_dir` fixture for temporary files
- Mark slow tests with `@pytest.mark.slow`
- Run tests in parallel: `pytest -n auto`

## Success Criteria

Integration tests verify:

- ✅ YAML validation catches invalid configs
- ✅ Compilation produces valid Caddy JSON
- ✅ Simulator correctly matches requests to rules
- ✅ Promotion workflow works with double-buffering
- ✅ Rollback works when reload fails
- ✅ All CLI tools work together
- ✅ Atomic writes prevent partial configs
- ✅ Metadata is correctly embedded
- ✅ 100% rule coverage with test cases
- ✅ All tests pass without Caddy installed (using mocks)

## Resources

- [AGENTS.md](../AGENTS.md): Full project specification
- [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md): Project structure guide
- [pytest documentation](https://docs.pytest.org/)
- [Caddy documentation](https://caddyserver.com/docs/)
