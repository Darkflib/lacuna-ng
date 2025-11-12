"""Tests for the promotion system - happy path scenarios."""

import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest
from lacuna_promote import PromoteOptions, ValidationError, compile_and_promote, validate_config
from lacuna_promote.promoter import backup_active, promote_config


class TestValidateConfig:
    """Test Caddy validation."""

    def test_validate_good_config(self, tmp_path: Path) -> None:
        """Test that valid config passes validation."""
        config_path = tmp_path / "good.json"
        config_path.write_text('{"apps": {}}')

        # Mock subprocess.run to simulate successful validation
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="Valid", stderr="")

            result = validate_config(config_path)

            assert result is True
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "caddy"
            assert args[1] == "validate"
            assert args[3] == str(config_path)

    def test_validate_bad_config(self, tmp_path: Path) -> None:
        """Test that invalid config fails validation."""
        config_path = tmp_path / "bad.json"
        config_path.write_text('{"invalid": "config"}')

        # Mock subprocess.run to simulate failed validation
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="validation error")

            result = validate_config(config_path)

            assert result is False

    def test_validate_caddy_not_found(self, tmp_path: Path) -> None:
        """Test graceful handling when Caddy binary doesn't exist."""
        config_path = tmp_path / "config.json"
        config_path.write_text('{"apps": {}}')

        # Mock subprocess.run to raise FileNotFoundError
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            result = validate_config(config_path, caddy_bin="nonexistent")

            assert result is False

    def test_validate_timeout(self, tmp_path: Path) -> None:
        """Test handling of validation timeout."""
        config_path = tmp_path / "config.json"
        config_path.write_text('{"apps": {}}')

        # Mock subprocess.run to raise TimeoutExpired
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("caddy", 30)):
            result = validate_config(config_path)

            assert result is False


class TestBackupActive:
    """Test active config backup."""

    def test_backup_existing_active(self, tmp_path: Path) -> None:
        """Test backup of existing active config."""
        active_path = tmp_path / "config.active.json"
        active_data: dict[str, Any] = {"apps": {"http": {"servers": {}}}}
        active_path.write_text(json.dumps(active_data))

        lastgood_path = backup_active(tmp_path)

        assert lastgood_path == tmp_path / "config.lastgood.json"
        assert lastgood_path.exists()

        # Verify content matches
        with lastgood_path.open("r") as f:
            lastgood_data = json.load(f)
        assert lastgood_data == active_data

    def test_backup_no_active(self, tmp_path: Path) -> None:
        """Test backup when no active config exists (first deployment)."""
        lastgood_path = backup_active(tmp_path)

        assert lastgood_path is None
        assert not (tmp_path / "config.lastgood.json").exists()

    def test_backup_preserves_content(self, tmp_path: Path) -> None:
        """Test that backup preserves exact content including formatting."""
        active_path = tmp_path / "config.active.json"
        original_content = '{"test": "data", "number": 123}'
        active_path.write_bytes(original_content.encode())

        lastgood_path = backup_active(tmp_path)

        assert lastgood_path is not None
        backup_content = lastgood_path.read_bytes().decode()
        assert backup_content == original_content


class TestPromoteConfig:
    """Test config promotion."""

    def test_promote_next_to_active(self, tmp_path: Path) -> None:
        """Test promotion of next config to active."""
        next_path = tmp_path / "config.next.json"
        next_data = {"apps": {"http": {"servers": {"new": "config"}}}}
        next_path.write_text(json.dumps(next_data))

        active_path = promote_config(tmp_path)

        assert active_path == tmp_path / "config.active.json"
        assert active_path.exists()

        # Verify content matches
        with active_path.open("r") as f:
            active_data = json.load(f)
        assert active_data == next_data

    def test_promote_overwrites_existing_active(self, tmp_path: Path) -> None:
        """Test that promotion overwrites existing active config."""
        # Create old active
        active_path = tmp_path / "config.active.json"
        active_path.write_text('{"old": "config"}')

        # Create new next
        next_path = tmp_path / "config.next.json"
        new_data = {"new": "config"}
        next_path.write_text(json.dumps(new_data))

        result_path = promote_config(tmp_path)

        assert result_path == active_path
        with active_path.open("r") as f:
            active_data = json.load(f)
        assert active_data == new_data

    def test_promote_missing_next(self, tmp_path: Path) -> None:
        """Test error when next config doesn't exist."""
        with pytest.raises(FileNotFoundError, match="config.next.json"):
            promote_config(tmp_path)


