"""
Semantic layer, Phase 3: engine integration (modes, fallback rules, cache,
logging, service source) with a fake provider — no network.

Run:  pytest tests/test_semantic_phase3.py -v
"""
import json
import logging
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LARS = REPO / "src" / "LARS"
DB_PATH = LARS / "data" / "lars_data_demo.duckdb"
sys.path.insert(0, str(LARS))
sys.path.insert(0, str(REPO))

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="lars_data_demo.duckdb not present")

from modules.query.messages import CATEGORY_UNSUPPORTED_MESSAGE  # noqa: E402
from modules.semantic import fallback as fb  # noqa: E402
from modules.semantic.llm import SpecProvider  # noqa: E402

NUTS_NC = "كم عدد العينات غير المطابقة في المكسرات؟"          # category refusal
HANDLER_Q = "كم عدد عينات الطماطم غير المطابقة؟"              # answered by handlers


class FakeProvider(SpecProvider):
    name = "fake"

    def __init__(self, answers=None, delay=0.0, raise_exc=None):
        self.answers, self.delay, self.raise_exc, self.calls = answers or {}, delay, raise_exc, []

    def fill(self, question, system_prompt):
        self.calls.append(question)
        if self.delay:
            time.sleep(self.delay)
        if self.raise_exc:
            raise self.raise_exc
        return self.answers.get(question, '{"metric": "sample_count", "unsupported": true, "reason": "x"}')


NUTS_SPEC = '{"metric": "noncompliant_count", "filters": {"category": ["المكسرات"]}}'


@pytest.fixture(scope="module")
def engine_off():
    logging.disable(logging.CRITICAL)
    from modules.query.core_query_engine import CoreQueryEngine
    return CoreQueryEngine(db_path=str(DB_PATH))


def with_semantic(engine, mode, provider, tmp_path):
    engine.semantic_mode = mode
    engine._semantic = fb.SemanticFallback(str(DB_PATH), mode, provider=provider,
                                           log_path=tmp_path / "semantic_log.jsonl")
    return engine._semantic


@pytest.fixture
def engine(engine_off):
    yield engine_off
    engine_off.semantic_mode, engine_off._semantic = "off", None


def log_lines(sem):
    p = sem.log_path
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


# ── off ──────────────────────────────────────────────────────────────────────

def test_off_builds_nothing(monkeypatch, engine_off):
    monkeypatch.delenv("LARS_SEMANTIC_MODE", raising=False)
    assert fb.mode_from_env() == "live"            # the default since 0a5b710
    monkeypatch.setenv("LARS_SEMANTIC_MODE", "off")
    assert fb.init_semantic(str(DB_PATH)) == ("off", None)
    monkeypatch.setenv("LARS_SEMANTIC_MODE", "bogus")
    assert fb.init_semantic(str(DB_PATH)) == ("off", None)
    assert engine_off.semantic_mode == "off" and engine_off._semantic is None


def test_off_keeps_the_refusal(engine_off):
    text, df = engine_off.process(NUTS_NC)[:2]
    assert (text, df, engine_off.last_source) == (CATEGORY_UNSUPPORTED_MESSAGE, None, "handler")


