"""
LARS — Laboratory Analytics & Risk System.

Main Streamlit entry point. This single file replaces both the
original ``app.py`` and its duplicate ``app_refactored.py``.

Responsibilities (and ONLY these):
    1. Page configuration & env setup
    2. Session state initialization
    3. Sidebar navigation rendering
    4. Page routing

All business logic lives in the ``modules/`` package.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st
import logging

# ── Internal modules ────────────────────────────────────────────
from modules.api_service import API_BASE_URL, get_api_client, initialize_session_state
from modules.dashboard import show_dashboard_overview
from modules.env_loader import load_env
from modules.predictions import show_predictions_page
from modules.risk_analysis import show_risk_analysis_page
from modules.statistical_insights import show_statistical_insights_page
from modules.trend_analysis import show_trend_analysis_page

if TYPE_CHECKING:
    from modules.api_service import APIClient

# ── Environment & Page Config ──────────────────────────────────
load_env()

st.set_page_config(
    page_title="🔮 LARS Dashboard",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Page registry ──────────────────────────────────────────────
# Lazy import for ai_assistant to keep startup fast (it pulls in
# openai, duckdb, etc.).
PAGES: dict[str, str] = {
    "🏠 Dashboard Overview": "modules.dashboard:show_dashboard_overview",
    "🤖 AI Assistant": "modules.ai_assistant:show_chat_page",
    "📊 Risk Analysis": "modules.risk_analysis:show_risk_analysis_page",
    "📈 Trend Analysis": "modules.trend_analysis:show_trend_analysis_page",
    "📋 Statistical Insights": "modules.statistical_insights:show_statistical_insights_page",
    "🔮 Predictions": "modules.predictions:show_predictions_page",
    "🎯 أولوية التفتيش": "modules.inspection_priority_page:show_inspection_priority_page",
    "📑 التقارير المتقدمة": "modules.advanced_reports:show_advanced_reports_page",
}


def _resolve_page_func(dotted_path: str):
    """Import and return a page function from 'module.path:func_name'.

    Why lazy import:
        ai_assistant.py imports heavy dependencies (openai, duckdb,
        google.generativeai). Importing everything at startup adds
        ~3s to first load. This loads each page module only when
        actually navigated to.
    """
    module_path, _, func_name = dotted_path.rpartition(":")
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


# ── UI Components ──────────────────────────────────────────────

def render_animated_header() -> None:
    """Render the LARS hero banner with CSS animation."""
    html = textwrap.dedent("""\
        <div class="lars-hero-container">
            <div class="lars-content">
                <h1 class="lars-main-title">
                    <span class="letter" style="animation-delay:0s">L</span>
                    <span class="letter" style="animation-delay:.1s">A</span>
                    <span class="letter" style="animation-delay:.2s">R</span>
                    <span class="letter" style="animation-delay:.3s">S</span>
                </h1>
                <h2 class="lars-subtitle-enhanced">
                    <span class="highlight">Laboratory</span>
                    <span class="accent-text">Analytics</span> &amp;
                    <span class="accent-text">Risk</span>
                    <span class="highlight">System</span>
                </h2>
                <p class="lars-tagline">
                    Powered by AI · Trusted by Scientists · Protecting Public Health
                </p>
                <div class="feature-badges">
                    <div class="badge">Real-time Analysis</div>
                    <div class="badge">Advanced Analytics</div>
                    <div class="badge">Secure &amp; Compliant</div>
                </div>
            </div>
        </div>
        <style>
        .lars-hero-container{background:linear-gradient(135deg,#e8f5e9,#c8e6c9 25%,#a5d6a7 50%,#81c784 75%,#66bb6a);padding:60px 20px;border-radius:0 0 30px 30px;text-align:center;margin-bottom:40px;margin-top:-30px;box-shadow:0 8px 30px rgba(46,125,50,.15)}
        .lars-main-title{font-size:4.5rem;font-weight:900;letter-spacing:15px;color:#1b5e20;margin-bottom:20px}
        .letter{display:inline-block;animation:letterPop .8s ease-out forwards}
        @keyframes letterPop{0%{opacity:0;transform:translateY(-30px)}100%{opacity:1;transform:translateY(0)}}
        .lars-subtitle-enhanced{font-size:1.8rem;color:#1b5e20;margin-bottom:15px}
        .highlight{font-weight:700;color:#2e7d32}.accent-text{color:#1b5e20;font-weight:700}
        .lars-tagline{font-style:italic;color:#388e3c;margin-bottom:25px}
        .feature-badges{display:flex;justify-content:center;gap:15px}
        .badge{background:#fff;padding:5px 15px;border-radius:20px;font-size:.9rem;color:#2e7d32;box-shadow:0 2px 5px rgba(0,0,0,.1)}
        </style>
    """)
    st.markdown(html, unsafe_allow_html=True)


def render_sidebar(api_client: "APIClient") -> None:
    """Render the navigation sidebar."""
    with st.sidebar:
        st.markdown("# 📍 LARS Menu")

        if st.button("🔄 Check API Status", use_container_width=True, type="primary"):
            with st.spinner("Checking..."):
                health = api_client.health_check()
                st.success("✅ Connected") if health else st.error("❌ Disconnected")

        st.markdown("---")

        page_options = list(PAGES.keys())
        current = st.session_state.get("current_page", page_options[0])
        if current not in page_options:
            current = page_options[0]

        st.session_state.current_page = st.selectbox(
            "Navigate to:",
            page_options,
            index=page_options.index(current),
            key="page_selector",
        )

        st.markdown("---")
        st.info(f"API Base: `{API_BASE_URL}`")
        st.caption("LARS v3.0 — Refactored")


# ── Main ───────────────────────────────────────────────────────

def main() -> None:
    """Application entry point."""
    initialize_session_state()
    api_client = get_api_client()

    # Load initial data once per session
    if not st.session_state.data_loaded:
        data_path = Path(__file__).parent / "data" / "6_months.xlsx"
        if data_path.exists():
            try:
                st.session_state.df = pd.read_excel(data_path, header=1)
                st.session_state.data_loaded = True
            except Exception as exc:
                st.warning(f"⚠️ Could not load initial data: {exc}")

    # Hero header (shown once)
    if not st.session_state.intro_shown:
        render_animated_header()
        st.session_state.intro_shown = True

    render_sidebar(api_client)

    # Route to selected page
    page_key = st.session_state.current_page
    dotted = PAGES.get(page_key)
    if dotted:
        page_func = _resolve_page_func(dotted)
        page_func(api_client)
    else:
        st.error(f"Page '{page_key}' is not implemented yet.")


if __name__ == "__main__":
    main()