"""Core compilation logic for converting Lacuna Config to Caddy JSON."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from typing import Any

from lacuna_schema.api import Config, sort_rules
from lacuna_schema.models import Host, Rule


def _get_git_hash() -> str:
    """Get current git commit hash, or 'unknown' if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "unknown"


def _compute_content_sha256(apps_block: dict[str, Any]) -> str:
    """Compute SHA256 of the apps block for change detection."""
    content = json.dumps(apps_block, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _build_exact_match_handler(rule: Rule, hsts_enabled: bool) -> list[dict[str, Any]]:
    """
    Build handler for exact path match.

    Returns a list of handlers:
    1. Headers handler (X-Lacuna-Rule + HSTS if enabled)
    2. Static response with Location and status code
    """
    handlers: list[dict[str, Any]] = []

    # Headers handler
    response_headers: dict[str, list[str]] = {
        "X-Lacuna-Rule": [rule.id],
    }

    if hsts_enabled:
        response_headers["Strict-Transport-Security"] = ["max-age=31536000; includeSubDomains; preload"]

    handlers.append(
        {
            "handler": "headers",
            "response": {
                "set": response_headers,
            },
        }
    )

    # Static response handler
    handlers.append(
        {
            "handler": "static_response",
            "headers": {
                "Location": [rule.to],
            },
            "status_code": rule.status,
        }
    )

    return handlers


def _build_prefix_match_handler(rule: Rule, hsts_enabled: bool, keep_query: bool) -> list[dict[str, Any]]:
    """
    Build handler for prefix path match.

    For prefix matches, we need:
    1. Path matcher with wildcard (e.g., "/blog*")
    2. Subroute handler with:
       - Rewrite handler (strip_path_prefix)
       - Headers handler (X-Lacuna-Rule + HSTS)
       - Static response with dynamic Location
    3. Vars handler for redirect_uri construction

    The Location header uses Caddy placeholders to preserve the path.
    """
    handlers: list[dict[str, Any]] = []

    # Build the Location header value
    # Strip trailing slash from 'to' and construct dynamic redirect
    to_base = rule.to.rstrip("/")

    # Build location with path preservation
    # For prefix matches, the path after stripping prefix is in {http.request.uri.path}
    if keep_query:
        # Use vars handler approach for complex redirect URI construction
        location_value = "{http.vars.redirect_uri}"
    else:
        # Direct construction without query
        location_value = f"{to_base}{{http.request.uri.path}}"

    # Headers for the response
    response_headers: dict[str, list[str]] = {
        "X-Lacuna-Rule": [rule.id],
    }

    if hsts_enabled:
        response_headers["Strict-Transport-Security"] = ["max-age=31536000; includeSubDomains; preload"]

    # Build subroute handler
    subroute_handlers: list[dict[str, Any]] = [
        {
            "handler": "rewrite",
            "strip_path_prefix": rule.from_,
        },
        {
            "handler": "headers",
            "response": {
                "set": response_headers,
            },
        },
        {
            "handler": "static_response",
            "headers": {
                "Location": [location_value],
            },
            "status_code": rule.status,
        },
    ]

    handlers.append(
        {
            "handler": "subroute",
            "routes": [
                {
                    "handle": subroute_handlers,
                }
            ],
        }
    )

    # If keep_query is true, add vars handler for redirect_uri
    if keep_query:
        handlers.append(
            {
                "handler": "vars",
                "redirect_uri": f"{to_base}{{http.request.uri.path}}{{http.request.uri.query}}",
            }
        )

    return handlers


def _build_host_route(host: Host, defaults_hsts: bool, defaults_keep_query: bool) -> dict[str, Any]:
    """
    Build a Caddy route for a single host.

    Returns a route with:
    - Host matcher
    - Subroute handler containing all rules
    - Terminal flag to prevent fallthrough
    """
    # Determine host-level HSTS setting
    hsts_enabled = host.hsts if host.hsts is not None else defaults_hsts

    # Sort rules for optimal evaluation order
    sorted_host = sort_rules(host)

    # Build rule routes (subroutes within the host's subroute)
    rule_routes: list[dict[str, Any]] = []

    for rule in sorted_host.rules:
        # Determine keep_query for this rule
        keep_query = rule.keep_query if rule.keep_query is not None else defaults_keep_query

        # Build path matcher
        if rule.match == "exact":
            path_pattern = rule.from_
            handlers = _build_exact_match_handler(rule, hsts_enabled)
        else:  # prefix
            path_pattern = f"{rule.from_}*"
            handlers = _build_prefix_match_handler(rule, hsts_enabled, keep_query)

        rule_route: dict[str, Any] = {
            "match": [{"path": [path_pattern]}],
            "handle": handlers,
        }

        rule_routes.append(rule_route)

    # Build the host route
    host_route: dict[str, Any] = {
        "match": [{"host": [host.host]}],
        "handle": [
            {
                "handler": "subroute",
                "routes": rule_routes,
            }
        ],
        "terminal": True,
    }

    return host_route


def _build_http_redirect_server() -> dict[str, Any]:
    """
    Build the HTTP (port 80) server that redirects all traffic to HTTPS.

    Returns a server config with a single route that issues a 308 redirect.
    """
    return {
        "listen": [":80"],
        "routes": [
            {
                "handle": [
                    {
                        "handler": "static_response",
                        "headers": {"Location": ["https://{http.request.host}{http.request.uri}"]},
                        "status_code": 308,
                    }
                ]
            }
        ],
    }


def _build_https_server(config: Config) -> dict[str, Any]:
    """
    Build the HTTPS (port 443) server with SNI routing per host.

    Returns a server config with routes for each host.
    """
    routes: list[dict[str, Any]] = []

    for host in config.hosts:
        host_route = _build_host_route(
            host,
            config.defaults.hsts,
            config.defaults.keep_query,
        )
        routes.append(host_route)

    return {
        "listen": [":443"],
        "routes": routes,
    }


def compile_to_caddy(cfg: Config) -> dict[str, Any]:
    """
    Compile a validated Lacuna Config to Caddy JSON.

    This generates a deterministic Caddy configuration with:
    - HTTP→HTTPS redirect server (port 80)
    - HTTPS server with SNI routing (port 443)
    - X-Lacuna-Rule headers on all redirects
    - HSTS headers per host policy
    - Metadata block with build info

    Args:
        cfg: Validated Config object from lacuna_schema

    Returns:
        Caddy JSON configuration as a dict

    Example:
        >>> from lacuna_schema import load_config
        >>> from pathlib import Path
        >>> config = load_config(Path("domainlist.yaml"))
        >>> caddy_json = compile_to_caddy(config)
        >>> print(caddy_json["apps"]["http"]["servers"].keys())
        dict_keys(['http_redirect', 'https'])
    """
    # Build the apps block
    apps_block = {
        "http": {
            "servers": {
                "http_redirect": _build_http_redirect_server(),
                "https": _build_https_server(cfg),
            }
        }
    }

    # Build metadata
    metadata = {
        "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git": _get_git_hash(),
        "content_sha256": _compute_content_sha256(apps_block),
    }

    # Assemble final config
    caddy_config = {
        "_meta": metadata,
        "apps": apps_block,
    }

    return caddy_config
