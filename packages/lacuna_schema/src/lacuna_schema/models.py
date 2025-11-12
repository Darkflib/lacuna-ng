"""Pydantic models for Lacuna v2 YAML configuration schema."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Defaults(BaseModel):
    """Global default settings."""

    hsts: bool = Field(
        default=True,
        description="Enable HSTS (HTTP Strict Transport Security) by default",
    )
    keep_query: bool = Field(
        default=True,
        description="Preserve query strings in redirects by default",
    )


class Rule(BaseModel):
    """A single redirect rule."""

    id: str = Field(
        description="Unique identifier for this rule (within a host)",
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    match: Literal["exact", "prefix"] = Field(
        description="Match type: exact path or prefix",
    )
    from_: str = Field(
        alias="from",
        description="Source path (must start with /)",
    )
    to: str = Field(
        description="Target URL (http/https schemes only)",
    )
    status: Literal[301, 302, 303, 307, 308] = Field(
        description="HTTP redirect status code",
    )
    keep_query: bool | None = Field(
        default=None,
        description="Override default keep_query behavior for this rule",
    )

    @field_validator("from_")
    @classmethod
    def validate_from_path(cls, v: str) -> str:
        """Validate that 'from' starts with /."""
        if not v.startswith("/"):
            raise ValueError(f"Path must start with /: {v}")
        return v

    @field_validator("to")
    @classmethod
    def validate_to_url(cls, v: str) -> str:
        """Validate 'to' URL: scheme allowlist and no templating chars."""
        # Check for templating characters
        forbidden_chars = ["{", "}", "$"]
        for char in forbidden_chars:
            if char in v:
                raise ValueError(f"URL must not contain templating character '{char}': {v}")

        # Check scheme allowlist
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"URL must use http or https scheme (not javascript:, data:, file:, etc.): {v}")

        return v

    model_config = {
        "populate_by_name": True,  # Allow both 'from' and 'from_' in initialization
    }


class Host(BaseModel):
    """A host with its redirect rules."""

    host: str = Field(
        description="Domain name (without protocol)",
    )
    hsts: bool | None = Field(
        default=None,
        description="Override default HSTS setting for this host",
    )
    rules: list[Rule] = Field(
        description="Redirect rules for this host",
    )

    @model_validator(mode="after")
    def validate_unique_rule_ids(self) -> "Host":
        """Validate that rule IDs are unique within this host."""
        seen_ids = set()
        duplicates = []

        for rule in self.rules:
            if rule.id in seen_ids:
                duplicates.append(rule.id)
            seen_ids.add(rule.id)

        if duplicates:
            raise ValueError(f"Duplicate rule IDs found in host '{self.host}': {', '.join(sorted(set(duplicates)))}")

        return self


class Config(BaseModel):
    """Top-level configuration."""

    version: int = Field(
        description="Configuration schema version",
    )
    defaults: Defaults = Field(
        description="Global default settings",
    )
    hosts: list[Host] = Field(
        description="List of hosts with their redirect rules",
    )

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        """Validate that version is supported."""
        if v != 1:
            raise ValueError(f"Only version 1 is supported, got: {v}")
        return v
