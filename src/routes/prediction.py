# src/routes/pesticide_prediction_routes.py
from fastapi import APIRouter, HTTPException, Depends, Request, status, BackgroundTasks
from fastapi.responses import JSONResponse
import logging
from typing import Dict, Any

from services.pesticide_prediction_service import PesticidePredictionService
from models.ProjectModel import ProjectModel
from models.db_schemes import DataChunk
from models.ChunkModel import ChunkModel
from controllers import NLPController

from models.pesticide_prediction_models import (
    PesticideSampleInput, 
    BatchPredictionInput,
    PredictionResult,
    BatchPredictionResult,
    ModelStatus
)
from services.pesticide_prediction_service import PesticidePredictionService

logger = logging.getLogger(__name__)

prediction_router = APIRouter(
    prefix="/api/v1/prediction",
    tags=["Pesticide Prediction"]
)

# Initialize the prediction service (singleton)
prediction_service = None

def get_prediction_service():
    """Dependency to get prediction service - UPDATED"""
    global prediction_service
    if prediction_service is None:
        try:
            prediction_service = PesticidePredictionService()
            
            # Service always initializes, but may use fallback mode
            logger.info("Prediction service initialized")
            
            # Log a warning if models aren't loaded
            if not prediction_service.model_loaded:
                logger.warning("⚠️  Prediction service running in FALLBACK mode")
                logger.warning("   To use ML models, run: python train_models.py")
            
        except Exception as e:
            logger.error(f"Failed to initialize prediction service: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Prediction service initialization failed: {str(e)}"
            )
    return prediction_service


@prediction_router.get("/status", response_model=ModelStatus)
async def get_model_status(service: PesticidePredictionService = Depends(get_prediction_service)):
    """
    Get current model status and health check
    """
    try:
        status = service.get_model_status()
        return ModelStatus(**status)
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")


# src/routes/prediction.py

@prediction_router.post("/predict", response_model=PredictionResult)
async def predict_sample_compliance(
    sample: PesticideSampleInput,
    service: PesticidePredictionService = Depends(get_prediction_service)
):
    """
    Predict compliance and risk for a single pesticide sample
    
    Now includes:
    - Specific pesticide name (not just group)
    - Season-aware predictions based on collection_date
    - Hybrid validation (Statistical + ML)
    """
    try:
        result = service.predict_sample_compliance(
            vegetable=sample.vegetable,
            pesticide_name=sample.pesticide_name,        # ⬅️ Specific pesticide
            pesticide_group=sample.pesticide_group,
            reading=sample.reading,
            limits=sample.limits,
            sample_code=sample.sample_code,
            collection_date=sample.collection_date       # ⬅️ Date for season
        )
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=result.get('error', 'Prediction failed')
            )
        
        return PredictionResult(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal prediction error: {str(e)}"
        )

@prediction_router.post("/predict/batch", response_model=BatchPredictionResult)
async def predict_batch_samples(
    batch_input: BatchPredictionInput,
    service: PesticidePredictionService = Depends(get_prediction_service)
):
    """
    Predict compliance for multiple samples
    Now supports season-aware batch predictions
    """
    try:
        samples_list = []
        for sample in batch_input.samples:
            samples_list.append({
                'vegetable': sample.vegetable,
                'pesticide_name': sample.pesticide_name,
                'pesticide_group': sample.pesticide_group,
                'reading': sample.reading,
                'limits': sample.limits,
                'sample_code': sample.sample_code,
                'collection_date': sample.collection_date
            })
        
        result = service.predict_batch_samples(samples_list)
        
        return BatchPredictionResult(**result)
        
    except Exception as e:
        logger.error(f"Batch prediction failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Batch prediction error: {str(e)}"
        )

@prediction_router.post("/predict-and-index/{project_id}")
async def predict_and_index_to_rag(
    project_id: int,
    sample: PesticideSampleInput,
    request: Request,
    background_tasks: BackgroundTasks,
    include_in_rag: bool = True,
    service: PesticidePredictionService = Depends(get_prediction_service)
):
    """
    Predict sample compliance and automatically index results into RAG system
    
    This endpoint combines real-time prediction with automatic indexing
    for seamless integration between prediction and historical analysis.
    """
    try:
        # Get prediction
        prediction_result = service.predict_sample_compliance(
            vegetable=sample.vegetable,
            pesticide_group=sample.pesticide_group,
            reading=sample.reading,
            limits=sample.limits,
            sample_code=sample.sample_code
        )
        
        if not prediction_result['success']:
            raise HTTPException(
                status_code=400,
                detail=prediction_result.get('error', 'Prediction failed')
            )
        
        # Index to RAG system in background if requested
        if include_in_rag:
            background_tasks.add_task(
                index_prediction_to_rag,
                request,
                project_id,
                prediction_result
            )
        
        return {
            "prediction": PredictionResult(**prediction_result),
            "indexing_status": "queued" if include_in_rag else "skipped",
            "project_id": project_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Predict and index failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Predict and index error: {str(e)}"
        )

