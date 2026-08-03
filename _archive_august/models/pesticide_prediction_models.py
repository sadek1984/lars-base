# src/models/pesticide_prediction_models.py
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime

class PesticideSampleInput(BaseModel):
    vegetable: str
    pesticide_name: str
    pesticide_group: Optional[str] = None
    reading: float
    limits: float
    sample_code: Optional[str] = None
    collection_date: Optional[str] = None  # ⬅️ NEW: Format "YYYY-MM-DD"
    
    @validator('pesticide_group', always=True)
    def set_pesticide_group(cls, v, values):
        """Auto-derive group from pesticide name if not provided"""
        if v is None and 'pesticide_name' in values:
            from models.PesticideClassificationModel import PesticideClassificationModel
            classifier = PesticideClassificationModel()
            v = classifier.classify_pesticide_group(values['pesticide_name'])
        return v
    
    @validator('collection_date', always=True)
    def set_default_date(cls, v):
        """Use current date if not provided"""
        if v is None or v == '':
            v = datetime.now().strftime("%Y-%m-%d")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "vegetable": "tomato",
                "pesticide_name": "Bifenthrin",
                "pesticide_group": "pyrethroid",
                "reading": 21.0,
                "limits": 10.0,
                "sample_code": "SAMPLE_001",
                "collection_date": "2025-06-15"
            }
        }

class BatchPredictionInput(BaseModel):
    samples: list[PesticideSampleInput]
    
    class Config:
        schema_extra = {
            "example": {
                "samples": [
                    {
                        "vegetable": "tomato",
                        "pesticide_name": "Bifenthrin",
                        "reading": 21.0,
                        "limits": 10.0,
                        "collection_date": "2025-06-15"
                    },
                    {
                        "vegetable": "cucumber",
                        "pesticide_name": "Pyridaben",
                        "reading": 8.5,
                        "limits": 15.0,
                        "collection_date": "2025-01-20"
                    }
                ]
            }
        }


class SampleInfo(BaseModel):
    """Sample information in prediction response"""
    sample_code: str
    vegetable: str
    pesticide_group: str
    reading: float
    limits: float
    exceedance_ratio: float

class RiskAssessment(BaseModel):
    """Risk assessment information"""
    risk_level: str
    risk_description: str
    exceedance_factor: float
    pesticide_group_risk: Dict[str, Any]

class PredictionResult(BaseModel):
    """Comprehensive prediction result"""
    success: bool
    sample_info: Optional[SampleInfo] = None
    predictions: Optional[Dict[str, Any]] = None
    risk_assessment: Optional[RiskAssessment] = None
    recommendations: Optional[List[str]] = None
    timestamp: str
    model_version: Optional[str] = None
    error: Optional[str] = None

class BatchPredictionResult(BaseModel):
    """Batch prediction result"""
    success: bool
    total_samples: int
    successful_predictions: int
    failed_predictions: int
    results: List[PredictionResult]
    failures: List[Dict[str, Any]]
    timestamp: str

class ModelStatus(BaseModel):
    """Model status information"""
    model_loaded: bool
    model_path: str
    components_loaded: Dict[str, bool]
    timestamp: str

class PredictionIndexRequest(BaseModel):
    """Request to index prediction results into RAG system"""
    prediction_result: PredictionResult
    project_id: int
    include_in_rag: bool = Field(default=True, description="Whether to include in RAG system")
    metadata_tags: Optional[List[str]] = Field(default=None, description="Additional tags for categorization")