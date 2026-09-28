import os
import sys
import logging
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lars_service")
LARS_SRC = os.environ.get(
    "LARS_SRC",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "LARS")
)
if LARS_SRC not in sys.path:
    sys.path.insert(0, LARS_SRC)
try:
    from modules.query.core_query_engine import CoreQueryEngine
    LARS_AVAILABLE = True
    logger.info("✅ CoreQueryEngine imported successfully")
except ImportError as e:
    logger.error(f"Failed to import CoreQueryEngine: {e}")
    LARS_AVAILABLE = False
    CoreQueryEngine = None
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_engine = None
def get_lars_engine():
    global _engine
    if _engine is None:
        if not LARS_AVAILABLE:
            raise Exception("CoreQueryEngine not available")
        db_path = os.environ.get("LARS_DUCKDB_PATH", os.path.join(LARS_SRC, "data", "lars_data_demo.duckdb"))
        logger.info(f"Initializing CoreQueryEngine with db_path={db_path}")
        _engine = CoreQueryEngine(db_path=db_path, enable_llm_fallback=False)
    return _engine
class QueryRequest(BaseModel):
    query: str


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _with_export(payload: dict, question: str, df, engine=None) -> dict:
    """Add "file_url" when the answer has a non-empty table (never for a
    refusal). An export failure is logged and leaves the answer unchanged."""
    if df is None or not hasattr(df, "empty") or df.empty or payload.get("refusal"):
        return payload
    try:
        from modules.reporting.excel_export import answer_info, write_export
        info = answer_info(engine, question, payload["answer"], payload["source"])
        name = write_export(question, df, payload["source"], info)
        payload["file_url"] = f"/api/lars/export/{quote(name)}"
    except Exception as e:
        logger.warning(f"Excel export failed: {e}")
    return payload
@app.post("/api/lars/query")
async def query_lars(request: QueryRequest):
    try:
        # ── فحص مبكر: أسئلة أولوية التفتيش تاخد ملخص صوتي مختصر ──
        # (مش الجدول الكامل — نفس مبدأ عدم قراءة جداول طويلة بالصوت)
        try:
            from modules.inspection.inspection_priority import (
                classify_inspection_priority, extract_priority_params,
                get_top, to_voice_summary,
            )
            kind = classify_inspection_priority(request.query)
            # Priority scores cover all dates: a question that names a period
            # goes through the engine, which refuses (or, live, the semantic layer answers).
            if kind in ("top", "urgent_neighborhood") and not get_lars_engine().names_period(request.query):
                params = extract_priority_params(request.query)
                level = "neighborhood" if kind == "urgent_neighborhood" else params["level"]
                db_path = os.environ.get("LARS_DUCKDB_PATH",
                                          "/app/src/LARS/data/lars_data_demo.duckdb")
                df = get_top(level=level, n=params["top_n"],
                            min_confidence="medium", db_path=db_path)
                if df.empty:
                    df = get_top(level=level, n=params["top_n"], db_path=db_path)
                answer = to_voice_summary(df, level)
                return _with_export({"success": True, "answer": answer, "source": "handler"},
                                    request.query, df)
        except Exception as e:
            logger.warning(f"Priority voice shortcut failed, falling back: {e}")

        engine = get_lars_engine()
        if hasattr(engine, "process"):
            result = engine.process(request.query)
        elif hasattr(engine, "process_query"):
            result = engine.process_query(request.query)
        elif hasattr(engine, "ask"):
            result = engine.ask(request.query)
        else:
            return {"success": False, "answer": "No query method found"}
        df = None
        if isinstance(result, dict):
            answer = result.get("answer") or result.get("result") or str(result)
        elif isinstance(result, tuple):
            answer = str(result[0])
            df = result[1] if len(result) > 1 else None
        else:
            answer = str(result)
        # "semantic" when the semantic fallback (LARS_SEMANTIC_MODE=live) answered
        # a question the handlers refused; "handler" otherwise.
        source = getattr(engine, "last_source", "handler")
        # Why the handlers refused (None for an answer), e.g. "period_not_applied".
        refusal = getattr(engine, "_refusal", None) if source == "handler" else None
        return _with_export({"success": True, "answer": answer, "source": source, "refusal": refusal},
                            request.query, df, engine)
    except Exception as e:
        logger.error(f"Query error: {e}")
        return {"success": False, "answer": f"Error: {e}"}
@app.get("/api/lars/export/{filename}")
async def get_export(filename: str):
    """Serve a workbook written by /api/lars/query — only plain *.xlsx names
    inside the export directory (no "..", no slashes)."""
    from modules.reporting.excel_export import export_path, valid_export_name
    if not valid_export_name(filename):
        raise HTTPException(status_code=400, detail="Invalid export name")
    path = export_path(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Export not found")
    ascii_name = path.name.split("_", 1)[0] + ".xlsx"        # "20260928-094116-55d36e.xlsx"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(path.name)}"
    return FileResponse(path, media_type=XLSX, headers={"Content-Disposition": disposition})


@app.get("/health")
async def health():
    # The engine's semantic mode once it is built, else the one it will use.
    mode = getattr(_engine, "semantic_mode", None)
    if mode is None and LARS_AVAILABLE:
        from modules.semantic.fallback import mode_from_env
        mode = mode_from_env()
    return {"status": "ok", "lars_available": LARS_AVAILABLE, "semantic_mode": mode}
