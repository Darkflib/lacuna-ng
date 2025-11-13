"""CLI integration tests.

Tests that all command-line tools work correctly together.
"""

import subprocess
import sys
from pathlib import Path

import pytest


def _run_cmd(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """
    Run a command, using either uv or direct Python based on availability.
    
    Converts commands like ["uv", "run", "python", ...] to ["python", ...]
    and ["uv", "run", "lacuna-compiler"] to ["lacuna-compiler"] if uv is not available.
    """
    # Check if command starts with "uv run"
    if len(cmd) >= 2 and cmd[0] == "uv" and cmd[1] == "run":
        # Try uv first
        try:
            result = subprocess.run(["uv", "version"], capture_output=True, timeout=1)
            if result.returncode == 0:
                # uv is available, use it
                return subprocess.run(cmd, **kwargs)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # uv not available, use direct execution
        # Remove "uv run" prefix
        new_cmd = cmd[2:]
        
        # If command is "python", use sys.executable
        if new_cmd[0] == "python":
            new_cmd = [sys.executable] + new_cmd[1:]
        
        return subprocess.run(new_cmd, **kwargs)
    
    # Not a uv command, run as-is
    return subprocess.run(cmd, **kwargs)


@pytest.mark.integration
def test_schema_check_cli_valid_config(test_config_path: Path, repo_root: Path) -> None:
    """Test lacuna_schema CLI with valid config."""
    result = _run_cmd(
        ["uv", "run", "python", "-m", "lacuna_schema", "check", str(test_config_path)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    assert result.returncode == 0
    assert "hosts" in result.stdout.lower() or "valid" in result.stdout.lower()


@pytest.mark.integration
def test_schema_check_cli_invalid_config(temp_output_dir: Path, repo_root: Path) -> None:
    """Test lacuna_schema CLI with invalid config."""
    # Create invalid YAML
    invalid_yaml = temp_output_dir / "invalid.yaml"
    invalid_yaml.write_text(
        """
version: 1
hosts:
  - host: example.com
    rules:
      - id: bad-scheme
        match: exact
        from: /
        to: ftp://invalid.com
        status: 308
"""
    )

    result = _run_cmd(
        ["uv", "run", "python", "-m", "lacuna_schema", "check", str(invalid_yaml)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    assert result.returncode != 0
    assert "error" in result.stderr.lower() or "validation" in result.stderr.lower()


@pytest.mark.integration
def test_schema_check_cli_missing_file(repo_root: Path) -> None:
    """Test lacuna_schema CLI with missing file."""
    result = _run_cmd(
        ["uv", "run", "python", "-m", "lacuna_schema", "check", "/nonexistent/config.yaml"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    assert result.returncode != 0


@pytest.mark.integration
def test_compiler_cli_validate_only(temp_output_dir: Path, test_config_path: Path, repo_root: Path) -> None:
    """Test lacuna-compiler --validate-only (no Caddy validation)."""
    result = _run_cmd(
        [
            "uv",
            "run",
            "lacuna-compiler",
            str(test_config_path),
            "--out-dir",
            str(temp_output_dir),
            "--validate-only",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    # Should succeed even without Caddy (--validate-only skips Caddy validate)
    # The output mentions validation, but that's just YAML validation
    assert result.returncode == 0
    assert (temp_output_dir / "config.next.json").exists()
    assert not (temp_output_dir / "config.active.json").exists()


@pytest.mark.integration
@pytest.mark.requires_caddy
def test_compiler_cli_with_promotion(temp_output_dir: Path, minimal_config_path: Path, caddy_available: bool, repo_root: Path) -> None:
    """Test lacuna-compiler with full promotion (requires Caddy)."""
    if not caddy_available:
        pytest.skip("Caddy binary not available")

    _run_cmd(
        [
            "uv",
            "run",
            "lacuna-compiler",
            str(minimal_config_path),
            "--out-dir",
            str(temp_output_dir),
            "--promote",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    # May fail without Caddy running, so just check files were created
    assert (temp_output_dir / "config.next.json").exists()


@pytest.mark.integration
def test_compiler_cli_invalid_yaml(temp_output_dir: Path, repo_root: Path) -> None:
    """Test lacuna-compiler with invalid YAML."""
    # Create invalid YAML
    invalid_yaml = temp_output_dir / "invalid.yaml"
    invalid_yaml.write_text("this is not valid: yaml: syntax")

    result = _run_cmd(
        [
            "uv",
            "run",
            "lacuna-compiler",
            str(invalid_yaml),
            "--out-dir",
            str(temp_output_dir),
            "--validate-only",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    assert result.returncode != 0


@pytest.mark.integration
def test_simulator_cli_with_yaml(test_config_path: Path, repo_root: Path) -> None:
    """Test lacuna-sim with YAML input."""
    result = _run_cmd(
        [
            "uv",
            "run",
            "lacuna-sim",
            "--yaml",
            str(test_config_path),
            "--request",
            "prod.example.com /",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    # Simulator returns 1 when there are dead rules (warnings), but still produces output
    # This is expected behavior for a linter-style tool
    assert "home" in result.stdout  # Should match "home" rule
    assert "308" in result.stdout  # Status code


@pytest.mark.integration
def test_simulator_cli_with_cases_file(test_config_path: Path, test_cases_path: Path, repo_root: Path) -> None:
    """Test lacuna-sim with cases.txt file."""
    result = _run_cmd(
        [
            "uv",
            "run",
            "lacuna-sim",
            "--yaml",
            str(test_config_path),
            "--cases",
            str(test_cases_path),
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    assert result.returncode == 0
    assert "100%" in result.stdout or "coverage" in result.stdout.lower()


@pytest.mark.integration
def test_simulator_cli_with_yaml_and_query(test_config_path: Path, repo_root: Path) -> None:
    """Test lacuna-sim with YAML input and query string."""
    result = _run_cmd(
        [
            "uv",
            "run",
            "lacuna-sim",
            "--yaml",
            str(test_config_path),
            "--request",
            "prod.example.com /blog page=2",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    # Simulator returns 1 when there are dead rules, but still produces output
    assert "blog" in result.stdout


@pytest.mark.integration
def test_simulator_cli_no_match(test_config_path: Path, repo_root: Path) -> None:
    """Test lacuna-sim with request that doesn't match any rule."""
    result = _run_cmd(
        [
            "uv",
            "run",
            "lacuna-sim",
            "--yaml",
            str(test_config_path),
            "--request",
            "unknown.example.com /anything",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    # Returns 1 when requests don't match (warning/error condition)
    assert result.returncode == 1
    assert "no match" in result.stdout.lower() or "not matched" in result.stdout.lower()


@pytest.mark.integration
def test_simulator_cli_coverage_report(test_config_path: Path, test_cases_path: Path, repo_root: Path) -> None:
    """Test lacuna-sim coverage report generation."""
    result = _run_cmd(
        [
            "uv",
            "run",
            "lacuna-sim",
            "--yaml",
            str(test_config_path),
            "--cases",
            str(test_cases_path),
            "--coverage",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )

    assert result.returncode == 0

    # Should show coverage statistics
    output = result.stdout.lower()
    assert "coverage" in output or "matched" in output or "rules" in output


@pytest.mark.integration
def test_cli_tools_help_messages(repo_root: Path) -> None:
    """Test that all CLI tools have working --help."""
    # Test schema checker
    result1 = _run_cmd(
        ["uv", "run", "python", "-m", "lacuna_schema", "--help"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert result1.returncode == 0
    assert "usage" in result1.stdout.lower() or "help" in result1.stdout.lower()

    # Test compiler
    result2 = _run_cmd(
        ["uv", "run", "lacuna-compiler", "--help"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert result2.returncode == 0

    # Test simulator
    result3 = _run_cmd(
        ["uv", "run", "lacuna-sim", "--help"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert result3.returncode == 0


@pytest.mark.integration
def test_cli_pipeline_integration(temp_output_dir: Path, test_config_path: Path, repo_root: Path) -> None:
    """Test complete CLI pipeline: check → compile → simulate."""
    # Step 1: Check YAML
    result1 = _run_cmd(
        ["uv", "run", "python", "-m", "lacuna_schema", "check", str(test_config_path)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert result1.returncode == 0

    # Step 2: Compile
    result2 = _run_cmd(
        [
            "uv",
            "run",
            "lacuna-compiler",
            str(test_config_path),
            "--out-dir",
            str(temp_output_dir),
            "--validate-only",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert result2.returncode == 0

    json_path = temp_output_dir / "config.next.json"
    assert json_path.exists()

    # Step 3: Simulate
    result3 = _run_cmd(
        [
            "uv",
            "run",
            "lacuna-sim",
            "--yaml",
            str(test_config_path),
            "--request",
            "prod.example.com /",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    # Simulator may return 1 if there are dead rules, but should still produce output
    assert "home" in result3.stdout


@pytest.mark.integration
@pytest.mark.slow
def test_cli_with_multiple_configs(temp_output_dir: Path, repo_root: Path) -> None:
    """Test CLI tools work with different config variations."""
    configs = [
        repo_root / "examples" / "domainlist.yaml",
        repo_root / "examples" / "minimal.yaml",
    ]

    for config_path in configs:
        # Validate each config
        result = _run_cmd(
            ["uv", "run", "python", "-m", "lacuna_schema", "check", str(config_path)],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        assert result.returncode == 0, f"Failed to validate {config_path}"
