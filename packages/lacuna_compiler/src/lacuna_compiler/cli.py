"""Command-line interface for lacuna-compiler."""

import sys
from pathlib import Path

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
        help="Only validate and compile, don't promote",
    ),
    promote: bool = typer.Option(
        False,
        "--promote",
        help="Promote config with double-buffer validation and rollback",
    ),
) -> None:
    """
    Compile a Lacuna YAML configuration to Caddy JSON.

    This command:
    1. Loads and validates the YAML config using lacuna_schema
    2. Compiles it to Caddy JSON
    3. Writes the result to {out_dir}/config.next.json
    4. Optionally promotes with double-buffer (--promote)

    Examples:

        # Compile and validate only
        $ lacuna-compiler examples/domainlist.yaml --validate-only

        # Compile and promote with double-buffer
        $ lacuna-compiler config.yaml --out-dir /srv/lacuna/config --promote

        # Just compile (no validation, no promotion)
        $ lacuna-compiler examples/domainlist.yaml
    """
    try:
        # Validate mutually exclusive options
        if validate_only and promote:
            typer.secho(
                "✗ Error: --validate-only and --promote are mutually exclusive",
                fg=typer.colors.RED,
                err=True,
            )
            sys.exit(1)

        # If --promote is specified, use lacuna_promote
        if promote:
            try:
                from lacuna_promote import PromoteOptions, compile_and_promote

                typer.echo("Promoting with double-buffer validation and rollback...")
                opts = PromoteOptions(out_dir=out_dir, validate_only=False)
                active_path = compile_and_promote(yaml_path, opts)
                typer.secho(
                    f"✓ Successfully promoted to {active_path}",
                    fg=typer.colors.GREEN,
                )
                sys.exit(0)

            except ImportError:
                typer.secho(
                    "✗ lacuna_promote not installed. Install it first:",
                    fg=typer.colors.RED,
                    err=True,
                )
                typer.secho(
                    "   uv pip install -e packages/lacuna_promote",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
                sys.exit(1)

            except Exception as e:
                typer.secho(f"✗ Promotion failed: {e}", fg=typer.colors.RED, err=True)
                sys.exit(1)

        # Otherwise, just compile (with or without validation)
        # Load and validate YAML
        typer.echo(f"Loading configuration from {yaml_path}...")
        config = load_config(yaml_path)

        # Report stats
        total_rules = sum(len(host.rules) for host in config.hosts)
        typer.echo(f"✓ Validated: {len(config.hosts)} hosts, {total_rules} total rules")

        # Compile to Caddy JSON and write
        typer.echo("Compiling to Caddy JSON...")
        output_path = write_candidate(config, out_dir)
        typer.echo(f"✓ Written to {output_path}")

        if validate_only:
            typer.echo("✓ Validation complete (--validate-only mode)")
            typer.echo("\nTo promote: Use --promote flag or manually run:")
            typer.echo("  caddy validate --config <path> && caddy reload --config <path>")
        else:
            typer.echo("\n✓ Config written to config.next.json")
            typer.echo("To promote with double-buffer: Use --promote flag")
            typer.echo(
                "To promote manually: caddy validate --config <path> && caddy reload --config <path>"
            )

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
