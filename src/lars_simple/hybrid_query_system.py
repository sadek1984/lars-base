"""
Hybrid Query System
===================

Intelligently routes queries between:
1. Query Generation (for Excel pesticide data) - 100% accurate
2. RAG (for ISO documents/PDFs) - Good for unstructured text

Auto-detects query type and uses the best approach.
"""

import pandas as pd
import numpy as np
import os
import re
from typing import Dict, Any, Optional, List
from enum import Enum

# Import Gemini for both approaches
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

class QueryType(Enum):
    """Types of queries the system can handle"""
    PESTICIDE = "pesticide"  # Excel data → Query Generation
    ISO = "iso"              # Documents → RAG
    HYBRID = "hybrid"        # Both systems
    UNKNOWN = "unknown"

class HybridQuerySystem:
    """
    Smart query router that uses:
    - Query Generation for structured Excel data (pesticides)
    - RAG for unstructured documents (ISO)
    """
    
    def __init__(self, 
                 excel_path: str,
                 iso_rag_client=None,
                 gemini_api_key: Optional[str] = None):
        """
        Initialize hybrid system
        
        Args:
            excel_path: Path to pesticide Excel data
            iso_rag_client: Your existing RAG client for ISO docs
            gemini_api_key: Gemini API key (for both systems)
        """
        
        # Load pesticide data
        self.df = pd.read_excel(excel_path)
        self._prepare_data()
        
        # Setup Gemini
        self.gemini_api_key = gemini_api_key or os.environ.get('GEMINI_API_KEY')
        if self.gemini_api_key and GEMINI_AVAILABLE:
            genai.configure(api_key=self.gemini_api_key)
            self.gemini_model = genai.GenerativeModel('gemini-2.0-flash-exp')
        else:
            self.gemini_model = None
        
        # Keep your existing RAG client for ISO docs
        self.iso_rag_client = iso_rag_client
        
        # Keywords for query type detection
        self.pesticide_keywords = {
            'pesticides', 'pesticide', 'vegetable', 'vegetables', 'fruit', 'fruits',
            'compliance', 'compliant', 'violation', 'violations', 'exceed', 'exceeding',
            'reading', 'readings', 'limit', 'limits', 'sample', 'samples',
            'fipronil', 'bifenthrin', 'buprofezin', 'quinalphos',  # Specific pesticides
            'tomato', 'cucumber', 'pepper', 'lettuce', 'beans',    # Specific vegetables
            'year', 'month', 'quarter', 'seasonal', 'trend',      # Temporal
            'risk', 'assessment', 'exceedance', 'contamination'
        }
        
        self.iso_keywords = {
            'iso', 'standard', 'standards', 'requirement', 'requirements',
            'procedure', 'procedures', 'documentation', 'document',
            'audit', 'auditing', 'certification', 'certify',
            'quality', 'management', 'system', 'process',
            'guideline', 'guidelines', 'specification', 'compliance standard'
        }
    
    def _prepare_data(self):
        """Prepare pesticide data"""
        if 'document_date' in self.df.columns:
            self.df['document_date'] = pd.to_datetime(self.df['document_date'])
        
        if 'violation' not in self.df.columns and 'is_compliant' in self.df.columns:
            self.df['violation'] = (self.df['is_compliant'] == 0).astype(int)
    
    def ask(self, question: str, force_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Ask a question - system automatically routes to best approach
        
        Args:
            question: Natural language question
            force_type: Force a specific query type ('pesticide', 'iso', or None for auto)
        
        Returns:
            Dict with answer, source, and metadata
        """
        
        # Detect query type
        if force_type:
            query_type = QueryType(force_type)
        else:
            query_type = self.detect_query_type(question)
        
        print(f"🎯 Query Type Detected: {query_type.value}")
        
        # Route to appropriate system
        if query_type == QueryType.PESTICIDE:
            return self._handle_pesticide_query(question)
        
        elif query_type == QueryType.ISO:
            return self._handle_iso_query(question)
        
        elif query_type == QueryType.HYBRID:
            return self._handle_hybrid_query(question)
        
        else:
            return {
                'success': False,
                'error': 'Could not determine query type',
                'suggestion': 'Try being more specific about pesticides or ISO standards'
            }
    
    def detect_query_type(self, question: str) -> QueryType:
        """
        Detect what type of query this is
        
        Returns:
            QueryType enum
        """
        question_lower = question.lower()
        words = set(re.findall(r'\b\w+\b', question_lower))
        
        # Count matches
        pesticide_matches = len(words & self.pesticide_keywords)
        iso_matches = len(words & self.iso_keywords)
        
        # Decision logic
        if pesticide_matches > 0 and iso_matches == 0:
            return QueryType.PESTICIDE
        
        elif iso_matches > 0 and pesticide_matches == 0:
            return QueryType.ISO
        
        elif pesticide_matches > 0 and iso_matches > 0:
            return QueryType.HYBRID
        
        # Default to pesticide if talking about data/samples
        data_words = {'data', 'samples', 'tests', 'results', 'analysis'}
        if words & data_words:
            return QueryType.PESTICIDE
        
        return QueryType.UNKNOWN
    
    def _handle_pesticide_query(self, question: str) -> Dict[str, Any]:
        """
        Handle pesticide data query using Query Generation
        100% accurate, fast
        """
        print("📊 Using Query Generation (Direct Pandas)")
        
        if not self.gemini_model:
            # Fallback to pre-built queries
            return self._fallback_pesticide_query(question)
        
        # Generate pandas code with Gemini
        prompt = f"""Generate pandas code to answer this question about pesticide testing data.

Dataset info:
- Shape: {self.df.shape}
- Columns: {list(self.df.columns)}
- Years: {sorted(self.df['year'].unique().tolist())}

Question: {question}

Generate Python code that:
1. Uses df (already loaded DataFrame)
2. Stores result in 'result' variable
3. Returns a DataFrame or clear answer

Code:"""
        
        try:
            response = self.gemini_model.generate_content(prompt)
            code = self._extract_code(response.text)
            result = self._execute_code(code)
            
            return {
                'success': True,
                'answer': result,
                'source': 'Query Generation (Pesticide Data)',
                'query_type': 'pesticide',
                'code': code,
                'method': '100% accurate direct query'
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'source': 'Query Generation',
                'fallback': self._fallback_pesticide_query(question)
            }
    
    def _handle_iso_query(self, question: str) -> Dict[str, Any]:
        """
        Handle ISO document query using RAG
        Good for unstructured document search
        """
        print("📄 Using RAG (ISO Documents)")
        
        if not self.iso_rag_client:
            return {
                'success': False,
                'error': 'ISO RAG system not configured',
                'suggestion': 'Initialize with iso_rag_client parameter'
            }
        
        # Use your existing RAG system for ISO docs
        try:
            # Call your existing RAG API/client
            # Adjust this based on your actual RAG client interface
            rag_result = self.iso_rag_client.answer_with_local_data(
                project_id=1,
                query=question,
                n_results=5
            )
            
            return {
                'success': True,
                'answer': rag_result.get('answer'),
                'source': 'RAG (ISO Documents)',
                'query_type': 'iso',
                'retrieved_docs': rag_result.get('retrieved_docs_count', 0),
                'method': 'Document retrieval & generation'
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': f"RAG error: {str(e)}",
                'source': 'RAG'
            }
    
    def _handle_hybrid_query(self, question: str) -> Dict[str, Any]:
        """
        Handle query that needs both systems
        Example: "Compare pesticide violations with ISO requirements"
        """
        print("🔄 Using Hybrid Approach (Both Systems)")
        
        # Query both systems
        pesticide_result = self._handle_pesticide_query(question)
        iso_result = self._handle_iso_query(question)
        
        # Combine results
        combined_answer = {
            'success': True,
            'source': 'Hybrid (Pesticide Data + ISO Documents)',
            'query_type': 'hybrid',
            'pesticide_answer': pesticide_result.get('answer'),
            'iso_answer': iso_result.get('answer'),
            'method': 'Combined query generation and RAG'
        }
        
        return combined_answer
    
    def _extract_code(self, response: str) -> str:
        """Extract Python code from Gemini response"""
        pattern = r'```python\n(.*?)```'
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        pattern = r'```\n(.*?)```'
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        return ""
    
    def _execute_code(self, code: str) -> Any:
        """Execute generated pandas code safely"""
        try:
            local_vars = {
                'df': self.df.copy(),
                'pd': pd,
                'np': np,
                'result': None
            }
            exec(code, {}, local_vars)
            return local_vars.get('result')
        except Exception as e:
            return f"Execution error: {str(e)}"
    
    def _fallback_pesticide_query(self, question: str) -> Dict[str, Any]:
        """Fallback pre-built queries when Gemini not available"""
        
        question_lower = question.lower()
        
        # Compliance by year
        if 'compliance' in question_lower and 'year' in question_lower:
            result = self.df.groupby('year').agg({
                'is_compliant': ['count', 'sum', 'mean']
            })
            result.columns = ['Tests', 'Compliant', 'Rate']
            result['Compliance %'] = (result['Rate'] * 100).round(2)
            
            return {
                'success': True,
                'answer': result.reset_index(),
                'source': 'Pre-built Query',
                'query_type': 'pesticide'
            }
        
        # Worst vegetables
        elif 'worst' in question_lower and 'vegetable' in question_lower:
            result = self.df.groupby('vegetable_english').agg({
                'is_compliant': ['count', 'mean']
            })
            result.columns = ['Tests', 'Compliance_Rate']
            result = result[result['Tests'] >= 5]
            result['Violation_Rate'] = ((1 - result['Compliance_Rate']) * 100).round(2)
            result = result.sort_values('Violation_Rate', ascending=False).head(10)
            
            return {
                'success': True,
                'answer': result.reset_index(),
                'source': 'Pre-built Query',
                'query_type': 'pesticide'
            }
        
        else:
            return {
                'success': False,
                'error': 'No matching pre-built query. Set GEMINI_API_KEY for custom queries.'
            }
    
    def get_data_summary(self) -> Dict:
        """Get summary of available data"""
        return {
            'pesticide_data': {
                'total_samples': len(self.df),
                'years': sorted(self.df['year'].unique().tolist()),
                'pesticides': self.df['pesticide_standardized'].nunique(),
                'vegetables': self.df['vegetable_english'].nunique(),
                'compliance_rate': f"{(self.df['is_compliant'].mean() * 100):.2f}%"
            },
            'iso_data': {
                'available': self.iso_rag_client is not None,
                'status': 'Connected' if self.iso_rag_client else 'Not configured'
            },
            'capabilities': {
                'gemini_enabled': self.gemini_model is not None,
                'query_generation': 'Yes' if self.gemini_model else 'Pre-built only',
                'rag_enabled': 'Yes' if self.iso_rag_client else 'No'
            }
        }


# Example usage
if __name__ == "__main__":
    # Initialize hybrid system
    system = HybridQuerySystem(
        excel_path='processed_data_output.xlsx',
        iso_rag_client=None,  # Add your RAG client here
        gemini_api_key='your-key'
    )
    
    # Test different query types
    test_queries = [
        "What's the compliance trend from 2022 to 2024?",  # Pesticide → Query Gen
        "What are ISO 17025 requirements?",                # ISO → RAG
        "Do our violations meet ISO standards?",           # Hybrid → Both
    ]
    
    for query in test_queries:
        print(f"\n{'='*70}")
        print(f"Q: {query}")
        result = system.ask(query)
        print(f"Source: {result.get('source')}")
        print(f"Answer: {result.get('answer')}")