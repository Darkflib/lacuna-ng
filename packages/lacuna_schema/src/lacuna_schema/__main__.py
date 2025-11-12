"""CLI for validating Lacuna v2 configuration files.

Usage:
    python -m lacuna_schema.check <yaml_file>
    python -m lacuna_schema <yaml_file>
"""

import sys
from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from .api import load_config

app = typer.Typer(
    name="lacuna_schema",
    help="Validate Lacuna v2 YAML configuration files",
    add_completion=False,
)


@app.command(name="check")
def check(
    yaml_file: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to YAML configuration file",
    ),
) -> None:
    """
    Validate a Lacuna v2 configuration file.

    Exits with code 0 on success, non-zero on validation errors.
    """
    try:
        config = load_config(yaml_file)

        # Calculate statistics
        total_rules = sum(len(host.rules) for host in config.hosts)
        hosts_count = len(config.hosts)

        # Print success message with statistics
        typer.secho(f"✓ Valid configuration: {yaml_file}", fg=typer.colors.GREEN)
        typer.echo(f"  Version: {config.version}")
        typer.echo(f"  Hosts: {hosts_count}")
        typer.echo(f"  Total rules: {total_rules}")

        # Per-host breakdown
        for host in config.hosts:
            exact_count = sum(1 for r in host.rules if r.match == "exact")
            prefix_count = sum(1 for r in host.rules if r.match == "prefix")
            hsts_status = host.hsts if host.hsts is not None else config.defaults.hsts
            hsts_indicator = "🔒" if hsts_status else "🔓"

            typer.echo(
                f"  - {host.host}: {len(host.rules)} rules "
                f"({exact_count} exact, {prefix_count} prefix) {hsts_indicator}"
            )

        sys.exit(0)

    except FileNotFoundError as e:
        typer.secho(f"✗ Error: {e}", err=True, fg=typer.colors.RED)
        sys.exit(1)

    except yaml.YAMLError as e:
        typer.secho("✗ YAML parsing error:", err=True, fg=typer.colors.RED)
        typer.echo(f"  {e}", err=True)
        sys.exit(1)

    except ValidationError as e:
        typer.secho(
            f"✗ Validation errors in {yaml_file}:",
            err=True,
            fg=typer.colors.RED,
        )

        # Format validation errors for readability
        for error in e.errors():
            location = " → ".join(str(loc) for loc in error["loc"]) if error["loc"] else "root"
            msg = error["msg"]
            typer.echo(f"  [{location}] {msg}", err=True)

        sys.exit(1)

    except Exception as e:
        typer.secho(
            f"✗ Unexpected error: {e}",
            err=True,
            fg=typer.colors.RED,
        )
        sys.exit(1)


@app.command(hidden=True)
def main(yaml_file: Path) -> None:
    """Default command (hidden) - delegates to check."""
    check(yaml_file)


def cli() -> None:
    """Entry point for the CLI."""
    # If no arguments or only the script name, show help
    if len(sys.argv) == 1:
        sys.argv.append("--help")
    # If first argument is not a flag and not 'check', treat it as check argument
    elif len(sys.argv) >= 2 and not sys.argv[1].startswith("-") and sys.argv[1] != "check":
        sys.argv.insert(1, "check")

    app()


if __name__ == "__main__":
    cli()
