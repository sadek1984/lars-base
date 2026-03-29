"""
Risk Assessment Service
Location: src/services/risk_assessment_service.py
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd

from helper.risk_assessment_config import RiskAssessmentConfig
from models.risk_assessment_models import (
    IndividualRiskResult, 
    RiskAssessmentSummary, 
    RiskLevel,
    CalculationDetails,
    PopulationType
)

class RiskAssessmentService:
    """Service for performing health risk assessments"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.config = RiskAssessmentConfig()
    
    def assess_sample_risk(self, 
                          sample_code: str,
                          pesticide_name: str, 
                          food_item: str,
                          concentration_ppb: float,
                          population_type: PopulationType = PopulationType.ADULT_AVERAGE,
                          custom_adi: Optional[float] = None,
                          custom_food_intake: Optional[float] = None,
                          custom_body_weight: Optional[float] = None) -> IndividualRiskResult:
        """
        Assess health risk for a single sample
        """
        
        # Get values (custom or default)
        adi = custom_adi or self.config.get_pesticide_adi(pesticide_name)
        food_intake = custom_food_intake or self.config.get_food_intake(food_item)
        body_weight = custom_body_weight or self.config.get_body_weight(population_type.value)
        
        # Determine sources
        adi_source = "Custom" if custom_adi else "WHO/FAO"
        intake_source = "Custom" if custom_food_intake else "Saudi nutrition study"
        
        # Calculate risk
        return self._calculate_individual_risk(
            sample_code=sample_code,
            pesticide_name=pesticide_name,
            food_item=food_item,
            concentration_ppb=concentration_ppb,
            adi=adi,
            food_intake=food_intake,
            body_weight=body_weight,
            adi_source=adi_source,
            intake_source=intake_source
        )
    
    def assess_dataframe_risk(self, 
                             df: pd.DataFrame,
                             population_type: PopulationType = PopulationType.ADULT_AVERAGE) -> RiskAssessmentSummary:
        """
        Assess health risk for multiple samples from DataFrame
        """
        
        if df is None or df.empty:
            raise ValueError("DataFrame is empty or None")
        
        assessment_results = []
        
        for _, row in df.iterrows():
            try:
                # Extract data from row
                sample_code = str(row.get('Sample Code', 'Unknown'))
                pesticide_name = str(row.get('Pesticide Name', '')).strip()
                raw_food_name = str(row.get('Sample Name', ''))
                concentration = float(row.get('Reading Value', 0))
                
                # Map food name
                food_item = self._extract_food_item(raw_food_name)
                
                # Assess risk
                risk_result = self.assess_sample_risk(
                    sample_code=sample_code,
                    pesticide_name=pesticide_name,
                    food_item=food_item,
                    concentration_ppb=concentration,
                    population_type=population_type
                )
                
                assessment_results.append(risk_result)
                
            except Exception as e:
                self.logger.error(f"Risk assessment failed for row: {e}")
                continue
        
        # Calculate risk distribution
        risk_distribution = {}
        for result in assessment_results:
            risk_level = result.risk_level.value
            risk_distribution[risk_level] = risk_distribution.get(risk_level, 0) + 1
        
        return RiskAssessmentSummary(
            total_samples_assessed=len(assessment_results),
            target_population="السكان السعوديين",
            population_type=population_type,
            assessment_results=assessment_results,
            assessment_timestamp=datetime.now().isoformat(),
            overall_risk_distribution=risk_distribution
        )
    
    def _extract_food_item(self, sample_name: str) -> str:
        """Extract food item from sample name (Arabic or English)"""
        
        sample_name_clean = sample_name.strip().lower()
        
        # Try Arabic mapping first
        for arabic_name, english_name in self.config.FOOD_NAME_MAPPING.items():
            if arabic_name in sample_name_clean:
                return english_name
        
        # Try direct English match
        for english_name in self.config.SAUDI_FOOD_INTAKE.keys():
            if english_name in sample_name_clean:
                return english_name
        
        self.logger.warning(f"Could not map food item: {sample_name}")
        return "unknown"
    
    def _calculate_individual_risk(self, 
                                 sample_code: str,
                                 pesticide_name: str,
                                 food_item: str, 
                                 concentration_ppb: float,
                                 adi: float,
                                 food_intake: float,
                                 body_weight: float,
                                 adi_source: str,
                                 intake_source: str) -> IndividualRiskResult:
        """Calculate health risk for individual sample"""
        
        # Unit conversion: ppb to mg/kg
        concentration_mg_kg = concentration_ppb / 1000
        
        # Calculate EDI (Estimated Daily Intake)
        edi = (concentration_mg_kg * food_intake) / body_weight
        
        # Calculate risk percentage
        risk_percentage = (edi / adi) * 100
        
        # Determine risk level and status
        risk_level, risk_status, recommendation = self._determine_risk_level(
            edi, adi, risk_percentage, pesticide_name, food_item
        )
        
        # Create calculation details
        calculation_details = CalculationDetails(
            formula="EDI = (التركيز × الاستهلاك اليومي) ÷ وزن الجسم",
            substitution=f"({concentration_mg_kg:.4f} × {food_intake}) ÷ {body_weight}",
            population_weight=f"{body_weight} kg",
            daily_intake=f"{food_intake} kg/day"
        )
        
        return IndividualRiskResult(
            sample_code=sample_code,
            pesticide_name=pesticide_name,
            food_item=food_item,
            concentration_ppb=concentration_ppb,
            concentration_mg_kg=concentration_mg_kg,
            edi_value=round(edi, 8),
            adi_value=adi,
            adi_source=adi_source,
            food_intake_source=intake_source,
            risk_percentage=round(risk_percentage, 2),
            risk_status=risk_status,
            risk_level=risk_level,
            recommendation=recommendation,
            calculation_details=calculation_details
        )
    
    def _determine_risk_level(self, edi: float, adi: float, risk_percentage: float,
                            pesticide_name: str, food_item: str) -> tuple:
        """Determine risk level, status and recommendation"""
        
        ratio = edi / adi
        
        if ratio <= self.config.RISK_THRESHOLDS["acceptable"]:
            risk_level = RiskLevel.ACCEPTABLE
            risk_status = "مقبول"
            recommendation = f"مستوى {pesticide_name} في {food_item} آمن للاستهلاك اليومي"
            
        elif ratio <= self.config.RISK_THRESHOLDS["low_concern"]:
            risk_level = RiskLevel.LOW_CONCERN
            risk_status = "قلق منخفض"
            recommendation = f"مستوى {pesticide_name} مرتفع قليلاً، يُنصح بالحد من الاستهلاك"
            
        elif ratio <= self.config.RISK_THRESHOLDS["moderate_concern"]:
            risk_level = RiskLevel.MODERATE_CONCERN
            risk_status = "قلق متوسط"
            recommendation = f"مستوى {pesticide_name} مرتفع، يُنصح بتجنب الاستهلاك المفرط"
            
        else:
            risk_level = RiskLevel.HIGH_CONCERN
            risk_status = "قلق عالي"
            recommendation = f"مستوى {pesticide_name} يتجاوز الحدود الآمنة بشكل كبير - تجنب الاستهلاك"
        
        return risk_level, risk_status, recommendation