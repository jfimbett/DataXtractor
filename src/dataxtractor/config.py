"""Configuration constants for DataXtractor."""
from __future__ import annotations

from pathlib import Path

DEFAULT_OUTPUT_DIR = Path("dataxtractor_output")
DEFAULT_DATE_FORMAT = "%Y-%m-%d"

# SEC EDGAR API endpoints
SEC_API_BASE = "https://data.sec.gov/api"
SEC_COMPANY_FACTS_ENDPOINT = "/xbrl/companyfacts/CIK{cik}.json"

# Headers required by the SEC API. Update the values to your contact details.
SEC_REQUEST_HEADERS = {
    "User-Agent": "jfimbett@gmail.com",
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

# Default chunk size for streaming downloads, should we expand functionality later.
DEFAULT_STREAM_CHUNK = 1024 * 32
