"""Chaos/failure tests for rollback scenarios."""

import json
from pathlib import Path
from unittest import mock

import pytest
from lacuna_promote import PromoteOptions, ReloadError, RollbackError, compile_and_promote
from lacuna_promote.promoter import rollback


class TestReloadFailureAndRollback:
    """Test reload failures and automatic rollback."""

    def test_reload_failure_triggers_rollback(self, tmp_path: Path) -> None:
        """Test that reload failure triggers automatic rollback."""
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

        def mock_subprocess(*args, **kwargs):
            """Mock subprocess calls, differentiating between git and caddy."""
            cmd = args[0]
            if cmd[0] == "git":
                # Git command for metadata
                return mock.Mock(returncode=0, stdout="abc1234", stderr="")
            elif cmd[0] == "caddy":
                if cmd[1] == "validate":
                    # Validation succeeds
                    return mock.Mock(returncode=0, stdout="", stderr="")
                elif cmd[1] == "reload":
                    config_path = cmd[3]
                    if "config.next.json" in config_path:
                        # Reload with next fails
                        return mock.Mock(returncode=1, stdout="", stderr="Reload failed")
                    elif "config.lastgood.json" in config_path:
                        # Rollback succeeds
                        return mock.Mock(returncode=0, stdout="", stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch("subprocess.run", side_effect=mock_subprocess):
            with pytest.raises(ReloadError, match="rolled back"):
                compile_and_promote(yaml_path, opts)

        # Active should be unchanged (still old config)
        with active_path.open("r") as f:
            current_data = json.load(f)
        assert current_data == old_config

        # Lastgood should exist with old config
        lastgood_path = out_dir / "config.lastgood.json"
        assert lastgood_path.exists()
        with lastgood_path.open("r") as f:
            lastgood_data = json.load(f)
        assert lastgood_data == old_config

    def test_rollback_success_restores_lastgood(self, tmp_path: Path) -> None:
        """Test successful rollback restores lastgood config."""
        # Setup: create lastgood config
        lastgood_path = tmp_path / "config.lastgood.json"
        lastgood_data = {"apps": {"http": {"lastgood": "config"}}}
        lastgood_path.write_text(json.dumps(lastgood_data))

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            result = rollback(tmp_path, caddy_bin="caddy")

            assert result is True
            mock_run.assert_called_once()

            # Verify reload was called with lastgood path
            args = mock_run.call_args[0][0]
            assert args[1] == "reload"
            assert str(lastgood_path) in args

    def test_rollback_failure_raises_critical_error(self, tmp_path: Path) -> None:
        """Test that rollback failure raises critical error."""
        # Setup: create lastgood config
        lastgood_path = tmp_path / "config.lastgood.json"
        lastgood_data = {"apps": {"http": {"lastgood": "config"}}}
        lastgood_path.write_text(json.dumps(lastgood_data))

        with mock.patch("subprocess.run") as mock_run:
            # Rollback reload fails
            mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="Fatal error")

            with pytest.raises(RollbackError, match="could not reload"):
                rollback(tmp_path, caddy_bin="caddy")

    def test_rollback_missing_lastgood(self, tmp_path: Path) -> None:
        """Test graceful error when lastgood doesn't exist."""
        # No lastgood.json exists

        with pytest.raises(RollbackError, match="does not exist"):
            rollback(tmp_path)


class TestReloadFailureOnFirstDeployment:
    """Test reload failure when there's no lastgood to rollback to."""

    def test_reload_failure_no_lastgood(self, tmp_path: Path) -> None:
        """Test reload failure on first deployment (no lastgood)."""
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

        def mock_subprocess(*args, **kwargs):
            """Mock subprocess calls."""
            cmd = args[0]
            if cmd[0] == "git":
                return mock.Mock(returncode=0, stdout="abc1234", stderr="")
            elif cmd[0] == "caddy":
                if cmd[1] == "validate":
                    return mock.Mock(returncode=0, stdout="", stderr="")
                elif cmd[1] == "reload":
                    # Reload fails
                    return mock.Mock(returncode=1, stdout="", stderr="Fatal")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch("subprocess.run", side_effect=mock_subprocess):
            with pytest.raises(ReloadError, match="no lastgood"):
                compile_and_promote(yaml_path, opts)

        # No active should be created
        assert not (out_dir / "config.active.json").exists()


