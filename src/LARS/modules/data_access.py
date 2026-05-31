"""
LARS Centralized Data Access Layer.

Single entry point for loading data (Excel/CSV) and connecting to DuckDB.

Why this module exists:
    load_data_from_path() and get_duckdb_connection() were duplicated
    in utils.py and ai_assistant.py with DIFFERENT path logic — meaning
    different modules could silently read different databases. This
    module enforces one canonical path resolution strategy.

Usage:
    from modules.data_access import load_dataframe, get_duckdb_read, get_duckdb_write
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

# ============================================================================
# PATH RESOLUTION
# ============================================================================
# All paths are resolved relative to the LARS package root:
#   src/LARS/  (parent of the 'modules' directory)

_MODULE_DIR = Path(__file__).resolve().parent          # src/LARS/modules/
_LARS_ROOT = _MODULE_DIR.parent                        # src/LARS/
_DATA_DIR = _LARS_ROOT / "data"
_DUCKDB_PATH = _DATA_DIR / "lars_data.duckdb"
_EXCEL_PATH = _DATA_DIR / "6_months.xlsx"


def _resolve_data_path(filename: str) -> Optional[Path]:
    """Resolve a data file path, checking multiple fallback locations.

    Args:
        filename: Name of the data file to find.

    Returns:
        Resolved Path or None if not found anywhere.

    Why multiple paths:
        In Docker the app runs from /app/src/LARS/, but during local
        development the CWD varies. We check the canonical location
        first, then fall back to common alternatives.
    """
    candidates = [
        _DATA_DIR / filename,
        Path("data") / filename,
        Path("src/LARS/data") / filename,
        Path("/app/src/LARS/data") / filename,
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


# ============================================================================
# DATAFRAME LOADING
# ============================================================================

def load_dataframe(
    filename: str = "6_months.xlsx",
) -> Optional[pd.DataFrame]:
    """Load the primary analysis DataFrame.

    Supports .csv, .xlsx, and .xls files. Returns None (instead of
    raising) when the file is missing so callers can show a friendly
    upload prompt.

    Args:
        filename: Data file name inside the data directory.

    Returns:
        pandas DataFrame or None if the file cannot be found/read.
    """
    path = _resolve_data_path(filename)
    if path is None:
        logger.warning("Data file '%s' not found in any known location.", filename)
        return None

    try:
        if path.suffix == ".csv":
            return pd.read_csv(path)
        return pd.read_excel(path)
    except Exception:
        logger.exception("Failed to load data from %s", path)
        return None


# ============================================================================
# DUCKDB CONNECTIONS
# ============================================================================

def _resolve_duckdb_path() -> Optional[Path]:
    """Find the DuckDB database file."""
    return _resolve_data_path("lars_data.duckdb")


def get_duckdb_read() -> Optional[duckdb.DuckDBPyConnection]:
    """Get a read-only DuckDB connection.

    Returns:
        DuckDB connection or None if the database file is missing.
    """
    db_path = _resolve_duckdb_path()
    if db_path is None:
        logger.warning("DuckDB file not found.")
        return None
    return duckdb.connect(str(db_path), read_only=True)


def get_duckdb_write() -> Optional[duckdb.DuckDBPyConnection]:
    """Get a read-write DuckDB connection.

    Returns:
        DuckDB connection or None if the database file is missing.

    Warning:
        Callers are responsible for closing the connection. Prefer
        using this as a context manager or in a try/finally block.
    """
    db_path = _resolve_duckdb_path()
    if db_path is None:
        logger.warning("DuckDB file not found.")
        return None
    return duckdb.connect(str(db_path), read_only=False)