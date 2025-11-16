"""SEC EDGAR API client utilities."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests
from rich.console import Console
from rich.table import Table

from .config import (
    SEC_API_BASE,
    SEC_COMPANY_FACTS_ENDPOINT,
    SEC_REQUEST_HEADERS,
)
from .exceptions import DownloadError, InvalidInputError
from .io_utils import build_output_path


def _normalize_cik(cik: str) -> str:
    cleaned = cik.strip().lstrip("0")
    if not cleaned.isdigit():
        raise InvalidInputError(f"Invalid CIK: {cik}")
    return cleaned.zfill(10)


def get_company_facts_payload(cik: str) -> Dict:
    normalized = _normalize_cik(cik)
    url = f"{SEC_API_BASE}{SEC_COMPANY_FACTS_ENDPOINT.format(cik=normalized)}"
    response = requests.get(url, headers=SEC_REQUEST_HEADERS, timeout=30)
    if response.status_code == 404:
        raise DownloadError(f"No company facts found for CIK {normalized}")
    if response.status_code != 200:
        raise DownloadError(
            f"SEC API returned status {response.status_code} for CIK {normalized}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise DownloadError("Failed to parse JSON response from SEC API") from exc


def _select_concept(
    payload: Dict,
    taxonomy: Optional[str],
    concept: Optional[str],
) -> Dict:
    if not taxonomy and not concept:
        return payload

    if not taxonomy or not concept:
        raise InvalidInputError("Specify both taxonomy and concept to filter the response")

    facts = payload.get("facts", {})
    taxonomy_bucket = facts.get(taxonomy)
    if not taxonomy_bucket:
        raise DownloadError(f"Taxonomy '{taxonomy}' not found for the selected CIK")

    concept_payload = taxonomy_bucket.get(concept)
    if not concept_payload:
        raise DownloadError(
            f"Concept '{concept}' not found within taxonomy '{taxonomy}' for the selected CIK"
        )
    return concept_payload


def _flatten_concept(concept_payload: Dict) -> List[Dict[str, Optional[str]]]:
    observations: List[Dict[str, Optional[str]]] = []
    for unit, entries in concept_payload.get("units", {}).items():
        for item in entries:
            observations.append(
                {
                    "unit": unit,
                    "value": item.get("val"),
                    "accn": item.get("accn"),
                    "fy": item.get("fy"),
                    "fp": item.get("fp"),
                    "form": item.get("form"),
                    "frame": item.get("frame"),
                    "end": item.get("end"),
                    "start": item.get("start"),
                }
            )
    if not observations:
        raise DownloadError("No reported values available for the requested concept")
    return observations


def download_company_facts(
    *,
    cik: str,
    taxonomy: Optional[str],
    concept: Optional[str],
    output_dir: Path,
    output_format: str,
    console: Console,
    payload: Dict | None = None,
    quiet: bool = False,
) -> Path:
    """Download company facts and persist in the requested format."""
    if payload is None:
        payload = get_company_facts_payload(cik)
    selection = _select_concept(payload, taxonomy, concept)

    if taxonomy and concept:
        observations = _flatten_concept(selection)
        filename = f"CIK{_normalize_cik(cik)}_{taxonomy}_{concept}.{output_format}"
        output_path = build_output_path(output_dir, filename)
        if output_format == "csv":
            fieldnames = list(observations[0].keys())
            with output_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(observations)
        else:
            with output_path.open("w", encoding="utf-8") as handle:
                json.dump(observations, handle, indent=2)

        if not quiet:
            console.print(
                f"[bold green]Saved concept data for {taxonomy}:{concept} to {output_path}[/bold green]"
            )
        return output_path

    filename = f"CIK{_normalize_cik(cik)}_company_facts.json"
    output_path = build_output_path(output_dir, filename)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(selection, handle, indent=2)

    if not quiet:
        console.print(
            f"[bold green]Saved full company facts payload to {output_path}[/bold green]"
        )
    return output_path


def summarize_available_concepts(
    payload: Dict,
    console: Console,
    limit: Optional[int] = None,
) -> None:
    """Render a summary table of available taxonomy and concept combinations."""
    facts = payload.get("facts", {})
    table = Table(title="Available Concepts", show_header=True, header_style="bold magenta")
    table.add_column("Taxonomy", style="cyan")
    table.add_column("Concept", style="green")
    table.add_column("Label")

    count = 0
    for taxonomy, concepts in facts.items():
        for concept_name, concept_payload in concepts.items():
            table.add_row(
                taxonomy,
                concept_name,
                concept_payload.get("label", ""),
            )
            count += 1
            if limit and count >= limit:
                console.print(table)
                console.print(
                    f"[yellow]Showing first {limit} concepts. Use --limit to adjust.[/yellow]"
                )
                return
    console.print(table)
