# src/api/routes/risk_assessment.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.enhanced_risk_assessment_service import EnhancedRiskAssessment

risk_ass_router = APIRouter()

# Initialize risk assessment service
risk_service = EnhancedRiskAssessment('./data/processed_data_output.xlsx')

class RiskAssessmentRequest(BaseModel):
    vegetable: str
    # vegetable_category: str
    pesticide_group: str
    reading: float
    limit: float
    is_compliant: bool

@risk_ass_router.post("/api/v1/risk/assess")
async def assess_risk(request: RiskAssessmentRequest):
    """Enhanced risk assessment endpoint"""
    
    result = risk_service.calculate_enhanced_risk_score(
        vegetable=request.vegetable,
        pesticide_group=request.pesticide_group,
        reading=request.reading,
        limit=request.limit,
        is_compliant=request.is_compliant
    )
    
    return result

@risk_ass_router.get("/api/v1/risk/thresholds")
async def get_risk_thresholds():
    """Get group-specific critical thresholds"""
    return risk_service.critical_thresholds