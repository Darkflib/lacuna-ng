"""Tests for validators and sorting utilities."""

from lacuna_schema import Host, Rule, sort_rules
from lacuna_schema.validators import (
    detect_duplicate_ids,
    sort_rules_by_path_length,
    validate_no_templating,
    validate_path_starts_with_slash,
    validate_rule_id_syntax,
    validate_scheme,
    validate_status_code,
)


class TestValidateRuleIdSyntax:
    """Tests for validate_rule_id_syntax function."""

    def test_valid_ids(self) -> None:
        """Test valid rule ID patterns."""
        valid_ids = [
            "simple",
            "with-dash",
            "with_underscore",
            "with.dot",
            "a1b2c3",
            "0starts-with-digit",
            "complex_rule-id.v2",
            "a",
            "0",
        ]
        for rule_id in valid_ids:
            assert validate_rule_id_syntax(rule_id), f"Expected {rule_id} to be valid"

    def test_invalid_ids(self) -> None:
        """Test invalid rule ID patterns."""
        invalid_ids = [
            "Has-Capital",
            "has space",
            "has@symbol",
            "-starts-with-dash",
            ".starts-with-dot",
            "_starts-with-underscore",
            "has/slash",
            "",
            "has#hash",
            "has!exclamation",
        ]
        for rule_id in invalid_ids:
            assert not validate_rule_id_syntax(rule_id), f"Expected {rule_id} to be invalid"


class TestValidateScheme:
    """Tests for validate_scheme function."""

    def test_http_allowed(self) -> None:
        """Test that http:// is allowed."""
        assert validate_scheme("http://example.com")
        assert validate_scheme("http://example.com/path?query=1")

    def test_https_allowed(self) -> None:
        """Test that https:// is allowed."""
        assert validate_scheme("https://example.com")
        assert validate_scheme("https://example.com/path?query=1")

    def test_javascript_rejected(self) -> None:
        """Test that javascript: is rejected."""
        assert not validate_scheme("javascript:alert('XSS')")

    def test_data_rejected(self) -> None:
        """Test that data: is rejected."""
        assert not validate_scheme("data:text/html,<script>")

    def test_file_rejected(self) -> None:
        """Test that file: is rejected."""
        assert not validate_scheme("file:///etc/passwd")

    def test_ftp_rejected(self) -> None:
        """Test that ftp: is rejected."""
        assert not validate_scheme("ftp://example.com")

    def test_relative_url_rejected(self) -> None:
        """Test that relative URLs are rejected."""
        assert not validate_scheme("/path/to/page")
        assert not validate_scheme("path/to/page")


class TestValidateNoTemplating:
    """Tests for validate_no_templating function."""

    def test_clean_url_accepted(self) -> None:
        """Test that clean URLs are accepted."""
        assert validate_no_templating("https://example.com")
        assert validate_no_templating("https://example.com/path?query=value")

    def test_curly_brace_open_rejected(self) -> None:
        """Test that opening curly brace is rejected."""
        assert not validate_no_templating("https://example.com/{var}")

    def test_curly_brace_close_rejected(self) -> None:
        """Test that closing curly brace is rejected."""
        assert not validate_no_templating("https://example.com/value}")

    def test_dollar_sign_rejected(self) -> None:
        """Test that dollar sign is rejected."""
        assert not validate_no_templating("https://example.com/$VAR")

    def test_multiple_forbidden_chars_rejected(self) -> None:
        """Test that multiple forbidden chars are all rejected."""
        assert not validate_no_templating("https://example.com/${VAR}")
        assert not validate_no_templating("https://example.com/{a}/${b}")


class TestValidateStatusCode:
    """Tests for validate_status_code function."""

    def test_valid_codes(self) -> None:
        """Test all valid redirect status codes."""
        valid_codes = [301, 302, 303, 307, 308]
        for code in valid_codes:
            assert validate_status_code(code), f"Expected {code} to be valid"

    def test_invalid_codes(self) -> None:
        """Test invalid status codes."""
        invalid_codes = [200, 204, 300, 304, 400, 404, 500, 502]
        for code in invalid_codes:
            assert not validate_status_code(code), f"Expected {code} to be invalid"


class TestValidatePathStartsWithSlash:
    """Tests for validate_path_starts_with_slash function."""

    def test_valid_paths(self) -> None:
        """Test paths that start with /."""
        valid_paths = ["/", "/path", "/path/to/page", "/api/v1/users"]
        for path in valid_paths:
            assert validate_path_starts_with_slash(path), f"Expected {path} to be valid"

    def test_invalid_paths(self) -> None:
        """Test paths that don't start with /."""
        invalid_paths = ["path", "path/to/page", "api/v1/users", ""]
        for path in invalid_paths:
            assert not validate_path_starts_with_slash(path), f"Expected {path} to be invalid"


