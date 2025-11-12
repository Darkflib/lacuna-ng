"""Unit tests for lacuna_compiler core compilation logic."""

import json
from typing import Any, Dict

import pytest
from lacuna_schema.models import Config, Defaults, Host, Rule

from lacuna_compiler.compiler import compile_to_caddy


def test_basic_structure() -> None:
    """Test that compiled output has correct basic structure."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                rules=[
                    Rule(
                        id="home",
                        match="exact",
                        **{"from": "/", "to": "https://www.example.com/", "status": 308},
                    )
                ],
            )
        ],
    )

    result = compile_to_caddy(config)

    # Check top-level structure
    assert "_meta" in result
    assert "apps" in result
    assert "http" in result["apps"]
    assert "servers" in result["apps"]["http"]

    # Check server names
    servers = result["apps"]["http"]["servers"]
    assert "http_redirect" in servers
    assert "https" in servers


def test_http_redirect_server() -> None:
    """Test HTTP→HTTPS redirect server configuration."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                rules=[
                    Rule(
                        id="test",
                        match="exact",
                        **{"from": "/", "to": "https://target.com/", "status": 308},
                    )
                ],
            )
        ],
    )

    result = compile_to_caddy(config)
    http_server = result["apps"]["http"]["servers"]["http_redirect"]

    # Check listen port
    assert http_server["listen"] == [":80"]

    # Check redirect route
    assert len(http_server["routes"]) == 1
    route = http_server["routes"][0]
    assert len(route["handle"]) == 1

    handler = route["handle"][0]
    assert handler["handler"] == "static_response"
    assert handler["status_code"] == 308
    assert handler["headers"]["Location"] == [
        "https://{http.request.host}{http.request.uri}"
    ]


def test_https_server_listen() -> None:
    """Test HTTPS server listen configuration."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                rules=[
                    Rule(
                        id="test",
                        match="exact",
                        **{"from": "/", "to": "https://target.com/", "status": 308},
                    )
                ],
            )
        ],
    )

    result = compile_to_caddy(config)
    https_server = result["apps"]["http"]["servers"]["https"]

    assert https_server["listen"] == [":443"]


def test_exact_match_rule() -> None:
    """Test exact match rule generation."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                hsts=True,
                rules=[
                    Rule(
                        id="home",
                        match="exact",
                        **{"from": "/about", "to": "https://target.com/about-us", "status": 308},
                    )
                ],
            )
        ],
    )

    result = compile_to_caddy(config)
    routes = result["apps"]["http"]["servers"]["https"]["routes"]

    assert len(routes) == 1
    host_route = routes[0]

    # Check host matcher
    assert host_route["match"][0]["host"] == ["example.com"]
    assert host_route["terminal"] is True

    # Check subroute
    subroute = host_route["handle"][0]
    assert subroute["handler"] == "subroute"

    # Check rule route
    rule_routes = subroute["routes"]
    assert len(rule_routes) == 1

    rule_route = rule_routes[0]
    # Check path matcher (exact - no wildcard)
    assert rule_route["match"][0]["path"] == ["/about"]

    # Check handlers
    handlers = rule_route["handle"]
    assert len(handlers) == 2

    # Headers handler
    headers_handler = handlers[0]
    assert headers_handler["handler"] == "headers"
    assert headers_handler["response"]["set"]["X-Lacuna-Rule"] == ["home"]
    assert "Strict-Transport-Security" in headers_handler["response"]["set"]

    # Static response handler
    response_handler = handlers[1]
    assert response_handler["handler"] == "static_response"
    assert response_handler["headers"]["Location"] == ["https://target.com/about-us"]
    assert response_handler["status_code"] == 308