async def index_prediction_to_rag(request: Request, project_id: int, prediction_result: Dict[str, Any]):
    """
    Background task to index prediction results into RAG system
    """
    try:
        # Get project
        project_model = await ProjectModel.create_instance(db_client=request.app.db_client)
        project = await project_model.get_project_or_create_one(project_id=project_id)
        
        # Create NLP controller
        nlp_controller = NLPController(
            vectordb_client=request.app.vectordb_client,
            generation_client=request.app.generation_client,
            embedding_client=request.app.embedding_client,
            template_parser=request.app.template_parser,
        )
        
        # Format prediction as document
        formatted_content = format_prediction_for_indexing(prediction_result)
        
        # Create chunk for indexing
        from langchain.schema import Document
        
        doc = Document(
            page_content=formatted_content,
            metadata={
                'source': 'prediction_api',
                'type': 'real_time_prediction',
                'sample_code': prediction_result['sample_info']['sample_code'],
                'vegetable': prediction_result['sample_info']['vegetable'],
                'pesticide_group': prediction_result['sample_info']['pesticide_group'],
                'compliance_probability': prediction_result['predictions'].get('compliance', {}).get('probability_compliant', 0),
                'risk_level': prediction_result['risk_assessment']['risk_level'],
                'timestamp': prediction_result['timestamp']
            }
        )
        
        # Create chunk record
        chunk_model = await ChunkModel.create_instance(db_client=request.app.db_client)
        
        chunk_record = DataChunk(
            chunk_text=formatted_content,
            chunk_metadata=doc.metadata,
            chunk_order=1,
            chunk_project_id=project.project_id,
            chunk_asset_id=1  # Default asset for predictions
        )
        
        # Save to database
        await chunk_model.create_chunk(chunk_record)
        
        # Index to vector database
        await nlp_controller.index_into_vector_db(
            project=project,
            chunks=[chunk_record],
            chunks_ids=[chunk_record.chunk_id]
        )
        
        logger.info(f"Successfully indexed prediction to RAG for project {project_id}")
        
    except Exception as e:
        logger.error(f"Failed to index prediction to RAG: {e}")

def format_prediction_for_indexing(prediction_result: Dict[str, Any]) -> str:
    """
    Format prediction result as searchable text for RAG indexing
    """
    sample_info = prediction_result['sample_info']
    risk_assessment = prediction_result['risk_assessment']
    recommendations = prediction_result.get('recommendations', [])
    
    content = f"""
**Real-time Prediction Result**

Sample Code: {sample_info['sample_code']}
Vegetable: {sample_info['vegetable']}
Pesticide Group: {sample_info['pesticide_group']}
Reading: {sample_info['reading']} μg/kg
Limits: {sample_info['limits']} μg/kg
Exceedance Ratio: {sample_info['exceedance_ratio']}

**Compliance Assessment:**
{prediction_result['predictions'].get('compliance', {}).get('prediction', 'Unknown')}
Confidence: {prediction_result['predictions'].get('compliance', {}).get('probability_compliant', 0):.2%}

**Risk Assessment:**
Risk Level: {risk_assessment['risk_level']}
Description: {risk_assessment['risk_description']}
Exceedance Factor: {risk_assessment['exceedance_factor']}x

**Recommendations:**
{chr(10).join([f"- {rec}" for rec in recommendations])}

**Analysis Date:** {prediction_result['timestamp']}
**Model Version:** {prediction_result.get('model_version', 'Unknown')}
"""
    
    return content.strip()

@prediction_router.get("/health")
async def health_check():
    """
    Simple health check endpoint
    """
    return {
        "status": "healthy",
        "service": "pesticide_prediction_api",
        "timestamp": "2024-01-01T00:00:00"
    }






# # routes/prediction.py
# from fastapi import APIRouter, HTTPException, Depends
# from fastapi.responses import JSONResponse
# import logging
# from typing import Dict, Any

