import os
import sys
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lars_service")
LARS_SRC = "/app/src/LARS"
if LARS_SRC not in sys.path:
    sys.path.insert(0, LARS_SRC)
try:
    from modules.core_query_engine import CoreQueryEngine
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
        db_path = os.environ.get("LARS_DUCKDB_PATH", "/app/src/LARS/data/lars_data.duckdb")
        logger.info(f"Initializing CoreQueryEngine with db_path={db_path}")
        _engine = CoreQueryEngine(db_path=db_path, enable_llm_fallback=False)
    return _engine
class QueryRequest(BaseModel):
    query: str
@app.post("/api/lars/query")
async def query_lars(request: QueryRequest):
    try:
        engine = get_lars_engine()
        if hasattr(engine, "process"):
            result = engine.process(request.query)
        elif hasattr(engine, "process_query"):
            result = engine.process_query(request.query)
        elif hasattr(engine, "ask"):
            result = engine.ask(request.query)
        else:
            return {"success": False, "answer": "No query method found"}
        if isinstance(result, dict):
            answer = result.get("answer") or result.get("result") or str(result)
        elif isinstance(result, tuple):
            answer = str(result[0])
        else:
            answer = str(result)
        return {"success": True, "answer": answer}
    except Exception as e:
        logger.error(f"Query error: {e}")
        return {"success": False, "answer": f"Error: {e}"}
@app.get("/health")
async def health():
    return {"status": "ok", "lars_available": LARS_AVAILABLE}
