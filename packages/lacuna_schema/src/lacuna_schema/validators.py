"""Semantic validators and sorting utilities for Lacuna v2 configuration."""

import re

from .models import Host, Rule

# Rule ID pattern (already enforced by Pydantic, but available as constant)
RULE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# Allowed URL schemes (security constraint)
ALLOWED_SCHEMES = {"http://", "https://"}

# Forbidden characters in 'to' URL (no templating)
FORBIDDEN_CHARS = {"{", "}", "$"}

# Valid HTTP redirect status codes
VALID_STATUS_CODES = {301, 302, 303, 307, 308}


def validate_rule_id_syntax(rule_id: str) -> bool:
    """
    Validate rule ID syntax.

    Args:
        rule_id: The rule ID to validate

    Returns:
        True if valid, False otherwise

    Rule ID must:
    - Start with lowercase letter or digit
    - Contain only lowercase letters, digits, dots, underscores, hyphens
    """
    return bool(RULE_ID_PATTERN.match(rule_id))


def validate_scheme(url: str) -> bool:
    """
    Validate that URL uses allowed scheme (http or https only).

    Args:
        url: The URL to validate

    Returns:
        True if scheme is allowed, False otherwise

    Security note: Rejects javascript:, data:, file:, etc.
    """
    return any(url.startswith(scheme) for scheme in ALLOWED_SCHEMES)


def validate_no_templating(url: str) -> bool:
    """
    Validate that URL contains no templating characters.

    Args:
        url: The URL to validate

    Returns:
        True if no templating chars found, False otherwise

    Forbidden characters: { } $
    This prevents template injection and keeps the system simple/static.
    """
    return not any(char in url for char in FORBIDDEN_CHARS)


def validate_status_code(status: int) -> bool:
    """
    Validate that status code is a valid HTTP redirect code.

    Args:
        status: The HTTP status code

    Returns:
        True if valid redirect code, False otherwise

    Valid codes: 301, 302, 303, 307, 308
    """
    return status in VALID_STATUS_CODES


def validate_path_starts_with_slash(path: str) -> bool:
    """
    Validate that path starts with forward slash.

    Args:
        path: The path to validate

    Returns:
        True if starts with /, False otherwise
    """
    return path.startswith("/")


def detect_duplicate_ids(rules: list[Rule]) -> list[str]:
    """
    Detect duplicate rule IDs in a list of rules.

    Args:
        rules: List of rules to check

    Returns:
        List of duplicate IDs found (empty if none)
    """
    seen = set()
    duplicates = []

    for rule in rules:
        if rule.id in seen:
            if rule.id not in duplicates:
                duplicates.append(rule.id)
        seen.add(rule.id)

    return sorted(duplicates)


def sort_rules_by_path_length(rules: list[Rule]) -> list[Rule]:
    """
    Sort rules by path length (longest first) within each match type.

    Sorting order:
    1. All exact match rules (longest path first)
    2. All prefix match rules (longest path first)

    This ensures more specific rules are evaluated before more general ones.

    Args:
        rules: List of rules to sort

    Returns:
        New list with sorted rules
    """
    exact_rules = [r for r in rules if r.match == "exact"]
    prefix_rules = [r for r in rules if r.match == "prefix"]

    # Sort each group by path length (longest first)
    exact_sorted = sorted(exact_rules, key=lambda r: len(r.from_), reverse=True)
    prefix_sorted = sorted(prefix_rules, key=lambda r: len(r.from_), reverse=True)

    # Combine: exact first, then prefix
    return exact_sorted + prefix_sorted


def sort_host_rules(host: Host) -> Host:
    """
    Return a new Host with rules sorted by match type and path length.

    Args:
        host: Host with rules to sort

    Returns:
        New Host instance with sorted rules
    """
    sorted_rules = sort_rules_by_path_length(host.rules)
    new_host: Host = host.model_copy(update={"rules": sorted_rules})
    return new_host