class TestDetectDuplicateIds:
    """Tests for detect_duplicate_ids function."""

    def test_no_duplicates(self) -> None:
        """Test with no duplicate IDs."""
        rules = [
            Rule(id="r1", match="exact", from_="/a", to="https://example.com", status=301),
            Rule(id="r2", match="exact", from_="/b", to="https://example.com", status=301),
            Rule(id="r3", match="exact", from_="/c", to="https://example.com", status=301),
        ]
        duplicates = detect_duplicate_ids(rules)
        assert duplicates == []

    def test_single_duplicate(self) -> None:
        """Test with a single duplicate ID."""
        rules = [
            Rule(id="r1", match="exact", from_="/a", to="https://example.com", status=301),
            Rule(id="r2", match="exact", from_="/b", to="https://example.com", status=301),
            Rule(id="r1", match="exact", from_="/c", to="https://example.com", status=301),
        ]
        duplicates = detect_duplicate_ids(rules)
        assert duplicates == ["r1"]

    def test_multiple_duplicates(self) -> None:
        """Test with multiple duplicate IDs."""
        rules = [
            Rule(id="r1", match="exact", from_="/a", to="https://example.com", status=301),
            Rule(id="r2", match="exact", from_="/b", to="https://example.com", status=301),
            Rule(id="r1", match="exact", from_="/c", to="https://example.com", status=301),
            Rule(id="r2", match="exact", from_="/d", to="https://example.com", status=301),
        ]
        duplicates = detect_duplicate_ids(rules)
        assert set(duplicates) == {"r1", "r2"}

    def test_triple_duplicate(self) -> None:
        """Test with an ID appearing three times."""
        rules = [
            Rule(id="r1", match="exact", from_="/a", to="https://example.com", status=301),
            Rule(id="r1", match="exact", from_="/b", to="https://example.com", status=301),
            Rule(id="r1", match="exact", from_="/c", to="https://example.com", status=301),
        ]
        duplicates = detect_duplicate_ids(rules)
        assert duplicates == ["r1"]


class TestSortRulesByPathLength:
    """Tests for sort_rules_by_path_length function."""

    def test_exact_rules_sorted_longest_first(self) -> None:
        """Test that exact match rules are sorted by path length (longest first)."""
        rules = [
            Rule(id="r1", match="exact", from_="/", to="https://example.com", status=301),
            Rule(
                id="r2",
                match="exact",
                from_="/about", to="https://example.com", status=301,
            ),
            Rule(
                id="r3",
                match="exact",
                from_="/about/team", to="https://example.com", status=301,
            ),
        ]
        sorted_rules = sort_rules_by_path_length(rules)

        assert sorted_rules[0].id == "r3"  # /about/team (longest)
        assert sorted_rules[1].id == "r2"  # /about
        assert sorted_rules[2].id == "r1"  # /

    def test_prefix_rules_sorted_longest_first(self) -> None:
        """Test that prefix match rules are sorted by path length (longest first)."""
        rules = [
            Rule(id="r1", match="prefix", from_="/", to="https://example.com", status=301),
            Rule(
                id="r2",
                match="prefix",
                from_="/api", to="https://example.com", status=301,
            ),
            Rule(
                id="r3",
                match="prefix",
                from_="/api/v2", to="https://example.com", status=301,
            ),
        ]
        sorted_rules = sort_rules_by_path_length(rules)

        assert sorted_rules[0].id == "r3"  # /api/v2 (longest)
        assert sorted_rules[1].id == "r2"  # /api
        assert sorted_rules[2].id == "r1"  # /

    def test_exact_before_prefix(self) -> None:
        """Test that exact rules come before prefix rules."""
        rules = [
            Rule(
                id="p1",
                match="prefix",
                from_="/blog", to="https://example.com", status=301,
            ),
            Rule(id="e1", match="exact", from_="/", to="https://example.com", status=301),
            Rule(id="p2", match="prefix", from_="/", to="https://example.com", status=301),
            Rule(
                id="e2",
                match="exact",
                from_="/about", to="https://example.com", status=301,
            ),
        ]
        sorted_rules = sort_rules_by_path_length(rules)

        # First two should be exact rules (longest first)
        assert sorted_rules[0].match == "exact"
        assert sorted_rules[1].match == "exact"
        assert sorted_rules[0].id == "e2"  # /about
        assert sorted_rules[1].id == "e1"  # /

        # Last two should be prefix rules (longest first)
        assert sorted_rules[2].match == "prefix"
        assert sorted_rules[3].match == "prefix"
        assert sorted_rules[2].id == "p1"  # /blog
        assert sorted_rules[3].id == "p2"  # /

    def test_empty_list(self) -> None:
        """Test sorting an empty list."""
        sorted_rules = sort_rules_by_path_length([])
        assert sorted_rules == []


class TestSortRulesAPI:
    """Tests for sort_rules API function."""

    def test_sort_rules_returns_new_host(self) -> None:
        """Test that sort_rules returns a new Host instance."""
        original_host = Host(
            host="example.com",
            rules=[
                Rule(
                    id="r1",
                    match="prefix",
                    from_="/",
                    to="https://example.com",
                    status=301,
                ),
                Rule(
                    id="r2",
                    match="exact",
                    from_="/about",
                    to="https://example.com",
                    status=301,
                ),
            ],
        )

        sorted_host = sort_rules(original_host)

        # Should be a different instance
        assert sorted_host is not original_host

        # Original should be unchanged
        assert original_host.rules[0].id == "r1"

        # Sorted should have exact rule first
        assert sorted_host.rules[0].id == "r2"
        assert sorted_host.rules[0].match == "exact"
        assert sorted_host.rules[1].id == "r1"
        assert sorted_host.rules[1].match == "prefix"

    def test_sort_rules_preserves_host_properties(self) -> None:
        """Test that sort_rules preserves other host properties."""
        original_host = Host(
            host="example.com",
            hsts=False,
            rules=[
                Rule(
                    id="r1",
                    match="prefix",
                    from_="/",
                    to="https://example.com",
                    status=301,
                ),
            ],
        )

        sorted_host = sort_rules(original_host)

        assert sorted_host.host == original_host.host
        assert sorted_host.hsts == original_host.hsts
