import pandas as pd
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
from dataclasses import dataclass
import re
from helper.config import get_settings

@dataclass
class PesticideReading:
    sample_code: str
    sample_name: str
    pesticide_name: str
    limits: str
    device_reading: str
    result: str
    source_file: str = ""
    row_index: int = 0

class ExcelPesticideProcessor:
   
    def __init__(self):
            self.config = get_settings()
            self.logger = logging.getLogger(__name__)
        
    def process_all_excel_files(self) -> List[Dict[str, Any]]:
        """Process all Excel files from month folders - COLAB STYLE"""
        documents = []
        metadata_list = []
        
        for month_folder in self.config.MONTHS_IN_ORDER:
            month_path = self.config.MAIN_FOLDER_PATH / month_folder
            
            if not month_path.exists():
                self.logger.warning(f"Month folder not found: {month_path}")
                continue
                
            self.logger.info(f"Processing: {month_folder}")
            
            # Process each Excel file in month folder
            for file_path in month_path.glob("*.xlsx"):
                try:
                    df = pd.read_excel(file_path, skiprows=7)
                    # Convert entire DataFrame to string (COLAB approach)
                    document_text = df.to_string(index=False)
                    
                    documents.append(document_text)
                    metadata_list.append({
                        "source_file": file_path.name,
                        "month": month_folder,
                        "file_path": str(file_path),
                        "total_rows": len(df),
                        "doc_id": len(documents) - 1
                    })
                    
                    self.logger.info(f"Processed: {file_path.name} ({len(df)} rows)")
                    
                except Exception as e:
                    self.logger.error(f"Error processing {file_path.name}: {e}")
        
        self.logger.info(f"Total documents processed: {len(documents)}")
        return documents, metadata_list