def test_setup_failure_falls_back_to_off(monkeypatch):
    monkeypatch.setattr(fb, "SemanticFallback", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no ADC")))
    assert fb.init_semantic(str(DB_PATH), "live") == ("off", None)


# ── live ─────────────────────────────────────────────────────────────────────

def test_live_answers_a_refused_question(engine, tmp_path):
    sem = with_semantic(engine, "live", FakeProvider({NUTS_NC: NUTS_SPEC}), tmp_path)
    text, df = engine.process(NUTS_NC)[:2]
    assert engine.last_source == "semantic"
    assert text.startswith("فهمت سؤالك كالتالي") and df["non_compliant"].iloc[0] == 5
    rec = log_lines(sem)[-1]
    assert rec["served"] is True and rec["handler"]["refusal"] == "category" and rec["row_count"] == 1
    for k in ("timestamp", "question", "mode", "spec", "validation", "sql", "answer", "latency_ms"):
        assert k in rec


def test_live_never_touches_handler_answers(engine, engine_off, tmp_path):
    engine.semantic_mode, engine._semantic = "off", None
    base = engine.process(HANDLER_Q)[:2]
    provider = FakeProvider()
    with_semantic(engine, "live", provider, tmp_path)
    got = engine.process(HANDLER_Q)[:2]
    assert provider.calls == [] and engine.last_source == "handler"
    assert got[0] == base[0] and got[1].to_csv() == base[1].to_csv()


OUT_OF_SCOPE_IDS = ["C016", "C025", "C026", "C028", "D018", "D021", "D027", "D041", "D042", "D043",
                    "D044", "E013", "E021", "E027", "E034"]


def test_live_never_answers_out_of_scope(engine, tmp_path):
    import csv
    with (REPO / "phase0" / "questions_bank.csv").open(encoding="utf-8") as f:
        bank = {r["id"]: r["question"] for r in csv.DictReader(f)}
    provider = FakeProvider(answers={})
    with_semantic(engine, "live", provider, tmp_path)
    for qid in OUT_OF_SCOPE_IDS:
        engine.process(bank[qid])
        assert engine._refusal == "out_of_scope" and engine.last_source == "handler", qid
    assert provider.calls == []


@pytest.mark.parametrize("provider", [
    FakeProvider(raise_exc=RuntimeError("503")),
    FakeProvider({NUTS_NC: "not json"}),
    FakeProvider({NUTS_NC: '{"metric": "noncompliant_count", "sql": "DROP TABLE x"}'}),
    FakeProvider({NUTS_NC: '{"metric": "noncompliant_count", "filters": {"category": ["الحلويات"]}}'}),
    FakeProvider({NUTS_NC: '{"metric": "sample_count", "unsupported": true, "reason": "x"}'}),
])
def test_any_failure_returns_the_original_refusal(engine, tmp_path, provider):
    sem = with_semantic(engine, "live", provider, tmp_path)
    text, df = engine.process(NUTS_NC)[:2]
    assert (text, df, engine.last_source) == (CATEGORY_UNSUPPORTED_MESSAGE, None, "handler")
    assert log_lines(sem)[-1]["served"] is False


def test_timeout_returns_the_original_refusal(engine, tmp_path, monkeypatch):
    monkeypatch.setattr(fb, "TIMEOUT_S", 0.2)
    sem = with_semantic(engine, "live", FakeProvider({NUTS_NC: NUTS_SPEC}, delay=1.0), tmp_path)
    t0 = time.perf_counter()
    text = engine.process(NUTS_NC)[0]
    assert text == CATEGORY_UNSUPPORTED_MESSAGE and time.perf_counter() - t0 < 1.0
    assert "timeout" in log_lines(sem)[-1]["llm"]["error"]


def test_live_caches_the_validated_spec(engine, tmp_path):
    provider = FakeProvider({NUTS_NC: NUTS_SPEC})
    sem = with_semantic(engine, "live", provider, tmp_path)
    first = engine.process(NUTS_NC)[0]
    second = engine.process(NUTS_NC.replace("ة", "ه"))[0]           # same normalized question
    assert first == second and len(provider.calls) == 1
    assert log_lines(sem)[-1]["llm"]["cache_hit"] is True


# ── shadow ───────────────────────────────────────────────────────────────────

def test_shadow_serves_the_handler_answer_and_logs(engine, tmp_path):
    sem = with_semantic(engine, "shadow", FakeProvider({NUTS_NC: NUTS_SPEC}), tmp_path)
    text, df = engine.process(NUTS_NC)[:2]
    assert (text, df, engine.last_source) == (CATEGORY_UNSUPPORTED_MESSAGE, None, "handler")
    sem._shadow_pool.shutdown(wait=True)
    rec = log_lines(sem)[-1]
    assert rec["mode"] == "shadow" and rec["served"] is False and rec["validation"]["ok"] is True


# ── service ──────────────────────────────────────────────────────────────────

def test_service_reports_the_source(monkeypatch):
    pytest.importorskip("fastapi")
    import asyncio
    import lars_service

    class Stub:
        last_source = "semantic"

        def process(self, q):
            return "answer", None
    monkeypatch.setattr(lars_service, "get_lars_engine", lambda: Stub())
    monkeypatch.setattr("modules.inspection.inspection_priority.classify_inspection_priority", lambda q: None)
    out = asyncio.run(lars_service.query_lars(lars_service.QueryRequest(query="x")))
    assert out == {"success": True, "answer": "answer", "source": "semantic"}
