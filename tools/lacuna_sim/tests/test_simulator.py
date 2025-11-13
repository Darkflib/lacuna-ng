"""Comprehensive tests for Lacuna v2 simulator.

Tests cover:
- Exact match behavior
- Prefix match behavior
- Path remainder calculation
- Query string handling
- Rule ordering (exact before prefix, longest-first)
- Dead rule detection
- Coverage calculation
- Cases file parsing
"""

import tempfile
from pathlib import Path

import pytest
from lacuna_schema import Config, Defaults, Host, Rule
from lacuna_sim import (
    MatchResult,
    Request,
    generate_coverage_report,
    match_request,
    parse_cases_file,
    simulate_batch,
)


# Test fixtures
@pytest.fixture
def basic_config() -> Config:
    """Basic config with exact and prefix rules."""
    return Config(
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
                        from_="/",
                        to="https://www.example.org/",
                        status=308,
                    ),
                    Rule(
                        id="blog",
                        match="prefix",
                        from_="/blog",
                        to="https://blog.example.org",
                        status=308,
                    ),
                    Rule(
                        id="api",
                        match="prefix",
                        from_="/api",
                        to="https://api.example.org",
                        status=307,
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def complex_config() -> Config:
    """Complex config for testing rule ordering and dead rules."""
    return Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                hsts=True,
                rules=[
                    # These should be sorted: exact longest-first, then prefix longest-first
                    Rule(
                        id="root-prefix",
                        match="prefix",
                        from_="/",
                        to="https://fallback.example.org",
                        status=308,
                    ),
                    Rule(
                        id="blog-post-exact",
                        match="exact",
                        from_="/blog/post-1",
                        to="https://special.example.org",
                        status=308,
                    ),
                    Rule(
                        id="blog-prefix",
                        match="prefix",
                        from_="/blog",
                        to="https://blog.example.org",
                        status=308,
                    ),
                    Rule(
                        id="docs-exact",
                        match="exact",
                        from_="/docs",
                        to="https://docs.example.org",
                        status=308,
                    ),
                    Rule(
                        id="never-matched",
                        match="exact",
                        from_="/never-used",
                        to="https://dead.example.org",
                        status=308,
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def query_config() -> Config:
    """Config for testing query string behavior."""
    return Config(
        version=1,
        defaults=Defaults(hsts=True, keep_query=True),
        hosts=[
            Host(
                host="example.com",
                rules=[
                    Rule(
                        id="keep-query",
                        match="prefix",
                        from_="/keep",
                        to="https://keep.example.org",
                        status=308,
                        keep_query=True,
                    ),
                    Rule(
                        id="drop-query",
                        match="prefix",
                        from_="/drop",
                        to="https://drop.example.org",
                        status=308,
                        keep_query=False,
                    ),
                ],
            ),
        ],
    )


class TestExactMatch:
    """Test exact match behavior."""

    def test_exact_match_root(self, basic_config: Config) -> None:
        """Request / matches exact rule for /."""
        req = Request(host="example.com", path="/")
        result = match_request(basic_config, req)

        assert result.matched is True
        assert result.rule_id == "home"
        assert result.status == 308
        assert result.location == "https://www.example.org/"

    def test_exact_no_match_similar_path(self, basic_config: Config) -> None:
        """Request /foo does NOT match exact rule for /."""
        req = Request(host="example.com", path="/foo")
        result = match_request(basic_config, req)

        # Should match prefix rule /api or /blog, not exact /
        # Actually should not match any since /foo doesn't start with /api or /blog
        # So it should not match
        assert result.matched is False

    def test_exact_match_with_query(self, basic_config: Config) -> None:
        """Exact match with query string preservation."""
        req = Request(host="example.com", path="/", query="ref=home")
        result = match_request(basic_config, req)

        assert result.matched is True
        assert result.rule_id == "home"
        assert result.location == "https://www.example.org/?ref=home"


class TestPrefixMatch:
    """Test prefix match behavior."""

    def test_prefix_match_exact_prefix(self, basic_config: Config) -> None:
        """Request /blog matches prefix rule for /blog."""
        req = Request(host="example.com", path="/blog")
        result = match_request(basic_config, req)

        assert result.matched is True
        assert result.rule_id == "blog"
        assert result.status == 308
        assert result.location == "https://blog.example.org"

    def test_prefix_match_with_remainder(self, basic_config: Config) -> None:
        """Request /blog/post-1 matches prefix rule for /blog."""
        req = Request(host="example.com", path="/blog/post-1")
        result = match_request(basic_config, req)

        assert result.matched is True
        assert result.rule_id == "blog"
        assert result.location == "https://blog.example.org/post-1"

    def test_prefix_match_with_trailing_slash(self, basic_config: Config) -> None:
        """Request /blog/ matches and preserves trailing slash."""
        req = Request(host="example.com", path="/blog/")
        result = match_request(basic_config, req)

        assert result.matched is True
        assert result.rule_id == "blog"
        # Remainder is "/", after stripping should give us the base URL
        assert result.location == "https://blog.example.org/"

    def test_prefix_no_match_different_prefix(self, basic_config: Config) -> None:
        """Request /docs does NOT match prefix rule for /blog."""
        req = Request(host="example.com", path="/docs")
        result = match_request(basic_config, req)

        assert result.matched is False


class TestPathRemainder:
    """Test path remainder calculation for prefix matches."""

    def test_remainder_simple(self, basic_config: Config) -> None:
        """Prefix /blog + request /blog/post-1 → location includes /post-1."""
        req = Request(host="example.com", path="/blog/post-1")
        result = match_request(basic_config, req)

        assert result.location == "https://blog.example.org/post-1"

    def test_remainder_nested(self, basic_config: Config) -> None:
        """Prefix /api + request /api/v1/users → location includes /v1/users."""
        req = Request(host="example.com", path="/api/v1/users")
        result = match_request(basic_config, req)

        assert result.matched is True
        assert result.rule_id == "api"
        assert result.location == "https://api.example.org/v1/users"

    def test_remainder_multiple_segments(self, basic_config: Config) -> None:
        """Deep path with multiple segments."""
        req = Request(host="example.com", path="/api/v2/users/123/profile")
        result = match_request(basic_config, req)

        assert result.location == "https://api.example.org/v2/users/123/profile"


class TestQueryString:
    """Test query string handling (keep/drop)."""

    def test_keep_query_true_with_query(self, query_config: Config) -> None:
        """keep_query=true + query → location includes query."""
        req = Request(host="example.com", path="/keep/page", query="foo=bar")
        result = match_request(query_config, req)

        assert result.matched is True
        assert result.rule_id == "keep-query"
        assert result.location == "https://keep.example.org/page?foo=bar"

    def test_keep_query_true_without_query(self, query_config: Config) -> None:
        """keep_query=true + no query → location without query."""
        req = Request(host="example.com", path="/keep/page")
        result = match_request(query_config, req)

        assert result.matched is True
        assert result.location == "https://keep.example.org/page"

    def test_keep_query_false_with_query(self, query_config: Config) -> None:
        """keep_query=false + query → location without query."""
        req = Request(host="example.com", path="/drop/page", query="foo=bar")
        result = match_request(query_config, req)

        assert result.matched is True
        assert result.rule_id == "drop-query"
        assert result.location == "https://drop.example.org/page"

    def test_query_with_multiple_params(self, query_config: Config) -> None:
        """Query string with multiple parameters."""
        req = Request(host="example.com", path="/keep", query="id=123&format=json&lang=en")
        result = match_request(query_config, req)

        assert result.location == "https://keep.example.org?id=123&format=json&lang=en"


class TestRuleOrdering:
    """Test rule evaluation order (exact before prefix, longest-first)."""

    def test_exact_matched_before_prefix(self, complex_config: Config) -> None:
        """Exact rules are checked before prefix rules."""
        # /blog/post-1 has both exact rule and prefix /blog rule
        # Exact should match first
        req = Request(host="example.com", path="/blog/post-1")
        result = match_request(complex_config, req)

        assert result.matched is True
        assert result.rule_id == "blog-post-exact"
        assert result.location == "https://special.example.org"

    def test_prefix_when_no_exact_match(self, complex_config: Config) -> None:
        """Prefix rule matches when no exact match exists."""
        req = Request(host="example.com", path="/blog/other-post")
        result = match_request(complex_config, req)

        assert result.matched is True
        assert result.rule_id == "blog-prefix"
        assert result.location == "https://blog.example.org/other-post"

    def test_longest_path_first_exact(self, complex_config: Config) -> None:
        """Longer exact paths are checked before shorter ones."""
        # /docs exact should match before falling through
        req = Request(host="example.com", path="/docs")
        result = match_request(complex_config, req)

        assert result.matched is True
        assert result.rule_id == "docs-exact"


class TestDeadRuleDetection:
    """Test dead rule detection and coverage reporting."""

    def test_all_rules_matched(self, basic_config: Config) -> None:
        """All rules matched → no dead rules."""
        requests = [
            Request(host="example.com", path="/"),
            Request(host="example.com", path="/blog"),
            Request(host="example.com", path="/api"),
        ]
        results = simulate_batch(basic_config, requests)
        report = generate_coverage_report(basic_config, results)

        assert report.total_rules == 3
        assert len(report.matched_rules) == 3
        assert len(report.dead_rules) == 0
        assert report.coverage_percent == 100.0
        assert report.all_matched is True

    def test_some_rules_not_matched(self, complex_config: Config) -> None:
        """Some rules not matched → dead rules reported."""
        requests = [
            Request(host="example.com", path="/blog/post-1"),
            Request(host="example.com", path="/docs"),
        ]
        results = simulate_batch(complex_config, requests)
        report = generate_coverage_report(complex_config, results)

        assert report.total_rules == 5
        assert len(report.matched_rules) == 2
        assert "never-matched" in report.dead_rules
        assert "blog-prefix" in report.dead_rules
        assert "root-prefix" in report.dead_rules
        assert report.coverage_percent < 100.0
        assert report.all_matched is False

    def test_no_rules_matched(self) -> None:
        """No rules matched → 0% coverage."""
        config = Config(
            version=1,
            defaults=Defaults(hsts=True, keep_query=True),
            hosts=[
                Host(
                    host="example.com",
                    rules=[
                        Rule(
                            id="only-rule",
                            match="exact",
                            from_="/test",
                            to="https://test.com",
                            status=308,
                        ),
                    ],
                ),
            ],
        )
        requests = [Request(host="example.com", path="/other")]
        results = simulate_batch(config, requests)
        report = generate_coverage_report(config, results)

        assert report.total_rules == 1
        assert len(report.matched_rules) == 0
        assert len(report.dead_rules) == 1
        assert report.coverage_percent == 0.0


class TestCoverageCalculation:
    """Test coverage percentage calculation."""

    def test_coverage_100_percent(self, basic_config: Config) -> None:
        """All rules matched → 100% coverage."""
        requests = [
            Request(host="example.com", path="/"),
            Request(host="example.com", path="/blog"),
            Request(host="example.com", path="/api"),
        ]
        results = simulate_batch(basic_config, requests)
        report = generate_coverage_report(basic_config, results)

        assert report.coverage_percent == 100.0

    def test_coverage_partial(self, complex_config: Config) -> None:
        """Some rules matched → partial coverage."""
        requests = [
            Request(host="example.com", path="/docs"),
            Request(host="example.com", path="/blog/post-1"),
        ]
        results = simulate_batch(complex_config, requests)
        report = generate_coverage_report(complex_config, results)

        # 2 out of 5 rules matched = 40%
        assert report.coverage_percent == 40.0

    def test_coverage_with_duplicate_matches(self, basic_config: Config) -> None:
        """Same rule matched multiple times → counted once."""
        requests = [
            Request(host="example.com", path="/"),
            Request(host="example.com", path="/", query="test=1"),
            Request(host="example.com", path="/", query="test=2"),
        ]
        results = simulate_batch(basic_config, requests)
        report = generate_coverage_report(basic_config, results)

        # Only 1 rule (home) matched, even though matched 3 times
        assert len(report.matched_rules) == 1
        assert "home" in report.matched_rules


class TestCasesFileParser:
    """Test parsing of cases.txt files."""

    def test_parse_simple_cases(self) -> None:
        """Parse simple cases file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# Comment line\n")
            f.write("example.com /\n")
            f.write("example.com /blog\n")
            f.write("\n")  # Empty line
            f.write("# Another comment\n")
            f.write("example.com /api/users\n")
            path = Path(f.name)

        try:
            requests = parse_cases_file(path)
            assert len(requests) == 3
            assert requests[0] == Request(host="example.com", path="/")
            assert requests[1] == Request(host="example.com", path="/blog")
            assert requests[2] == Request(host="example.com", path="/api/users")
        finally:
            path.unlink()

    def test_parse_cases_with_query(self) -> None:
        """Parse cases with query strings."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("example.com / ref=home\n")
            f.write("example.com /blog page=2\n")
            f.write("example.com /api id=123&format=json\n")
            path = Path(f.name)

        try:
            requests = parse_cases_file(path)
            assert len(requests) == 3
            assert requests[0].query == "ref=home"
            assert requests[1].query == "page=2"
            assert requests[2].query == "id=123&format=json"
        finally:
            path.unlink()

    def test_parse_empty_file(self) -> None:
        """Parse empty file returns empty list."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# Only comments\n")
            f.write("\n")
            f.write("# More comments\n")
            path = Path(f.name)

        try:
            requests = parse_cases_file(path)
            assert len(requests) == 0
        finally:
            path.unlink()

    def test_parse_invalid_format(self) -> None:
        """Invalid format raises ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("example.com /\n")
            f.write("invalid-line-with-no-path\n")
            path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Invalid format"):
                parse_cases_file(path)
        finally:
            path.unlink()

    def test_parse_nonexistent_file(self) -> None:
        """Nonexistent file raises FileNotFoundError."""
        path = Path("/nonexistent/cases.txt")
        with pytest.raises(FileNotFoundError):
            parse_cases_file(path)


class TestHostMatching:
    """Test host matching behavior."""

    def test_no_host_match(self, basic_config: Config) -> None:
        """Request for unknown host → no match."""
        req = Request(host="unknown.com", path="/")
        result = match_request(basic_config, req)

        assert result.matched is False
        assert result.rule_id is None
        assert result.status is None
        assert result.location is None

    def test_correct_host_match(self, basic_config: Config) -> None:
        """Request for known host → matches rules."""
        req = Request(host="example.com", path="/")
        result = match_request(basic_config, req)

        assert result.matched is True
        assert result.rule_id == "home"


class TestSimulateBatch:
    """Test batch simulation."""

    def test_batch_maintains_order(self, basic_config: Config) -> None:
        """Results maintain same order as input requests."""
        requests = [
            Request(host="example.com", path="/api"),
            Request(host="example.com", path="/blog"),
            Request(host="example.com", path="/"),
        ]
        results = simulate_batch(basic_config, requests)

        assert len(results) == 3
        assert results[0].rule_id == "api"
        assert results[1].rule_id == "blog"
        assert results[2].rule_id == "home"

    def test_batch_empty_list(self, basic_config: Config) -> None:
        """Empty request list returns empty results."""
        results = simulate_batch(basic_config, [])
        assert len(results) == 0


class TestMatchResult:
    """Test MatchResult data class."""

    def test_match_result_displays(self) -> None:
        """Test display properties."""
        req = Request(host="example.com", path="/test")
        result = MatchResult(
            request=req,
            rule_id="test-rule",
            status=308,
            location="https://example.org",
            matched=True,
        )

        assert result.rule_display == "test-rule"
        assert result.status_display == "308"
        assert result.location_display == "https://example.org"

    def test_no_match_displays(self) -> None:
        """Test display properties for no-match result."""
        req = Request(host="example.com", path="/test")
        result = MatchResult(
            request=req,
            rule_id=None,
            status=None,
            location=None,
            matched=False,
        )

        assert result.rule_display == "(no match)"
        assert result.status_display == "-"
        assert result.location_display == "-"
