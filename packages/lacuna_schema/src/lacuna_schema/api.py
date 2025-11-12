"""Public API for loading and manipulating Lacuna v2 configurations."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import Config, Host
from .validators import sort_host_rules


def load_config(path: Path) -> Config:
    """
    Load and validate a YAML configuration file.

    Args:
        path: Path to YAML configuration file

    Returns:
        Validated Config object

    Raises:
        FileNotFoundError: If the config file doesn't exist
        yaml.YAMLError: If the YAML is malformed
        ValidationError: If the config doesn't match the schema or fails validation

    Example:
        >>> from pathlib import Path
        >>> config = load_config(Path("domainlist.yaml"))
        >>> print(f"Loaded {len(config.hosts)} hosts")
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        try:
            data: dict[str, Any] = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Failed to parse YAML from {path}: {e}") from e

    if not isinstance(data, dict):
        raise ValidationError.from_exception_data(
            "config",
            [
                {
                    "type": "value_error",
                    "loc": (),
                    "msg": "Config file must contain a YAML mapping (dict), not a list or scalar",
                    "input": data,
                }
            ],
        )

    try:
        config = Config.model_validate(data)
    except ValidationError:
        # Re-raise with preserved error context
        raise

    return config


def sort_rules(host: Host) -> Host:
    """
    Sort rules in a host by match type and path length.

    Sorting order:
    1. Exact match rules (longest path first)
    2. Prefix match rules (longest path first)

    This ensures more specific rules are evaluated before more general ones,
    which is important for correct routing behavior.

    Args:
        host: Host with rules to sort

    Returns:
        New Host instance with sorted rules (original host is not modified)

    Example:
        >>> from lacuna_schema.models import Host, Rule
        >>> host = Host(
        ...     host="example.com",
        ...     rules=[
        ...         Rule(id="r1", match="prefix", **{"from": "/", "to": "https://a.com", "status": 301}),
        ...         Rule(id="r2", match="exact", **{"from": "/about", "to": "https://b.com", "status": 301}),
        ...     ]
        ... )
        >>> sorted_host = sort_rules(host)
        >>> print(sorted_host.rules[0].match)  # "exact" comes first
        exact
    """
    return sort_host_rules(host)