class TestProbeFailures:
    """Test sentinel probe failures."""

    def test_probe_failure_aborts_promotion(self, tmp_path: Path) -> None:
        """Test that probe failure prevents promotion."""
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
        opts = PromoteOptions(
            out_dir=out_dir, sentinel_urls=["http://example.com/health"]
        )

        def mock_subprocess(*args, **kwargs):
            """Mock subprocess calls."""
            cmd = args[0]
            if cmd[0] == "git":
                return mock.Mock(returncode=0, stdout="abc1234", stderr="")
            elif cmd[0] == "caddy":
                # All caddy commands succeed
                return mock.Mock(returncode=0, stdout="", stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch("subprocess.run", side_effect=mock_subprocess):
            # Mock requests.get to fail
            with mock.patch("requests.get") as mock_get:
                import requests
                mock_get.side_effect = requests.RequestException("Connection refused")

                from lacuna_promote import ProbeError

                with pytest.raises(ProbeError):
                    compile_and_promote(yaml_path, opts)

        # Next should exist but not active
        assert (out_dir / "config.next.json").exists()
        assert not (out_dir / "config.active.json").exists()

    def test_probe_wrong_status_fails(self, tmp_path: Path) -> None:
        """Test that non-30x probe response fails."""
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
        opts = PromoteOptions(
            out_dir=out_dir, sentinel_urls=["http://example.com/health"]
        )

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            # Mock requests.get to return 200 (not 30x)
            with mock.patch("requests.get") as mock_get:
                mock_get.return_value = mock.Mock(status_code=200)

                from lacuna_promote import ProbeError

                with pytest.raises(ProbeError):
                    compile_and_promote(yaml_path, opts)

    def test_probe_success_allows_promotion(self, tmp_path: Path) -> None:
        """Test that 30x probe response allows promotion."""
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
        opts = PromoteOptions(
            out_dir=out_dir, sentinel_urls=["http://example.com/health"]
        )

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")

            # Mock requests.get to return 301 (30x)
            with mock.patch("requests.get") as mock_get:
                mock_get.return_value = mock.Mock(status_code=301)

                active_path = compile_and_promote(yaml_path, opts)

                assert active_path.exists()
                mock_get.assert_called_once()


class TestAtomicOperations:
    """Test that file operations are atomic."""

    def test_backup_is_atomic(self, tmp_path: Path) -> None:
        """Test that backup uses atomic write pattern."""
        from lacuna_promote.promoter import backup_active

        # Create active config
        active_path = tmp_path / "config.active.json"
        active_path.write_text('{"test": "data"}')

        # Backup should use temp file and atomic replace
        lastgood_path = backup_active(tmp_path)

        assert lastgood_path is not None
        # Verify no temp files left behind
        temp_files = list(tmp_path.glob(".config.lastgood.json.tmp.*"))
        assert len(temp_files) == 0

    def test_promote_is_atomic(self, tmp_path: Path) -> None:
        """Test that promotion uses atomic write pattern."""
        from lacuna_promote.promoter import promote_config

        # Create next config
        next_path = tmp_path / "config.next.json"
        next_path.write_text('{"test": "data"}')

        # Promote should use temp file and atomic replace
        active_path = promote_config(tmp_path)

        assert active_path.exists()
        # Verify no temp files left behind
        temp_files = list(tmp_path.glob(".config.active.json.tmp.*"))
        assert len(temp_files) == 0

    def test_failed_backup_cleans_up_temp(self, tmp_path: Path) -> None:
        """Test that failed backup cleans up temp files."""
        from lacuna_promote.promoter import backup_active

        # Create active config
        active_path = tmp_path / "config.active.json"
        active_path.write_text('{"test": "data"}')

        # Mock os.fsync to raise an error
        with mock.patch("os.fsync", side_effect=OSError("Disk full")):
            with pytest.raises(OSError):
                backup_active(tmp_path)

        # Verify temp file is cleaned up
        temp_files = list(tmp_path.glob(".config.lastgood.json.tmp.*"))
        assert len(temp_files) == 0

    def test_failed_promote_cleans_up_temp(self, tmp_path: Path) -> None:
        """Test that failed promotion cleans up temp files."""
        from lacuna_promote.promoter import promote_config

        # Create next config
        next_path = tmp_path / "config.next.json"
        next_path.write_text('{"test": "data"}')

        # Mock os.fsync to raise an error
        with mock.patch("os.fsync", side_effect=OSError("Disk full")):
            with pytest.raises(OSError):
                promote_config(tmp_path)

        # Verify temp file is cleaned up
        temp_files = list(tmp_path.glob(".config.active.json.tmp.*"))
        assert len(temp_files) == 0


class TestErrorMessages:
    """Test that error messages are clear and actionable."""

    def test_validation_error_includes_details(self, tmp_path: Path) -> None:
        """Test that validation errors include helpful details."""
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
            mock_run.return_value = mock.Mock(
                returncode=1, stdout="", stderr="Invalid JSON syntax"
            )

            try:
                compile_and_promote(yaml_path, opts)
            except Exception as e:
                assert "validation failed" in str(e).lower()

    def test_rollback_error_is_critical(self, tmp_path: Path) -> None:
        """Test that rollback errors are marked as critical."""
        lastgood_path = tmp_path / "config.lastgood.json"
        lastgood_path.write_text('{"test": "data"}')

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="Fatal")

            with pytest.raises(RollbackError) as exc_info:
                rollback(tmp_path)

            assert "could not reload" in str(exc_info.value).lower()
