"""Identifier mapping utilities using sec-cik-mapper."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

from sec_cik_mapper import StockMapper

from .exceptions import InvalidInputError

_STOCK_MAPPER = StockMapper()


@dataclass(slots=True)
class MappingResult:
    ticker: Optional[str]
    cik: Optional[str]
    company_name: Optional[str]


def _normalize_cik(cik: str) -> str:
    cleaned = cik.strip().lstrip("0")
    if not cleaned.isdigit():
        raise InvalidInputError(f"Invalid CIK: {cik}")
    return cleaned.zfill(10)


def _dict_lookup(mapping: Dict, key: str):
    if not isinstance(mapping, dict):
        return None
    candidates = [key, key.upper(), key.lower(), key.lstrip("0")]
    for candidate in candidates:
        if candidate in mapping:
            return mapping[candidate]
    try:
        numeric = int(key)
    except ValueError:
        pass
    else:
        if numeric in mapping:
            return mapping[numeric]
    return None


def _find_row_by_column(df, column: str, value: str) -> Dict | None:  # pragma: no cover - optional
    if df is None:
        return None
    try:
        iterrows = df.iterrows  # type: ignore[attr-defined]
    except AttributeError:
        return None
    try:
        for _, row in iterrows():
            if not hasattr(row, "get"):
                continue
            candidate = row.get(column)
            if candidate is None:
                continue
            if column == "cik":
                candidate_value = _normalize_cik(str(candidate))
                if candidate_value == _normalize_cik(value):
                    return dict(row)
            else:
                if str(candidate).upper() == value.upper():
                    return dict(row)
    except Exception:
        return None
    return None


def _resolve_company_name(ticker: str, cik: str | None) -> Optional[str]:
    mapping = getattr(_STOCK_MAPPER, "ticker_to_company_name", None)
    if isinstance(mapping, dict):
        name = _dict_lookup(mapping, ticker)
        if isinstance(name, str):
            return name
    if cik:
        cik_mapping = getattr(_STOCK_MAPPER, "cik_to_company_name", None)
        if isinstance(cik_mapping, dict):
            name = _dict_lookup(cik_mapping, cik)
            if isinstance(name, str):
                return name
    df = getattr(_STOCK_MAPPER, "raw_dataframe", None)
    row = _find_row_by_column(df, "ticker", ticker)
    if row:
        for key in ("company_name", "title", "entity_name"):
            if key in row and isinstance(row[key], str):
                return row[key]
    return None


def map_tickers_to_ciks(tickers: Iterable[str]) -> List[MappingResult]:
    mapping = getattr(_STOCK_MAPPER, "ticker_to_cik", None)
    results: List[MappingResult] = []
    df = getattr(_STOCK_MAPPER, "raw_dataframe", None)

    for ticker in tickers:
        ticker_upper = ticker.upper()
        cik_value = None
        if isinstance(mapping, dict):
            cik_value = _dict_lookup(mapping, ticker_upper)
        if cik_value is None and df is not None:
            row = _find_row_by_column(df, "ticker", ticker_upper)
            if row and "cik" in row:
                cik_value = row["cik"]
        cik_normalized = _normalize_cik(str(cik_value)) if cik_value else None
        company_name = _resolve_company_name(ticker_upper, cik_normalized)
        results.append(MappingResult(ticker=ticker_upper, cik=cik_normalized, company_name=company_name))
    return results


def map_ciks_to_tickers(ciks: Iterable[str]) -> List[MappingResult]:
    ticker_map = getattr(_STOCK_MAPPER, "cik_to_tickers", None)
    results: List[MappingResult] = []
    df = getattr(_STOCK_MAPPER, "raw_dataframe", None)
    company_map = getattr(_STOCK_MAPPER, "cik_to_company_name", None)

    for cik in ciks:
        normalized = _normalize_cik(cik)
        ticker_value = None
        if isinstance(ticker_map, dict):
            entry = _dict_lookup(ticker_map, normalized)
            if isinstance(entry, list) and entry:
                ticker_value = str(entry[0])
            elif isinstance(entry, str):
                ticker_value = entry
        if ticker_value is None and df is not None:
            row = _find_row_by_column(df, "cik", normalized)
            if row and "ticker" in row:
                ticker_value = row["ticker"]
        if ticker_value:
            ticker_value = str(ticker_value).upper()
        company_name = None
        if isinstance(company_map, dict):
            entry = _dict_lookup(company_map, normalized)
            if isinstance(entry, str):
                company_name = entry
        if company_name is None:
            company_name = _resolve_company_name(ticker_value or "", normalized)
        results.append(MappingResult(ticker=ticker_value, cik=normalized, company_name=company_name))
    return results


def get_all_tickers() -> List[str]:
    """Return a sorted list of all ticker symbols known to the mapper."""
    mapping = getattr(_STOCK_MAPPER, "ticker_to_cik", None)
    tickers: Set[str] = set()
    if isinstance(mapping, dict):
        for key in mapping.keys():
            if key is None:
                continue
            tickers.add(str(key).upper())

    if not tickers:
        df = getattr(_STOCK_MAPPER, "raw_dataframe", None)
        if df is not None:
            try:
                for _, row in df.iterrows():  # type: ignore[attr-defined]
                    value = row.get("ticker") if hasattr(row, "get") else None
                    if value:
                        tickers.add(str(value).upper())
            except Exception:
                pass

    if not tickers:
        raise InvalidInputError("Unable to retrieve ticker universe from sec-cik-mapper database.")

    return sorted(tickers)
