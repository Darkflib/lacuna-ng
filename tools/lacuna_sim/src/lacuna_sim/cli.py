"""CLI for Lacuna v2 simulator - test redirect configs without running Caddy.

Usage:
    lacuna-sim --yaml config.yaml --cases cases.txt
    lacuna-sim --yaml config.yaml --request "host.com /path query=val"
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .simulator import (
    CoverageReport,
    MatchResult,
    Request,
    generate_coverage_report,
    load_config_from_yaml,
    match_request,
    parse_cases_file,
    simulate_batch,
)

app = typer.Typer(
    name="lacuna-sim",
    help="Dry-run simulator for Lacuna v2 redirect configurations",
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True)


def print_results_table(results: list[MatchResult]) -> None:
    """
    Print match results in a formatted table.

    Args:
        results: List of match results to display
    """
    table = Table(title="Simulation Results", show_header=True, header_style="bold cyan")

    table.add_column("Request", style="white", no_wrap=False)
    table.add_column("Rule ID", style="yellow")
    table.add_column("Status", style="green", justify="center")
    table.add_column("Location", style="blue", no_wrap=False)

    for result in results:
        # Color-code based on match status
        if result.matched:
            request_str = str(result.request)
        else:
            request_str = f"[red]{result.request}[/red]"

        table.add_row(
            request_str,
            result.rule_display,
            result.status_display,
            result.location_display,
        )

    console.print(table)


def print_coverage_report(report: CoverageReport) -> None:
    """
    Print coverage report with colored output.

    Args:
        report: Coverage report to display
    """
    console.print("\n[bold]Coverage Report:[/bold]")

    # Coverage percentage
    if report.coverage_percent == 100.0:
        console.print(
            f"[green]✓[/green] {len(report.matched_rules)}/{report.total_rules} "
            f"rules matched ([green]{report.coverage_percent:.0f}%[/green])"
        )
    else:
        console.print(
            f"[yellow]⚠[/yellow] {len(report.matched_rules)}/{report.total_rules} "
            f"rules matched ([yellow]{report.coverage_percent:.1f}%[/yellow])"
        )

    # Dead rules
    if report.dead_rules:
        console.print(f"[red]✗[/red] Dead rules (never matched):")
        for rule_id in sorted(report.dead_rules):
            console.print(f"  - [red]{rule_id}[/red]")
    else:
        console.print("[green]✓[/green] No dead rules")


def parse_request_arg(request_str: str) -> Request:
    """
    Parse a request from command-line argument.

    Format: "HOST PATH [QUERY]"

    Args:
        request_str: Request string from CLI

    Returns:
        Parsed Request object

    Raises:
        ValueError: If format is invalid
    """
    parts = request_str.split(None, 2)

    if len(parts) < 2:
        raise ValueError(
            f"Invalid request format: '{request_str}'\n" f"Expected: HOST PATH [QUERY]"
        )

    host = parts[0]
    path = parts[1]
    query = parts[2] if len(parts) == 3 else ""

    return Request(host=host, path=path, query=query)


@app.command()
def main(
    yaml: Optional[Path] = typer.Option(
        None,
        "--yaml",
        "-y",
        help="Path to YAML config file",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    cases: Optional[Path] = typer.Option(
        None,
        "--cases",
        "-c",
        help="Path to test cases file (HOST PATH [QUERY] format)",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    request: Optional[str] = typer.Option(
        None,
        "--request",
        "-r",
        help='Single request to test (format: "HOST PATH [QUERY]")',
    ),
    show_coverage: bool = typer.Option(
        True,
        "--coverage/--no-coverage",
        help="Show coverage report (default: enabled)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output with additional details",
    ),
) -> None:
    """
    Simulate redirect rules against test requests.

    Examples:

        # Test with cases file
        lacuna-sim --yaml domainlist.yaml --cases cases.txt

        # Test single request
        lacuna-sim --yaml domainlist.yaml --request "prod.example.com /blog"

        # Test single request with query
        lacuna-sim --yaml domainlist.yaml --request "prod.example.com /blog page=2"
    """
    # Validate arguments
    if not yaml:
        err_console.print("[red]Error:[/red] --yaml is required")
        raise typer.Exit(1)

    if not cases and not request:
        err_console.print(
            "[red]Error:[/red] Either --cases or --request is required"
        )
        raise typer.Exit(1)

    if cases and request:
        console.print(
            "[yellow]Warning:[/yellow] Both --cases and --request provided, "
            "using --request only"
        )

    # Load config
    try:
        if verbose:
            console.print(f"Loading config from: {yaml}")
        cfg = load_config_from_yaml(yaml)
        if verbose:
            console.print(f"[green]✓[/green] Loaded {len(cfg.hosts)} host(s)")
    except Exception as e:
        err_console.print(f"[red]Error loading config:[/red] {e}")
        raise typer.Exit(1)

    # Load or parse requests
    requests: list[Request] = []
    try:
        if request:
            # Single request from CLI argument
            requests = [parse_request_arg(request)]
        elif cases:
            # Multiple requests from file
            if verbose:
                console.print(f"Loading test cases from: {cases}")
            requests = parse_cases_file(cases)
            if verbose:
                console.print(f"[green]✓[/green] Loaded {len(requests)} test case(s)")
    except Exception as e:
        err_console.print(f"[red]Error loading requests:[/red] {e}")
        raise typer.Exit(1)

    # Simulate requests
    if verbose:
        console.print(f"\nSimulating {len(requests)} request(s)...\n")
    else:
        console.print(f"Simulating {len(requests)} request(s)...\n")

    results = simulate_batch(cfg, requests)

    # Print results table
    print_results_table(results)

    # Print coverage report
    if show_coverage:
        report = generate_coverage_report(cfg, results)
        print_coverage_report(report)

        # Check for unmatched requests
        unmatched = [r for r in results if not r.matched]
        if unmatched:
            console.print(f"\n[yellow]⚠[/yellow] {len(unmatched)} request(s) did not match any rule")

        # Success summary
        if report.all_matched and not unmatched:
            console.print("\n[green bold]✓ All test cases passed![/green bold]")
        else:
            console.print("\n[yellow bold]⚠ Some issues found[/yellow bold]")
            # Exit with error if there are dead rules or unmatched requests
            if report.dead_rules or unmatched:
                raise typer.Exit(1)


if __name__ == "__main__":
    app()
