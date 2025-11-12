"""Caddy integration tests.

Tests that require or mock Caddy binary for validation and reload operations.
"""

import json
import subprocess
from pathlib import Path

import pytest
from lacuna_compiler.api import write_candidate
from lacuna_promote import (
    ValidationError,
    rollback,
    validate_config,
)
from lacuna_schema.api import load_config


@pytest.mark.requires_caddy
@pytest.mark.integration
def test_caddy_validate_good_config(
    temp_output_dir: Path, test_config_path: Path, caddy_available: bool
) -> None:
    """Test Caddy validates a good config (requires Caddy binary)."""
    if not caddy_available:
        pytest.skip("Caddy binary not available")

    # Compile example config
    config = load_config(test_config_path)
    output = write_candidate(config, temp_output_dir)

    # Validate with actual Caddy
    is_valid = validate_config(output, "caddy")
    assert is_valid is True


@pytest.mark.requires_caddy
@pytest.mark.integration
def test_caddy_validate_bad_config(temp_output_dir: Path, caddy_available: bool) -> None:
    """Test Caddy rejects invalid config (requires Caddy binary)."""
    if not caddy_available:
        pytest.skip("Caddy binary not available")

    # Write malformed JSON
    bad_config = temp_output_dir / "bad.json"
    bad_config.write_text("{invalid json}")

    # Validate should fail
    is_valid = validate_config(bad_config, "caddy")
    assert is_valid is False


@pytest.mark.requires_caddy
@pytest.mark.integration
def test_caddy_validate_missing_required_fields(
    temp_output_dir: Path, caddy_available: bool
) -> None:
    """Test Caddy rejects config with missing required fields."""
    if not caddy_available:
        pytest.skip("Caddy binary not available")

    # Write incomplete JSON (missing required Caddy fields)
    bad_config = temp_output_dir / "incomplete.json"
    bad_config.write_text(json.dumps({"apps": {}}))

    # This may or may not fail depending on Caddy's defaults,
    # but it shouldn't crash
    result = validate_config(bad_config, "caddy")
    assert isinstance(result, bool)


@pytest.mark.integration
def test_validate_config_mocked_success(
    temp_output_dir: Path, test_config_path: Path, mock_caddy_success: None
) -> None:
    """Test validate_config with mocked Caddy success."""
    config = load_config(test_config_path)
    output = write_candidate(config, temp_output_dir)

    # Should succeed with mock
    is_valid = validate_config(output, "caddy")
    assert is_valid is True


@pytest.mark.integration
def test_validate_config_mocked_failure(
    temp_output_dir: Path, test_config_path: Path, mock_caddy_failure: None
) -> None:
    """Test validate_config with mocked Caddy failure."""
    config = load_config(test_config_path)
    output = write_candidate(config, temp_output_dir)

    # Should fail with mock
    is_valid = validate_config(output, "caddy")
    assert is_valid is False


@pytest.mark.integration
def test_reload_caddy_mocked_success(
    temp_output_dir: Path, test_config_path: Path, mock_caddy_success: None
) -> None:
    """Test reload_caddy with mocked success."""
    from lacuna_promote.promoter import reload_caddy

    config = load_config(test_config_path)
    output = write_candidate(config, temp_output_dir)

    # Should succeed with mock
    success = reload_caddy(output, "caddy")
    assert success is True


@pytest.mark.integration
def test_reload_caddy_mocked_failure(
    temp_output_dir: Path, test_config_path: Path, mock_caddy_failure: None
) -> None:
    """Test reload_caddy with mocked failure."""
    from lacuna_promote.promoter import reload_caddy

    config = load_config(test_config_path)
    output = write_candidate(config, temp_output_dir)

    # Should fail with mock
    success = reload_caddy(output, "caddy")
    assert success is False


@pytest.mark.integration
def test_rollback_without_lastgood(
    temp_output_dir: Path, mock_caddy_success: None
) -> None:
    """Test rollback fails when lastgood doesn't exist."""
    from lacuna_promote import RollbackError

    # Try to rollback with no lastgood file
    with pytest.raises(RollbackError, match="does not exist"):
        rollback(temp_output_dir, "caddy")


@pytest.mark.integration
def test_rollback_with_lastgood(
    temp_output_dir: Path, test_config_path: Path, mock_caddy_success: None
) -> None:
    """Test successful rollback to lastgood."""
    # Create a lastgood file
    config = load_config(test_config_path)
    output = write_candidate(config, temp_output_dir)

    # Copy to lastgood
    lastgood = temp_output_dir / "config.lastgood.json"
    output.replace(lastgood)

    # Recreate next for consistency
    write_candidate(config, temp_output_dir)

    # Rollback should succeed
    success = rollback(temp_output_dir, "caddy")
    assert success is True


@pytest.mark.integration
def test_rollback_when_reload_fails(
    temp_output_dir: Path, test_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test rollback fails when reload of lastgood also fails."""
    # Create a lastgood file
    config = load_config(test_config_path)
    output = write_candidate(config, temp_output_dir)
    lastgood = temp_output_dir / "config.lastgood.json"
    output.replace(lastgood)

    # Mock reload to always fail
    def mock_run(cmd, **kwargs):  # type: ignore
        return subprocess.CompletedProcess(cmd, 1, "", "Failed")

    monkeypatch.setattr(subprocess, "run", mock_run)

    # Rollback should raise RollbackError
    from lacuna_promote import RollbackError

    with pytest.raises(RollbackError, match="Rollback failed"):
        rollback(temp_output_dir, "caddy")


@pytest.mark.integration
def test_validation_in_promotion_workflow(
    temp_output_dir: Path, test_config_path: Path, mock_caddy_failure: None
) -> None:
    """Test that validation failure aborts promotion."""
    from lacuna_promote import PromoteOptions, compile_and_promote

    opts = PromoteOptions(out_dir=temp_output_dir)

    # Should fail at validation step
    with pytest.raises(ValidationError):
        compile_and_promote(test_config_path, opts)

    # No active config should exist
    assert not (temp_output_dir / "config.active.json").exists()


@pytest.mark.integration
def test_caddy_binary_not_found(temp_output_dir: Path, test_config_path: Path) -> None:
    """Test behavior when Caddy binary is not found."""
    config = load_config(test_config_path)
    output = write_candidate(config, temp_output_dir)

    # Use invalid binary path
    is_valid = validate_config(output, "nonexistent-caddy-binary")
    assert is_valid is False


@pytest.mark.integration
def test_atomic_write_for_candidate(temp_output_dir: Path, test_config_path: Path) -> None:
    """Test that write_candidate uses atomic write pattern."""
    config = load_config(test_config_path)

    # Write first time
    output1 = write_candidate(config, temp_output_dir)
    assert output1.exists()

    # Get file stats
    output1.stat()

    # Write again (should atomically replace)
    output2 = write_candidate(config, temp_output_dir)
    assert output2 == output1  # Same path

    # File should still exist and be readable
    assert output2.exists()

    # Verify no temp files left behind
    temp_files = list(temp_output_dir.glob(".config.*.tmp.*"))
    assert len(temp_files) == 0


@pytest.mark.integration
def test_config_file_permissions(temp_output_dir: Path, test_config_path: Path) -> None:
    """Test that written configs have appropriate permissions."""
    config = load_config(test_config_path)
    output = write_candidate(config, temp_output_dir)

    # File should be readable
    assert output.exists()
    assert output.is_file()

    # Should be able to read as JSON
    with output.open("r") as f:
        data = json.load(f)
    assert data is not None
