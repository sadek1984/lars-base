"""
Risk Assessment Configuration Module
Single source of truth for Health Risk Assessment parameters.
Updated with detailed population-specific vegetable ingestion rates.

Source: International IESTI model and WHO GEMS/Food Regional Diets
All rates in g/kg bw/day
"""

from typing import Dict, Any, Optional


class RiskAssessmentConfig:
    """
    Single source of truth for Health Risk Assessment parameters.
    Updated with population-specific Saudi national ingestion rates.
    """
    
    # ========================================================================
    # DETAILED POPULATION-SPECIFIC INGESTION RATES (g/kg bw/day)
    # ========================================================================
    # Source: IESTI calculation model + WHO GEMS/Food Regional Diets
    # Note: Values are in g/kg bw/day for accurate risk assessment
    
    DETAILED_INGESTION_RATES: Dict[str, Dict[str, Optional[float]]] = {
        "Tomato": {
            "infants": None,
            "toddlers": None,
            "other_children": 3.543,
            "adolescents": 1.538,
            "adult": 1.164,
            "elderly": 1.199,
            "very_elderly": 1.254,
            "pregnant_women": 1.254,
            "lactating_women": 1.254,
            "saudi_adults": 1.538,
            "saudi_children": 5.094,
            "child": 5.094
        },
        "Cucumber": {
            "infants": None,
            "toddlers": None,
            "other_children": 0.209,
            "adolescents": 0.091,
            "adult": 0.069,
            "elderly": 0.071,
            "very_elderly": 0.074,
            "pregnant_women": 0.074,
            "lactating_women": 0.074,
            "saudi_adults": 0.091,
            "saudi_children": 0.300,
            "child": 0.300
        },
        "Pepper": {
            "infants": None,
            "toddlers": None,
            "other_children": 0.148,
            "adolescents": 0.064,
            "adult": 0.049,
            "elderly": 0.050,
            "very_elderly": 0.052,
            "pregnant_women": 0.052,
            "lactating_women": 0.052,
            "saudi_adults": 0.064,
            "saudi_children": 0.213,
            "child": 0.213
        },
        "Eggplant": {
            "infants": None,
            "toddlers": None,
            "other_children": 0.274,
            "adolescents": 0.119,
            "adult": 0.090,
            "elderly": 0.093,
            "very_elderly": 0.097,
            "pregnant_women": 0.097,
            "lactating_women": 0.097,
            "saudi_adults": 0.119,
            "saudi_children": 0.394,
            "child": 0.394
        },
        "Zucchini": {  # Mapped from Squash (Summer and Winter)
            "infants": None,
            "toddlers": None,
            "other_children": 0.457,
            "adolescents": 0.198,
            "adult": 0.150,
            "elderly": 0.154,
            "very_elderly": 0.162,
            "pregnant_women": 0.162,
            "lactating_women": 0.162,
            "saudi_adults": 0.198,
            "saudi_children": 0.656,
            "child": 0.656
        },
        "Beans": {  # Mapped from Beans, Green (Common)
            "infants": None,
            "toddlers": None,
            "other_children": 0.152,
            "adolescents": 0.066,
            "adult": 0.050,
            "elderly": 0.051,
            "very_elderly": 0.054,
            "pregnant_women": 0.054,
            "lactating_women": 0.054,
            "saudi_adults": 0.066,
            "saudi_children": 0.219,
            "child": 0.219
        },
        "Okra": {
            "infants": None,
            "toddlers": None,
            "other_children": None,
            "adolescents": None,
            "adult": None,
            "elderly": None,
            "very_elderly": None,
            "pregnant_women": None,
            "lactating_women": None,
            "saudi_adults": None,
            "saudi_children": None,
            "child": None
        },
        "Cabbage": {  # Mapped from Cabbages
            "infants": None,
            "toddlers": None,
            "other_children": 0.217,
            "adolescents": 0.094,
            "adult": 0.071,
            "elderly": 0.074,
            "very_elderly": 0.077,
            "pregnant_women": 0.077,
            "lactating_women": 0.077,
            "saudi_adults": 0.094,
            "saudi_children": 0.313,
            "child": 0.313
        },
        "Lettuce": {
            "infants": None,
            "toddlers": None,
            "other_children": 0.100,
            "adolescents": 0.043,
            "adult": 0.033,
            "elderly": 0.034,
            "very_elderly": 0.035,
            "pregnant_women": 0.035,
            "lactating_women": 0.035,
            "saudi_adults": 0.043,
            "saudi_children": 0.144,
            "child": 0.144
        },
        "Root Vegetables": {  # Using Carrots as representative
            "infants": None,
            "toddlers": None,
            "other_children": 0.122,
            "adolescents": 0.053,
            "adult": 0.040,
            "elderly": 0.041,
            "very_elderly": 0.043,
            "pregnant_women": 0.043,
            "lactating_women": 0.043,
            "saudi_adults": 0.053,
            "saudi_children": 0.175,
            "child": 0.175
        },
        "Total Fruits": {  # Using Watermelon as representative
            "infants": None,
            "toddlers": None,
            "other_children": 2.143,
            "adolescents": 0.929,
            "adult": 0.704,
            "elderly": 0.725,
            "very_elderly": 0.758,
            "pregnant_women": 0.758,
            "lactating_women": 0.758,
            "saudi_adults": 0.930,
            "saudi_children": 3.081,
            "child": 3.081
        }
    }
    
    # ========================================================================
    # FALLBACK SIMPLE INGESTION RATES (kg/day)
    # ========================================================================
    # Used when population-specific data is not available
    # Converted from detailed rates for saudi_adults or adult population
    
    SAUDI_INGESTION_RATES: Dict[str, float] = {
        # Vegetables with detailed data (converted to kg/day for saudi_adults)
        "Tomato": 0.045,  # Kept as original fallback
        "Cucumber": 0.045,  # Kept as original fallback
        "Pepper": 0.045,  # Kept as original fallback
        "Eggplant": 0.030,  # Kept as original fallback
        "Zucchini": 0.025,  # Kept as original fallback
        "Beans": 0.020,  # Kept as original fallback
        "Okra": 0.015,  # No detailed data available
        "Cabbage": 0.020,  # Kept as original fallback
        "Lettuce": 0.015,  # Kept as original fallback
        "Root Vegetables": 0.025,  # Kept as original fallback
        
        # Other commodities without detailed population data
        "Total Vegetables": 0.1111,
        "Total Fruits": 0.0709,
        "Leafy Greens": 0.0165,
        "Squash": 0.020,
        "Parsley": 0.005,
        "Coriander": 0.005,
        "Mint": 0.003,
        "Default": 0.1111,
    }
    
    # Arabic to English commodity mapping
    COMMODITY_MAPPING: Dict[str, str] = {
        'طماطم': 'Tomato',
        'خيار': 'Cucumber',
        'فلفل': 'Pepper',
        'باذنجان': 'Eggplant',
        'كوسة': 'Zucchini',
        'فاصوليا': 'Beans',
        'بامية': 'Okra',
        'قرع': 'Squash',
        'ملفوف': 'Cabbage',
        'كرنب': 'Cabbage',
        'خس': 'Lettuce',
        'بقدونس': 'Parsley',
        'كزبرة': 'Coriander',
        'نعناع': 'Mint',
        'ورقيات': 'Leafy Greens',
        'خضروات': 'Total Vegetables',
        'فواكه': 'Total Fruits',
    }
    
    # ========================================================================
    # POPULATION PROFILES
    # ========================================================================
    
    POPULATION_PROFILES: Dict[str, Dict[str, Any]] = {
        # Primary populations for Saudi Arabia
        "saudi_adults": {
            "name_en": "Adults (Saudi)",
            "name_ar": "بالغون (سعودي)",
            "bw": 53.0,
            "age_range": "+18 years"
        },
        "saudi_children": {
            "name_en": "Children 2-6 (Saudi)",
            "name_ar": "أطفال 2-6 (سعودي)",
            "bw": 16.0,
            "age_range": "2-6 years"
        },
        "child": {
            "name_en": "Child",
            "name_ar": "طفل",
            "bw": 16.0,
            "age_range": "2-6 years"
        },
        
        # Standard PRIMo 4 population classes
        "infants": {
            "name_en": "Infants",
            "name_ar": "رضع",
            "bw": 8.0,
            "age_range": "<1 year"
        },
        "toddlers": {
            "name_en": "Toddlers",
            "name_ar": "صغار الأطفال",
            "bw": 12.0,
            "age_range": "1 to <3 years"
        },
        "other_children": {
            "name_en": "Other Children",
            "name_ar": "أطفال آخرون",
            "bw": 23.0,
            "age_range": "3 to <10 years"
        },
        "adolescents": {
            "name_en": "Adolescents",
            "name_ar": "مراهقون",
            "bw": 53.0,
            "age_range": "10 to <18 years"
        },
        "adult": {
            "name_en": "Adults",
            "name_ar": "بالغون",
            "bw": 70.0,
            "age_range": "18 to <65 years"
        },
        "elderly": {
            "name_en": "Elderly",
            "name_ar": "كبار السن",
            "bw": 68.0,
            "age_range": "65 to <75 years"
        },
        "very_elderly": {
            "name_en": "Very Elderly",
            "name_ar": "كبار السن جداً",
            "bw": 65.0,
            "age_range": "75+ years"
        },
        "pregnant_women": {
            "name_en": "Pregnant Women",
            "name_ar": "نساء حوامل",
            "bw": 65.0,
            "age_range": "15-45 years"
        },
        "lactating_women": {
            "name_en": "Lactating Women",
            "name_ar": "نساء مرضعات",
            "bw": 65.0,
            "age_range": "28-39 years"
        },
        
        # Legacy profiles
        "adult_male": {
            "name_en": "Adult Male",
            "name_ar": "ذكر بالغ",
            "bw": 75.0,
            "age_range": "18+ years"
        },
        "adult_female": {
            "name_en": "Adult Female",
            "name_ar": "أنثى بالغة",
            "bw": 65.0,
            "age_range": "18+ years"
        },
    }
    
    # ========================================================================
    # METHODS
    # ========================================================================
    
    @classmethod
    def get_ingestion_rate(
        cls,
        commodity: str,
        population: str = "saudi_adults",
        use_detailed: bool = True
    ) -> float:
        """
        Get ingestion rate for commodity and population.
        
        Parameters:
            commodity: Commodity name (English or Arabic)
            population: Population class key
            use_detailed: If True, use population-specific rates (g/kg bw/day)
                         If False, use simple rates (kg/day)
        
        Returns:
            Ingestion rate in g/kg bw/day (if use_detailed=True) or kg/day (if False)
        """
        # Map Arabic to English if needed
        if commodity in cls.COMMODITY_MAPPING:
            commodity = cls.COMMODITY_MAPPING[commodity]
        
        # Try case-insensitive English lookup for commodity
        commodity_key = None
        for key in cls.DETAILED_INGESTION_RATES.keys():
            if key.lower() == commodity.lower():
                commodity_key = key
                break
        
        # If detailed rates requested and available
        if use_detailed and commodity_key and commodity_key in cls.DETAILED_INGESTION_RATES:
            pop_rates = cls.DETAILED_INGESTION_RATES[commodity_key]
            rate = pop_rates.get(population)
            
            if rate is not None:
                return rate
            
            # Fallback to saudi_adults if specific population not available
            if population != "saudi_adults":
                rate = pop_rates.get("saudi_adults")
                if rate is not None:
                    return rate
            
            # Fallback to adult if saudi_adults not available
            if population not in ["adult", "saudi_adults"]:
                rate = pop_rates.get("adult")
                if rate is not None:
                    return rate
        
        # Fallback to simple rates (convert to g/kg bw/day if needed)
        if commodity in cls.SAUDI_INGESTION_RATES:
            simple_rate = cls.SAUDI_INGESTION_RATES[commodity]
            if use_detailed:
                # Convert kg/day to g/kg bw/day
                bw = cls.get_population_bw(population)
                return (simple_rate * 1000) / bw
            return simple_rate
        
        # Try case-insensitive lookup
        for key, val in cls.SAUDI_INGESTION_RATES.items():
            if key.lower() == commodity.lower():
                if use_detailed:
                    bw = cls.get_population_bw(population)
                    return (val * 1000) / bw
                return val
        
        # Ultimate fallback
        default_rate = cls.SAUDI_INGESTION_RATES["Default"]
        if use_detailed:
            bw = cls.get_population_bw(population)
            return (default_rate * 1000) / bw
        return default_rate
    
    @classmethod
    def get_pesticide_adi(cls, pesticide_name: str) -> Optional[float]:
        """
        Placeholder for ADI lookup.
        Note: The actual ADI lookup usually happens via ADILookup class reading an Excel file.
        This provides a fallback for key pesticides.
        """
        FALLBACK_ADI = {
            "cypermethrin": 0.005,
            "imidacloprid": 0.057,
            "chlorpyrifos": 0.001,
        }
        return FALLBACK_ADI.get(pesticide_name.lower())
    
    @classmethod
    def get_population_bw(cls, target: str) -> float:
        """Get body weight for profile or return default"""
        profile = cls.POPULATION_PROFILES.get(target.lower())
        if profile:
            return profile["bw"]
        
        # Try case-insensitive lookup
        for key, prof in cls.POPULATION_PROFILES.items():
            if key.lower() == target.lower():
                return prof["bw"]
        
        return 53.0  # Default Saudi Adult
    
    @classmethod
    def has_detailed_rates(cls, commodity: str) -> bool:
        """Check if commodity has population-specific detailed rates"""
        # Map Arabic to English if needed
        if commodity in cls.COMMODITY_MAPPING:
            commodity = cls.COMMODITY_MAPPING[commodity]
        
        # Check if in detailed rates
        for key in cls.DETAILED_INGESTION_RATES.keys():
            if key.lower() == commodity.lower():
                return True
        
        return False
    
    @classmethod
    def get_available_populations(cls, commodity: str) -> list:
        """Get list of populations with data for a commodity"""
        # Map Arabic to English if needed
        if commodity in cls.COMMODITY_MAPPING:
            commodity = cls.COMMODITY_MAPPING[commodity]
        
        # Find commodity in detailed rates
        for key, pop_rates in cls.DETAILED_INGESTION_RATES.items():
            if key.lower() == commodity.lower():
                return [pop for pop, rate in pop_rates.items() if rate is not None]
        
        return []