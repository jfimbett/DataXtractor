"""Yahoo Finance data download helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import yfinance as yf
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from .exceptions import DownloadError
from .io_utils import build_output_path


@dataclass(slots=True)
class PriceDownloadResult:
    saved_paths: List[Path]
    failures: List[str]


def download_price_history(
    *,
    tickers: Iterable[str],
    start: Optional[datetime],
    end: Optional[datetime],
    output_dir: Path,
    console: Console,
) -> PriceDownloadResult:
    """Download historical price data for tickers and save to CSV files."""
    ticker_list: Sequence[str] = list(tickers)
    if not ticker_list:
        raise DownloadError("No tickers provided for price download.")

    saved_paths: List[Path] = []
    failures: list[str] = []

    progress = Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )

    with progress:
        task_id = progress.add_task("Downloading price history", total=len(ticker_list))
        for ticker in ticker_list:
            try:
                params: dict = {"auto_adjust": True}
                if start is None and end is None:
                    params["period"] = "max"
                else:
                    if start is not None:
                        params["start"] = start
                    if end is not None:
                        params["end"] = end
                    if start is None and end is not None:
                        params.setdefault("period", "max")
                history = yf.Ticker(ticker).history(**params)
            except Exception as exc:  # yfinance raises generic exceptions
                failures.append(f"{ticker}: {exc}")
                progress.advance(task_id)
                continue

            if history.empty:
                range_msg = "max to latest"
                if start and end:
                    range_msg = f"{start.date()} to {end.date()}"
                elif start and not end:
                    range_msg = f"{start.date()} onward"
                elif not start and end:
                    range_msg = f"max to {end.date()}"
                failures.append(f"{ticker}: no data returned within {range_msg}")
                progress.advance(task_id)
                continue

            start_label = start.date().isoformat() if start else "max"
            end_label = end.date().isoformat() if end else "latest"
            output_path = build_output_path(output_dir, f"{ticker}_{start_label}_{end_label}.csv")
            history.to_csv(output_path)
            saved_paths.append(output_path)
            progress.advance(task_id)

    if not saved_paths:
        raise DownloadError("No price files were saved. Check the ticker symbols and date range.")

    return PriceDownloadResult(saved_paths=saved_paths, failures=failures)
