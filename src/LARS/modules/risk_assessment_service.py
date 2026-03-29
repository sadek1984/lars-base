"""
Risk Assessment Service for LARS Application

This module provides comprehensive dietary exposure and risk assessment calculations
based on ADI (Acceptable Daily Intake) values and MRL (Maximum Residue Levels).

Implements PRIMo 4 methodology for:
- EDI (Estimated Daily Intake)
- HQc (Hazard Quotient chronic)
- HIc (Hazard Index chronic) by chemical group

Author: LARS Team
"""

import pandas as pd
import numpy as np
import json
import os
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from functools import lru_cache
import sys
# Get the directory where this module is located
MODULE_DIR = Path(__file__).parent
SCRIPTS_DIR = MODULE_DIR.parent / 'scripts'

# Add project root to sys.path to allow importing from helper
project_root = str(MODULE_DIR.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from helper.risk_assessment_config import RiskAssessmentConfig

# Default paths
DEFAULT_ADI_FILE = SCRIPTS_DIR / 'pesticide_adi_simple_20260112_221046.xlsx'
CHEMICAL_CLASSIFICATION_FILE = SCRIPTS_DIR / 'chemical_classification.json'

# EU MRL API endpoint (unofficial - with fallback to offline data)
EU_MRL_API_BASE = "https://ec.europa.eu/food/api/pesticides/mrl"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class PopulationClass:
    """Represents a population class with body weight for risk calculations."""
    key: str
    name_en: str
    name_ar: str
    age_range: str
    default_weight_kg: float


@dataclass
class ChemicalGroup:
    """Represents a chemical group/class of pesticides."""
    key: str
    name_en: str
    name_ar: str
    pesticides: List[str]
    primary_use: Optional[str] = None


@dataclass
class RiskResult:
    """Result of a risk assessment calculation."""
    pesticide: str
    concentration: float
    adi: Optional[float]
    edi: Optional[float]
    hqc: Optional[float]
    mrl: Optional[float]
    mrl_ratio: Optional[float]
    chemical_group: Optional[str]
    interpretation: str
    unit: str = "mg/kg bw/day"


# ============================================================================
# POPULATION CLASSES (PRIMo 4)
# ============================================================================

POPULATION_CLASSES = {
    'infants': PopulationClass('infants', 'Infants', 'رضع', '<1', 8.0),
    'toddlers': PopulationClass('toddlers', 'Toddlers', 'صغار الأطفال', '1-<3', 12.0),
    'other_children': PopulationClass('other_children', 'Other Children', 'أطفال آخرون', '3-<10', 23.0),
    'adolescents': PopulationClass('adolescents', 'Adolescents', 'مراهقون', '10-<18', 53.0),
    'adult': PopulationClass('adult', 'Adults', 'بالغون', '18-<65', 70.0),
    'elderly': PopulationClass('elderly', 'Elderly', 'كبار السن', '65-<75', 68.0),
    'very_elderly': PopulationClass('very_elderly', 'Very Elderly', 'كبار السن جداً', '>=75', 65.0),
    'pregnant_women': PopulationClass('pregnant_women', 'Pregnant Women', 'نساء حوامل', '15-45', 65.0),
    'lactating_women': PopulationClass('lactating_women', 'Lactating Women', 'نساء مرضعات', '28-39', 65.0),
    # Saudi-specific population classes
    'saudi_adults': PopulationClass('saudi_adults', 'Adults (Saudi)', 'بالغون (سعودي)', '18+', 53.0),
    'saudi_children': PopulationClass('saudi_children', 'Children 2-6 (Saudi)', 'أطفال 2-6 (سعودي)', '2-6', 16.0),
    'child': PopulationClass('child', 'Child', 'طفل', '2-6', 16.0),
}


# ============================================================================
# SAUDI ARABIA INGESTION RATES (IR)
# Sources: National Nutrition Surveys & SFDA
# ============================================================================

# Saudi Arabia Ingestion Rates (IR) - Now handled by RiskAssessmentConfig
SAUDI_IR_DATA = RiskAssessmentConfig.SAUDI_INGESTION_RATES
SAUDI_COMMODITY_MAPPING = RiskAssessmentConfig.COMMODITY_MAPPING

# Legacy mapping for compatibility
SAUDI_COMMODITY_MAPPING = RiskAssessmentConfig.COMMODITY_MAPPING

# EU Commodity Codes Mapping (Regulation (EC) No 396/2005)
EU_COMMODITY_CODES = {
    'Tomato': '0211010',
    'Cucumber': '0222010',
    'Pepper': '0222000',
    'Eggplant': '0212030',
    'Zucchini': '0222030',
    'Beans': '0260010',
    'Okra': '0222020',
    'Cabbage': '0241010',
    'Lettuce': '0251010',
    'Parsley': '0256030',
    'Coriander': '0256020',
    'Mint': '0256050',
    'Leafy Greens': '0250000',
}


def get_population_weight(popclass: str) -> float:
    """Get default body weight for a population class from unified config."""
    profile = RiskAssessmentConfig.POPULATION_PROFILES.get(popclass)
    if profile:
        return profile["bw"]
    return RiskAssessmentConfig.get_population_bw(popclass)


def get_population_options() -> List[Dict[str, str]]:
    """Get list of population options for dropdown from unified config."""
    return [
        {
            'key': key,
            'label': f"{prof['name_en']} ({prof['name_ar']}) - {prof['bw']} kg",
            'name_en': prof['name_en'],
            'name_ar': prof['name_ar'],
            'weight': prof['bw']
        }
        for key, prof in RiskAssessmentConfig.POPULATION_PROFILES.items()
    ]


# ============================================================================
# CHEMICAL CLASSIFICATION
# ============================================================================

class ChemicalClassifier:
    """Classifier for pesticides by chemical group."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize with configuration file."""
        self.config_path = config_path or CHEMICAL_CLASSIFICATION_FILE
        self._groups: Dict[str, ChemicalGroup] = {}
        self._pesticide_to_group: Dict[str, str] = {}
        self._load_configuration()
    
    def _load_configuration(self):
        """Load chemical classification from JSON file."""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                for key, data in config.get('chemical_groups', {}).items():
                    group = ChemicalGroup(
                        key=key,
                        name_en=data.get('name_en', key),
                        name_ar=data.get('name_ar', key),
                        pesticides=data.get('pesticides', []),
                        primary_use=data.get('primary_use')
                    )
                    self._groups[key] = group
                    
                    # Build reverse lookup
                    for pesticide in group.pesticides:
                        self._pesticide_to_group[pesticide.lower()] = key
        except Exception as e:
            print(f"Warning: Could not load chemical classification: {e}")
    
    def get_group(self, pesticide_name: str) -> Optional[str]:
        """Get chemical group for a pesticide."""
        return self._pesticide_to_group.get(pesticide_name.lower().strip())
    
    def get_group_info(self, group_key: str) -> Optional[ChemicalGroup]:
        """Get information about a chemical group."""
        return self._groups.get(group_key)
    
    def get_all_groups(self) -> Dict[str, ChemicalGroup]:
        """Get all chemical groups."""
        return self._groups
    
    def classify_pesticides(self, pesticide_list: List[str]) -> Dict[str, List[str]]:
        """Classify a list of pesticides by chemical group."""
        result = {}
        for pesticide in pesticide_list:
            group = self.get_group(pesticide)
            if group:
                if group not in result:
                    result[group] = []
                result[group].append(pesticide)
            else:
                if 'unknown' not in result:
                    result['unknown'] = []
                result['unknown'].append(pesticide)
        return result


# ============================================================================
# ADI LOOKUP
# ============================================================================

class ADILookup:
    """ADI (Acceptable Daily Intake) lookup module for LARS application."""
    
    def __init__(self, adi_file_path: Optional[Path] = None):
        """Initialize with ADI data file."""
        self.adi_file_path = adi_file_path or DEFAULT_ADI_FILE
        self.adi_dict: Dict[str, Dict[str, Any]] = {}
        self._load_adi_data()
    
    def _load_adi_data(self):
        """Load ADI data from Excel file."""
        try:
            if self.adi_file_path.exists():
                df = pd.read_excel(self.adi_file_path)
                
                # Expected columns: Pesticide, ADI_Value, ADI_Unit, Year, Author
                for _, row in df.iterrows():
                    pesticide = str(row.get('Pesticide', '')).strip().lower()
                    adi_value = row.get('ADI_Value')
                    
                    if pesticide and pd.notna(adi_value):
                        self.adi_dict[pesticide] = {
                            'value': float(adi_value),
                            'unit': str(row.get('ADI_Unit', 'mg/kg bw/day')),
                            'year': row.get('Year'),
                            'author': row.get('Author', 'Unknown')
                        }
                
                print(f"✅ Loaded {len(self.adi_dict)} ADI values from {self.adi_file_path}")
            else:
                print(f"⚠️ ADI file not found: {self.adi_file_path}")
        except Exception as e:
            print(f"❌ Error loading ADI data: {e}")
    
    def get_adi(self, pesticide_name: str) -> Optional[Dict[str, Any]]:
        """
        Get ADI value for a pesticide.
        
        Parameters:
            pesticide_name: Name of the pesticide
        
        Returns:
            Dictionary with 'value', 'unit', 'year', 'author' or None if not found
        """
        # Try exact match first
        key = pesticide_name.strip().lower()
        if key in self.adi_dict:
            return self.adi_dict[key]
        
        # Try partial match
        for stored_name, adi_info in self.adi_dict.items():
            if key in stored_name or stored_name in key:
                return adi_info
        
        return None
    
    def get_adi_value(self, pesticide_name: str) -> Optional[float]:
        """Get just the ADI value (mg/kg bw/day) for a pesticide."""
        adi_info = self.get_adi(pesticide_name)
        return adi_info['value'] if adi_info else None
    
    def list_all(self) -> List[str]:
        """List all pesticides with ADI values."""
        return list(self.adi_dict.keys())


# ============================================================================
# EU MRL API CLIENT
# ============================================================================

class EUMRLClient:
    """Client for fetching MRL values from EU Pesticides Database."""
    
    def __init__(self, timeout: int = 30):
        """Initialize MRL client."""
        self.timeout = timeout
        self._cache: Dict[str, Dict] = {}
    
    def get_commodity_code(self, commodity_name: str) -> Optional[str]:
        """Map commodity name to EU product code."""
        # Clean name
        name = commodity_name.strip()
        
        # Check direct mapping
        if name in EU_COMMODITY_CODES:
            return EU_COMMODITY_CODES[name]
        
        # Check Arabic mapping
        mapped_en = SAUDI_COMMODITY_MAPPING.get(name)
        if mapped_en and mapped_en in EU_COMMODITY_CODES:
            return EU_COMMODITY_CODES[mapped_en]
            
        # Try case-insensitive
        name_lower = name.lower()
        for key, code in EU_COMMODITY_CODES.items():
            if key.lower() == name_lower:
                return code
                
        return None

    def fetch_mrl(
        self, 
        pesticide_name: Optional[str] = None,
        pesticide_code: Optional[str] = None,
        commodity_code: Optional[str] = None,
        commodity_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch MRL value from EU Pesticides Database API.
        
        Parameters:
            pesticide_name: Name of the active substance (e.g., "Chlorpyrifos")
            pesticide_code: Official code of the substance (more accurate)
            commodity_code: Product code per Regulation (EC) No 396/2005
            commodity_name: Name of commodity (will attempt to map to code)
        
        Returns:
            Dictionary with MRL information or error
        """
        # Resolve commodity code
        if not commodity_code and commodity_name:
            commodity_code = self.get_commodity_code(commodity_name)
            
        # Check cache first
        cache_key = f"{pesticide_name}:{pesticide_code}:{commodity_code}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        if not pesticide_code and not pesticide_name:
            return {"error": "Must provide pesticide name or code"}
        
        # Build API request
        params = {}
        if pesticide_code:
            params['activeSubstanceCode'] = pesticide_code
        elif pesticide_name:
            params['activeSubstance'] = pesticide_name
        
        if commodity_code:
            params['productCode'] = commodity_code
        
        try:
            # Use the specific endpoint for active substances as suggested
            url = f"{EU_MRL_API_BASE}/activeSubstances"
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if data and isinstance(data, list) and len(data) > 0:
                # Find the best match if multiple results (usually first is best)
                mrl_info = data[0]
                
                # If we have a product code, try to find exact match in results if they are expanded
                # Actually for this endpoint, it usually returns MRL for the specific product if productCode is provided
                
                mrl_value_str = str(mrl_info.get('mrl', 'Not specified'))
                
                # Parse MRL value (handle * for LOQ and other non-numeric chars)
                try:
                    # Remove * and handle potential ranges or non-numeric strings
                    clean_str = mrl_value_str.replace('*', '').strip()
                    mrl_value = float(clean_str)
                    is_at_loq = '*' in mrl_value_str
                except ValueError:
                    mrl_value = mrl_value_str # Keep as string if failed
                    is_at_loq = False
                
                result = {
                    "active_substance": mrl_info.get('activeSubstance'),
                    "product": mrl_info.get('product'),
                    "mrl": mrl_value,
                    "is_at_loq": is_at_loq,
                    "unit": mrl_info.get('unit', 'mg/kg'),
                    "source": "EU Pesticides Database (Real-time)"
                }
                self._cache[cache_key] = result
                return result
            else:
                return {"error": "No MRL data found for specified criteria"}
        
        except requests.exceptions.RequestException as e:
            return {"error": f"API request failed: {e}"}
        except ValueError as e:
            return {"error": f"Failed to parse response: {e}"}
    
    def clear_cache(self):
        """Clear the MRL cache."""
        self._cache.clear()


# ============================================================================
# RISK ASSESSMENT SERVICE
# ============================================================================

class RiskAssessmentService:
    """
    Comprehensive risk assessment service for pesticide residues.
    
    Implements EDI, HQc, and HIc calculations per PRIMo 4 methodology.
    """
    
    def __init__(
        self,
        adi_file_path: Optional[Path] = None,
        classification_file_path: Optional[Path] = None
    ):
        """Initialize the risk assessment service."""
        self.adi_lookup = ADILookup(adi_file_path)
        self.classifier = ChemicalClassifier(classification_file_path)
        self.mrl_client = EUMRLClient()
    
    def get_mrl(self, pesticide: str, commodity: str) -> Optional[float]:
        """Fetch MRL from EU API for a pesticide and commodity."""
        result = self.mrl_client.fetch_mrl(pesticide_name=pesticide, commodity_name=commodity)
        if "error" not in result:
            mrl = result.get('mrl')
            return float(mrl) if isinstance(mrl, (int, float)) else None
        return None

    def calculate_edi(
        self,
        residue_concentration: float,
        consumption_rate: float,
        body_weight: float
    ) -> float:
        """
        Calculate Estimated Daily Intake (EDI).

        Delegates to RiskAssessmentConfig.calculate_edi() — single formula source.

        Parameters:
            residue_concentration: Pesticide concentration in food (mg/kg)
            consumption_rate: Food consumption rate (kg/day)
            body_weight: Body weight (kg)

        Returns:
            EDI in mg/kg bw/day
        """
        return RiskAssessmentConfig.calculate_edi(
            residue_concentration, consumption_rate, body_weight
        )
    
    def calculate_hqc(
        self,
        pesticide_name: str,
        residue_concentration: float,
        consumption_rate: float,
        body_weight: float
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate Hazard Quotient for chronic exposure (HQc).
        
        HQc = EDI / ADI
        
        Parameters:
            pesticide_name: Name of the pesticide
            residue_concentration: Concentration in mg/kg
            consumption_rate: Food consumption in kg/day
            body_weight: Body weight in kg
        
        Returns:
            Dictionary with HQc calculation results or None if ADI not found
        """
        adi_info = self.adi_lookup.get_adi(pesticide_name)
        
        if not adi_info:
            return None
        
        edi = self.calculate_edi(residue_concentration, consumption_rate, body_weight)
        hqc = edi / adi_info['value']
        
        # Determine risk interpretation using shared thresholds from RiskAssessmentConfig
        _t = RiskAssessmentConfig.RISK_THRESHOLDS
        if hqc >= _t["moderate_concern"]:
            interpretation = "⚠️ Risk unacceptable (HQc ≥ 1)"
            interpretation_ar = "⚠️ خطر غير مقبول"
        elif hqc >= _t["low_concern"]:
            interpretation = "⚡ Elevated risk (0.5 ≤ HQc < 1)"
            interpretation_ar = "⚡ خطر مرتفع"
        elif hqc >= _t["acceptable"]:
            interpretation = "⚠ Moderate risk (0.1 ≤ HQc < 0.5)"
            interpretation_ar = "⚠ خطر متوسط"
        else:
            interpretation = "✅ Risk acceptable (HQc < 0.1)"
            interpretation_ar = "✅ خطر مقبول"
        
        return {
            'pesticide': pesticide_name,
            'edi': edi,
            'adi': adi_info['value'],
            'adi_unit': adi_info['unit'],
            'adi_year': adi_info.get('year'),
            'hqc': hqc,
            'hqc_percent': hqc * 100,
            'interpretation': interpretation,
            'interpretation_ar': interpretation_ar,
            'chemical_group': self.classifier.get_group(pesticide_name)
        }
    
    def calculate_hic(
        self,
        hqc_results: List[Dict[str, Any]],
        group_by_chemical_class: bool = True
    ) -> Dict[str, Any]:
        """
        Calculate Hazard Index for chronic exposure (HIc).
        
        HIc = Σ HQc (sum of individual hazard quotients)
        
        Parameters:
            hqc_results: List of HQc calculation results
            group_by_chemical_class: If True, calculate HIc per chemical group
        
        Returns:
            Dictionary with HIc results, optionally grouped by chemical class
        """
        if group_by_chemical_class:
            # Group results by chemical class
            groups: Dict[str, List[Dict]] = {}
            for result in hqc_results:
                if result and result.get('hqc') is not None:
                    group = result.get('chemical_group', 'unknown')
                    if group not in groups:
                        groups[group] = []
                    groups[group].append(result)
            
            # Calculate HIc per group
            hic_by_group = {}
            for group, results in groups.items():
                total_hqc = sum(r['hqc'] for r in results)
                group_info = self.classifier.get_group_info(group)
                
                hic_by_group[group] = {
                    'name_en': group_info.name_en if group_info else group,
                    'name_ar': group_info.name_ar if group_info else group,
                    'hic': total_hqc,
                    'hic_percent': total_hqc * 100,
                    'pesticide_count': len(results),
                    'pesticides': [r['pesticide'] for r in results],
                    'interpretation': "⚠️ Risk unacceptable" if total_hqc >= 1 else "✅ Risk acceptable"
                }
            
            # Total HIc across all groups
            total_hic = sum(g['hic'] for g in hic_by_group.values())
            
            return {
                'total_hic': total_hic,
                'total_hic_percent': total_hic * 100,
                'by_chemical_group': hic_by_group,
                'interpretation': "⚠️ Total risk unacceptable" if total_hic >= 1 else "✅ Total risk acceptable"
            }
        else:
            # Simple sum of all HQc
            total_hic = sum(r['hqc'] for r in hqc_results if r and r.get('hqc') is not None)
            return {
                'total_hic': total_hic,
                'total_hic_percent': total_hic * 100,
                'interpretation': "⚠️ Risk unacceptable" if total_hic >= 1 else "✅ Risk acceptable"
            }
    
    def analyze_sample_risk(
        self,
        sample_results: List[Dict[str, Any]],
        population_class: str = 'adult',
        consumption_rate: float = 0.1,  # Default consumption in kg/day
        use_realtime_mrl: bool = False,
        commodity_name: str = "Total Vegetables"
    ) -> Dict[str, Any]:
        """
        Perform complete risk analysis for a sample with multiple pesticide residues.
        
        Parameters:
            sample_results: List of dicts with 'pesticide' and 'concentration' keys
            population_class: Population class for body weight
            consumption_rate: Food consumption rate in kg/day
            use_realtime_mrl: If True, fetch MRLs from EU API
            commodity_name: Name of the commodity for MRL lookup
        
        Returns:
            Comprehensive risk analysis results
        """
        body_weight = get_population_weight(population_class)
        pop_info = POPULATION_CLASSES.get(population_class, POPULATION_CLASSES.get('adult'))
        
        # Calculate HQc for each pesticide
        hqc_results = []
        missing_adi = []
        
        for residue in sample_results:
            pesticide = residue.get('pesticide', '')
            concentration = residue.get('concentration', 0)
            
            if concentration > 0:
                hqc_result = self.calculate_hqc(
                    pesticide,
                    concentration,
                    consumption_rate,
                    body_weight
                )
                
                if hqc_result:
                    # Enrich with MRL if requested
                    if use_realtime_mrl:
                        mrl = self.get_mrl(pesticide, commodity_name)
                        if mrl is not None:
                            hqc_result['mrl'] = mrl
                            hqc_result['mrl_ratio'] = concentration / mrl if mrl > 0 else float('inf')
                    
                    hqc_result['concentration'] = concentration
                    hqc_results.append(hqc_result)
                else:
                    missing_adi.append(pesticide)
        
        # Calculate HIc grouped by chemical class
        hic_results = self.calculate_hic(hqc_results, group_by_chemical_class=True)
        
        # Find highest risk pesticide
        highest_risk = None
        if hqc_results:
            highest_risk = max(hqc_results, key=lambda x: x['hqc'])
        
        # Find highest risk chemical group
        highest_risk_group = None
        if hic_results.get('by_chemical_group'):
            groups = hic_results['by_chemical_group']
            if groups:
                highest_risk_group_key = max(groups.keys(), key=lambda k: groups[k]['hic'])
                highest_risk_group = groups[highest_risk_group_key]
                highest_risk_group['key'] = highest_risk_group_key
        
        return {
            'population': {
                'class': population_class,
                'name_en': pop_info.name_en,
                'name_ar': pop_info.name_ar,
                'body_weight': body_weight
            },
            'consumption_rate': consumption_rate,
            'pesticide_count': len(sample_results),
            'analyzed_count': len(hqc_results),
            'missing_adi_count': len(missing_adi),
            'missing_adi': missing_adi,
            'individual_risks': hqc_results,
            'hazard_index': hic_results,
            'highest_risk_pesticide': highest_risk,
            'highest_risk_group': highest_risk_group,
            'overall_interpretation': hic_results.get('interpretation', 'Unknown')
        }
    
    def analyze_dataframe(
        self,
        df: pd.DataFrame,
        pesticide_col: str = 'pesticide',
        concentration_col: str = 'reading',
        population_class: str = 'adult',
        consumption_rate: float = 0.1
    ) -> pd.DataFrame:
        """
        Analyze risk for a DataFrame of pesticide residue data.
        
        Parameters:
            df: DataFrame with pesticide data
            pesticide_col: Column name for pesticide names
            concentration_col: Column name for concentrations
            population_class: Population class for body weight
            consumption_rate: Food consumption rate in kg/day
        
        Returns:
            DataFrame with added risk columns
        """
        body_weight = get_population_weight(population_class)
        
        # Create result columns
        df = df.copy()
        df['adi'] = None
        df['edi'] = None
        df['hqc'] = None
        df['hqc_percent'] = None
        df['chemical_group'] = None
        df['risk_interpretation'] = None
        
        for idx, row in df.iterrows():
            pesticide = str(row.get(pesticide_col, ''))
            concentration = float(row.get(concentration_col, 0) or 0)
            
            if pesticide and concentration > 0:
                hqc_result = self.calculate_hqc(
                    pesticide,
                    concentration,
                    consumption_rate,
                    body_weight
                )
                
                if hqc_result:
                    df.at[idx, 'adi'] = hqc_result['adi']
                    df.at[idx, 'edi'] = hqc_result['edi']
                    df.at[idx, 'hqc'] = hqc_result['hqc']
                    df.at[idx, 'hqc_percent'] = hqc_result['hqc_percent']
                    df.at[idx, 'chemical_group'] = hqc_result['chemical_group']
                    df.at[idx, 'risk_interpretation'] = hqc_result['interpretation']
        
        return df


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

_risk_service_instance: Optional[RiskAssessmentService] = None

def get_risk_service() -> RiskAssessmentService:
    """Return the shared RiskAssessmentService instance (singleton).

    RiskAssessmentService.__init__ loads an Excel ADI file and a JSON
    chemical classification file from disk.  Creating a new instance on
    every call reloads both files for every query.  A module-level
    singleton avoids that repeated I/O while keeping the API identical.
    """
    global _risk_service_instance
    if _risk_service_instance is None:
        _risk_service_instance = RiskAssessmentService()
    return _risk_service_instance


def quick_hqc(
    pesticide: str,
    concentration: float,
    population: str = 'adult',
    consumption: float = 0.1
) -> Optional[Dict[str, Any]]:
    """
    Quick HQc calculation with default parameters.
    
    Parameters:
        pesticide: Pesticide name
        concentration: Residue concentration in mg/kg
        population: Population class (default: adults)
        consumption: Food consumption in kg/day
    
    Returns:
        HQc result dictionary or None
    """
    service = get_risk_service()
    body_weight = get_population_weight(population)
    return service.calculate_hqc(pesticide, concentration, consumption, body_weight)


def calculate_iqr(concentration: float, mrl: float) -> float:
    """
    Calculate Index of Quality for Residues (IqR).
    
    IqR = concentration / MRL
    
    Parameters:
        concentration: Residue concentration in mg/kg
        mrl: Maximum Residue Limit in mg/kg
    
    Returns:
        IqR value (ratio)
    """
    if mrl <= 0:
        return float('inf') if concentration > 0 else 0.0
    return concentration / mrl


def calculate_sample_iqr_summary(
    residue_list: List[Dict[str, Any]],
    commodity: str = "Total Vegetables"
) -> Dict[str, Any]:
    """
    🆕 New Sample-Level IQR Calculation (as per user's diagram)
    
    Logic:
    1. For each SAMPLE, sum the IQR of all pesticides detected in that sample
       IQR_sample = Σ (concentration_i / MRL_i) for all pesticides i in sample
    2. Classify each sample based on its total IQR:
       - Excellent: IQR = 0 (no pesticides detected)
       - Good: 0 < IQR <= 0.6
       - Adequate: 0.6 < IQR <= 1
       - Inadequate: IQR > 1
    3. Return summary statistics for the commodity
    
    Parameters:
        residue_list: List of dicts with keys:
            - 'sample_code': Unique sample identifier
            - 'name': pesticide name
            - 'concentration': residue concentration mg/kg
            - 'mrl': Maximum Residue Limit mg/kg
        commodity: Commodity name (for reference)
    
    Returns:
        Dictionary with:
            - sample_iqr_details: List of {sample_code, total_iqr, category}
            - category_counts: {Excellent, Good, Adequate, Inadequate}
            - category_percentages: {Excellent, Good, Adequate, Inadequate}
            - total_samples: Total number of unique samples
    """
    # Get risk service for MRL lookup if needed
    service = get_risk_service()
    
    # Group residues by sample_code
    samples = {}
    for item in residue_list:
        sample_code = item.get('sample_code', 'unknown')
        if sample_code not in samples:
            samples[sample_code] = []
        samples[sample_code].append(item)
    
    # Calculate IQR for each sample
    sample_iqr_details = []
    
    for sample_code, residues in samples.items():
        total_iqr = 0.0
        pesticide_details = []
        
        for res in residues:
            p_name = res.get('name', '')
            concentration = res.get('concentration', 0)
            mrl = res.get('mrl', 0)
            
            # Skip if no valid data
            if not p_name or p_name in ('NO DATA', 'NO DETECTION', ''):
                continue
            
            # Calculate IQR for this pesticide
            if mrl and mrl > 0:
                iqr_val = concentration / mrl
            else:
                iqr_val = 0.0
            
            total_iqr += iqr_val
            pesticide_details.append({
                'pesticide': p_name,
                'concentration': concentration,
                'mrl': mrl,
                'iqr': iqr_val
            })
        
        # Classify sample
        if total_iqr == 0:
            category = "Excellent"
        elif total_iqr <= 0.6:
            category = "Good"
        elif total_iqr <= 1.0:
            category = "Adequate"
        else:
            category = "Inadequate"
        
        sample_iqr_details.append({
            'sample_code': sample_code,
            'total_iqr': total_iqr,
            'category': category,
            'pesticides': pesticide_details,
            'pesticide_count': len(pesticide_details)
        })
    
    # Count categories
    category_counts = {
        "Excellent": 0,
        "Good": 0,
        "Adequate": 0,
        "Inadequate": 0
    }
    
    for detail in sample_iqr_details:
        category_counts[detail['category']] += 1
    
    total_samples = len(sample_iqr_details)
    
    # Calculate percentages
    category_percentages = {}
    for cat, count in category_counts.items():
        category_percentages[cat] = (count / total_samples * 100) if total_samples > 0 else 0
    
    return {
        "sample_iqr_details": sample_iqr_details,
        "category_counts": category_counts,
        "category_percentages": category_percentages,
        "total_samples": total_samples,
        "commodity": commodity
    }



"""
INSTRUCTIONS FOR UPDATING risk_assessment_service.py

The following changes need to be made to utilize the new population-specific 
ingestion rates:

1. Update the get_saudi_ir() function to support population parameter
2. Update calculate_commodity_summary_metrics() to use population-specific rates
3. Update calculate_lars_metrics() to use population-specific rates
4. Update analyze_sample_risk() to use population-specific rates

Below are the updated functions:
"""

# ============================================================================
# UPDATED FUNCTION 1: get_saudi_ir() with population support
# ============================================================================

def get_saudi_ir(commodity: str, population: str = "saudi_adults") -> float:
    """
    Get Saudi ingestion rate for a commodity in g/kg bw/day using RiskAssessmentConfig.
    
    Parameters:
        commodity: Commodity name (English or Arabic)
        population: Population class (default: saudi_adults)
    
    Returns:
        Ingestion rate in g/kg bw/day
    """
    return RiskAssessmentConfig.get_ingestion_rate(
        commodity, 
        population=population,
        use_detailed=True  # Returns g/kg bw/day
    )


# ============================================================================
# UPDATED FUNCTION 2: calculate_commodity_summary_metrics()
# ============================================================================

def calculate_commodity_summary_metrics(
    residue_list: List[Dict[str, Any]],
    commodity: str = "Total Vegetables",
    target: str = "adult",
    body_weight: Optional[float] = None,
    ingestion_rate: Optional[float] = None,
    use_realtime_mrl: bool = False
) -> Dict[str, Any]:
    """
    🆕 New Aggregate Risk Calculation Logic (Chronic Risk by Commodity)
    
    UPDATED to use population-specific ingestion rates in g/kg bw/day
    
    Formula:
    EDI = (Concentration_mg/kg * IngestionRate_g/kg_bw/day) / 1000
    HQ = EDI / ADI
    """
    # Define body weight based on target OR use explicit parameter
    bw = body_weight if body_weight is not None else RiskAssessmentConfig.get_population_bw(target)
    
    # Get ingestion rate for commodity and population
    # UPDATED: Now gets population-specific rate in g/kg bw/day
    if ingestion_rate is not None:
        # If explicit rate provided, use it (assume it's in kg/day, convert to g/kg bw/day)
        ir = (ingestion_rate * 1000) / bw
    else:
        # Get detailed population-specific rate (already in g/kg bw/day)
        ir = RiskAssessmentConfig.get_ingestion_rate(
            commodity, 
            population=target,
            use_detailed=True
        )
    
    # Get risk service for ADI lookup
    service = get_risk_service()
    
    # Group detections by pesticide name
    pesticide_groups = {}
    for item in residue_list:
        p_name = item.get('name', '')
        if not p_name or p_name in ('NO DATA', 'NO DETECTION'):
            continue
            
        if p_name not in pesticide_groups:
            pesticide_groups[p_name] = []
        
        concentration = item.get('concentration', 0)
        pesticide_groups[p_name].append(concentration)
    
    # Calculate stats for each pesticide
    pesticide_summary = []
    total_hi_median = 0.0
    
    for p_name, concentrations in pesticide_groups.items():
        if not concentrations:
            continue
            
        min_val = float(np.min(concentrations))
        max_val = float(np.max(concentrations))
        median_val = float(np.median(concentrations))
        
        # Look up ADI
        adi = None
        adi_info = service.adi_lookup.get_adi(p_name)
        if adi_info:
            adi = adi_info['value']
            
        hqc_median = 0.0
        edi_median = 0.0
        if adi and adi > 0:
            # UPDATED FORMULA: EDI = (Concentration_mg/kg * IR_g/kg_bw/day) / 1000
            # This gives EDI in mg/kg bw/day
            edi_median = (median_val * ir) / 1000
            hqc_median = edi_median / adi
            total_hi_median += hqc_median
            
        # Get chemical group for classification
        group = service.classifier.get_group(p_name) or "Other/Unknown"
        group_info = service.classifier.get_group_info(group)
        group_name = group_info.name_en if group_info else group
        
        pesticide_summary.append({
            "pesticide": p_name,
            "chemical_group": group_name,
            "min": min_val,
            "max": max_val,
            "median": median_val,
            "adi": adi,
            "ir": ir,  # Now in g/kg bw/day
            "bw": bw,
            "edi_median": edi_median,
            "hqc": hqc_median,
            "hqc_percent": hqc_median * 100
        })
        
    # Sort summary by HQ descending
    pesticide_summary = sorted(pesticide_summary, key=lambda x: x['hqc'], reverse=True)
    
    # Build result
    analysis = {
        "individual_results": pesticide_summary,
        "hi_total": total_hi_median,
        "total_pesticides": len(pesticide_summary),
        "total_detections": len(residue_list),
        "population": {
            "target": target,
            "body_weight_kg": bw,
            "commodity": commodity,
            "ingestion_rate_g_kg_bw_day": ir  # UPDATED: Now shows g/kg bw/day
        },
        "hi_interpretation": "⚠️ Risk unacceptable" if total_hi_median >= 1 else "✅ Risk acceptable"
    }
    
    return analysis


# ============================================================================
# UPDATED FUNCTION 3: calculate_lars_metrics()
# ============================================================================

def calculate_lars_metrics(
    residue_list: List[Dict[str, Any]],
    commodity: str = "Total Vegetables",
    target: str = "adult",
    body_weight: Optional[float] = None,
    ingestion_rate: Optional[float] = None,
    use_realtime_mrl: bool = False
) -> Dict[str, Any]:
    """
    Calculate comprehensive LARS metrics for a list of pesticide residues.
    
    UPDATED to use population-specific ingestion rates in g/kg bw/day
    
    Formula:
    EDI = (Concentration_mg/kg * IngestionRate_g/kg_bw/day) / 1000
    HQ = EDI / ADI
    """
    # Define body weight based on target OR use explicit parameter
    bw = body_weight if body_weight is not None else RiskAssessmentConfig.get_population_bw(target)
    
    # Get ingestion rate for commodity and population
    # UPDATED: Now gets population-specific rate in g/kg bw/day
    if ingestion_rate is not None:
        # If explicit rate provided, use it (assume it's in kg/day, convert to g/kg bw/day)
        ir = (ingestion_rate * 1000) / bw
    else:
        # Get detailed population-specific rate (already in g/kg bw/day)
        ir = RiskAssessmentConfig.get_ingestion_rate(
            commodity,
            population=target,
            use_detailed=True
        )
    
    # Get risk service for ADI lookup
    service = get_risk_service()
    
    # Initialize analysis result
    analysis = {
        "stats": {},
        "iqr_total": 0.0,
        "hi_total": 0.0,
        "risk_driver": None,
        "iqr_driver": None,
        "individual_results": [],
        "population": {
            "target": target,
            "body_weight_kg": bw,
            "commodity": commodity,
            "ingestion_rate_g_kg_bw_day": ir  # UPDATED: Now shows g/kg bw/day
        }
    }
    
    highest_hqc = 0.0
    highest_iqr = 0.0
    risk_driver_name = None
    iqr_driver_name = None
    
    for item in residue_list:
        p_name = item.get('name', '')
        concentration = item.get('concentration', 0)
        
        # Determine MRL source
        if use_realtime_mrl:
            mrl_api = service.get_mrl(p_name, commodity)
            mrl = mrl_api if mrl_api is not None else item.get('mrl', 0)
        else:
            mrl = item.get('mrl', 0)
            
        adi = item.get('adi')
        
        # Get chemical group
        group = service.classifier.get_group(p_name) or "Other/Unknown"
        group_info = service.classifier.get_group_info(group)
        group_name = group_info.name_en if group_info else group
        
        # Calculate IqR
        iqr_val = calculate_iqr(concentration, mrl) if mrl > 0 else 0.0
        analysis["iqr_total"] += iqr_val
        
        # Track IqR driver
        if iqr_val > highest_iqr:
            highest_iqr = iqr_val
            iqr_driver_name = f"{p_name} ({group_name})"
        
        # Calculate HQc (need ADI)
        hqc = 0.0
        edi = 0.0
        if adi is None:
            # Try to look up ADI
            adi_info = service.adi_lookup.get_adi(p_name)
            if adi_info:
                adi = adi_info['value']
        
        if adi and adi > 0:
            # UPDATED FORMULA: EDI = (Concentration_mg/kg * IR_g/kg_bw/day) / 1000
            edi = (concentration * ir) / 1000
            hqc = edi / adi
            analysis["hi_total"] += hqc
            
            # Track HQc risk driver
            if hqc > highest_hqc:
                highest_hqc = hqc
                risk_driver_name = f"{p_name} ({group_name})"
        
        # Store individual result
        analysis["individual_results"].append({
            "pesticide": p_name,
            "chemical_group": group_name,
            "concentration": concentration,
            "mrl": mrl,
            "adi": adi,
            "iqr": iqr_val,
            "edi": edi,
            "hqc": hqc,
            "iqr_percent": iqr_val * 100 if iqr_val else 0,
            "hqc_percent": hqc * 100 if hqc else 0
        })
        
        # Aggregate group statistics
        if group_name not in analysis["stats"]:
            analysis["stats"][group_name] = {"concentrations": []}
        analysis["stats"][group_name]["concentrations"].append(concentration)
    
    # Set risk drivers
    analysis["risk_driver"] = risk_driver_name
    analysis["iqr_driver"] = iqr_driver_name
    
    # Calculate final statistics per group
    for group_name, data in analysis["stats"].items():
        vals = data["concentrations"]
        if vals:
            analysis["stats"][group_name] = {
                "min": float(np.min(vals)),
                "max": float(np.max(vals)),
                "mean": float(np.mean(vals)),
                "median": float(np.median(vals)),
                "count": len(vals),
                "concentrations": vals
            }
    
    # Add risk interpretations
    analysis["hi_interpretation"] = "⚠️ Risk unacceptable" if analysis["hi_total"] >= 1 else "✅ Risk acceptable"
    analysis["iqr_interpretation"] = "⚠️ Quality concern" if analysis["iqr_total"] >= 1 else "✅ Quality acceptable"
    
    return analysis


def detect_query_type(query: str) -> Optional[str]:
    """
    Detect if query triggers Health Risk or Quality window.
    
    Parameters:
        query: User query text (Arabic or English)
    
    Returns:
        "[TRIGGER_UI: HEALTH_RISK_WINDOW]" for risk queries
        "[TRIGGER_UI: QUALITY_INDEX_WINDOW]" for quality queries
        None if no trigger detected
    """
    query_lower = query.lower()
    
    # Health Risk keywords (Arabic and English)
    # Use specific phrases to avoid false positives
    # IMPORTANT: Use word boundaries for English keywords to prevent 'bifenthrin' matching 'hri'
    import re
    
    # Arabic keywords (substring match is OK for Arabic)
    arabic_risk_keywords = ['خطر صحي', 'مؤشر الخطر', 'مؤشر خطر', 'خطورة', 'مؤشر الخطورة', 'هازارد', 'تقييم خطر', 'تقييم المخاطر']
    # English keywords (need word boundary matching)
    english_risk_keywords = ['hri', 'health risk', 'hazard', 'risk assessment', 'risk index']
    
    # Check Arabic keywords
    if any(kw in query_lower for kw in arabic_risk_keywords):
        return "[TRIGGER_UI: HEALTH_RISK_WINDOW]"
    
    # Check English keywords with word boundaries
    for kw in english_risk_keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', query_lower):
            return "[TRIGGER_UI: HEALTH_RISK_WINDOW]"
    
    # Quality Index keywords (Arabic and English)
    # IMPORTANT: Avoid 'جودة' alone because it matches 'الموجودة' (existing)
    # Use specific phrases instead
    arabic_quality_keywords = ['مؤشر جودة', 'مؤشر الجودة']
    english_quality_keywords = ['iqr', 'pti', 'quality index', 'index of quality']
    
    # Check Arabic keywords
    if any(kw in query_lower for kw in arabic_quality_keywords):
        return "[TRIGGER_UI: QUALITY_INDEX_WINDOW]"
    
    # Check English keywords with word boundaries
    for kw in english_quality_keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', query_lower):
            return "[TRIGGER_UI: QUALITY_INDEX_WINDOW]"
    
    return None




# ============================================================================
# MODULE TEST
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("RISK ASSESSMENT SERVICE - TEST")
    print("=" * 80)
    
    # Initialize service
    service = RiskAssessmentService()
    
    # Test ADI lookup
    print("\n📊 Testing ADI Lookup:")
    for pesticide in ['chlorpyrifos', 'deltamethrin', 'imidacloprid', 'unknown_pest']:
        adi = service.adi_lookup.get_adi(pesticide)
        if adi:
            print(f"  ✅ {pesticide}: ADI = {adi['value']} {adi['unit']}")
        else:
            print(f"  ❌ {pesticide}: NOT FOUND")
    
    # Test chemical classification
    print("\n🧪 Testing Chemical Classification:")
    pesticides_to_classify = ['lambda-cyhalothrin', 'chlorpyrifos', 'carbendazim', 'unknown']
    for pest in pesticides_to_classify:
        group = service.classifier.get_group(pest)
        print(f"  {pest} → {group or 'Unknown'}")
    
    # Test HQc calculation
    print("\n🔬 Testing HQc Calculation:")
    result = service.calculate_hqc('chlorpyrifos', 0.1, 0.1, 70)
    if result:
        print(f"  Pesticide: {result['pesticide']}")
        print(f"  EDI: {result['edi']:.6f} mg/kg bw/day")
        print(f"  ADI: {result['adi']} mg/kg bw/day")
        print(f"  HQc: {result['hqc']:.4f} ({result['hqc_percent']:.2f}%)")
        print(f"  Interpretation: {result['interpretation']}")
    
    # Test sample analysis
    print("\n📋 Testing Sample Risk Analysis:")
    sample = [
        {'pesticide': 'lambda-cyhalothrin', 'concentration': 0.02},
        {'pesticide': 'chlorpyrifos', 'concentration': 0.1},
        {'pesticide': 'carbendazim', 'concentration': 0.05}
    ]
    
    analysis = service.analyze_sample_risk(sample, population_class='toddlers')
    print(f"  Population: {analysis['population']['name_en']} ({analysis['population']['body_weight']} kg)")
    print(f"  Analyzed: {analysis['analyzed_count']}/{analysis['pesticide_count']} pesticides")
    print(f"  Total HIc: {analysis['hazard_index']['total_hic']:.4f}")
    print(f"  Overall: {analysis['overall_interpretation']}")
    
    if analysis['highest_risk_group']:
        print(f"  Highest risk group: {analysis['highest_risk_group']['name_en']}")
    
    print("\n" + "=" * 80)
    print("✅ Test completed!")
