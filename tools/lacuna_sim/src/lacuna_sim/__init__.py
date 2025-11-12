"""Lacuna v2 Simulator - Dry-run testing for redirect configurations.

This package provides a simulator for testing Lacuna redirect configs without
running Caddy. It evaluates redirect rules to find dead rules, verify expected
behavior, and generate coverage reports.

Public API:
    Simulator functions:
        - match_request: Match a single request against config
        - simulate_batch: Simulate multiple requests
        - generate_coverage_report: Generate coverage statistics
        - parse_cases_file: Parse test cases from file
        - load_config_from_yaml: Load config from YAML

    Data classes:
        - Request: HTTP request (host, path, query)
        - MatchResult: Result of matching a request
        - CoverageReport: Coverage statistics and dead rules

    CLI:
        Use the 'lacuna-sim' command installed by this package

Example:
    >>> from pathlib import Path
    >>> from lacuna_sim import load_config_from_yaml, parse_cases_file, simulate_batch
    >>>
    >>> # Load config and test cases
    >>> cfg = load_config_from_yaml(Path("domainlist.yaml"))
    >>> requests = parse_cases_file(Path("cases.txt"))
    >>>
    >>> # Simulate
    >>> results = simulate_batch(cfg, requests)
    >>> for result in results:
    ...     print(f"{result.request} -> {result.location}")
"""

__version__ = "2.0.0-dev"

# Public API exports
from .simulator import (
    CoverageReport,
    MatchResult,
    Request,
    generate_coverage_report,
    load_config_from_yaml,
    match_request,
    parse_cases_file,
    simulate_batch,
)

__all__ = [
    # Version
    "__version__",
    # Data classes
    "Request",
    "MatchResult",
    "CoverageReport",
    # Functions
    "match_request",
    "simulate_batch",
    "generate_coverage_report",
    "parse_cases_file",
    "load_config_from_yaml",
]
