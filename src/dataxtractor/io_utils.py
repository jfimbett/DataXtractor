"""Utility helpers for file and input handling."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence

from .config import DEFAULT_DATE_FORMAT
from .exceptions import InvalidInputError


def normalize_date(date_str: str, *, param_name: str) -> datetime:
    """Parse a date string using the default format."""
    try:
        return datetime.strptime(date_str, DEFAULT_DATE_FORMAT)
    except ValueError as exc:
        raise InvalidInputError(
            f"{param_name} must match {DEFAULT_DATE_FORMAT} (received '{date_str}')"
        ) from exc


def ensure_output_directory(output_path: Path) -> None:
    """Create the output directory if it does not exist."""
    output_path.mkdir(parents=True, exist_ok=True)


def _read_identifier_file(file_path: Path) -> List[str]:
    if not file_path.exists():
        raise InvalidInputError(f"File not found: {file_path}")
    values: List[str] = []
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        candidate = raw_line.strip()
        if candidate:
            values.append(candidate)
    if not values:
        raise InvalidInputError(f"No identifiers found in {file_path}")
    return values


def resolve_identifier_inputs(
    identifiers: Sequence[str] | None,
    identifier_file: Path | None,
    *,
    label: str,
) -> List[str]:
    """Combine identifiers provided inline or via file input."""
    collected: list[str] = []

    if identifiers:
        collected.extend([value.strip() for value in identifiers if value.strip()])

    if identifier_file:
        collected.extend(_read_identifier_file(identifier_file))

    unique = []
    seen = set()
    for value in collected:
        upper_value = value.upper()
        if upper_value not in seen:
            unique.append(upper_value)
            seen.add(upper_value)

    if not unique:
        raise InvalidInputError(
            f"Provide at least one {label} via arguments or a file with one entry per line."
        )
    return unique


def build_output_path(base_dir: Path, filename: str) -> Path:
    """Compose an output path ensuring the suffixed filename."""
    ensure_output_directory(base_dir)
    return base_dir / filename
