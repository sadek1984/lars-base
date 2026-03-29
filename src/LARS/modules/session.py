"""
LARS Session State Manager.

Centralizes Streamlit session state initialization into a single,
declarative configuration instead of repeating ``if key not in
st.session_state`` blocks.

Why:
    app.py (and its duplicate app_refactored.py) had 8+ individual
    ``if`` checks. Adding a new state variable required editing two
    files. This module makes it a one-line addition to _DEFAULTS.

Usage:
    from modules.session import initialize_session_state
    initialize_session_state()
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from modules.api_service import DEFAULT_YEAR

# ============================================================================
# DEFAULT VALUES (single source of truth)
# ============================================================================

_DEFAULTS: Dict[str, Any] = {
    "chat_messages": [
        {
            "role": "assistant",
            "content": (
                "👋 Hello! I'm your **pesticide analysis AI assistant** — "
                "ready to help you explore, assess, and analyze pesticide "
                "data with ease.\n\n"
                "💬 **Type your question below and I'll analyze the data "
                "for you** 🚀"
            ),
        }
    ],
    "selected_year": DEFAULT_YEAR,
    "indexed_years": set(),
    "project_id": "default_project",
    "intro_shown": False,
    "current_page": "🏠 Dashboard Overview",
    "data_loaded": False,
}


def initialize_session_state(
    extra_defaults: Dict[str, Any] | None = None,
) -> None:
    """Ensure all required session-state keys exist.

    Only sets a key if it is not already present, preserving any
    values that were set during the current session.

    Args:
        extra_defaults: Optional additional defaults to register
            (e.g., page-specific state). Merged with _DEFAULTS;
            extra_defaults takes precedence on conflict.
    """
    merged = {**_DEFAULTS, **(extra_defaults or {})}
    for key, value in merged.items():
        if key not in st.session_state:
            st.session_state[key] = value