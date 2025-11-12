"""Pytest fixtures for integration tests."""

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest


@pytest.fixture
def test_config_path() -> Path:
    """Path to the main test configuration (examples/domainlist.yaml)."""
    return Path("/home/user/Lacuna-ng/examples/domainlist.yaml")


@pytest.fixture
def minimal_config_path() -> Path:
    """Path to the minimal test configuration."""
    return Path("/home/user/Lacuna-ng/examples/minimal.yaml")


@pytest.fixture
def test_cases_path() -> Path:
    """Path to test cases file for simulator."""
    return Path("/home/user/Lacuna-ng/examples/cases.txt")


@pytest.fixture
def temp_output_dir() -> Any:
    """Temporary output directory for compiled configs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def compiled_config(temp_output_dir: Path, test_config_path: Path) -> Path:
    """Pre-compiled configuration as config.next.json."""
    from lacuna_compiler.api import write_candidate
    from lacuna_schema.api import load_config

    config = load_config(test_config_path)
    output = write_candidate(config, temp_output_dir)
    return output


@pytest.fixture
def mock_caddy_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock Caddy commands to succeed."""

    def mock_run(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", mock_run)


@pytest.fixture
def mock_caddy_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock Caddy commands to fail."""

    def mock_run(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(cmd, 1, "", "Caddy error")

    monkeypatch.setattr(subprocess, "run", mock_run)


@pytest.fixture
def mock_caddy_validate_success_reload_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock Caddy: validate succeeds, reload fails."""

    def mock_run(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
        if "validate" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if "reload" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "Reload failed")
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", mock_run)


@pytest.fixture
def caddy_available() -> bool:
    """Check if Caddy binary is available."""
    try:
        result = subprocess.run(
            ["caddy", "version"], capture_output=True, check=False, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.fixture
def fixture_config_path() -> Path:
    """Path to the simple test fixture configuration."""
    return Path("/home/user/Lacuna-ng/tests/fixtures/test_config.yaml")
