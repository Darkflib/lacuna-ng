"""Tests for Pydantic models."""

from pathlib import Path

import pytest
from lacuna_schema import Config, Defaults, Host, Rule, load_config
from pydantic import ValidationError


class TestDefaults:
    """Tests for Defaults model."""

    def test_defaults_with_values(self) -> None:
        """Test creating Defaults with explicit values."""
        defaults = Defaults(hsts=True, keep_query=False)
        assert defaults.hsts is True
        assert defaults.keep_query is False

    def test_defaults_with_defaults(self) -> None:
        """Test Defaults uses correct default values."""
        defaults = Defaults()
        assert defaults.hsts is True
        assert defaults.keep_query is True


class TestRule:
    """Tests for Rule model."""

    def test_valid_rule(self) -> None:
        """Test creating a valid rule."""
        rule = Rule(
            id="test-rule",
            match="exact",
            **{"from": "/path", "to": "https://example.com", "status": 301},
        )
        assert rule.id == "test-rule"
        assert rule.match == "exact"
        assert rule.from_ == "/path"
        assert rule.to == "https://example.com"
        assert rule.status == 301
        assert rule.keep_query is None

    def test_rule_id_pattern_valid(self) -> None:
        """Test valid rule ID patterns."""
        valid_ids = [
            "simple",
            "with-dash",
            "with_underscore",
            "with.dot",
            "a1b2c3",
            "0starts-with-digit",
            "complex_rule-id.v2",
        ]
        for rule_id in valid_ids:
            rule = Rule(
                id=rule_id,
                match="exact",
                **{"from": "/", "to": "https://example.com", "status": 301},
            )
            assert rule.id == rule_id

    def test_rule_id_pattern_invalid(self) -> None:
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
        ]
        for rule_id in invalid_ids:
            with pytest.raises(ValidationError) as exc_info:
                Rule(
                    id=rule_id,
                    match="exact",
                    **{"from": "/", "to": "https://example.com", "status": 301},
                )
            assert "id" in str(exc_info.value).lower()

    def test_path_must_start_with_slash(self) -> None:
        """Test that 'from' path must start with /."""
        with pytest.raises(ValidationError) as exc_info:
            Rule(
                id="test",
                match="exact",
                **{"from": "no-slash", "to": "https://example.com", "status": 301},
            )
        assert "must start with /" in str(exc_info.value)

    def test_scheme_allowlist_http(self) -> None:
        """Test that http:// scheme is allowed."""
        rule = Rule(id="test", match="exact", **{"from": "/", "to": "http://example.com", "status": 301})
        assert rule.to == "http://example.com"

    def test_scheme_allowlist_https(self) -> None:
        """Test that https:// scheme is allowed."""
        rule = Rule(id="test", match="exact", **{"from": "/", "to": "https://example.com", "status": 301})
        assert rule.to == "https://example.com"

    def test_scheme_reject_javascript(self) -> None:
        """Test that javascript: scheme is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Rule(
                id="test",
                match="exact",
                **{"from": "/", "to": "javascript:alert('XSS')", "status": 301},
            )
        assert "http or https scheme" in str(exc_info.value)

    def test_scheme_reject_data(self) -> None:
        """Test that data: scheme is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Rule(
                id="test",
                match="exact",
                **{"from": "/", "to": "data:text/html,<script>", "status": 301},
            )
        assert "http or https scheme" in str(exc_info.value)

    def test_scheme_reject_file(self) -> None:
        """Test that file: scheme is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Rule(id="test", match="exact", **{"from": "/", "to": "file:///etc/passwd", "status": 301})
        assert "http or https scheme" in str(exc_info.value)

    def test_reject_templating_curly_braces(self) -> None:
        """Test that curly braces are rejected in 'to' URL."""
        with pytest.raises(ValidationError) as exc_info:
            Rule(
                id="test",
                match="exact",
                **{"from": "/", "to": "https://example.com/{user}", "status": 301},
            )
        assert "templating character" in str(exc_info.value)

    def test_reject_templating_dollar(self) -> None:
        """Test that dollar sign is rejected in 'to' URL."""
        with pytest.raises(ValidationError) as exc_info:
            Rule(
                id="test",
                match="exact",
                **{"from": "/", "to": "https://example.com/$VAR", "status": 301},
            )
        assert "templating character" in str(exc_info.value)

    def test_status_codes_valid(self) -> None:
        """Test all valid status codes."""
        valid_codes = [301, 302, 303, 307, 308]
        for status in valid_codes:
            rule = Rule(
                id="test",
                match="exact",
                **{"from": "/", "to": "https://example.com", "status": status},
            )
            assert rule.status == status

    def test_status_codes_invalid(self) -> None:
        """Test invalid status codes."""
        invalid_codes = [200, 300, 304, 400, 404, 500]
        for status in invalid_codes:
            with pytest.raises(ValidationError):
                Rule(
                    id="test",
                    match="exact",
                    **{"from": "/", "to": "https://example.com", "status": status},
                )

    def test_match_type_valid(self) -> None:
        """Test valid match types."""
        for match_type in ["exact", "prefix"]:
            rule = Rule(
                id="test",
                match=match_type,
                **{"from": "/", "to": "https://example.com", "status": 301},
            )
            assert rule.match == match_type

    def test_match_type_invalid(self) -> None:
        """Test invalid match type."""
        with pytest.raises(ValidationError):
            Rule(
                id="test",
                match="regex",
                **{"from": "/", "to": "https://example.com", "status": 301},
            )


class TestHost:
    """Tests for Host model."""

    def test_valid_host(self) -> None:
        """Test creating a valid host."""
        host = Host(
            host="example.com",
            hsts=True,
            rules=[
                Rule(
                    id="r1",
                    match="exact",
                    **{"from": "/", "to": "https://example.com", "status": 301},
                )
            ],
        )
        assert host.host == "example.com"
        assert host.hsts is True
        assert len(host.rules) == 1

    def test_host_without_hsts(self) -> None:
        """Test host without explicit HSTS setting."""
        host = Host(
            host="example.com",
            rules=[
                Rule(
                    id="r1",
                    match="exact",
                    **{"from": "/", "to": "https://example.com", "status": 301},
                )
            ],
        )
        assert host.hsts is None

    def test_duplicate_rule_ids_rejected(self) -> None:
        """Test that duplicate rule IDs within a host are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Host(
                host="example.com",
                rules=[
                    Rule(
                        id="duplicate",
                        match="exact",
                        **{"from": "/a", "to": "https://example.com/a", "status": 301},
                    ),
                    Rule(
                        id="duplicate",
                        match="exact",
                        **{"from": "/b", "to": "https://example.com/b", "status": 301},
                    ),
                ],
            )
        assert "duplicate" in str(exc_info.value).lower()

    def test_different_rule_ids_allowed(self) -> None:
        """Test that different rule IDs are allowed."""
        host = Host(
            host="example.com",
            rules=[
                Rule(
                    id="rule1",
                    match="exact",
                    **{"from": "/a", "to": "https://example.com/a", "status": 301},
                ),
                Rule(
                    id="rule2",
                    match="exact",
                    **{"from": "/b", "to": "https://example.com/b", "status": 301},
                ),
            ],
        )
        assert len(host.rules) == 2


