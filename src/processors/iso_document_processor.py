# In src/processors/iso_document_processor.py
import re
from pathlib import Path
from typing import List, Dict, Any
import PyPDF2
import docx
import pandas as pd

def extract_iso_clauses(text: str) -> List[str]:
    """Extracts ISO 17025 clause numbers from text."""
    # This regex finds patterns like '7.2.1', 'clause 8.9', etc.
    clauses = re.findall(r'(?:clause\s)?(\b\d{1,2}\.\d{1,2}(?:\.\d{1,2})?\b)', text)
    return list(set(clauses))

def extract_document_hierarchy(text: str, document_type: str) -> Dict[str, Any]:
    """استخراج التسلسل الهرمي للمستند"""
    
    hierarchy_info = {
        "main_sections": [],
        "related_procedures": [],
        "referenced_documents": []
    }
    
    # استخراج العناوين الرئيسية
    sections = re.findall(r'^\d+\.\s+([^\n]+)', text, re.MULTILINE)
    hierarchy_info["main_sections"] = sections[:5]  # أول 5 عناوين
    
    # البحث عن مراجع المستندات
    doc_refs = re.findall(r'(PROC-\d+|QM-\d+|WI-\d+|FORM-\d+)', text)
    hierarchy_info["referenced_documents"] = list(set(doc_refs))
    
    return hierarchy_info

def parse_document_metadata(file_path: str, document_type: str = None) -> Dict[str, Any]:
    """Parses a document to extract text and ISO 17025 specific metadata."""
    path = Path(file_path)
    text_content = ""
    metadata = {
        "source_file": path.name,
        "document_type": "Unknown",
        "document_id": "Unknown",
        "related_clauses": []
    }

    # 1. Extract Document Type from folder structure
    # (e.g., '2_procedures' -> 'Procedure')
    parent_folder_name = path.parent.name.lower()
    if "quality_manual" in parent_folder_name:
        metadata["document_type"] = "Quality Manual"
    elif "procedures" in parent_folder_name:
        metadata["document_type"] = "Procedure"
    elif "work_instructions" in parent_folder_name:
        metadata["document_type"] = "Work Instruction"
    elif "forms" in parent_folder_name or "records" in parent_folder_name:
        metadata["document_type"] = "Form/Record"

    # 2. Extract Document ID from filename (e.g., "PROC-01")
    doc_id_match = re.search(r'([A-Z]+-\d+)', path.name)
    if doc_id_match:
        metadata["document_id"] = doc_id_match.group(1)

    # 3. Extract text content based on file type
    if path.suffix == ".pdf":
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text_content += page.extract_text() or ""
    elif path.suffix == ".docx":
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            text_content += para.text + "\n"
    elif path.suffix == ".xlsx":
        # For Excel, we'll just concatenate text from all cells
        df = pd.read_excel(file_path, sheet_name=None)
        for sheet_name, sheet_df in df.items():
            text_content += sheet_df.to_string()

    # 4. Extract ISO clauses from the text
    metadata["related_clauses"] = extract_iso_clauses(text_content)
    if document_type:
        metadata["document_type"] = document_type
    
    hierarchy_info = extract_document_hierarchy(text_content, document_type or metadata["document_type"])
    metadata.update(hierarchy_info)

    return {"text": text_content, "metadata": metadata}

# Example usage (for testing)
if __name__ == '__main__':
    # Assume you have the folder structure mentioned before
    test_file = 'iso_17025_documents/2_procedures/PROC-02_Pipette_Calibration.docx'
    result = parse_document_metadata(test_file)
    print(result['metadata'])
    # Expected output might be:
    # {'source_file': 'PROC-02_Pipette_Calibration.docx', 'document_type': 'Procedure', 
    #  'document_id': 'PROC-02', 'related_clauses': ['7.6', '6.4.4']}

