"""Public API for the lacuna_compiler package."""

import json
import os
from pathlib import Path
from typing import Any, Dict

from lacuna_schema.api import Config

from .compiler import compile_to_caddy


def write_candidate(cfg: Config, out_dir: Path) -> Path:
    """
    Write compiled Caddy JSON to config.next.json (candidate configuration).

    This function:
    1. Compiles the config to Caddy JSON
    2. Creates the output directory if needed
    3. Writes to a temporary file with fsync
    4. Atomically replaces config.next.json

    Args:
        cfg: Validated Config object from lacuna_schema
        out_dir: Directory where config.next.json should be written

    Returns:
        Path to the written config.next.json file

    Raises:
        OSError: If directory creation or file writing fails

    Example:
        >>> from lacuna_schema import load_config
        >>> from pathlib import Path
        >>> config = load_config(Path("domainlist.yaml"))
        >>> output_path = write_candidate(config, Path("./vol/config"))
        >>> print(output_path)
        /path/to/vol/config/config.next.json
    """
    # Compile to Caddy JSON
    caddy_json = compile_to_caddy(cfg)

    # Ensure output directory exists
    out_dir.mkdir(parents=True, exist_ok=True)

    # Target file path
    target_path = out_dir / "config.next.json"

    # Write to temporary file first (atomic write pattern)
    temp_path = out_dir / f".config.next.json.tmp.{os.getpid()}"

    try:
        # Write and fsync
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(caddy_json, f, indent=2, sort_keys=False)
            f.write("\n")  # Trailing newline
            f.flush()
            os.fsync(f.fileno())

        # Atomic replace
        temp_path.replace(target_path)

    except Exception:
        # Clean up temp file on error
        if temp_path.exists():
            temp_path.unlink()
        raise

    return target_path


# Re-export compile_to_caddy for convenience
__all__ = ["compile_to_caddy", "write_candidate"]
