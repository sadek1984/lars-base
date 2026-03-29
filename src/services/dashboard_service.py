import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

# Set up a logger for this module
logger = logging.getLogger(__name__)

class DashboardService:
    """
    Service layer to handle all business logic for dashboard data.
    It manages data loading (from Excel or DB), caching, and processing.
    """
    
    def __init__(self, db_client: Any = None, excel_path: str = "/app/data/dataset.xlsx"):
        """
        Initializes the service.

        Args:
            db_client: An asynchronous database client session (optional).
            excel_path: The path inside the container to the Excel data file.
        """
        self.db_client = db_client
        self.excel_path = excel_path
        self.processed_data: Optional[List[Dict]] = None
        self.cache_timestamp: Optional[datetime] = None
        self.cache_duration: timedelta = timedelta(hours=1)
        logger.info(f"DashboardService instance created. Excel path: '{self.excel_path}'")

    async def get_executive_dashboard(self) -> Dict[str, Any]:
        """Generates the data payload for the executive dashboard."""
        try:
            data = await self._get_pesticide_data_smart()
            
            if not data:
                return {"success": False, "message": "No data available to generate dashboard."}
            
            df = pd.DataFrame(data)
            
            # --- Safely calculate metrics ---
            total_samples = len(df)
            compliant = len(df[df['is_compliant'] == True]) if 'is_compliant' in df.columns else 0
            non_compliant = total_samples - compliant
            compliance_rate = (compliant / total_samples * 100) if total_samples > 0 else 0
            
            risk_distribution = df['risk_level'].value_counts().to_dict() if 'risk_level' in df.columns else {}
            
            contaminated_df = df[df['exceeds_limit'] == True] if 'exceeds_limit' in df.columns else pd.DataFrame()
            top_vegetables = contaminated_df['vegetable'].value_counts().head(10).to_dict() if 'vegetable' in contaminated_df.columns else {}
            
            pesticide_freq = df['pesticide'].value_counts().head(10).to_dict() if 'pesticide' in df.columns else {}

            return {
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "data": {
                    "summary": {
                        "total_samples": total_samples,
                        "compliant_samples": compliant,
                        "non_compliant_samples": non_compliant,
                        "compliance_rate": round(compliance_rate, 1),
                        "last_update": self.cache_timestamp.isoformat() if self.cache_timestamp else datetime.now().isoformat()
                    },
                    "risk_distribution": risk_distribution,
                    "top_contaminated_vegetables": top_vegetables,
                    "pesticide_frequency": pesticide_freq
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating executive dashboard: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def get_laboratory_dashboard(self) -> Dict[str, Any]:
        """Generates the data payload for the laboratory dashboard."""
        logger.info("Generating laboratory dashboard data.")
        try:
            data = await self._get_pesticide_data_smart()
            if not data:
                return {"success": False, "message": "No data available."}

            df = pd.DataFrame(data)
            high_risk_df = df[df['risk_level'].isin(['high', 'critical'])] if 'risk_level' in df.columns else pd.DataFrame()
            
            return {
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "data": {
                    "summary": {
                        "total_samples_processed": len(df),
                        "high_risk_alerts": len(high_risk_df),
                        "instrument_status": "All systems operational" # Mock data
                    },
                    "recent_high_risk_samples": high_risk_df.head(5).to_dict('records')
                }
            }
        except Exception as e:
            logger.error(f"Error generating laboratory dashboard: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


    async def get_regulatory_dashboard(self) -> Dict[str, Any]:
        """Generates the data payload for the regulatory dashboard."""
        logger.info("Generating regulatory dashboard data.")
        try:
            data = await self._get_pesticide_data_smart()
            if not data:
                return {"success": False, "message": "No data available."}
                
            df = pd.DataFrame(data)
            non_compliant_df = df[df['is_compliant'] == False] if 'is_compliant' in df.columns else pd.DataFrame()

            return {
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "data": {
                    "compliance_summary": {
                        "total_samples": len(df),
                        "non_compliant_samples": len(non_compliant_df),
                        "compliance_rate": round((1 - (len(non_compliant_df) / len(df))) * 100, 1) if len(df) > 0 else 100
                    },
                    "recent_violations": non_compliant_df.head(10).to_dict('records')
                }
            }
        except Exception as e:
            logger.error(f"Error generating regulatory dashboard: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _is_cache_valid(self) -> bool:
        """Checks if the in-memory cache is still valid."""
        if not self.processed_data or not self.cache_timestamp:
            return False
        is_valid = (datetime.now() - self.cache_timestamp) < self.cache_duration
        logger.info(f"Cache check: {'Valid' if is_valid else 'Expired'}")
        return is_valid

    async def _get_pesticide_data_smart(self) -> List[Dict]:
        """
        Smart data retrieval with caching.
        1. Checks cache. 2. Tries DB. 3. Falls back to Excel.
        """
        if self._is_cache_valid():
            return self.processed_data

        if self.db_client:
            logger.info("Attempting to load from database...")
            # db_data = await self._get_data_from_db() # Your DB logic would go here
            # if db_data:
            #     self.processed_data = db_data
            #     self.cache_timestamp = datetime.now()
            #     return db_data

        logger.info(f"Loading from Excel file as fallback: {self.excel_path}")
        excel_data = self._load_from_excel()
        if excel_data:
            self.processed_data = excel_data
            self.cache_timestamp = datetime.now()
            return excel_data
        
        return []

    def _load_from_excel(self) -> List[Dict]:
        """Loads and processes data from the Excel file."""
        try:
            if not Path(self.excel_path).exists():
                logger.error(f"Excel file not found at container path: {self.excel_path}")
                return []
            
            df = pd.read_excel(self.excel_path)
            logger.info(f"Loaded {len(df)} rows from Excel")

            # --- Your robust column mapping ---
            column_mapping = {
                'result': 'result', 'النتيجة': 'result', 'النتيجة result': 'result',
                'uncertainty': 'uncertainty', 'اللا يقين': 'uncertainty', 'اللا يقين uncertainty': 'uncertainty',
                'limits': 'limits', 'الحدود': 'limits', 'الحدود limits': 'limits',
                'reading': 'reading', 'قراءة الجهاز': 'reading', 'قراءة الجهاز reading of device': 'reading',
                'pesticide': 'pesticide', 'اسم المبيد': 'pesticide', 'اسم المبيد pesticide name': 'pesticide',
                'vegetable_arabic': 'vegetable', 'اسم العينة': 'vegetable', 'اسم العينة sample name': 'vegetable',
                'sample_code': 'sample_code', 'كود العينة': 'sample_code', 'كود العينة sample code': 'sample_code',
                'document_date': 'test_date', 'date': 'test_date'
            }
            df.rename(columns={col: column_mapping.get(col.strip(), col) for col in df.columns}, inplace=True)

            # --- Data Cleaning and Transformation ---
            for col in ['reading', 'limits', 'uncertainty']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            df['exceeds_limit'] = (df['reading'] > df['limits']) & (df['limits'] > 0)
            df['is_compliant'] = df['result'].astype(str).str.strip() == 'مطابق'
            df['risk_level'] = df.apply(lambda row: self._calculate_risk_level(row['reading'], row['limits']), axis=1)

            # Use to_dict('records') for much better performance than iterrows
            return df.to_dict('records')

        except Exception as e:
            logger.error(f"Failed to load or process Excel file: {e}", exc_info=True)
            return []

    def _calculate_risk_level(self, reading: float, limits: float) -> str:
        """Calculates a risk category based on reading vs. limits."""
        if limits <= 0:
            return 'unknown'
        
        ratio = reading / limits
        if ratio <= 1: return 'low'
        if ratio <= 2: return 'medium'
        if ratio <= 5: return 'high'
        return 'critical'