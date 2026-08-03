import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from langchain.schema import Document
import logging
from pathlib import Path
import json
import re

class SmartExcelParser:
    """
    Smart parser that extracts structured data from Excel files
    Similar to LlamaParse but without LLM costs - uses pattern matching
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Column patterns for automatic detection (Arabic and English)
        self.column_patterns = {
            'sample_code': [
                r'sample.*code', r'كود.*العينة', r'رقم.*العينة',
                r'sample\s*#', r'code', r'كود', r'كود العينة sample code'
            ],
            'sample_name': [
                r'sample.*name', r'اسم.*العينة', r'العينة',
                r'sample.*type', r'نوع.*العينة',r'اسم العينة sample name'
            ],
            'pesticide_name': [
                r'pesticide', r'اسم.*المبيد', r'المبيد',
                r'active.*ingredient', r'المادة.*الفعالة', r'اسم المبيد Pesticide Name'
            ],
            'limits': [
                r'limit', r'الحدود', r'الحد.*المسموح',
                r'mrl', r'maximum.*residue', r'الحدود Limits'
            ],
            'device_reading': [
                r'reading', r'قراءة.*الجهاز', r'القراءة',
                r'result.*value', r'القيمة', r'قراءة الجهاز Reading of device'
            ],
            'result': [
                r'result', r'النتيجة', r'compliance',
                r'status', r'الحالة', r'النتيجة Result'
            ]
        }

    def parse_excel_to_documents(self, 
                                file_path: str, 
                                project_id: str,
                                chunk_strategy: str = 'semantic') -> List[Document]:
        """
        Parse Excel file into structured documents with intelligent chunking
        
        Args:
            file_path: Path to Excel file
            project_id: Project ID
            chunk_strategy: 'semantic' (group by result type) or 'sequential' (by rows)
            
        Returns:
            List of Document objects with structured data
        """
        try:
            # Read Excel with multiple strategies
            df = self._read_excel_intelligently(file_path)
            
            if df is None or df.empty:
                return []
            
            # Detect column mapping
            column_mapping = self._detect_columns(df)
            
            # Extract structured data
            structured_data = self._extract_structured_data(df, column_mapping)
            
            # Create documents based on strategy
            if chunk_strategy == 'semantic':
                return self._create_semantic_chunks(structured_data, file_path, project_id)
            else:
                return self._create_sequential_chunks(structured_data, file_path, project_id)
                
        except Exception as e:
            self.logger.error(f"Error parsing Excel file {file_path}: {e}")
            return []

    def _read_excel_intelligently(self, file_path: str) -> Optional[pd.DataFrame]:
        """
        Try multiple strategies to read Excel file
        """
        strategies = [
            {'skiprows': 7},  # Your current approach
            {'header': 0},    # First row as header
            {'header': 1},    # Second row as header
            {'header': None}, # No header
        ]
        
        for strategy in strategies:
            try:
                df = pd.read_excel(file_path, **strategy, engine='openpyxl')
                
                # Validate if this looks like pesticide data
                if self._validate_dataframe(df):
                    self.logger.info(f"Successfully read Excel with strategy: {strategy}")
                    return df
            except:
                continue
        
        # Last resort - read everything and clean
        try:
            df = pd.read_excel(file_path, engine='openpyxl')
            df = self._clean_dataframe(df)
            return df
        except Exception as e:
            self.logger.error(f"Failed to read Excel file: {e}")
            return None

    def _validate_dataframe(self, df: pd.DataFrame) -> bool:
        """
        Check if DataFrame looks like pesticide data
        """
        if df.empty or len(df.columns) < 4:
            return False
        
        # Check for expected patterns in data
        text_content = df.astype(str).values.flatten()
        text_combined = ' '.join(text_content).lower()
        
        # Must contain some expected keywords
        expected_keywords = ['مطابق', 'compliant', 'pesticide', 'مبيد', 'sample', 'عينة']
        return any(keyword in text_combined for keyword in expected_keywords)

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean DataFrame by removing empty rows/columns
        """
        # Remove empty columns
        df = df.dropna(axis=1, how='all')
        
        # Remove empty rows
        df = df.dropna(axis=0, how='all')
        
        # Remove rows that look like headers (contain column-like text)
        header_keywords = ['sample', 'code', 'كود', 'العينة', 'pesticide', 'المبيد']
        
        for idx, row in df.iterrows():
            row_text = ' '.join(row.astype(str).values).lower()
            if sum(keyword in row_text for keyword in header_keywords) >= 3:
                df = df.drop(idx)
        
        return df.reset_index(drop=True)

    def _detect_columns(self, df: pd.DataFrame) -> Dict[str, int]:
        """
        Automatically detect column indices based on patterns
        """
        column_mapping = {}
        
        # Check column headers first
        for col_idx, col_name in enumerate(df.columns):
            col_str = str(col_name).lower().strip()
            
            for field, patterns in self.column_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, col_str):
                        column_mapping[field] = col_idx
                        break
        
        # If not all found, check first few rows for patterns
        if len(column_mapping) < 6:
            sample_rows = df.head(3).astype(str)
            
            for col_idx in range(len(df.columns)):
                if col_idx in column_mapping.values():
                    continue
                    
                col_values = ' '.join(sample_rows.iloc[:, col_idx].values).lower()
                
                # Check for result pattern
                if 'مطابق' in col_values or 'compliant' in col_values:
                    column_mapping['result'] = col_idx
                # Check for codes (usually alphanumeric)
                elif re.search(r'[A-Z]\d+', col_values):
                    if 'sample_code' not in column_mapping:
                        column_mapping['sample_code'] = col_idx
                # Check for decimal numbers (readings/limits)
                elif re.search(r'\d+\.\d+', col_values):
                    if 'device_reading' not in column_mapping:
                        column_mapping['device_reading'] = col_idx
                    elif 'limits' not in column_mapping:
                        column_mapping['limits'] = col_idx
        
        # Default mapping if detection fails
        if not column_mapping:
            column_mapping = {
                'sample_code': 0,
                'sample_name': 1,
                'pesticide_name': 2,
                'limits': 3,
                'device_reading': 4,
                'result': 5
            }
        
        return column_mapping

    def _extract_structured_data(self, df: pd.DataFrame, column_mapping: Dict[str, int]) -> List[Dict]:
        """
        Extract structured data from DataFrame
        """
        structured_data = []
        
        for idx, row in df.iterrows():
            record = {}
            
            for field, col_idx in column_mapping.items():
                if col_idx < len(row):
                    value = row.iloc[col_idx]
                    if pd.notna(value):
                        record[field] = str(value).strip()
                    else:
                        record[field] = ''
                else:
                    record[field] = ''
            
            # Skip empty records
            if not any(record.values()):
                continue
            
            # Add analysis flags
            result_text = record.get('result', '').lower()
            sample_name = record.get('sample_name', '').lower()
            
            record['is_non_compliant'] = 'غير مطابق' in result_text or 'non-compliant' in result_text
            record['is_compliant'] = 'مطابق' in result_text and 'غير' not in result_text
            record['is_pepper'] = any(term in sample_name for term in ['فلفل', 'pepper'])
            record['is_tomato'] = any(term in sample_name for term in ['طماطم', 'tomato'])
            record['is_cucumber'] = any(term in sample_name for term in ['خيار', 'cucumber'])
            
            structured_data.append(record)
        
        return structured_data

    def _create_semantic_chunks(self, 
                               structured_data: List[Dict],
                               file_path: str,
                               project_id: str) -> List[Document]:
        """
        Create chunks grouped by semantic meaning (e.g., all non-compliant together)
        """
        documents = []
        file_name = Path(file_path).name
        
        # Group by result type
        groups = {
            'non_compliant': [],
            'compliant': [],
            'unknown': []
        }
        
        for record in structured_data:
            if record.get('is_non_compliant'):
                groups['non_compliant'].append(record)
            elif record.get('is_compliant'):
                groups['compliant'].append(record)
            else:
                groups['unknown'].append(record)
        
        # Create document for each group
        for group_name, records in groups.items():
            if not records:
                continue
            
            # Create markdown table
            content = self._create_markdown_table(records, group_name)
            
            # Create metadata
            metadata = {
                'source_file': file_name,
                'project_id': project_id,
                'chunk_type': f'semantic_{group_name}',
                'record_count': len(records),
                'file_type': 'excel',
                'group': group_name
            }
            
            # Add sample types found
            sample_types = set()
            pesticides = set()
            
            for record in records:
                if record.get('is_pepper'):
                    sample_types.add('pepper')
                if record.get('is_tomato'):
                    sample_types.add('tomato')
                if record.get('is_cucumber'):
                    sample_types.add('cucumber')
                if record.get('pesticide_name'):
                    pesticides.add(record['pesticide_name'])
            
            metadata['sample_types'] = list(sample_types)
            metadata['pesticides'] = list(pesticides)[:10]
            
            documents.append(Document(
                page_content=content,
                metadata=metadata
            ))
        
        return documents

    def _create_sequential_chunks(self,
                                 structured_data: List[Dict],
                                 file_path: str,
                                 project_id: str,
                                 chunk_size: int = 10) -> List[Document]:
        """
        Create chunks sequentially by rows
        """
        documents = []
        file_name = Path(file_path).name
        
        for chunk_idx, start_idx in enumerate(range(0, len(structured_data), chunk_size)):
            end_idx = min(start_idx + chunk_size, len(structured_data))
            chunk_records = structured_data[start_idx:end_idx]
            
            # Create content
            content = self._create_markdown_table(chunk_records, f"chunk_{chunk_idx + 1}")
            
            # Create metadata
            metadata = {
                'source_file': file_name,
                'project_id': project_id,
                'chunk_type': 'sequential',
                'chunk_number': chunk_idx + 1,
                'start_row': start_idx,
                'end_row': end_idx,
                'record_count': len(chunk_records),
                'file_type': 'excel'
            }
            
            # Analyze chunk content
            non_compliant = sum(1 for r in chunk_records if r.get('is_non_compliant'))
            compliant = sum(1 for r in chunk_records if r.get('is_compliant'))
            
            metadata['non_compliant_count'] = non_compliant
            metadata['compliant_count'] = compliant
            
            documents.append(Document(
                page_content=content,
                metadata=metadata
            ))
        
        return documents

    def _create_markdown_table(self, records: List[Dict], title: str = "") -> str:
        """
        Create a markdown table from records
        """
        if not records:
            return ""
        
        content = []
        
        # Title
        if title:
            content.append(f"## {title.replace('_', ' ').title()}")
            content.append("")
        
        # Table header
        content.append("| كود العينة | اسم العينة | اسم المبيد | الحدود | قراءة الجهاز | النتيجة |")
        content.append("|------------|------------|-------------|---------|--------------|---------|")
        
        # Table rows
        for record in records:
            row = (
                f"| {record.get('sample_code', '')} "
                f"| {record.get('sample_name', '')} "
                f"| {record.get('pesticide_name', '')} "
                f"| {record.get('limits', '')} "
                f"| {record.get('device_reading', '')} "
                f"| {record.get('result', '')} |"
            )
            content.append(row)
        
        # Add summary
        content.append("")
        content.append(f"**Total records in this section: {len(records)}**")
        
        # Add searchable text
        content.append("")
        content.append("### Searchable Content:")
        
        for record in records:
            searchable = []
            if record.get('sample_name'):
                searchable.append(f"Sample: {record['sample_name']}")
            if record.get('pesticide_name'):
                searchable.append(f"Pesticide: {record['pesticide_name']}")
            if record.get('result'):
                searchable.append(f"Result: {record['result']}")
                
            if searchable:
                content.append(f"- {', '.join(searchable)}")
        
        return "\n".join(content)