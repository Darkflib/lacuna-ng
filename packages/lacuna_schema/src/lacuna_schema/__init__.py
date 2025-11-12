"""Lacuna v2 Schema - YAML validation and type models for redirect configurations.

This package provides Pydantic v2 models for validating Lacuna redirect configurations,
along with semantic validators and utilities for safe configuration loading.

Public API:
    Models:
        - Config: Top-level configuration
        - Host: Host with redirect rules
        - Rule: Individual redirect rule
        - Defaults: Global default settings

    Functions:
        - load_config(path): Load and validate YAML config
        - sort_rules(host): Sort rules by match type and path length

Example:
    >>> from pathlib import Path
    >>> from lacuna_schema import load_config, sort_rules
    >>>
    >>> # Load and validate a config file
    >>> config = load_config(Path("domainlist.yaml"))
    >>>
    >>> # Sort rules for optimal evaluation order
    >>> for host in config.hosts:
    ...     sorted_host = sort_rules(host)
    ...     print(f"{sorted_host.host}: {len(sorted_host.rules)} rules")
"""

__version__ = "2.0.0-dev"

# Public API exports
from .api import load_config, sort_rules
from .models import Config, Defaults, Host, Rule

__all__ = [
    # Version
    "__version__",
    # Models
    "Config",
    "Defaults",
    "Host",
    "Rule",
    # API functions
    "load_config",
    "sort_rules",
]
