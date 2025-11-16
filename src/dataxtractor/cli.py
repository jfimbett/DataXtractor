"""Command line interface for DataXtractor."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import click
from rich.console import Console
from rich.theme import Theme
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.traceback import install

from .config import DEFAULT_OUTPUT_DIR
from .exceptions import DataXtractorError, DownloadError, InvalidInputError
from .io_utils import (
    ensure_output_directory,
    normalize_date,
    resolve_identifier_inputs,
)
from .mapping import get_all_tickers, map_ciks_to_tickers, map_tickers_to_ciks
from .sec_client import (
    download_company_facts,
    get_company_facts_payload,
    summarize_available_concepts,
)
from .yahoo_client import download_price_history

install(show_locals=False)

_theme = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "yellow",
        "error": "bold red",
        "highlight": "bright_cyan",
    }
)

_console = Console(theme=_theme)

_DEFAULT_PRICES_DIR = DEFAULT_OUTPUT_DIR / "prices"
_DEFAULT_SEC_DIR = DEFAULT_OUTPUT_DIR / "sec"


def _handle_error(exc: DataXtractorError) -> None:
    _console.print(f"[error]{exc}[/error]")


@click.group(help="Download market and accounting data with ease.")
@click.option(
    "--quiet",
    is_flag=True,
    default=False,
    help="Suppress success messages; errors will still be shown.",
)
@click.pass_context
def cli(ctx: click.Context, quiet: bool) -> None:
    """Entry point for the DataXtractor CLI."""
    ctx.obj = {"quiet": quiet}


@cli.command(help="Download historical price data from Yahoo Finance.")
@click.option(
    "--tickers",
    "tickers",
    multiple=True,
    help="Ticker symbols to download (can be provided multiple times).",
)
@click.option(
    "--ticker-file",
    type=click.Path(path_type=Path),
    help="Path to a text file containing ticker symbols (one per line).",
)
@click.option(
    "--all-tickers",
    is_flag=True,
    help="Download for every ticker available in the sec-cik-mapper database.",
)
@click.option(
    "--start",
    required=False,
    help="Start date (YYYY-MM-DD). If omitted, the full available history is retrieved.",
)
@click.option(
    "--end",
    required=False,
    help="End date (YYYY-MM-DD). If omitted, data is fetched up to the most recent trading day.",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=DEFAULT_OUTPUT_DIR,
    show_default=True,
    help="Folder where the CSV files will be saved.",
)
@click.pass_context
def prices(
    ctx: click.Context,
    tickers: Sequence[str],
    ticker_file: Path | None,
    all_tickers: bool,
    start: str | None,
    end: str | None,
    output_dir: Path,
) -> None:
    try:
        if all_tickers:
            if tickers or ticker_file:
                raise InvalidInputError("Use --all-tickers without specifying tickers or ticker files.")
            resolved_tickers = get_all_tickers()
        else:
            resolved_tickers = resolve_identifier_inputs(
                tickers,
                ticker_file,
                label="ticker symbol",
            )
        start_dt = normalize_date(start, param_name="start") if start else None
        end_dt = normalize_date(end, param_name="end") if end else None
        if start_dt and end_dt and start_dt >= end_dt:
            raise InvalidInputError("Start date must be before end date.")
        ensure_output_directory(output_dir)
        result = download_price_history(
            tickers=resolved_tickers,
            start=start_dt,
            end=end_dt,
            output_dir=output_dir,
            console=_console,
        )
        if result.failures:
            preview = "\n".join(result.failures[:10])
            if len(result.failures) > 10:
                preview += f"\n... (+{len(result.failures) - 10} more)"
            _console.print(
                "[warning]Price download issues:[/warning]\n" + preview
            )
        if not ctx.obj.get("quiet"):
            _console.print(
                f"[success]Saved {len(result.saved_paths)} price files to {output_dir.resolve()}[/success]"
            )
    except DataXtractorError as exc:
        _handle_error(exc)
        ctx.exit(1)


@cli.command(name="full-download", help="Download prices and SEC company facts for the provided tickers.")
@click.option(
    "--tickers",
    multiple=True,
    help="Ticker symbols to process (can be provided multiple times).",
)
@click.option(
    "--ticker-file",
    type=click.Path(path_type=Path),
    help="Path to a text file containing ticker symbols.",
)
@click.option(
    "--all-tickers",
    is_flag=True,
    help="Process every ticker available in the sec-cik-mapper database.",
)
@click.option(
    "--start",
    required=False,
    help="Start date for price history (YYYY-MM-DD). If omitted, the full available history is retrieved.",
)
@click.option(
    "--end",
    required=False,
    help="End date for price history (YYYY-MM-DD). If omitted, data is fetched up to the most recent trading day.",
)
@click.option(
    "--prices-dir",
    type=click.Path(path_type=Path),
    default=_DEFAULT_PRICES_DIR,
    show_default=True,
    help="Output folder for downloaded price CSV files.",
)
@click.option(
    "--sec-dir",
    type=click.Path(path_type=Path),
    default=_DEFAULT_SEC_DIR,
    show_default=True,
    help="Output folder for SEC company facts JSON files.",
)
@click.pass_context
def full_download(
    ctx: click.Context,
    tickers: Sequence[str],
    ticker_file: Path | None,
    all_tickers: bool,
    start: str | None,
    end: str | None,
    prices_dir: Path,
    sec_dir: Path,
) -> None:
    """Run the end-to-end workflow for each ticker."""

    try:
        if all_tickers:
            if tickers or ticker_file:
                raise InvalidInputError("Use --all-tickers without specifying tickers or ticker files.")
            resolved_tickers = get_all_tickers()
        else:
            resolved_tickers = resolve_identifier_inputs(
                tickers,
                ticker_file,
                label="ticker symbol",
            )
        start_dt = normalize_date(start, param_name="start") if start else None
        end_dt = normalize_date(end, param_name="end") if end else None
        if start_dt and end_dt and start_dt >= end_dt:
            raise InvalidInputError("Start date must be before end date.")

        ensure_output_directory(prices_dir)
        ensure_output_directory(sec_dir)

        mapping_results = map_tickers_to_ciks(resolved_tickers)
        if len(mapping_results) <= 20 and not all_tickers:
            _render_mapping_table(mapping_results, label="Ticker to CIK")
        else:
            mapped = sum(1 for entry in mapping_results if entry.cik)
            missing = len(mapping_results) - mapped
            _console.print(
                f"[info]Resolved {mapped} CIKs (missing {missing}) for {len(mapping_results)} tickers.[/info]"
            )

        known_ciks = [entry for entry in mapping_results if entry.cik]
        missing_ciks = [entry.ticker for entry in mapping_results if not entry.cik]

        if not known_ciks:
            raise DownloadError("No CIK mappings were found for the supplied tickers.")

        price_result = download_price_history(
            tickers=resolved_tickers,
            start=start_dt,
            end=end_dt,
            output_dir=prices_dir,
            console=_console,
        )
        if price_result.failures:
            preview_prices = "\n".join(price_result.failures[:10])
            if len(price_result.failures) > 10:
                preview_prices += f"\n... (+{len(price_result.failures) - 10} more)"
            _console.print(
                "[warning]Price download issues:[/warning]\n" + preview_prices
            )

        sec_files: list[Path] = []
        sec_failures: list[str] = []
        progress = Progress(
            SpinnerColumn(style="magenta"),
            TextColumn("{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=_console,
            transient=True,
        )

        with progress:
            task_id = progress.add_task("Downloading SEC company facts", total=len(known_ciks))
            for entry in known_ciks:
                try:
                    path = download_company_facts(
                        cik=entry.cik or "",
                        taxonomy=None,
                        concept=None,
                        output_dir=sec_dir,
                        output_format="json",
                        console=_console,
                        quiet=True,
                    )
                    sec_files.append(path)
                except DownloadError as exc:
                    sec_failures.append(f"{entry.ticker or entry.cik}: {exc}")
                finally:
                    progress.advance(task_id)

        if missing_ciks:
            preview_missing = ", ".join(missing_ciks[:10])
            if len(missing_ciks) > 10:
                preview_missing += f", ... (+{len(missing_ciks) - 10} more)"
            _console.print(
                f"[warning]Tickers without CIK mappings: {preview_missing}[/warning]"
            )

        if sec_failures:
            preview_sec = "\n".join(sec_failures[:10])
            if len(sec_failures) > 10:
                preview_sec += f"\n... (+{len(sec_failures) - 10} more)"
            _console.print(
                "[warning]Issues while downloading SEC data:\n" + preview_sec + "[/warning]"
            )

        if not sec_files:
            raise DownloadError("No SEC company facts files were saved. See warnings above.")

        if not ctx.obj.get("quiet"):
            _console.print(
                f"[success]Saved {len(price_result.saved_paths)} price files to {prices_dir.resolve()}[/success]"
            )
            _console.print(
                f"[success]Saved {len(sec_files)} SEC files to {sec_dir.resolve()}[/success]"
            )

    except DataXtractorError as exc:
        _handle_error(exc)
        ctx.exit(1)


@cli.command(name="company-facts", help="Download SEC company facts for a specific CIK.")
@click.option("--cik", required=True, help="Central Index Key (CIK) identifier.")
@click.option("--taxonomy", help="Taxonomy name, for example us-gaap.")
@click.option("--concept", help="Concept name within the selected taxonomy.")
@click.option(
    "--output-format",
    type=click.Choice(["json", "csv"], case_sensitive=False),
    default="json",
    show_default=True,
    help="Output format. CSV requires taxonomy and concept.",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=DEFAULT_OUTPUT_DIR,
    show_default=True,
    help="Folder where the SEC payload will be saved.",
)
@click.option(
    "--list-concepts/--no-list-concepts",
    default=False,
    help="List available taxonomy and concept combinations before downloading.",
)
@click.option(
    "--limit",
    type=int,
    default=20,
    show_default=True,
    help="Number of concepts to show when listing available options.",
)
@click.pass_context
def company_facts(
    ctx: click.Context,
    cik: str,
    taxonomy: str | None,
    concept: str | None,
    output_format: str,
    output_dir: Path,
    list_concepts: bool,
    limit: int,
) -> None:
    try:
        ensure_output_directory(output_dir)
        payload = get_company_facts_payload(cik)

        if list_concepts:
            summarize_available_concepts(payload, console=_console, limit=limit)

        if output_format == "csv" and not (taxonomy and concept):
            raise InvalidInputError("CSV output requires both taxonomy and concept.")

        path = download_company_facts(
            cik=cik,
            taxonomy=taxonomy,
            concept=concept,
            output_dir=output_dir,
            output_format=output_format.lower(),
            console=_console,
            payload=payload,
        )
        if not ctx.obj.get("quiet"):
            _console.print(f"[success]Saved SEC data to {path.resolve()}[/success]")
    except DataXtractorError as exc:
        _handle_error(exc)
        ctx.exit(1)


@cli.command(name="map-tickers", help="Map ticker symbols to their CIK identifiers.")
@click.option(
    "--tickers",
    multiple=True,
    help="Ticker symbols to map (can be provided multiple times).",
)
@click.option(
    "--ticker-file",
    type=click.Path(path_type=Path),
    help="Path to a text file containing ticker symbols.",
)
@click.pass_context
def map_ticker_command(
    ctx: click.Context,
    tickers: Sequence[str],
    ticker_file: Path | None,
) -> None:
    try:
        resolved_tickers = resolve_identifier_inputs(
            tickers,
            ticker_file,
            label="ticker symbol",
        )
        results = map_tickers_to_ciks(resolved_tickers)
        _render_mapping_table(results, label="Ticker to CIK")
    except DataXtractorError as exc:
        _handle_error(exc)
        ctx.exit(1)


@cli.command(name="map-ciks", help="Map CIK identifiers to their ticker symbols.")
@click.option(
    "--ciks",
    multiple=True,
    help="CIK identifiers to map (can be provided multiple times).",
)
@click.option(
    "--cik-file",
    type=click.Path(path_type=Path),
    help="Path to a text file containing CIK identifiers.",
)
@click.pass_context
def map_cik_command(
    ctx: click.Context,
    ciks: Sequence[str],
    cik_file: Path | None,
) -> None:
    try:
        resolved_ciks = resolve_identifier_inputs(
            ciks,
            cik_file,
            label="CIK",
        )
        results = map_ciks_to_tickers(resolved_ciks)
        _render_mapping_table(results, label="CIK to Ticker")
    except DataXtractorError as exc:
        _handle_error(exc)
        ctx.exit(1)


def _render_mapping_table(results, label: str) -> None:
    from rich.table import Table

    table = Table(title=label, header_style="bold cyan")
    table.add_column("Ticker", style="green")
    table.add_column("CIK", style="cyan")
    table.add_column("Company Name", style="white")

    for entry in results:
        table.add_row(entry.ticker or "-", entry.cik or "-", entry.company_name or "-")

    _console.print(table)


def main() -> None:
    cli(prog_name="dataxtractor")


if __name__ == "__main__":  # pragma: no cover
    main()