def test_prefix_match_rule() -> None:
    """Test prefix match rule generation."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                hsts=True,
                rules=[
                    Rule(
                        id="blog",
                        match="prefix",
                        **{"from": "/blog", "to": "https://blog.example.com", "status": 308},
                        keep_query=True,
                    )
                ],
            )
        ],
    )

    result = compile_to_caddy(config)
    routes = result["apps"]["http"]["servers"]["https"]["routes"]
    rule_routes = routes[0]["handle"][0]["routes"]
    rule_route = rule_routes[0]

    # Check path matcher (prefix - has wildcard)
    assert rule_route["match"][0]["path"] == ["/blog*"]

    # Check handlers
    handlers = rule_route["handle"]
    assert len(handlers) == 2

    # Subroute handler
    subroute_handler = handlers[0]
    assert subroute_handler["handler"] == "subroute"

    subroute_routes = subroute_handler["routes"]
    assert len(subroute_routes) == 1

    subroute_handlers = subroute_routes[0]["handle"]

    # Rewrite handler
    rewrite_handler = subroute_handlers[0]
    assert rewrite_handler["handler"] == "rewrite"
    assert rewrite_handler["strip_path_prefix"] == "/blog"

    # Headers handler
    headers_handler = subroute_handlers[1]
    assert headers_handler["handler"] == "headers"
    assert headers_handler["response"]["set"]["X-Lacuna-Rule"] == ["blog"]

    # Static response handler
    response_handler = subroute_handlers[2]
    assert response_handler["handler"] == "static_response"
    assert response_handler["headers"]["Location"] == ["{http.vars.redirect_uri}"]
    assert response_handler["status_code"] == 308

    # Vars handler (for query string handling)
    vars_handler = handlers[1]
    assert vars_handler["handler"] == "vars"
    assert "redirect_uri" in vars_handler
    # Should include both path and query placeholders
    assert "{http.request.uri.path}" in vars_handler["redirect_uri"]
    assert "{http.request.uri.query}" in vars_handler["redirect_uri"]


def test_prefix_without_query() -> None:
    """Test prefix match rule without query preservation."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                rules=[
                    Rule(
                        id="docs",
                        match="prefix",
                        **{"from": "/docs", "to": "https://docs.example.com", "status": 308},
                        keep_query=False,  # Explicitly disable
                    )
                ],
            )
        ],
    )

    result = compile_to_caddy(config)
    routes = result["apps"]["http"]["servers"]["https"]["routes"]
    rule_routes = routes[0]["handle"][0]["routes"]
    rule_route = rule_routes[0]

    handlers = rule_route["handle"]

    # Should have only 1 handler (subroute, no vars)
    assert len(handlers) == 1

    subroute_handler = handlers[0]
    subroute_routes = subroute_handler["routes"]
    response_handler = subroute_routes[0]["handle"][2]

    # Location should NOT use vars, should construct directly
    location = response_handler["headers"]["Location"][0]
    assert "{http.vars.redirect_uri}" not in location
    assert "{http.request.uri.path}" in location
    assert "{http.request.uri.query}" not in location


def test_x_lacuna_rule_header() -> None:
    """Test that X-Lacuna-Rule header is present on all redirects."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=False, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                hsts=False,
                rules=[
                    Rule(
                        id="rule1",
                        match="exact",
                        **{"from": "/one", "to": "https://target.com/1", "status": 301},
                    ),
                    Rule(
                        id="rule2",
                        match="prefix",
                        **{"from": "/two", "to": "https://target.com/2", "status": 302},
                    ),
                ],
            )
        ],
    )

    result = compile_to_caddy(config)
    rule_routes = result["apps"]["http"]["servers"]["https"]["routes"][0]["handle"][0]["routes"]

    # Check exact match rule
    exact_handlers = rule_routes[0]["handle"]
    exact_headers = exact_handlers[0]["response"]["set"]
    assert exact_headers["X-Lacuna-Rule"] == ["rule1"]

    # Check prefix match rule
    prefix_handlers = rule_routes[1]["handle"][0]["routes"][0]["handle"]
    prefix_headers = prefix_handlers[1]["response"]["set"]
    assert prefix_headers["X-Lacuna-Rule"] == ["rule2"]


def test_hsts_header_enabled() -> None:
    """Test HSTS header when enabled."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                hsts=True,
                rules=[
                    Rule(
                        id="test",
                        match="exact",
                        **{"from": "/", "to": "https://target.com/", "status": 308},
                    )
                ],
            )
        ],
    )

    result = compile_to_caddy(config)
    rule_routes = result["apps"]["http"]["servers"]["https"]["routes"][0]["handle"][0]["routes"]

    headers = rule_routes[0]["handle"][0]["response"]["set"]
    assert "Strict-Transport-Security" in headers
    assert headers["Strict-Transport-Security"] == [
        "max-age=31536000; includeSubDomains; preload"
    ]


def test_hsts_header_disabled() -> None:
    """Test HSTS header when disabled."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=False, keep_query=True),
        hosts=[
            Host(
                host="parked.example.com",
                hsts=False,
                rules=[
                    Rule(
                        id="parked",
                        match="exact",
                        **{"from": "/", "to": "https://target.com/", "status": 302},
                    )
                ],
            )
        ],
    )

    result = compile_to_caddy(config)
    rule_routes = result["apps"]["http"]["servers"]["https"]["routes"][0]["handle"][0]["routes"]

    headers = rule_routes[0]["handle"][0]["response"]["set"]
    assert "Strict-Transport-Security" not in headers
    # But X-Lacuna-Rule should still be present
    assert "X-Lacuna-Rule" in headers


def test_hsts_host_override() -> None:
    """Test that host-level HSTS overrides default."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),  # Default is True
        hosts=[
            Host(
                host="parked.example.com",
                hsts=False,  # Override to False
                rules=[
                    Rule(
                        id="test",
                        match="exact",
                        **{"from": "/", "to": "https://target.com/", "status": 302},
                    )
                ],
            )
        ],
    )

    result = compile_to_caddy(config)
    rule_routes = result["apps"]["http"]["servers"]["https"]["routes"][0]["handle"][0]["routes"]

    headers = rule_routes[0]["handle"][0]["response"]["set"]
    # Should NOT have HSTS because host overrides default
    assert "Strict-Transport-Security" not in headers


