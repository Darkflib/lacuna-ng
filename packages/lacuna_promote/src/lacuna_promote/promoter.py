"""
Core double-buffer promotion logic with validation, reload, and rollback.

This module implements the safe config promotion algorithm:
1. Validate candidate config with Caddy
2. Optional: probe sentinel URLs
3. Backup current active config
4. Reload Caddy with candidate
5. On failure: rollback to lastgood
6. On success: promote candidate to active
"""

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from lacuna_compiler.api import write_candidate
from lacuna_schema.api import load_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


# Custom exceptions for clarity
class ValidationError(Exception):
    """Raised when Caddy validation fails."""

    pass


class ProbeError(Exception):
    """Raised when sentinel URL probes fail."""

    pass


class ReloadError(Exception):
    """Raised when Caddy reload fails."""

    pass


class RollbackError(Exception):
    """Raised when rollback to lastgood fails."""

    pass


@dataclass(frozen=True)
class PromoteOptions:
    """Options for config promotion."""

    out_dir: Path
    caddy_bin: str = "caddy"
    validate_only: bool = False
    sentinel_urls: list[str] | None = None
    probe_timeout: float = 5.0


def validate_config(config_path: Path, caddy_bin: str = "caddy") -> bool:
    """
    Validate config with Caddy.

    Args:
        config_path: Path to config file to validate
        caddy_bin: Path to caddy binary

    Returns:
        True if valid, False otherwise

    Logs validation errors with stdout/stderr from caddy.
    """
    logger.info(f"Validating config: {config_path}")

    try:
        result = subprocess.run(
            [caddy_bin, "validate", "--config", str(config_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            logger.info(f"✓ Validation passed: {config_path}")
            if result.stdout:
                logger.debug(f"Validation stdout: {result.stdout}")
            return True
        else:
            logger.error(f"✗ Validation failed: {config_path}")
            if result.stdout:
                logger.error(f"Validation stdout: {result.stdout}")
            if result.stderr:
                logger.error(f"Validation stderr: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"✗ Validation timed out: {config_path}")
        return False
    except FileNotFoundError:
        logger.error(f"✗ Caddy binary not found: {caddy_bin}")
        return False
    except Exception as e:
        logger.error(f"✗ Validation error: {e}")
        return False


def probe_sentinels(urls: list[str], timeout: float = 5.0) -> bool:
    """
    Probe sentinel URLs, expect 30x responses.

    Args:
        urls: List of URLs to probe
        timeout: Request timeout in seconds

    Returns:
        True if all probes succeed, False otherwise

    Logs probe results for each URL.
    """
    logger.info(f"Probing {len(urls)} sentinel URL(s)...")

    all_success = True
    for url in urls:
        try:
            logger.info(f"Probing: {url}")
            response = requests.get(url, timeout=timeout, allow_redirects=False)

            # Expect 30x status codes
            if 300 <= response.status_code < 400:
                logger.info(f"✓ Probe succeeded: {url} → {response.status_code}")
            else:
                logger.warning(
                    f"✗ Probe returned unexpected status: {url} → {response.status_code}"
                )
                all_success = False

        except requests.Timeout:
            logger.error(f"✗ Probe timed out: {url}")
            all_success = False
        except requests.RequestException as e:
            logger.error(f"✗ Probe failed: {url} → {e}")
            all_success = False

    return all_success


def backup_active(out_dir: Path) -> Path | None:
    """
    Backup active config to lastgood.

    Args:
        out_dir: Directory containing config files

    Returns:
        Path to lastgood if backup created, None if no active config exists

    Uses atomic write pattern: temp + fsync + replace.
    """
    active_path = out_dir / "config.active.json"
    lastgood_path = out_dir / "config.lastgood.json"

    if not active_path.exists():
        logger.info("No active config to backup (first deployment)")
        return None

    logger.info(f"Backing up active config: {active_path} → {lastgood_path}")

    # Use atomic write pattern
    temp_path = out_dir / f".config.lastgood.json.tmp.{os.getpid()}"

    try:
        # Read active config
        with active_path.open("rb") as src:
            data = src.read()

        # Write to temp file with fsync
        with temp_path.open("wb") as dst:
            dst.write(data)
            dst.flush()
            os.fsync(dst.fileno())

        # Atomic replace
        temp_path.replace(lastgood_path)

        logger.info(f"✓ Backup created: {lastgood_path}")
        return lastgood_path

    except Exception as e:
        logger.error(f"✗ Backup failed: {e}")
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()
        raise


def reload_caddy(config_path: Path, caddy_bin: str = "caddy") -> bool:
    """
    Reload Caddy with new config.

    Args:
        config_path: Path to config file to load
        caddy_bin: Path to caddy binary

    Returns:
        True if reload succeeds, False otherwise

    Logs stdout/stderr from caddy reload command.
    """
    logger.info(f"Reloading Caddy with config: {config_path}")

    try:
        result = subprocess.run(
            [caddy_bin, "reload", "--config", str(config_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            logger.info(f"✓ Caddy reload succeeded: {config_path}")
            if result.stdout:
                logger.debug(f"Reload stdout: {result.stdout}")
            return True
        else:
            logger.error(f"✗ Caddy reload failed: {config_path}")
            if result.stdout:
                logger.error(f"Reload stdout: {result.stdout}")
            if result.stderr:
                logger.error(f"Reload stderr: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"✗ Caddy reload timed out: {config_path}")
        return False
    except FileNotFoundError:
        logger.error(f"✗ Caddy binary not found: {caddy_bin}")
        return False
    except Exception as e:
        logger.error(f"✗ Reload error: {e}")
        return False


def rollback(out_dir: Path, caddy_bin: str = "caddy") -> bool:
    """
    Rollback to lastgood config.

    Args:
        out_dir: Directory containing config files
        caddy_bin: Path to caddy binary

    Returns:
        True if rollback succeeds, False otherwise

    Raises:
        RollbackError: If lastgood.json doesn't exist or rollback fails
    """
    lastgood_path = out_dir / "config.lastgood.json"

    if not lastgood_path.exists():
        msg = f"✗ Cannot rollback: {lastgood_path} does not exist"
        logger.critical(msg)
        raise RollbackError(msg)

    logger.warning(f"!!! ROLLBACK: Restoring lastgood config: {lastgood_path}")

    success = reload_caddy(lastgood_path, caddy_bin)

    if success:
        logger.info(f"✓ Rollback succeeded: restored {lastgood_path}")
        return True
    else:
        msg = f"✗ Rollback failed: could not reload {lastgood_path}"
        logger.critical(msg)
        logger.critical("!!! MANUAL INTERVENTION REQUIRED !!!")
        raise RollbackError(msg)


def promote_config(out_dir: Path) -> Path:
    """
    Atomically promote next → active.

    Args:
        out_dir: Directory containing config files

    Returns:
        Path to active config

    Raises:
        FileNotFoundError: If config.next.json doesn't exist
        OSError: If promotion fails

    Uses atomic write pattern: temp + fsync + replace.
    """
    next_path = out_dir / "config.next.json"
    active_path = out_dir / "config.active.json"

    if not next_path.exists():
        raise FileNotFoundError(f"Cannot promote: {next_path} does not exist")

    logger.info(f"Promoting config: {next_path} → {active_path}")

    # Use atomic write pattern
    temp_path = out_dir / f".config.active.json.tmp.{os.getpid()}"

    try:
        # Read next config
        with next_path.open("rb") as src:
            data = src.read()

        # Write to temp file with fsync
        with temp_path.open("wb") as dst:
            dst.write(data)
            dst.flush()
            os.fsync(dst.fileno())

        # Atomic replace
        temp_path.replace(active_path)

        logger.info(f"✓ Promotion complete: {active_path}")
        return active_path

    except Exception as e:
        logger.error(f"✗ Promotion failed: {e}")
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()
        raise


def compile_and_promote(yaml_path: Path, opts: PromoteOptions) -> Path:
    """
    Main entry point: compile YAML and promote with double-buffer.

    This function implements the full promotion algorithm:
    1. Load config with lacuna_schema.load_config()
    2. Compile with lacuna_compiler.write_candidate() → writes config.next.json
    3. Validate with caddy validate
    4. Optional: Probe sentinel URLs
    5. Backup active → lastgood
    6. Reload Caddy with next
    7. On failure: rollback to lastgood
    8. On success: promote next → active

    Args:
        yaml_path: Path to YAML config file
        opts: Promotion options

    Returns:
        Path to active config on success

    Raises:
        ValidationError: If validation fails
        ProbeError: If sentinel probes fail
        ReloadError: If Caddy reload fails and rollback succeeds
        RollbackError: If rollback fails (critical - manual intervention required)
        OSError: If file operations fail

    Example:
        >>> from pathlib import Path
        >>> from lacuna_promote import PromoteOptions, compile_and_promote
        >>> opts = PromoteOptions(out_dir=Path("./vol/config"))
        >>> active_path = compile_and_promote(Path("config.yaml"), opts)
        >>> print(f"Promoted to {active_path}")
    """
    start_time = time.time()
    logger.info("=" * 80)
    logger.info("Starting config promotion")
    logger.info(f"YAML config: {yaml_path}")
    logger.info(f"Output dir: {opts.out_dir}")
    logger.info(f"Caddy binary: {opts.caddy_bin}")
    logger.info(f"Validate only: {opts.validate_only}")
    logger.info("=" * 80)

    try:
        # Step 1: Load and validate YAML
        logger.info("Step 1/8: Loading YAML config")
        config = load_config(yaml_path)
        total_rules = sum(len(host.rules) for host in config.hosts)
        logger.info(f"✓ Loaded: {len(config.hosts)} hosts, {total_rules} rules")

        # Step 2: Compile to Caddy JSON and write next
        logger.info("Step 2/8: Compiling to Caddy JSON")
        next_path = write_candidate(config, opts.out_dir)
        logger.info(f"✓ Compiled and written to: {next_path}")

        # Step 3: Validate with Caddy
        logger.info("Step 3/8: Validating with Caddy")
        if not validate_config(next_path, opts.caddy_bin):
            raise ValidationError(f"Caddy validation failed for {next_path}")
        logger.info("✓ Caddy validation passed")

        # If validate-only mode, stop here
        if opts.validate_only:
            logger.info("Validate-only mode: stopping here")
            elapsed = time.time() - start_time
            logger.info("=" * 80)
            logger.info(f"✓ Validation complete in {elapsed:.2f}s")
            logger.info("=" * 80)
            return next_path

        # Step 4: Optional sentinel probes
        if opts.sentinel_urls:
            logger.info(f"Step 4/8: Probing {len(opts.sentinel_urls)} sentinel URL(s)")
            if not probe_sentinels(opts.sentinel_urls, opts.probe_timeout):
                raise ProbeError("Sentinel probe(s) failed")
            logger.info("✓ All sentinel probes passed")
        else:
            logger.info("Step 4/8: No sentinel URLs configured (skipping)")

        # Step 5: Backup active config
        logger.info("Step 5/8: Backing up active config")
        lastgood_path = backup_active(opts.out_dir)
        if lastgood_path:
            logger.info(f"✓ Backup created: {lastgood_path}")
        else:
            logger.info("✓ No active config to backup (first deployment)")

        # Step 6: Reload Caddy with next
        logger.info("Step 6/8: Reloading Caddy with new config")
        reload_success = reload_caddy(next_path, opts.caddy_bin)

        if not reload_success:
            # Step 7: Rollback on failure
            logger.error("✗ Caddy reload failed!")
            if lastgood_path:
                logger.warning("Step 7/8: Attempting rollback to lastgood")
                try:
                    rollback(opts.out_dir, opts.caddy_bin)
                    logger.info("✓ Rollback succeeded")
                except RollbackError:
                    logger.critical("✗ ROLLBACK FAILED - MANUAL INTERVENTION REQUIRED")
                    raise
                raise ReloadError(f"Caddy reload failed, rolled back to {lastgood_path}")
            else:
                raise ReloadError("Caddy reload failed and no lastgood config to rollback to")

        logger.info("✓ Caddy reload succeeded")

        # Step 7: Promote next → active (on reload success)
        logger.info("Step 7/8: Promoting next → active")
        active_path = promote_config(opts.out_dir)
        logger.info(f"✓ Promoted to: {active_path}")

        # Step 8: Done
        elapsed = time.time() - start_time
        logger.info("Step 8/8: Complete")
        logger.info("=" * 80)
        logger.info(f"✓ Config promotion successful in {elapsed:.2f}s")
        logger.info(f"✓ Active config: {active_path}")
        logger.info("=" * 80)

        return active_path

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("=" * 80)
        logger.error(f"✗ Config promotion failed after {elapsed:.2f}s")
        logger.error(f"✗ Error: {e}")
        logger.error("=" * 80)
        raise