# from models.pesticide_prediction_models import (
#     PesticideSampleInput, 
#     BatchPredictionInput,
#     PredictionResult,
#     BatchPredictionResult,
#     ModelStatus
# )
# from services.pesticide_prediction_service import PesticidePredictionService

# logger = logging.getLogger(__name__)

# # Create router
# prediction_router = APIRouter(
#     prefix="/api/v1/prediction",
#     tags=["Pesticide Prediction"]
# )

# # Initialize the prediction service (singleton)
# prediction_service = None

# def get_prediction_service():
#     """Dependency to get prediction service"""
#     global prediction_service
#     if prediction_service is None:
#         try:
#             prediction_service = PesticidePredictionService()
#             logger.info("Prediction service initialized successfully")
#         except Exception as e:
#             logger.error(f"Failed to initialize prediction service: {e}")
#             raise HTTPException(
#                 status_code=503,
#                 detail=f"Prediction service initialization failed: {str(e)}"
#             )
#     return prediction_service

# @prediction_router.get("/health")
# async def health_check():
#     """Simple health check endpoint"""
#     return {
#         "status": "healthy",
#         "service": "pesticide_prediction_api",
#         "timestamp": "2024-01-01T00:00:00"
#     }

# @prediction_router.get("/status", response_model=ModelStatus)
# async def get_model_status(service: PesticidePredictionService = Depends(get_prediction_service)):
#     """
#     Get current model status and health check
#     """
#     try:
#         status = service.get_model_status()
#         return ModelStatus(**status)
#     except Exception as e:
#         logger.error(f"Status check failed: {e}")
#         raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")

# @prediction_router.post("/predict", response_model=PredictionResult)
# async def predict_sample_compliance(
#     sample: PesticideSampleInput,
#     service: PesticidePredictionService = Depends(get_prediction_service)
# ):
#     """
#     Predict compliance and risk for a single pesticide sample
    
#     This endpoint provides real-time classification for new samples including:
#     - Compliance probability
#     - Risk assessment
#     - Actionable recommendations
#     """
#     try:
#         result = service.predict_sample_compliance(
#             vegetable=sample.vegetable,
#             pesticide_group=sample.pesticide_group,
#             reading=sample.reading,
#             limits=sample.limits,
#             sample_code=sample.sample_code
#         )
        
#         if not result['success']:
#             raise HTTPException(
#                 status_code=400,
#                 detail=result.get('error', 'Prediction failed')
#             )
        
#         return PredictionResult(**result)
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Prediction failed: {e}")
#         raise HTTPException(
#             status_code=500,
#             detail=f"Internal prediction error: {str(e)}"
#         )

# @prediction_router.post("/predict/{project_id}", response_model=PredictionResult)
# async def predict_sample_with_project(
#     project_id: int,
#     sample: PesticideSampleInput,
#     service: PesticidePredictionService = Depends(get_prediction_service)
# ):
#     """
#     Predict compliance and risk for a single pesticide sample with project context
#     """
#     try:
#         result = service.predict_sample_compliance(
#             vegetable=sample.vegetable,
#             pesticide_group=sample.pesticide_group,
#             reading=sample.reading,
#             limits=sample.limits,
#             sample_code=sample.sample_code
#         )
        
#         if not result['success']:
#             raise HTTPException(
#                 status_code=400,
#                 detail=result.get('error', 'Prediction failed')
#             )
        
#         # Add project context to the result
#         result['project_id'] = project_id
        
#         return PredictionResult(**result)
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Prediction failed for project {project_id}: {e}")
#         raise HTTPException(
#             status_code=500,
#             detail=f"Internal prediction error: {str(e)}"
#         )

# @prediction_router.post("/predict/batch", response_model=BatchPredictionResult)
# async def predict_batch_samples(
#     batch_input: BatchPredictionInput,
#     service: PesticidePredictionService = Depends(get_prediction_service)
# ):
#     """
#     Predict compliance for multiple samples in batch
    
#     Efficiently process multiple samples at once with detailed results
#     for each sample and overall batch statistics.
#     """
#     try:
#         # Convert Pydantic models to dictionaries for service
#         samples_dict = [sample.dict() for sample in batch_input.samples]
        
#         result = service.predict_batch_samples(samples_dict)
        
#         if not result['success']:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Batch prediction failed"
#             )
        
#         return BatchPredictionResult(**result)
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Batch prediction failed: {e}")
#         raise HTTPException(
#             status_code=500,
#             detail=f"Batch prediction error: {str(e)}"
#         )