class TestFullPromotionFlow:
    """Test full promotion flow with mocked Caddy."""

    def test_full_promotion_success(self, tmp_path: Path) -> None:
        """Test complete promotion flow with all steps succeeding."""
        # Create a minimal valid YAML config
        yaml_path = tmp_path / "config.yaml"
        yaml_content = """version: 1
defaults:
  hsts: true
  keep_query: true
hosts:
  - host: example.com
    rules:
      - id: home
        match: exact
        from: /
        to: https://www.example.com/
        status: 308
"""
        yaml_path.write_text(yaml_content)

        out_dir = tmp_path / "config"
        opts = PromoteOptions(out_dir=out_dir)

        # Mock subprocess.run for caddy commands
        with mock.patch("subprocess.run") as mock_run:
            # All caddy commands succeed
            mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            active_path = compile_and_promote(yaml_path, opts)

            assert active_path == out_dir / "config.active.json"
            assert active_path.exists()

            # Verify config files exist
            assert (out_dir / "config.next.json").exists()
            # On first deployment, no lastgood is created (no active to backup)
            assert not (out_dir / "config.lastgood.json").exists()

            # Verify caddy was called for validate and reload
            # Note: git may also be called for metadata
            calls = mock_run.call_args_list
            caddy_calls = [c for c in calls if c[0][0][0] == "caddy"]
            assert len(caddy_calls) >= 2  # At least validate + reload
            validate_call = caddy_calls[0][0][0]
            assert validate_call[1] == "validate"
            reload_call = caddy_calls[1][0][0]
            assert reload_call[1] == "reload"

    def test_validate_only_mode(self, tmp_path: Path) -> None:
        """Test that validate-only mode stops after validation."""
        yaml_path = tmp_path / "config.yaml"
        yaml_content = """version: 1
defaults:
  hsts: true
  keep_query: true
hosts:
  - host: example.com
    rules:
      - id: test
        match: exact
        from: /
        to: https://example.com/
        status: 301
"""
        yaml_path.write_text(yaml_content)

        out_dir = tmp_path / "config"
        opts = PromoteOptions(out_dir=out_dir, validate_only=True)

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            result_path = compile_and_promote(yaml_path, opts)

            # Should return next path, not active
            assert result_path == out_dir / "config.next.json"
            assert result_path.exists()

            # Active should not be created in validate-only mode
            assert not (out_dir / "config.active.json").exists()

            # Only validate called, not reload (git may be called for metadata)
            caddy_calls = [c for c in mock_run.call_args_list if c[0][0][0] == "caddy"]
            assert len(caddy_calls) == 1
            validate_call = caddy_calls[0][0][0]
            assert validate_call[1] == "validate"

    def test_validation_failure_aborts(self, tmp_path: Path) -> None:
        """Test that validation failure prevents promotion."""
        yaml_path = tmp_path / "config.yaml"
        yaml_content = """version: 1
defaults:
  hsts: true
  keep_query: true
hosts:
  - host: example.com
    rules:
      - id: test
        match: exact
        from: /
        to: https://example.com/
        status: 301
"""
        yaml_path.write_text(yaml_content)

        out_dir = tmp_path / "config"
        opts = PromoteOptions(out_dir=out_dir)

        with mock.patch("subprocess.run") as mock_run:
            # Validation fails
            mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="Invalid")

            with pytest.raises(ValidationError):
                compile_and_promote(yaml_path, opts)

            # Next should be written but not active
            assert (out_dir / "config.next.json").exists()
            assert not (out_dir / "config.active.json").exists()

    def test_first_deployment_no_backup(self, tmp_path: Path) -> None:
        """Test first deployment when there's no active config to backup."""
        yaml_path = tmp_path / "config.yaml"
        yaml_content = """version: 1
defaults:
  hsts: true
  keep_query: true
hosts:
  - host: example.com
    rules:
      - id: test
        match: exact
        from: /
        to: https://example.com/
        status: 301
"""
        yaml_path.write_text(yaml_content)

        out_dir = tmp_path / "config"
        opts = PromoteOptions(out_dir=out_dir)

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            active_path = compile_and_promote(yaml_path, opts)

            # Active should be created
            assert active_path.exists()

            # But lastgood should not exist (no previous active)
            # Actually, it should exist after promotion because we backup before reload
            # Let me check the logic... Looking at the code, backup_active is called
            # before reload, so if there's no active, no backup is created.
            # But after successful reload, we promote next to active.
            # So lastgood should NOT exist on first deployment.
            assert not (out_dir / "config.lastgood.json").exists()

    def test_subsequent_deployment_creates_backup(self, tmp_path: Path) -> None:
        """Test that subsequent deployments create lastgood backup."""
        yaml_path = tmp_path / "config.yaml"
        yaml_content = """version: 1
defaults:
  hsts: true
  keep_query: true
hosts:
  - host: example.com
    rules:
      - id: test
        match: exact
        from: /
        to: https://example.com/
        status: 301
"""
        yaml_path.write_text(yaml_content)

        out_dir = tmp_path / "config"
        opts = PromoteOptions(out_dir=out_dir)

        # Create existing active config
        active_path = out_dir / "config.active.json"
        active_path.parent.mkdir(parents=True, exist_ok=True)
        old_config = {"apps": {"http": {"old": "config"}}}
        active_path.write_text(json.dumps(old_config))

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            compile_and_promote(yaml_path, opts)

            # Lastgood should be created with old config
            lastgood_path = out_dir / "config.lastgood.json"
            assert lastgood_path.exists()

            with lastgood_path.open("r") as f:
                lastgood_data = json.load(f)
            assert lastgood_data == old_config
