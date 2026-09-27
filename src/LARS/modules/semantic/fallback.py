"""
Semantic fallback: runs only after the deterministic handlers refuse.

  off     nothing is built; the engine behaves exactly as without this layer
  shadow  the user gets the handler answer; the semantic run is only logged
  live    a successful semantic answer replaces the refusal

The LLM call has an 8 s budget; any failure (timeout, invalid JSON, spec
rejected by the validator, no matching samples) returns the original refusal.
In live mode the validated QuerySpec is cached per normalized question, so a
repeated question gets the same answer. Every run is logged to
logs/semantic_log.jsonl.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import duckdb

from modules.query.text_norm import norm
from modules.semantic.answer import SemanticAnswer, answer_spec
from modules.semantic.catalog import build_catalog
from modules.semantic.llm import TIMEOUT_S, SpecProvider, build_system_prompt, parse_spec
from modules.semantic.query_spec import QuerySpec

MODES = ("off", "shadow", "live")
# Refusals the semantic layer may try to answer. Out-of-scope is never one.
SEMANTIC_ELIGIBLE = frozenset({
    "not_understood", "unresolved_product", "unresolved_period",
    "unresolved_municipality", "multi_month", "category",
})
DEFAULT_LOG = Path(__file__).resolve().parents[4] / "logs" / "semantic_log.jsonl"


def mode_from_env() -> str:
    mode = os.environ.get("LARS_SEMANTIC_MODE", "off").strip().lower()
    return mode if mode in MODES else "off"


def init_semantic(db_path: str, mode: Optional[str] = None) -> Tuple[str, Optional["SemanticFallback"]]:
    """(mode, fallback). Off, or any setup failure → ("off", None)."""
    mode = mode or mode_from_env()
    if mode == "off":
        return "off", None
    try:
        return mode, SemanticFallback(db_path, mode)
    except Exception:
        logging.exception("Semantic layer disabled: setup failed")
        return "off", None


class SemanticFallback:
    def __init__(self, db_path: str, mode: str, provider: Optional[SpecProvider] = None,
                 log_path: Optional[Path] = None):
        from modules.query.entity_resolver import EntityResolver
        self.db_path, self.mode = str(db_path), mode
        self.catalog = build_catalog(self.db_path)
        with duckdb.connect(self.db_path, read_only=True) as con:
            self.resolver = EntityResolver(con)
        self.system_prompt = build_system_prompt(self.catalog)
        if provider is None:
            from modules.semantic.llm import GeminiVertexProvider
            provider = GeminiVertexProvider()
        self.provider = provider
        self.log_path = Path(os.environ.get("LARS_SEMANTIC_LOG", log_path or DEFAULT_LOG))
        self.cache: Dict[str, QuerySpec] = {}
        # Separate pools: a shadow run waits on an LLM call, so they must never
        # compete for the same workers.
        self._llm_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="semantic-llm")
        self._shadow_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="semantic-shadow")
        self._log_lock = threading.Lock()

    # ── spec ────────────────────────────────────────────────────────────────
    def fill_spec(self, question: str, inline: bool = False) -> Tuple[Optional[QuerySpec], dict]:
        """Ask the LLM (8 s budget). Returns (spec or None, llm log record).
        `inline`: call the provider on this thread (shadow runs are already in
        the background; the provider's own 8 s HTTP timeout bounds the call)."""
        rec = {"provider": self.provider.name, "raw": None, "error": None}
        t0 = time.perf_counter()
        try:
            raw = (self.provider.fill(question, self.system_prompt) if inline else
                   self._llm_pool.submit(self.provider.fill, question, self.system_prompt).result(timeout=TIMEOUT_S))
            rec["raw"] = raw
            return parse_spec(raw), rec
        except FutureTimeout:
            rec["error"] = f"timeout after {TIMEOUT_S:g}s"
        except Exception as e:  # provider, network, JSON or schema error
            rec["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        finally:
            rec["latency_ms"] = round(1000 * (time.perf_counter() - t0))
        return None, rec

    # ── answer ──────────────────────────────────────────────────────────────
    def answer(self, question: str, handler_text: str, refusal: str, serve: bool,
               use_cache: bool = True, inline: bool = False) -> Optional[SemanticAnswer]:
        """Semantic answer, or None (→ keep the refusal). Always logged."""
        t0 = time.perf_counter()
        key = norm(question)
        cached = self.cache.get(key) if use_cache else None
        if cached is not None:
            spec, llm = cached, {"provider": self.provider.name, "cache_hit": True, "latency_ms": 0}
        else:
            spec, llm = self.fill_spec(question, inline=inline)
            llm["cache_hit"] = False
        ans: Optional[SemanticAnswer] = None
        error = llm.get("error")
        if spec is not None:
            try:
                ans = answer_spec(spec, self.catalog, self.resolver, self.db_path, question=question)
            except Exception as e:
                error = f"{type(e).__name__}: {str(e)[:300]}"
        ok = ans is not None and ans.ok
        if ok and use_cache and self.mode == "live":
            self.cache[key] = spec
        self._log({
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "question": question,
            "mode": self.mode,
            "handler": {"refusal": refusal, "text": (handler_text or "")[:500]},
            "llm": llm,
            "spec": spec.model_dump(mode="json", exclude_defaults=True) if spec else None,
            "validation": {"ok": ok, "message": None if ok else (ans.text if ans else error)},
            "sql": ans.info.get("sql") if ok else None,
            "row_count": int(len(ans.df)) if ok and ans.df is not None else None,
            "coverage_added": list(ans.resolved.added_from_question) if ok and ans.resolved else [],
            "answer": ans.text if ok else None,
            "latency_ms": round(1000 * (time.perf_counter() - t0)),
            "served": bool(ok and serve),
        })
        return ans if ok else None

    def submit_shadow(self, question: str, handler_text: str, refusal: str) -> None:
        """Shadow mode: run and log in the background; the user is not delayed."""
        self._shadow_pool.submit(self._shadow_run, question, handler_text, refusal)

    def _shadow_run(self, question: str, handler_text: str, refusal: str) -> None:
        try:
            self.answer(question, handler_text, refusal, serve=False, use_cache=False, inline=True)
        except Exception:
            logging.exception(f"Shadow semantic run failed: {question!r}")

    def _log(self, record: dict) -> None:
        try:
            with self._log_lock:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception:
            logging.exception("Could not write the semantic log")
