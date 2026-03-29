import os
from pathlib import Path
from typing import List, Optional, Union
import logging

# langchain.schema.Document هو المعيار المستخدم في المشروع للـ chunks
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
# Langchain loaders for PDF as in the original project
from langchain_community.document_loaders import PyMuPDFLoader, TextLoader

from .BaseControllers import BaseControllers
from .ProjectControllers import ProjectControllers
# استيراد الـ processor المحسن لملفات Excel
from processors.excel_processor import ExcelPesticideProcessor
import pandas as pd
from processors.smart_excel_parser import SmartExcelParser


class ProcessControllers(BaseControllers):
    """
    Enhanced Controller for processing different file types,
    with improved logic for Excel files containing pesticide data.
    """
    def __init__(self, project_id: str):
        super().__init__()
        self.project_id = project_id
        self.project_path = ProjectControllers().get_project_path(project_id=project_id)
        # تهيئة معالج الإكسل المحسن
        self.excel_processor = ExcelPesticideProcessor()
        self.logger = logging.getLogger(__name__)

    def get_file_loader(self, file_path: str, file_ext: str):
        """Selects the appropriate Langchain document loader based on file extension."""
        if file_ext == '.pdf':
            return PyMuPDFLoader(file_path),
        elif file_ext in '.txt':
            return TextLoader(file_path, encoding='utf-8'),
        return None

    def create_rich_content_text(self, reading, index: int) -> str:
        """
        Create rich, searchable text content for better vector search matching
        """
        # Create comprehensive text in both Arabic and English
        content_parts = []
        
        # Arabic content
        arabic_content = (
            f"السجل رقم {index + 1}: "
            f"كود العينة: {reading.sample_code or 'غير محدد'}, "
            f"اسم العينة: {reading.sample_name or 'غير محدد'}, "
            f"اسم المبيد: {reading.pesticide_name or 'غير محدد'}, "
            f"الحدود المسموحة: {reading.limits or 'غير محدد'}, "
            f"قراءة الجهاز: {reading.device_reading or 'غير محدد'}, "
            f"النتيجة: {reading.result or 'غير محدد'}. "
        )
        content_parts.append(arabic_content)
        
        # English content for bilingual search
        english_content = (
            f"Record {index + 1}: "
            f"Sample Code: {reading.sample_code or 'Not specified'}, "
            f"Sample Name: {reading.sample_name or 'Not specified'}, "
            f"Pesticide Name: {reading.pesticide_name or 'Not specified'}, "
            f"Limits: {reading.limits or 'Not specified'}, "
            f"Device Reading: {reading.device_reading or 'Not specified'}, "
            f"Result: {reading.result or 'Not specified'}. "
        )
        content_parts.append(english_content)
        
        # Add searchable keywords
        keywords = []
        
        # Sample type keywords
        sample_name_lower = (reading.sample_name or '').lower()
        if 'pepper' in sample_name_lower or 'فلفل' in sample_name_lower:
            keywords.extend(['pepper', 'فلفل', 'bell pepper', 'capsicum'])
        elif 'tomato' in sample_name_lower or 'طماطم' in sample_name_lower:
            keywords.extend(['tomato', 'طماطم', 'tomatoes'])
        elif 'cucumber' in sample_name_lower or 'خيار' in sample_name_lower:
            keywords.extend(['cucumber', 'خيار', 'cucumbers'])
        
        # Compliance keywords
        result_lower = (reading.result or '').lower()
        if 'غير مطابق' in result_lower or 'non-compliant' in result_lower:
            keywords.extend(['non-compliant', 'غير مطابق', 'failed', 'exceeds limits', 'تجاوز الحدود'])
        elif 'مطابق' in result_lower or 'compliant' in result_lower:
            keywords.extend(['compliant', 'مطابق', 'passed', 'within limits', 'ضمن الحدود'])
        
        # Pesticide analysis keywords
        keywords.extend(['pesticide analysis', 'تحليل المبيدات', 'residue', 'بقايا', 'laboratory', 'مختبر'])
        
        if keywords:
            content_parts.append(f"Keywords: {', '.join(keywords)}.")
        
        return ' '.join(content_parts)

    def create_comprehensive_metadata(self, reading, index: int) -> dict:
        """
        Create comprehensive metadata for better filtering and search
        """
        metadata = reading.__dict__.copy()
        metadata.update({
            "record_type": "pesticide_reading",
            "project_id": self.project_id,
            "chunk_index": index,
            
            # Normalized fields for better matching
            "sample_name_normalized": (reading.sample_name or '').lower().strip(),
            "pesticide_name_normalized": (reading.pesticide_name or '').lower().strip(),
            "result_normalized": (reading.result or '').lower().strip(),
            
            # Boolean flags for easy filtering
            "is_non_compliant": 'غير مطابق' in (reading.result or '').lower(),
            "is_compliant": 'مطابق' in (reading.result or '').lower() and 'غير مطابق' not in (reading.result or '').lower(),
            "has_sample_code": bool((reading.sample_code or '').strip()),
            "has_device_reading": bool((reading.device_reading or '').strip()),
            
            # Sample type detection
            "is_pepper": any(term in (reading.sample_name or '').lower() 
                           for term in ['pepper', 'فلفل', 'bell pepper', 'capsicum']),
            "is_tomato": any(term in (reading.sample_name or '').lower() 
                           for term in ['tomato', 'طماطم']),
            "is_cucumber": any(term in (reading.sample_name or '').lower() 
                             for term in ['cucumber', 'خيار']),
            
            # Text content for search
            "searchable_text": f"{reading.sample_name} {reading.pesticide_name} {reading.result}".lower(),
            
            # Data completeness score
            "completeness_score": sum([
                bool((reading.sample_code or '').strip()),
                bool((reading.sample_name or '').strip()),
                bool((reading.pesticide_name or '').strip()),
                bool((reading.limits or '').strip()),
                bool((reading.device_reading or '').strip()),
                bool((reading.result or '').strip())
            ]) / 6.0
        })
        
        return metadata

    def get_file_content(self, file_id: str) -> Union[List[Document], List[str]]:
        """
        SIMPLIFIED: Process Excel like Colab - no chunking, keep data intact
        """
        file_path = os.path.join(self.project_path, file_id)
        if not os.path.exists(file_path):
            return []

        file_ext = Path(file_path).suffix.lower()

        if file_ext in ['.xlsx', '.xls']:
            # COLAB APPROACH: Read entire Excel as single document
            try:
                
                df = pd.read_excel(file_path, engine='openpyxl')
                
                # Convert entire DataFrame to string (like Colab)
                document_text = df.to_string(index=False)
                
                # Create single document with all Excel data
                metadata = {
                    "source_file": file_id,
                    "project_id": self.project_id,
                    "record_type": "excel_data",
                    "file_type": "excel",
                    "total_rows": len(df)
                }
                
                return [Document(page_content=document_text, metadata=metadata)]
                
            except Exception as e:
                self.logger.error(f"Error reading Excel: {e}")
                return []
        else:
            # Handle other file types normally
            loader = self.get_file_loader(file_path, file_ext)
            if loader:
                return loader.load()
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return [Document(page_content=content)]

    def process_file_content(self, file_content: List[Document], file_id: str,
                           chunk_size: int = 1000, overlap_size: int = 100) -> List[Document]:
        """
        SIMPLIFIED: Don't chunk Excel data - keep it intact
        """
        if not file_content:
            return []
            
        # Check if it's Excel data
        first_doc = file_content[0]
        if first_doc.metadata.get("record_type") == "excel_data":
            # DON'T CHUNK - return as is (like Colab)
            return file_content

        # Only chunk non-Excel files
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap_size,
        )
        split_documents = text_splitter.split_documents(file_content)

        for i, doc in enumerate(split_documents):
            doc.metadata["source_file"] = file_id
            doc.metadata["chunk_index"] = i
            doc.metadata["project_id"] = self.project_id
            
        return split_documents


    def debug_processed_content(self, file_id: str) -> dict:
        """
        Debug function to analyze processed content
        """
        try:
            content = self.get_file_content(file_id)
            processed_content = self.process_file_content(content, file_id)
            
            debug_info = {
                "file_id": file_id,
                "raw_content_count": len(content),
                "processed_content_count": len(processed_content),
                "sample_documents": []
            }
            
            # Add sample documents for analysis
            for i, doc in enumerate(processed_content[:5]):  # First 5 documents
                debug_info["sample_documents"].append({
                    "index": i,
                    "content_preview": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                    "metadata": doc.metadata,
                    "is_pesticide_data": doc.metadata.get("record_type") == "pesticide_reading",
                    "is_pepper": doc.metadata.get("is_pepper", False),
                    "is_non_compliant": doc.metadata.get("is_non_compliant", False)
                })
            
            return debug_info
            
        except Exception as e:
            return {"error": str(e), "file_id": file_id}
        
