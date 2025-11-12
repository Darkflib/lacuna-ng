"""End-to-end workflow integration tests.

Tests the complete pipeline from YAML → Compilation → Simulation → Promotion.
"""

import json
from pathlib import Path

import pytest
from lacuna_compiler.api import compile_to_caddy, write_candidate
from lacuna_promote import PromoteOptions, ReloadError, compile_and_promote
from lacuna_schema.api import load_config
from lacuna_sim import (
    Request,
    generate_coverage_report,
    simulate_batch,
)


@pytest.mark.integration
def test_full_compilation_workflow(temp_output_dir: Path, test_config_path: Path) -> None:
    """Test complete workflow: schema → compiler → simulator."""
    # Step 1: Validate YAML with lacuna_schema
    config = load_config(test_config_path)
    assert config.hosts is not None
    assert len(config.hosts) == 3
    assert config.hosts[0].host == "prod.example.com"

    # Step 2: Compile to Caddy JSON with lacuna_compiler
    caddy_json = compile_to_caddy(config)
    assert "_meta" in caddy_json
    assert "apps" in caddy_json
    assert "http" in caddy_json["apps"]

    # Verify metadata
    meta = caddy_json["_meta"]
    assert "built_at" in meta
    assert "content_sha256" in meta

    # Step 3: Write to temp directory
    output = write_candidate(config, temp_output_dir)
    assert output.exists()
    assert output.name == "config.next.json"

    # Verify file contents are valid JSON
    with output.open("r") as f:
        written_json = json.load(f)
    assert written_json == caddy_json

    # Step 4: Simulate requests with lacuna_sim
    requests = [
        Request("prod.example.com", "/", ""),
        Request("prod.example.com", "/blog/post", ""),
        Request("old.example.com", "/anything", ""),
    ]
    results = simulate_batch(config, requests)
    assert len(results) == 3
    assert all(r.matched for r in results)

    # Verify specific redirects
    assert results[0].rule_id == "home"
    assert results[0].location == "https://www.example.org/"
    assert results[0].status == 308

    assert results[1].rule_id == "blog"
    assert results[1].location == "https://blog.example.org/post"
    assert results[1].status == 308

    assert results[2].rule_id == "catch-all"
    assert results[2].location == "https://new.example.com/anything"
    assert results[2].status == 301

    # Step 5: Generate coverage report
    report = generate_coverage_report(config, results)
    assert report.total_rules > 0
    assert len(report.matched_rules) > 0
    assert len(report.matched_rules) == 3


@pytest.mark.integration
def test_full_workflow_with_all_test_cases(
    temp_output_dir: Path, test_config_path: Path, test_cases_path: Path
) -> None:
    """Test workflow with all test cases from cases.txt."""
    # Load config and compile
    config = load_config(test_config_path)
    output = write_candidate(config, temp_output_dir)
    assert output.exists()

    # Load and simulate all test cases
    from lacuna_sim import parse_cases_file

    requests = parse_cases_file(test_cases_path)
    assert len(requests) > 0

    results = simulate_batch(config, requests)
    assert len(results) == len(requests)

    # All requests should match a rule
    assert all(r.matched for r in results)

    # Generate coverage report - should have 100% coverage
    report = generate_coverage_report(config, results)
    assert report.coverage_percent == 100.0
    assert len(report.dead_rules) == 0


@pytest.mark.integration
def test_promotion_workflow_mocked(
    temp_output_dir: Path, test_config_path: Path, mock_caddy_success: None
) -> None:
    """Test full promotion workflow with mocked Caddy."""
    # Run promotion
    opts = PromoteOptions(out_dir=temp_output_dir)
    active_path = compile_and_promote(test_config_path, opts)

    # Verify files exist
    assert active_path.exists()
    assert active_path.name == "config.active.json"
    assert (temp_output_dir / "config.next.json").exists()
    assert (temp_output_dir / "config.active.json").exists()

    # Note: lastgood only exists if there was a previous active config
    # On first run, there's no backup


@pytest.mark.integration
def test_promotion_validate_only_mode(
    temp_output_dir: Path, test_config_path: Path, mock_caddy_success: None
) -> None:
    """Test promotion with validate-only flag."""
    opts = PromoteOptions(out_dir=temp_output_dir, validate_only=True)
    result_path = compile_and_promote(test_config_path, opts)

    # Should return next path, not active
    assert result_path.name == "config.next.json"
    assert result_path.exists()

    # Active should NOT exist in validate-only mode
    assert not (temp_output_dir / "config.active.json").exists()


