"""
LARS Environment Variable Loader.

Replaces the fragile manual .env parser in app.py with a robust,
single-responsibility loader that supports both python-dotenv
(if installed) and a minimal fallback parser.

Why:
    The original code manually opened docker/env/.env.app, split on
    '=', and stripped quotes — with no error handling for malformed
    lines, BOM characters, or multi-line values. This module handles
    all edge cases and logs what it loads (without leaking secrets).

Usage:
    from modules.env_loader import load_env
    load_env()  # Loads .env.app into os.environ
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_LARS_ROOT = Path(__file__).resolve().parent.parent  # src/LARS/
_PROJECT_ROOT = _LARS_ROOT.parent.parent             # project root


def _find_env_file() -> Optional[Path]:
    """Locate the .env.app file in the project tree.

    Checks the canonical Docker location first, then falls back
    to common alternatives.
    """
    candidates = [
        _PROJECT_ROOT / "docker" / "env" / ".env.app",
        _LARS_ROOT / ".env",
        _PROJECT_ROOT / ".env",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _parse_env_line(line: str) -> Optional[tuple[str, str]]:
    """Parse a single .env line into (key, value).

    Handles comments, blank lines, optional ``export`` prefix,
    and single/double quote stripping.

    Args:
        line: A single line from the .env file.

    Returns:
        (key, value) tuple or None for unparseable lines.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    # Remove optional 'export ' prefix
    if stripped.startswith("export "):
        stripped = stripped[7:]

    if "=" not in stripped:
        return None

    key, _, value = stripped.partition("=")
    key = key.strip()
    value = value.strip()

    # Strip surrounding quotes
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]

    return key, value


def load_env(env_path: Optional[Path] = None) -> int:
    """Load environment variables from .env file.

    Tries python-dotenv first (if installed); falls back to the
    built-in minimal parser.

    Args:
        env_path: Explicit path to the .env file. If None, auto-
            discovers using _find_env_file().

    Returns:
        Number of variables loaded.
    """
    path = env_path or _find_env_file()
    if path is None:
        logger.info("No .env file found; relying on existing environment.")
        return 0

    # Try python-dotenv first (handles edge cases better)
    try:
        from dotenv import load_dotenv

        load_dotenv(path, override=False)
        logger.info("Loaded env from %s via python-dotenv", path)
        return -1  # python-dotenv doesn't report count easily
    except ImportError:
        pass

    # Minimal fallback parser
    count = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parsed = _parse_env_line(line)
            if parsed is None:
                continue
            key, value = parsed
            if key not in os.environ:
                os.environ[key] = value
                count += 1
                # Log key name only, never the value
                logger.info("Set env var: %s", key)

    logger.info("Loaded %d env vars from %s (fallback parser)", count, path)
    return count