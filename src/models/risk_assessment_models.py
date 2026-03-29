"""
Risk Assessment Data Models
Location: src/models/risk_assessment_models.py
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class RiskLevel(str, Enum):
    """Risk level enumeration"""
    ACCEPTABLE = "acceptable"
    LOW_CONCERN = "low_concern"
    MODERATE_CONCERN = "moderate_concern"
    HIGH_CONCERN = "high_concern"

class PopulationType(str, Enum):
    """Population type enumeration"""
    ADULT_MALE = "adult_male"
    ADULT_FEMALE = "adult_female"
    ADULT_AVERAGE = "adult_average"
    CHILD = "child"
    TEENAGER = "teenager"
    ELDERLY = "elderly"

class LocalAnswerRequest(BaseModel):
    """Request model for local answer with optional risk assessment"""
    query: str = Field(..., description="Query string")
    n_results: int = Field(default=100, description="Number of results")
    include_risk_assessment: bool = Field(default=False, description="Include health risk assessment")
    population_type: str = Field(default="adult_average", description="Target population")

class RiskAssessmentRequest(BaseModel):
    """Basic risk assessment request"""
    pesticide_name: str = Field(..., description="Name of the pesticide")
    food_item: str = Field(..., description="Name of the food item")
    concentration_ppb: float = Field(..., description="Concentration in ppb")
    population_type: PopulationType = Field(default=PopulationType.ADULT_AVERAGE)

class CustomRiskAssessmentRequest(BaseModel):
    """Custom risk assessment with user-defined values"""
    pesticide_name: str = Field(..., description="Name of the pesticide")
    food_item: str = Field(..., description="Name of the food item")
    concentration_ppb: float = Field(..., description="Concentration in ppb")
    adi_value: Optional[float] = Field(None, description="Custom ADI value (mg/kg/day)")
    food_intake: Optional[float] = Field(None, description="Custom daily food intake (kg/day)")
    body_weight: Optional[float] = Field(None, description="Custom body weight (kg)")
    population_type: PopulationType = Field(default=PopulationType.ADULT_AVERAGE)

class CalculationDetails(BaseModel):
    """Detailed calculation information"""
    formula: str = Field(..., description="Formula used")
    substitution: str = Field(..., description="Values substituted in formula")
    population_weight: str = Field(..., description="Body weight used")
    daily_intake: str = Field(..., description="Daily intake used")

class IndividualRiskResult(BaseModel):
    """Risk assessment result for individual sample"""
    sample_code: str = Field(..., description="Sample identifier")
    pesticide_name: str = Field(..., description="Pesticide name")
    food_item: str = Field(..., description="Food item")
    concentration_ppb: float = Field(..., description="Concentration in ppb")
    concentration_mg_kg: float = Field(..., description="Concentration in mg/kg")
    edi_value: float = Field(..., description="Estimated Daily Intake")
    adi_value: float = Field(..., description="Acceptable Daily Intake")
    adi_source: str = Field(..., description="Source of ADI value")
    food_intake_source: str = Field(..., description="Source of food intake data")
    risk_percentage: float = Field(..., description="Risk as percentage of ADI")
    risk_status: str = Field(..., description="Risk status in Arabic")
    risk_level: RiskLevel = Field(..., description="Risk level category")
    recommendation: str = Field(..., description="Health recommendation in Arabic")
    calculation_details: CalculationDetails = Field(..., description="Calculation breakdown")

class RiskAssessmentSummary(BaseModel):
    """Summary of risk assessment results"""
    total_samples_assessed: int = Field(..., description="Total number of samples")
    target_population: str = Field(..., description="Target population description")
    population_type: PopulationType = Field(..., description="Population type")
    assessment_results: List[IndividualRiskResult] = Field(..., description="Individual results")
    assessment_timestamp: str = Field(..., description="Assessment timestamp")
    overall_risk_distribution: Dict[str, int] = Field(default_factory=dict, description="Risk level counts")

class PesticideADIResponse(BaseModel):
    """Response for pesticide ADI lookup"""
    pesticide_name: str = Field(..., description="Pesticide name")
    adi_value: float = Field(..., description="ADI value")
    unit: str = Field(default="mg/kg/day", description="Unit of measurement")
    source: str = Field(default="WHO/FAO", description="Data source")
    available_pesticides: List[str] = Field(..., description="List of available pesticides")

class FoodIntakeResponse(BaseModel):
    """Response for food intake lookup"""
    food_item: str = Field(..., description="Food item name")
    daily_intake: Optional[float] = Field(None, description="Daily intake value")
    unit: str = Field(default="kg/day", description="Unit of measurement")
    population: str = Field(default="Saudi Arabia", description="Population")
    message: Optional[str] = Field(None, description="Additional message")
    available_foods: List[str] = Field(..., description="List of available foods")

class ConstantsResponse(BaseModel):
    """Response for all constants"""
    pesticide_adi: Dict[str, float] = Field(..., description="Pesticide ADI values")
    saudi_food_intake: Dict[str, float] = Field(..., description="Saudi food intake data")
    saudi_body_weight: Dict[str, float] = Field(..., description="Saudi body weight data")
    food_name_mapping: Dict[str, str] = Field(..., description="Arabic to English food mapping")
    last_updated: str = Field(..., description="Last update date")