class DirectPesticideController:
    """
    Enhanced direct controller with better Excel processing
    """
    
    def __init__(self, project_path: str):
        self.project_path = project_path
    
    def process_excel_to_structured_data(self) -> List[dict]:
        """Process Excel files to structured data - ENHANCED VERSION"""
        all_data = []
        
        for filename in os.listdir(self.project_path):
            if filename.endswith('.xlsx'):
                file_path = os.path.join(self.project_path, filename)
                try:
                    # Try multiple sheet reading approaches
                    df = None
                    
                    # Approach 1: Read normally
                    try:
                        df = pd.read_excel(file_path, engine='openpyxl')
                    except:
                        pass
                    
                    # Approach 2: Try different headers if first fails
                    if df is None or df.empty:
                        for header_row in [1, 2, 0]:
                            try:
                                df = pd.read_excel(file_path, header=header_row, engine='openpyxl')
                                if not df.empty:
                                    break
                            except:
                                continue
                    
                    if df is None or df.empty:
                        print(f"Could not read {filename}")
                        continue
                    
                    print(f"Processing {filename}: {df.shape} - Columns: {list(df.columns)}")
                    
                    # Enhanced column mapping with more patterns
                    column_map = {}
                    for col in df.columns:
                        col_str = str(col).lower().strip()
                        
                        # Sample code detection
                        if any(term in col_str for term in ['sample code', 'كود العينة', 'كود', 'sample_code', 'رقم']):
                            column_map['sample_code'] = col
                        # Sample name detection  
                        elif any(term in col_str for term in ['sample name', 'اسم العينة', 'sample_name', 'العينة', 'النوع']):
                            column_map['sample_name'] = col
                        # Pesticide name detection
                        elif any(term in col_str for term in ['pesticide', 'مبيد', 'اسم المبيد', 'pesticide name']):
                            column_map['pesticide_name'] = col
                        # Limits detection
                        elif any(term in col_str for term in ['limit', 'حدود', 'الحدود', 'حد']):
                            column_map['limits'] = col
                        # Reading detection
                        elif any(term in col_str for term in ['reading', 'قراءة', 'قراءة الجهاز', 'device']):
                            column_map['device_reading'] = col
                        # Result detection
                        elif any(term in col_str for term in ['result', 'نتيجة', 'النتيجة']):
                            column_map['result'] = col
                    
                    print(f"Column mapping for {filename}: {column_map}")
                    
                    # Process all rows (not just first few)
                    record_count = 0
                    for idx, row in df.iterrows():
                        # Skip header-like rows
                        if idx < 2:  # Allow for multiple header rows
                            first_cell = str(row.iloc[0]).lower().strip()
                            if any(term in first_cell for term in ['sample', 'كود', 'رقم', 'code']):
                                continue
                        
                        # Create record
                        record = {}
                        has_data = False
                        
                        for field, col in column_map.items():
                            if col in df.columns:
                                value = row[col]
                                if pd.notna(value) and str(value).strip():
                                    record[field] = str(value).strip()
                                    has_data = True
                                else:
                                    record[field] = ''
                        
                        # Skip empty records
                        if not has_data:
                            continue
                            
                        # Add classification flags
                        result_text = record.get('result', '').lower()
                        sample_name = record.get('sample_name', '').lower()
                        
                        record['is_non_compliant'] = 'غير مطابق' in result_text
                        record['is_compliant'] = 'مطابق' in result_text and 'غير' not in result_text
                        record['is_pepper'] = any(term in sample_name for term in ['فلفل', 'pepper', 'فلف'])
                        record['is_tomato'] = any(term in sample_name for term in ['طماطم', 'tomato'])
                        record['is_cucumber'] = any(term in sample_name for term in ['خيار', 'cucumber'])
                        
                        all_data.append(record)
                        record_count += 1
                    
                    print(f"Extracted {record_count} records from {filename}")
                            
                except Exception as e:
                    print(f"Error processing {filename}: {e}")
                    import traceback
                    traceback.print_exc()
        
        print(f"Total records extracted: {len(all_data)}")
        return all_data
    
    def create_formatted_table(self, data: List[dict], max_rows: int = 50) -> str:
        """Create a clean formatted table with ALL data (no artificial limits)"""
        if not data:
            return "No data available."
        
        # DON'T limit data - show everything found
        display_data = data  # Remove artificial limiting
        
        # Create table
        table = []
        table.append("**Pesticide Analysis Results:**\n")
        table.append("| كود العينة | اسم العينة | اسم المبيد | الحدود | قراءة الجهاز | النتيجة |")
        table.append("|----------|----------|---------|-------|----------|-------|")
        
        # Show ALL records, not just first few
        for record in display_data:
            # Clean empty values
            sample_code = record.get('sample_code', '').strip() or 'N/A'
            sample_name = record.get('sample_name', '').strip() or 'N/A'
            pesticide_name = record.get('pesticide_name', '').strip() or 'N/A'
            limits = record.get('limits', '').strip() or 'N/A'
            device_reading = record.get('device_reading', '').strip() or 'N/A'
            result = record.get('result', '').strip() or 'N/A'
            
            row = f"| {sample_code[:15]} | {sample_name[:20]} | {pesticide_name[:25]} | {limits[:12]} | {device_reading[:15]} | {result[:12]} |"
            table.append(row)
        
        # Add summary
        table.append(f"\n**الملخص Summary:**")
        table.append(f"- إجمالي السجلات Total records: {len(data)}")
        table.append(f"- جميع السجلات معروضة All records displayed: {len(display_data)}")
        
        return "\n".join(table)
    
    def answer_query(self, query: str, generation_client) -> str:
        """Enhanced query answering with structured processing"""
        
        # Get structured data
        structured_data = self.process_excel_to_structured_data()
        
        if not structured_data:
            return "No Excel data found."
        
        # Filter data based on query
        query_lower = query.lower()
        filtered_data = structured_data
        
        if 'غير مطابق' in query or 'non-compliant' in query_lower:
            filtered_data = [item for item in structured_data if item.get('is_non_compliant', False)]
        elif 'pepper' in query_lower or 'فلفل' in query:
            filtered_data = [item for item in structured_data if item.get('is_pepper', False)]
        
        if not filtered_data:
            return f"No data found matching query: {query}"
        
        # Create formatted response
        formatted_table = self.create_formatted_table(filtered_data)
        
        return formatted_table