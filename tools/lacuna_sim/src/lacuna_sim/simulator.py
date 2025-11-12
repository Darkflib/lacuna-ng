"""Simulator for evaluating Lacuna v2 redirect rules without running Caddy.

This module provides a dry-run simulator that evaluates redirect rules to:
- Test which rule matches for a given request
- Generate coverage reports showing dead rules
- Validate expected redirect behavior without deploying to Caddy

The matching algorithm mirrors Caddy's routing logic to ensure accuracy.
"""

from dataclasses import dataclass
from pathlib import Path

from lacuna_schema import Config, Host, load_config, sort_rules


@dataclass(frozen=True)
class Request:
    """A simulated HTTP request."""

    host: str
    path: str
    query: str = ""

    def __str__(self) -> str:
        """Format request as host+path[+query]."""
        if self.query:
            return f"{self.host} {self.path} {self.query}"
        return f"{self.host} {self.path}"


@dataclass(frozen=True)
class MatchResult:
    """Result of matching a request against config rules."""

    request: Request
    rule_id: str | None
    status: int | None
    location: str | None
    matched: bool

    @property
    def rule_display(self) -> str:
        """Display rule ID or '(no match)' for tables."""
        return self.rule_id if self.rule_id else "(no match)"

    @property
    def status_display(self) -> str:
        """Display status or '-' for tables."""
        return str(self.status) if self.status else "-"

    @property
    def location_display(self) -> str:
        """Display location or '-' for tables."""
        return self.location if self.location else "-"


@dataclass(frozen=True)
class CoverageReport:
    """Coverage report showing which rules were matched."""

    total_rules: int
    matched_rules: set[str]
    dead_rules: set[str]
    coverage_percent: float

    @property
    def all_matched(self) -> bool:
        """True if all rules were matched (100% coverage)."""
        return len(self.dead_rules) == 0


def match_request(cfg: Config, req: Request) -> MatchResult:
    """
    Match a single request against config rules.

    Algorithm (mirrors Caddy routing):
    1. Find host matching req.host
    2. Sort rules (exact first, then prefix; longest-path first within each)
    3. Iterate through rules in order:
       - Exact: path must equal rule.from exactly
       - Prefix: path must start with rule.from
    4. Build Location header:
       - Exact: use rule.to as-is
       - Prefix: append path remainder to rule.to
       - If keep_query=true and query exists: append ?{query}

    Args:
        cfg: Validated Lacuna config
        req: Request to match

    Returns:
        MatchResult with matched rule details or no-match result
    """
    # Find matching host
    host_config: Host | None = None
    for h in cfg.hosts:
        if h.host == req.host:
            host_config = h
            break

    if not host_config:
        # No host matched
        return MatchResult(
            request=req,
            rule_id=None,
            status=None,
            location=None,
            matched=False,
        )

    # Sort rules for correct evaluation order
    sorted_host = sort_rules(host_config)

    # Iterate through rules in sorted order
    for rule in sorted_host.rules:
        matched = False
        location = ""

        if rule.match == "exact":
            # Exact match: path must match exactly
            if req.path == rule.from_:
                matched = True
                # For exact match, use rule.to as-is
                location = rule.to

        elif rule.match == "prefix":
            # Prefix match: path must start with rule.from
            if req.path.startswith(rule.from_):
                matched = True
                # For prefix match, append remainder to rule.to
                remainder = req.path[len(rule.from_) :]

                # Build location: rule.to + remainder
                # Strip trailing slash from rule.to, strip leading slash from remainder
                base = rule.to.rstrip("/")
                if remainder:
                    remainder_clean = remainder.lstrip("/")
                    if remainder_clean:
                        location = f"{base}/{remainder_clean}"
                    else:
                        # Remainder was just slashes (e.g., "/"), preserve trailing slash
                        location = f"{base}/"
                else:
                    location = base

        if matched:
            # Determine if we should keep query string
            keep_query = rule.keep_query
            if keep_query is None:
                # Use default from config
                keep_query = cfg.defaults.keep_query

            # Append query string if keep_query=true and query exists
            if keep_query and req.query:
                location = f"{location}?{req.query}"

            return MatchResult(
                request=req,
                rule_id=rule.id,
                status=rule.status,
                location=location,
                matched=True,
            )

    # No rule matched
    return MatchResult(
        request=req,
        rule_id=None,
        status=None,
        location=None,
        matched=False,
    )


def simulate_batch(cfg: Config, requests: list[Request]) -> list[MatchResult]:
    """
    Simulate a batch of requests against the config.

    Args:
        cfg: Validated Lacuna config
        requests: List of requests to simulate

    Returns:
        List of match results in same order as input requests
    """
    results = []
    for req in requests:
        result = match_request(cfg, req)
        results.append(result)
    return results


def generate_coverage_report(cfg: Config, results: list[MatchResult]) -> CoverageReport:
    """
    Generate coverage report showing which rules were matched.

    Args:
        cfg: Validated Lacuna config
        results: List of match results from simulate_batch

    Returns:
        CoverageReport with coverage statistics and dead rules
    """
    # Collect all rule IDs from config
    all_rule_ids: set[str] = set()
    for host in cfg.hosts:
        for rule in host.rules:
            all_rule_ids.add(rule.id)

    # Collect matched rule IDs from results
    matched_rule_ids: set[str] = set()
    for result in results:
        if result.matched and result.rule_id:
            matched_rule_ids.add(result.rule_id)

    # Calculate dead rules
    dead_rule_ids = all_rule_ids - matched_rule_ids

    # Calculate coverage percentage
    total_rules = len(all_rule_ids)
    if total_rules > 0:
        coverage_percent = (len(matched_rule_ids) / total_rules) * 100.0
    else:
        coverage_percent = 0.0

    return CoverageReport(
        total_rules=total_rules,
        matched_rules=matched_rule_ids,
        dead_rules=dead_rule_ids,
        coverage_percent=coverage_percent,
    )


def parse_cases_file(path: Path) -> list[Request]:
    """
    Parse test cases file into Request objects.

    File format:
        # Comments start with #
        HOST PATH [QUERY]

    Example:
        # Test homepage
        prod.example.com /
        prod.example.com /blog/post-1 page=2
        old.example.com /anything

    Args:
        path: Path to cases.txt file

    Returns:
        List of Request objects

    Raises:
        FileNotFoundError: If cases file doesn't exist
        ValueError: If a line has invalid format
    """
    if not path.exists():
        raise FileNotFoundError(f"Cases file not found: {path}")

    requests: list[Request] = []

    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            # Strip whitespace
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Parse: HOST PATH [QUERY]
            parts = line.split(None, 2)  # Split on whitespace, max 3 parts

            if len(parts) < 2:
                raise ValueError(
                    f"Invalid format at line {line_num}: '{line}'\n"
                    f"Expected: HOST PATH [QUERY]"
                )

            host = parts[0]
            req_path = parts[1]
            query = parts[2] if len(parts) == 3 else ""

            requests.append(Request(host=host, path=req_path, query=query))

    return requests


def load_config_from_yaml(path: Path) -> Config:
    """
    Load config from YAML file.

    Args:
        path: Path to YAML config file

    Returns:
        Validated Config object

    Raises:
        FileNotFoundError: If YAML file doesn't exist
        ValidationError: If config is invalid
    """
    return load_config(path)
