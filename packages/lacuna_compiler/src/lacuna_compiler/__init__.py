"""Lacuna v2 Compiler - YAML to Caddy JSON compilation.

This package compiles validated Lacuna YAML configurations into Caddy JSON
format with proper redirect handling, headers, and HSTS support.

Public API:
    compile_to_caddy(cfg): Compile Config to Caddy JSON dict
    write_candidate(cfg, out_dir): Write config.next.json

CLI:
    lacuna-compiler <yaml_path> --out-dir <dir> [--validate-only]

Example:
    >>> from pathlib import Path
    >>> from lacuna_schema import load_config
    >>> from lacuna_compiler import compile_to_caddy, write_candidate
    >>>
    >>> # Load config
    >>> config = load_config(Path("domainlist.yaml"))
    >>>
    >>> # Compile to Caddy JSON
    >>> caddy_json = compile_to_caddy(config)
    >>> print(caddy_json.keys())
    dict_keys(['_meta', 'apps'])
    >>>
    >>> # Write to file
    >>> output_path = write_candidate(config, Path("./vol/config"))
    >>> print(output_path)
    ./vol/config/config.next.json
"""

__version__ = "2.0.0-dev"

from .api import compile_to_caddy, write_candidate

__all__ = [
    "__version__",
    "compile_to_caddy",
    "write_candidate",
]
