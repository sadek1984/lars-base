# main.py - REPLACE your import section with this:

from fastapi import FastAPI
from routes.base import base_router  
from routes.data import data_router
from routes.data import debug_router
from routes import nlp
from helper.config import get_settings
from stores.llm.LLMProviderFactory import LLMProviderFactory
from stores.VectorDB.VectorDBProviderFactory import VectorDBProviderFactory
from stores.llm.templates.template_parser import TemplateParser
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from utils.metrics import setup_metrics
from controllers import NLPController
from routes.risk_assessment_routes import risk_router
from routes import iso
from dependencies import init_dependencies
from motor.motor_asyncio import AsyncIOMotorClient
from routes.time_series import timeseries_router, load_and_train_models
from routes.dashboards import dashboard_router
import logging
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from services.pesticide_prediction_service import PesticidePredictionService
import os
from routes import analytics, risk_assessment

app = FastAPI(
    title="Pesticide & ISO RAG System",
    description="Unified system for pesticide analysis and ISO 17025 compliance"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup Prometheus metrics
setup_metrics(app)

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Import prediction router cleanly
try:
    from routes.prediction import prediction_router
    logger.info("Successfully imported prediction_router")
    print("Successfully imported prediction_router")
except Exception as e:
    logger.error(f"Failed to import prediction_router: {e}")
    print(f"Failed to import prediction_router: {e}")
    prediction_router = None

# ... keep your existing startup_span and shutdown_span functions ...

async def startup_span():
    settings = get_settings()
    postgres_conn = f"postgresql+asyncpg://{settings.POSTGRES_USERNAME}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_MAIN_DATABASE}"

    app.db_engine = create_async_engine(postgres_conn)
    app.db_client = sessionmaker(
        app.db_engine, class_=AsyncSession, expire_on_commit=False
    )
    llm_provider_factory = LLMProviderFactory(settings)
    vectordb_provider_factory = VectorDBProviderFactory(config=settings, db_client=app.db_client)

    # generation client
    app.generation_client = llm_provider_factory.create(provider=settings.GENERATION_BACKEND)
    app.generation_client.set_generation_model(model_id = settings.GENERATION_MODEL_ID)
    print(settings.EMBEDDING_BACKEND)

    # embedding client
    app.embedding_client = llm_provider_factory.create(provider=settings.EMBEDDING_BACKEND)
    app.embedding_client.set_embedding_model(model_id=settings.EMBEDDING_MODEL_ID,
                                             embedding_size=settings.EMBEDDING_MODEL_SIZE)

    # vector db client
    app.vectordb_client = vectordb_provider_factory.create(
    provider=settings.VECTOR_DB_BACKEND
    )
    await app.vectordb_client.connect()

    app.template_parser = TemplateParser(
        language=settings.PRIMARY_LANG,
        default_language=settings.DEFAULT_LANG,
    )
    init_dependencies(app.db_client, app.vectordb_client)

    # Debug routes at startup
    print("\n=== All Registered Routes ===")
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            print(f"{route.methods} {route.path}")
    print("=== End Routes ===\n")

    load_and_train_models()
    
    # Debug routes at startup
    print("\n=== All Registered Routes ===")
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            print(f"{route.methods} {route.path}")
    print("=== End Routes ===\n")

    """Train models on startup - just like time series forecasting"""
    
    logger.info("🚀 Application Startup - Training Models")
    logger.info("=" * 80)
    
    # 1. Train Time Series Forecasting Models (existing)
    logger.info("\n📈 Training Time Series Forecasting Models...")
    load_and_train_models()
    
    # 2. Train Pesticide Classification Models (NEW - same pattern)
    logger.info("\n🤖 Training Pesticide Classification Models...")
    
    # Check if models already exist
    model_path = Path("single_dataset_system/trained_models")
    
    if model_path.exists() and list(model_path.glob("*.pkl")):
        logger.info("✅ Prediction models already exist - skipping training")
        logger.info(f"   Models found at: {model_path}")
    else:
        logger.info("🔧 No existing models found - training new models...")
        
        # Define dataset path (same as your time series data)
        dataset_path = os.getenv("PREDICTION_DATASET_PATH", "/app/data/dataset.xlsx")
        
        # Train and save models
        success = PesticidePredictionService.train_and_save_models(
            dataset_path=dataset_path,
            output_dir="single_dataset_system"
        )
        
        if success:
            logger.info("✅ Prediction models trained and ready!")
        else:
            logger.warning("⚠️  Prediction model training failed - will use fallback mode")
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ All Models Ready - API Started Successfully!")
    logger.info("=" * 80)

@app.get("/")
def root():
    return {
        "message": "Pesticide Analysis API",
        "endpoints": {
            "prediction": "/api/v1/prediction/predict",
            "forecasting": "/api/v1/timeseries/predict",
            "docs": "/docs"
        }
    }

async def shutdown_span():
    app.db_engine.dispose()
    await app.vectordb_client.disconnect()
    
app.on_event("startup")(startup_span)
app.on_event("shutdown")(shutdown_span)

# Include all routers
app.include_router(base_router)
app.include_router(data_router)
app.include_router(nlp.nlp_router)
app.include_router(debug_router)
app.include_router(risk_router, prefix="/api/v1")
app.include_router(iso.router)
app.include_router(timeseries_router)
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(analytics.analytics_router)
app.include_router(risk_assessment.risk_ass_router, tags=["Risk Assessment"])


# Include prediction router
if prediction_router:
    app.include_router(prediction_router)
    print("Successfully included prediction_router")
    print(f"Prediction endpoints added with prefix: {prediction_router.prefix}")
else:
    print("ERROR: prediction_router is None!")

# In main.py startup_span function:
try:
    load_and_train_models()
    logger.info("Model training completed successfully")
except Exception as e:
    logger.error(f"Model training failed: {e}")
    # Don't let this crash the entire app

# ... rest of your main.py code ...