class TestConfig:
    """Tests for Config model."""

    def test_valid_config(self) -> None:
        """Test creating a valid config."""
        config = Config(
            version=1,
            defaults=Defaults(hsts=True, keep_query=True),
            hosts=[
                Host(
                    host="example.com",
                    rules=[
                        Rule(
                            id="r1",
                            match="exact",
                            **{"from": "/", "to": "https://example.com", "status": 301},
                        )
                    ],
                )
            ],
        )
        assert config.version == 1
        assert len(config.hosts) == 1

    def test_version_must_be_1(self) -> None:
        """Test that only version 1 is supported."""
        with pytest.raises(ValidationError) as exc_info:
            Config(
                version=2,
                defaults=Defaults(),
                hosts=[],
            )
        assert "version 1 is supported" in str(exc_info.value)


class TestLoadConfig:
    """Tests for load_config API function."""

    def test_load_valid_config(self) -> None:
        """Test loading a valid configuration file."""
        fixture_path = Path(__file__).parent / "fixtures" / "valid.yaml"
        config = load_config(fixture_path)

        assert config.version == 1
        assert len(config.hosts) == 3
        assert config.hosts[0].host == "example.com"
        assert len(config.hosts[0].rules) == 4

    def test_load_invalid_scheme(self) -> None:
        """Test loading config with invalid scheme."""
        fixture_path = Path(__file__).parent / "fixtures" / "invalid_scheme.yaml"
        with pytest.raises(ValidationError) as exc_info:
            load_config(fixture_path)
        assert "http or https scheme" in str(exc_info.value)

    def test_load_invalid_templating(self) -> None:
        """Test loading config with templating characters."""
        fixture_path = Path(__file__).parent / "fixtures" / "invalid_templating.yaml"
        with pytest.raises(ValidationError) as exc_info:
            load_config(fixture_path)
        assert "templating character" in str(exc_info.value)

    def test_load_nonexistent_file(self) -> None:
        """Test loading a file that doesn't exist."""
        with pytest.raises(FileNotFoundError):
            load_config(Path("/nonexistent/file.yaml"))