@pytest.mark.integration
def test_promotion_rollback_on_reload_failure(
    temp_output_dir: Path, test_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test rollback when reload fails."""
    import subprocess

    call_count = 0

    def mock_run(cmd, **kwargs):  # type: ignore
        nonlocal call_count
        # Mock git commands to succeed
        if "git" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "abc1234", "")
        if "validate" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if "reload" in cmd:
            call_count += 1
            if call_count == 1:
                # First reload fails
                return subprocess.CompletedProcess(cmd, 1, "", "Reload failed")
            # Second reload (rollback) succeeds
            return subprocess.CompletedProcess(cmd, 0, "", "")
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", mock_run)

    # First promotion: create initial config (will fail but no rollback)
    opts = PromoteOptions(out_dir=temp_output_dir)

    with pytest.raises(ReloadError):
        compile_and_promote(test_config_path, opts)

    # Reload was attempted once (no rollback since no lastgood exists)
    assert call_count == 1


@pytest.mark.integration
def test_promotion_rollback_with_existing_config(
    temp_output_dir: Path, test_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test rollback when an active config exists."""
    import subprocess

    # First, create an initial active config (simulate successful first promotion)
    from lacuna_compiler.api import write_candidate
    from lacuna_schema.api import load_config

    config = load_config(test_config_path)
    next_path = write_candidate(config, temp_output_dir)

    # Manually promote to active to simulate existing deployment
    active_path = temp_output_dir / "config.active.json"
    next_path.replace(active_path)

    # Now create next again for second promotion
    next_path = write_candidate(config, temp_output_dir)

    call_count = 0

    def mock_run(cmd, **kwargs):  # type: ignore
        nonlocal call_count
        # Mock git commands to succeed
        if "git" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "abc1234", "")
        if "validate" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if "reload" in cmd:
            call_count += 1
            if call_count == 1:
                # First reload (new config) fails
                return subprocess.CompletedProcess(cmd, 1, "", "Reload failed")
            # Second reload (rollback to lastgood) succeeds
            return subprocess.CompletedProcess(cmd, 0, "", "")
        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", mock_run)

    # Second promotion should fail and rollback
    opts = PromoteOptions(out_dir=temp_output_dir)

    with pytest.raises(ReloadError, match="rolled back"):
        compile_and_promote(test_config_path, opts)

    # Verify rollback was attempted (2 reload calls)
    assert call_count == 2

    # Verify lastgood was created
    assert (temp_output_dir / "config.lastgood.json").exists()


@pytest.mark.integration
def test_double_buffer_promotion_sequence(
    temp_output_dir: Path, minimal_config_path: Path, mock_caddy_success: None
) -> None:
    """Test multiple promotions in sequence (double-buffer pattern)."""
    opts = PromoteOptions(out_dir=temp_output_dir)

    # First promotion
    active1 = compile_and_promote(minimal_config_path, opts)
    assert active1.exists()

    # Read first active config
    with active1.open("r") as f:
        config1 = json.load(f)

    # Second promotion (should backup first to lastgood)
    active2 = compile_and_promote(minimal_config_path, opts)
    assert active2.exists()

    # Verify lastgood was created from first active
    lastgood = temp_output_dir / "config.lastgood.json"
    assert lastgood.exists()

    with lastgood.open("r") as f:
        lastgood_config = json.load(f)

    # Lastgood should match first active config
    assert lastgood_config == config1


@pytest.mark.integration
def test_metadata_in_compiled_json(temp_output_dir: Path, test_config_path: Path) -> None:
    """Verify metadata block is present and correct in compiled JSON."""
    config = load_config(test_config_path)
    output = write_candidate(config, temp_output_dir)

    with output.open("r") as f:
        caddy_json = json.load(f)

    # Check metadata
    assert "_meta" in caddy_json
    meta = caddy_json["_meta"]

    assert "built_at" in meta
    assert "content_sha256" in meta

    # Verify metadata types
    assert isinstance(meta["built_at"], str)
    assert isinstance(meta["content_sha256"], str)
    assert len(meta["content_sha256"]) == 64  # SHA256 hex string

    # Optional git field
    if "git" in meta:
        assert isinstance(meta["git"], str)
