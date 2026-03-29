"""
Risk Assessment API Routes
Location: src/routes/risk_assessment_routes.py
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List

from models.risk_assessment_models import (
    RiskAssessmentRequest,
    CustomRiskAssessmentRequest, 
    IndividualRiskResult,
    PesticideADIResponse,
    FoodIntakeResponse,
    ConstantsResponse,
    PopulationType
)
from services.risk_assessment_service import RiskAssessmentService
from helper.risk_assessment_config import RiskAssessmentConfig

# Create router
risk_router = APIRouter(prefix="/risk-assessment", tags=["Risk Assessment"])

def get_risk_service():
    """Dependency to get risk assessment service"""
    return RiskAssessmentService()

def get_config():
    """Dependency to get configuration"""
    return RiskAssessmentConfig()

@risk_router.post("/evaluate", response_model=IndividualRiskResult)
async def evaluate_pesticide_risk(
    request: RiskAssessmentRequest,
    service: RiskAssessmentService = Depends(get_risk_service)
):
    """
    تقييم المخاطر الصحية الأساسي للمواطن السعودي
    Basic health risk assessment for Saudi citizens
    """
    try:
        result = service.assess_sample_risk(
            sample_code="USER_INPUT",
            pesticide_name=request.pesticide_name,
            food_item=request.food_item,
            concentration_ppb=request.concentration_ppb,
            population_type=request.population_type
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Risk assessment failed: {str(e)}")

@risk_router.post("/custom-evaluate", response_model=IndividualRiskResult)
async def custom_evaluate_pesticide_risk(
    request: CustomRiskAssessmentRequest,
    service: RiskAssessmentService = Depends(get_risk_service)
):
    """
    تقييم المخاطر مع قيم مخصصة
    Risk assessment with custom values
    """
    try:
        result = service.assess_sample_risk(
            sample_code="CUSTOM_INPUT",
            pesticide_name=request.pesticide_name,
            food_item=request.food_item,
            concentration_ppb=request.concentration_ppb,
            population_type=request.population_type,
            custom_adi=request.adi_value,
            custom_food_intake=request.food_intake,
            custom_body_weight=request.body_weight
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Custom risk assessment failed: {str(e)}")

@risk_router.get("/pesticide-adi/{pesticide_name}", response_model=PesticideADIResponse)
async def get_pesticide_adi(
    pesticide_name: str,
    config: RiskAssessmentConfig = Depends(get_config)
):
    """
    الحصول على قيمة ADI لمبيد معين
    Get ADI value for specific pesticide
    """
    adi = config.PESTICIDE_ADI.get(pesticide_name)
    
    if not adi:
        raise HTTPException(
            status_code=404, 
            detail=f"ADI not found for pesticide: {pesticide_name}"
        )
    
    return PesticideADIResponse(
        pesticide_name=pesticide_name,
        adi_value=adi,
        available_pesticides=list(config.PESTICIDE_ADI.keys())
    )

@risk_router.get("/food-intake/{food_item}", response_model=FoodIntakeResponse)
async def get_food_intake(
    food_item: str,
    config: RiskAssessmentConfig = Depends(get_config)
):
    """
    الحصول على الاستهلاك اليومي لغذاء معين في السعودية
    Get daily food intake for specific food in Saudi Arabia
    """
    intake = config.SAUDI_FOOD_INTAKE.get(food_item.lower())
    
    if not intake:
        return FoodIntakeResponse(
            food_item=food_item,
            daily_intake=None,
            message="No specific data available, using default 0.05 kg/day",
            available_foods=list(config.SAUDI_FOOD_INTAKE.keys())
        )
    
    return FoodIntakeResponse(
        food_item=food_item,
        daily_intake=intake,
        available_foods=list(config.SAUDI_FOOD_INTAKE.keys())
    )

@risk_router.get("/constants", response_model=ConstantsResponse)
async def get_all_constants(config: RiskAssessmentConfig = Depends(get_config)):
    """
    الحصول على جميع القيم الثابتة المستخدمة في التقييم
    Get all constants used in risk assessment
    """
    return ConstantsResponse(
        pesticide_adi=config.PESTICIDE_ADI,
        saudi_food_intake=config.SAUDI_FOOD_INTAKE,
        saudi_body_weight=config.SAUDI_BODY_WEIGHT,
        food_name_mapping=config.FOOD_NAME_MAPPING,
        last_updated="2024-09-01"
    )

@risk_router.get("/population-types")
async def get_population_types():
    """
    الحصول على أنواع السكان المتاحة
    Get available population types
    """
    return {
        "population_types": [
            {"value": "adult_male", "label": "ذكر بالغ", "weight": 75},
            {"value": "adult_female", "label": "أنثى بالغة", "weight": 65},
            {"value": "adult_average", "label": "متوسط البالغين", "weight": 70},
            {"value": "child", "label": "طفل (5-12 سنة)", "weight": 25},
            {"value": "teenager", "label": "مراهق (13-17 سنة)", "weight": 55},
            {"value": "elderly", "label": "كبار السن", "weight": 68}
        ]
    }