def test_multiple_hosts() -> None:
    """Test configuration with multiple hosts."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                rules=[
                    Rule(
                        id="home",
                        match="exact",
                        **{"from": "/", "to": "https://target1.com/", "status": 308},
                    )
                ],
            ),
            Host(
                host="other.com",
                rules=[
                    Rule(
                        id="root",
                        match="prefix",
                        **{"from": "/", "to": "https://target2.com", "status": 301},
                    )
                ],
            ),
        ],
    )

    result = compile_to_caddy(config)
    routes = result["apps"]["http"]["servers"]["https"]["routes"]

    # Should have 2 host routes
    assert len(routes) == 2

    # Check first host
    assert routes[0]["match"][0]["host"] == ["example.com"]

    # Check second host
    assert routes[1]["match"][0]["host"] == ["other.com"]


def test_metadata_block() -> None:
    """Test that metadata block is present and has required fields."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                rules=[
                    Rule(
                        id="test",
                        match="exact",
                        **{"from": "/", "to": "https://target.com/", "status": 308},
                    )
                ],
            )
        ],
    )

    result = compile_to_caddy(config)

    assert "_meta" in result
    meta = result["_meta"]

    # Check required fields
    assert "built_at" in meta
    assert "git" in meta
    assert "content_sha256" in meta

    # Check timestamp format (ISO 8601 UTC)
    assert meta["built_at"].endswith("Z")
    assert "T" in meta["built_at"]

    # Check SHA256 is hex string
    assert len(meta["content_sha256"]) == 64
    assert all(c in "0123456789abcdef" for c in meta["content_sha256"])


def test_deterministic_output() -> None:
    """Test that same input produces identical output (deterministic build)."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                rules=[
                    Rule(
                        id="home",
                        match="exact",
                        **{"from": "/", "to": "https://target.com/", "status": 308},
                    ),
                    Rule(
                        id="blog",
                        match="prefix",
                        **{"from": "/blog", "to": "https://blog.target.com", "status": 308},
                    ),
                ],
            )
        ],
    )

    result1 = compile_to_caddy(config)
    result2 = compile_to_caddy(config)

    # Remove timestamps which will differ
    del result1["_meta"]["built_at"]
    del result2["_meta"]["built_at"]

    # Everything else should be identical
    assert json.dumps(result1, sort_keys=True) == json.dumps(result2, sort_keys=True)


def test_status_codes() -> None:
    """Test that different status codes are preserved."""
    status_codes = [301, 302, 303, 307, 308]

    for status in status_codes:
        config = Config(
            version=1,
            defaults=Defaults(hsts=False, keep_query=True),
            hosts=[
                Host(
                    host="example.com",
                    rules=[
                        Rule(
                            id=f"rule{status}",
                            match="exact",
                            **{"from": "/", "to": "https://target.com/", "status": status},
                        )
                    ],
                )
            ],
        )

        result = compile_to_caddy(config)
        rule_routes = result["apps"]["http"]["servers"]["https"]["routes"][0]["handle"][0]["routes"]
        response_handler = rule_routes[0]["handle"][1]

        assert response_handler["status_code"] == status


def test_path_trailing_slash_handling() -> None:
    """Test that trailing slashes in 'to' URLs are handled correctly for prefix matches."""
    # With trailing slash
    config1 = Config(
        version=1,
        defaults=Defaults(hsts=False, keep_query=False),
        hosts=[
            Host(
                host="example.com",
                rules=[
                    Rule(
                        id="test",
                        match="prefix",
                        **{"from": "/api", "to": "https://api.example.com/", "status": 308},
                        keep_query=False,
                    )
                ],
            )
        ],
    )

    result1 = compile_to_caddy(config1)
    rule_routes1 = result1["apps"]["http"]["servers"]["https"]["routes"][0]["handle"][0]["routes"]
    handlers1 = rule_routes1[0]["handle"]
    response1 = handlers1[0]["routes"][0]["handle"][2]
    location1 = response1["headers"]["Location"][0]

    # Should strip trailing slash and add path placeholder
    assert location1 == "https://api.example.com{http.request.uri.path}"

    # Without trailing slash
    config2 = Config(
        version=1,
        defaults=Defaults(hsts=False, keep_query=False),
        hosts=[
            Host(
                host="example.com",
                rules=[
                    Rule(
                        id="test",
                        match="prefix",
                        **{"from": "/api", "to": "https://api.example.com", "status": 308},
                        keep_query=False,
                    )
                ],
            )
        ],
    )

    result2 = compile_to_caddy(config2)
    rule_routes2 = result2["apps"]["http"]["servers"]["https"]["routes"][0]["handle"][0]["routes"]
    handlers2 = rule_routes2[0]["handle"]
    response2 = handlers2[0]["routes"][0]["handle"][2]
    location2 = response2["headers"]["Location"][0]

    # Should preserve no trailing slash and add path placeholder
    assert location2 == "https://api.example.com{http.request.uri.path}"


def test_terminal_flag() -> None:
    """Test that host routes have terminal flag set."""
    config = Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                rules=[
                    Rule(
                        id="test",
                        match="exact",
                        **{"from": "/", "to": "https://target.com/", "status": 308},
                    )
                ],
            )
        ],
    )

    result = compile_to_caddy(config)
    routes = result["apps"]["http"]["servers"]["https"]["routes"]

    for route in routes:
        assert route["terminal"] is True
