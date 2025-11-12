"""
lacuna_promote - Double-buffer config promotion for Lacuna v2.

This package provides safe config promotion with validation, reload, and rollback:

- Atomic file operations (temp + fsync + os.replace)
- Caddy validation before promotion
- Optional health probes
- Automatic rollback on failure
- Clear logging at each step

Example:
    >>> from pathlib import Path
    >>> from lacuna_promote import PromoteOptions, compile_and_promote
    >>> opts = PromoteOptions(out_dir=Path("./vol/config"))
    >>> active_path = compile_and_promote(Path("config.yaml"), opts)
    >>> print(f"Promoted to {active_path}")
"""

from lacuna_promote.api import (
    ProbeError,
    PromoteOptions,
    ReloadError,
    RollbackError,
    ValidationError,
    compile_and_promote,
    rollback,
    validate_config,
)

__version__ = "2.0.0-dev"

__all__ = [
    "PromoteOptions",
    "compile_and_promote",
    "validate_config",
    "rollback",
    "ValidationError",
    "ProbeError",
    "ReloadError",
    "RollbackError",
]
