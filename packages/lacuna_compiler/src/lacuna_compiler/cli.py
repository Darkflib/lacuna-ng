"""Command-line interface for lacuna-compiler."""

import sys
from pathlib import Path
from typing import Optional

import typer
from lacuna_schema.api import load_config
from pydantic import ValidationError
from yaml import YAMLError

from .api import write_candidate

app = typer.Typer(
    name="lacuna-compiler",
    help="Compile Lacuna YAML configurations to Caddy JSON",
    add_completion=False,
)


@app.command()
def main(
    yaml_path: Path = typer.Argument(
        ...,
        help="Path to YAML configuration file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    out_dir: Path = typer.Option(
        "./vol/config",
        "--out-dir",
        "-o",
        help="Output directory for config.next.json",
    ),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help="Only validate and compile, don't promote (lacuna_promote not yet implemented)",
    ),
) -> None:
    """
    Compile a Lacuna YAML configuration to Caddy JSON.

    This command:
    1. Loads and validates the YAML config using lacuna_schema
    2. Compiles it to Caddy JSON
    3. Writes the result to {out_dir}/config.next.json

    Future: When lacuna_promote is implemented, this will also promote
    the config unless --validate-only is specified.

    Examples:

        # Compile and validate only
        $ lacuna-compiler examples/domainlist.yaml --validate-only

        # Compile with custom output directory
        $ lacuna-compiler config.yaml --out-dir /srv/lacuna/config

        # Use default output directory (./vol/config)
        $ lacuna-compiler examples/domainlist.yaml
    """
    try:
        # Load and validate YAML
        typer.echo(f"Loading configuration from {yaml_path}...")
        config = load_config(yaml_path)

        # Report stats
        total_rules = sum(len(host.rules) for host in config.hosts)
        typer.echo(
            f"✓ Validated: {len(config.hosts)} hosts, {total_rules} total rules"
        )

        # Compile to Caddy JSON and write
        typer.echo(f"Compiling to Caddy JSON...")
        output_path = write_candidate(config, out_dir)
        typer.echo(f"✓ Written to {output_path}")

        if validate_only:
            typer.echo("✓ Validation complete (--validate-only mode)")
            typer.echo(
                "\nNote: Promotion is not yet implemented. "
                "Use 'caddy validate' and 'caddy reload' manually."
            )
        else:
            typer.echo(
                "\nNote: lacuna_promote is not yet implemented. "
                "Config written to config.next.json but not promoted."
            )
            typer.echo("To apply: caddy validate --config <path> && caddy reload --config <path>")

        sys.exit(0)

    except FileNotFoundError as e:
        typer.secho(f"✗ Error: {e}", fg=typer.colors.RED, err=True)
        sys.exit(1)

    except YAMLError as e:
        typer.secho(f"✗ YAML Parse Error: {e}", fg=typer.colors.RED, err=True)
        sys.exit(1)

    except ValidationError as e:
        typer.secho("✗ Validation Error:", fg=typer.colors.RED, err=True)
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        sys.exit(1)

    except OSError as e:
        typer.secho(f"✗ I/O Error: {e}", fg=typer.colors.RED, err=True)
        sys.exit(1)

    except Exception as e:
        typer.secho(f"✗ Unexpected Error: {e}", fg=typer.colors.RED, err=True)
        raise  # Re-raise for debugging


if __name__ == "__main__":
    app()
