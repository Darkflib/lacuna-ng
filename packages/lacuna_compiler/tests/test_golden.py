"""Golden file tests for deterministic output validation."""

import json
from pathlib import Path

import pytest
from lacuna_schema.api import load_config

from lacuna_compiler.compiler import compile_to_caddy


@pytest.fixture
def example_yaml_path() -> Path:
    """Path to the example YAML file."""
    return Path(__file__).parent.parent.parent.parent / "examples" / "domainlist.yaml"


@pytest.fixture
def golden_json_path() -> Path:
    """Path to the golden JSON file."""
    return Path(__file__).parent / "golden" / "domainlist.json"


def test_golden_file_match(example_yaml_path: Path, golden_json_path: Path) -> None:
    """
    Test that compiling domainlist.yaml produces output matching the golden file.

    This is the main golden file test - it ensures deterministic output by comparing
    the compiled result against a known-good reference output.
    """
    # Load and compile the example YAML
    config = load_config(example_yaml_path)
    compiled = compile_to_caddy(config)

    # Load the golden file
    with golden_json_path.open("r") as f:
        golden = json.load(f)

    # Normalize metadata fields that vary between runs
    # Keep only content_sha256 as it should be stable
    compiled_meta = compiled.pop("_meta")
    golden_meta = golden.pop("_meta")

    # Content SHA should match (since apps block should be identical)
    assert compiled_meta["content_sha256"] == golden_meta["content_sha256"], \
        "Content SHA256 mismatch - apps block has changed"

    # Compare the apps block (deterministic)
    # Use JSON serialization for comparison to ensure stable ordering
    compiled_json = json.dumps(compiled, sort_keys=True, indent=2)
    golden_json = json.dumps(golden, sort_keys=True, indent=2)

    if compiled_json != golden_json:
        # Print diff for debugging
        compiled_lines = compiled_json.split("\n")
        golden_lines = golden_json.split("\n")

        print("\n=== DIFF ===")
        for i, (compiled_line, golden_line) in enumerate(zip(compiled_lines, golden_lines), 1):
            if compiled_line != golden_line:
                print(f"Line {i} differs:")
                print(f"  Golden:   {golden_line}")
                print(f"  Compiled: {compiled_line}")

        # Show length difference if any
        if len(compiled_lines) != len(golden_lines):
            print(f"\nLength mismatch: golden={len(golden_lines)}, compiled={len(compiled_lines)}")

    assert compiled_json == golden_json, \
        "Compiled output does not match golden file - see diff above"


def test_golden_file_exists(golden_json_path: Path) -> None:
    """Verify that the golden file exists."""
    assert golden_json_path.exists(), \
        f"Golden file not found: {golden_json_path}"


def test_golden_file_valid_json(golden_json_path: Path) -> None:
    """Verify that the golden file is valid JSON."""
    with golden_json_path.open("r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            pytest.fail(f"Golden file is not valid JSON: {e}")

    # Basic structure validation
    assert isinstance(data, dict), "Golden file root should be a dict"
    assert "_meta" in data, "Golden file should have _meta block"
    assert "apps" in data, "Golden file should have apps block"


def test_golden_structure_completeness(golden_json_path: Path) -> None:
    """Verify that the golden file has all expected structural elements."""
    with golden_json_path.open("r") as f:
        data = json.load(f)

    # Check metadata
    assert "built_at" in data["_meta"]
    assert "git" in data["_meta"]
    assert "content_sha256" in data["_meta"]

    # Check apps structure
    assert "http" in data["apps"]
    assert "servers" in data["apps"]["http"]

    servers = data["apps"]["http"]["servers"]
    assert "http_redirect" in servers
    assert "https" in servers

    # Check HTTP redirect server
    http_redirect = servers["http_redirect"]
    assert http_redirect["listen"] == [":80"]
    assert "routes" in http_redirect

    # Check HTTPS server
    https_server = servers["https"]
    assert https_server["listen"] == [":443"]
    assert "routes" in https_server

    # Verify we have host routes
    host_routes = https_server["routes"]
    assert len(host_routes) > 0, "Should have at least one host route"

    # Check first host route structure
    first_route = host_routes[0]
    assert "match" in first_route
    assert "host" in first_route["match"][0]
    assert "handle" in first_route
    assert "terminal" in first_route
    assert first_route["terminal"] is True


def test_deterministic_compilation(example_yaml_path: Path) -> None:
    """
    Test that compiling the same input multiple times produces identical output.

    This ensures the compiler is deterministic (apart from timestamp/git fields).
    """
    config = load_config(example_yaml_path)

    # Compile multiple times
    result1 = compile_to_caddy(config)
    result2 = compile_to_caddy(config)
    result3 = compile_to_caddy(config)

    # Remove varying metadata
    for result in [result1, result2, result3]:
        result["_meta"]["built_at"] = "normalized"
        result["_meta"]["git"] = "normalized"

    # All results should be identical
    json1 = json.dumps(result1, sort_keys=True)
    json2 = json.dumps(result2, sort_keys=True)
    json3 = json.dumps(result3, sort_keys=True)

    assert json1 == json2 == json3, \
        "Compiler is not deterministic - multiple compilations produced different output"


def test_golden_has_all_hosts(golden_json_path: Path, example_yaml_path: Path) -> None:
    """Verify that the golden file includes all hosts from the example YAML."""
    # Load example YAML to get expected host count
    config = load_config(example_yaml_path)
    expected_hosts = {host.host for host in config.hosts}

    # Load golden JSON
    with golden_json_path.open("r") as f:
        data = json.load(f)

    # Extract host names from golden file
    routes = data["apps"]["http"]["servers"]["https"]["routes"]
    golden_hosts = {route["match"][0]["host"][0] for route in routes}

    assert golden_hosts == expected_hosts, \
        f"Host mismatch - expected: {expected_hosts}, got: {golden_hosts}"


def test_golden_has_required_headers(golden_json_path: Path) -> None:
    """Verify that the golden file includes required headers (X-Lacuna-Rule, HSTS where applicable)."""
    with golden_json_path.open("r") as f:
        data = json.load(f)

    routes = data["apps"]["http"]["servers"]["https"]["routes"]

    for host_route in routes:
        host_name = host_route["match"][0]["host"][0]
        rule_routes = host_route["handle"][0]["routes"]

        for rule_route in rule_routes:
            # Navigate to headers handler
            # Structure varies by match type, but all should have headers
            handlers = rule_route["handle"]

            # Find headers in the structure
            found_lacuna_header = False

            def check_handlers(handler_list):
                nonlocal found_lacuna_header
                for handler in handler_list:
                    if handler.get("handler") == "headers":
                        response_headers = handler.get("response", {}).get("set", {})
                        if "X-Lacuna-Rule" in response_headers:
                            found_lacuna_header = True
                    elif handler.get("handler") == "subroute":
                        # Recurse into subroute
                        for subroute in handler.get("routes", []):
                            check_handlers(subroute.get("handle", []))

            check_handlers(handlers)

            assert found_lacuna_header, \
                f"X-Lacuna-Rule header not found in rule for host {host_name}"
