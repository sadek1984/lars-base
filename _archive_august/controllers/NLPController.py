import logging
import json
from typing import List, Dict, Tuple, Optional, Any
import os
import pandas as pd
import numpy as np
from pathlib import Path
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
import google.generativeai as genai
from google.api_core import retry
import logging
from tqdm import tqdm
import io

from .BaseControllers import BaseControllers
from models.db_schemes import Project, DataChunk
from stores.llm.LLMEnum import DocumentTypeEnum

import re
from bidi.algorithm import get_display

# استيراد الـ Parser المتخصص الجديد لتقارير المبيدات
from stores.llm.templates.pesticide_templates import PesticideTemplateParser

from utils.data_cleaning import clean_pesticide_data, load_and_prepare_excel, format_rows_as_text

from io import BytesIO # <-- Add this import
from utils.response_parser import parse_llm_response_to_df
from services.risk_assessment_service import RiskAssessmentService
from models.risk_assessment_models import PopulationType, RiskAssessmentSummary





class NLPController(BaseControllers):
    """
    Enhanced NLP Controller that integrates pesticide-specific query analysis
    with improved document retrieval and filtering logic.
    """

    def __init__(self, vectordb_client, generation_client, 
                 embedding_client, template_parser):
        super().__init__()

        self.vectordb_client = vectordb_client
        self.generation_client = generation_client
        self.embedding_client = embedding_client
        
        # الـ Parser العام للـ RAG القياسي
        self.template_parser = template_parser
        # الـ Parser المتخصص لتقارير المبيدات
        self.pesticide_template_parser = PesticideTemplateParser()
        
        self.logger = logging.getLogger(__name__)

    # --- الدوال المتوافقة مع المشروع الأصلي (بدون تغيير) ---

    def create_collection_name(self, project_id: str):
        return f"collection_{self.vectordb_client.default_vector_size}_{project_id}".strip()
    
    async def reset_vector_db_collection(self, project: Project):
        collection_name = self.create_collection_name(project_id=project.project_id)
        return await self.vectordb_client.delete_collection(collection_name=collection_name)
    
    async def get_vector_db_collection_info(self, project: Project):
        collection_name = self.create_collection_name(project_id=project.project_id)
        collection_info = await self.vectordb_client.get_collection_info(collection_name=collection_name)
        return json.loads(json.dumps(collection_info, default=lambda x: x.__dict__))
    
    async def index_into_vector_db(self, project: Project, chunks: List[DataChunk],
                                   chunks_ids: List[int], 
                                   do_reset: bool = False):
        collection_name = self.create_collection_name(project_id=project.project_id)
        texts = [c.chunk_text for c in chunks]
        metadata = [c.chunk_metadata for c in chunks]
        vectors = self.embedding_client.embed_text(text=texts, 
                                                  document_type=DocumentTypeEnum.DOCUMENT.value)
        await self.vectordb_client.create_collection(
            collection_name=collection_name,
            embedding_size=self.embedding_client.embedding_size,
            do_reset=do_reset,
        )
        await self.vectordb_client.insert_many(
            collection_name=collection_name,
            texts=texts,
            metadata=metadata,
            vectors=vectors,
            record_ids=chunks_ids,
        )
        return True

    async def search_vector_db_collection(self, project: Project, text: str, limit: int = 100):
        collection_name = self.create_collection_name(project_id=project.project_id)
        vectors = self.embedding_client.embed_text(text=text, 
                                                 document_type=DocumentTypeEnum.QUERY.value)
        if not vectors or not vectors[0]: 
            return False
        
        results = await self.vectordb_client.search_by_vector(
            collection_name=collection_name,
            vector=vectors[0],
            limit=limit
        )
        return results if results else False
    
    # --- الدوال الجديدة والمنطق المدمج المحسن ---

    def analyze_query_intent(self, query: str) -> dict:
        """
        Enhanced query intent analysis with better keyword detection.
        """
        query_lower = query.lower()
        intent_info = {
            'type': 'general', 
            'filters': {},
            'keywords': [],
            'search_terms': []
        }

        # Intent detection with Arabic and English support
        if any(term in query_lower for term in ['غير مطابق', 'non-compliant', 'non compliant', 'failed', 'exceed']):
            intent_info['type'] = 'non_compliant'
            intent_info['filters']['result_contains'] = 'غير مطابق'
            intent_info['keywords'].extend(['غير مطابق', 'non-compliant'])
        elif any(term in query_lower for term in ['مطابق', 'compliant', 'passed', 'acceptable']) and 'غير مطابق' not in query_lower:
            intent_info['type'] = 'compliant'
            intent_info['filters']['result_contains'] = 'مطابق'
            intent_info['keywords'].extend(['مطابق', 'compliant'])
        elif any(term in query_lower for term in ['summary', 'ملخص', 'تقرير', 'report', 'overview']):
            intent_info['type'] = 'summary'

        # Enhanced sample type detection
        sample_mappings = {
            'pepper': ['pepper', 'فلفل', 'bell pepper', 'capsicum'],
            'tomato': ['tomato', 'طماطم', 'tomatoes'],
            'cucumber': ['cucumber', 'خيار', 'cucumbers'],
            'eggplant': ['eggplant', 'باذنجان', 'aubergine'],
            'lettuce': ['lettuce', 'خس', 'salad'],
            'carrot': ['carrot', 'جزر', 'carrots']
        }
        
        for sample_type, keywords in sample_mappings.items():
            if any(keyword in query_lower for keyword in keywords):
                intent_info['filters']['sample_name_contains'] = sample_type
                intent_info['keywords'].extend(keywords)
                break

        # Build search terms for better vector retrieval
        intent_info['search_terms'] = intent_info['keywords'].copy()
        if intent_info['type'] != 'general':
            intent_info['search_terms'].append(query)
        
        return intent_info

    def filter_documents_by_intent(self, documents: List, intent_info: dict) -> List:
        """
        Enhanced document filtering based on intent analysis.
        """
        if not documents or intent_info['type'] == 'general':
            return documents
        
        filtered_docs = []
        
        for doc in documents:
            metadata = getattr(doc, 'metadata', {})
            content = getattr(doc, 'text', getattr(doc, 'page_content', ''))
            
            # Skip if not pesticide data
            if metadata.get('record_type') != 'pesticide_reading':
                continue
            
            match = True
            
            # Filter by result compliance
            if 'result_contains' in intent_info['filters']:
                expected_result = intent_info['filters']['result_contains']
                actual_result = str(metadata.get('result', '')).lower()
                content_lower = content.lower()
                
                if expected_result.lower() not in actual_result and expected_result.lower() not in content_lower:
                    match = False
            
            # Filter by sample name
            if 'sample_name_contains' in intent_info['filters']:
                expected_sample = intent_info['filters']['sample_name_contains']
                actual_sample = str(metadata.get('sample_name', '')).lower()
                content_lower = content.lower()
                
                # Check both metadata and content
                sample_found = False
                for keyword in sample_mappings.get(expected_sample, [expected_sample]):
                    if keyword.lower() in actual_sample or keyword.lower() in content_lower:
                        sample_found = True
                        break
                
                if not sample_found:
                    match = False
            
            if match:
                filtered_docs.append(doc)
        
        return filtered_docs

    async def enhanced_document_search(self, project: Project, query: str, intent_info: dict, limit: int = 10) -> List:
        """
        Enhanced document search with multiple strategies.
        """
        all_documents = []
        
        # Strategy 1: Direct query search
        direct_results = await self.search_vector_db_collection(project, query, limit)
        if direct_results:
            all_documents.extend(direct_results)
        
        # Strategy 2: Search with intent-specific terms
        for search_term in intent_info.get('search_terms', []):
            if search_term != query:  # Avoid duplicate searches
                term_results = await self.search_vector_db_collection(project, search_term, limit//2)
                if term_results:
                    all_documents.extend(term_results)
        
        # Strategy 3: Broader search for specific intents
        if intent_info['type'] in ['non_compliant', 'compliant']:
            broader_terms = ['pesticide', 'مبيد', 'analysis', 'تحليل', 'result', 'نتيجة']
            for term in broader_terms:
                broad_results = await self.search_vector_db_collection(project, term, limit//4)
                if broad_results:
                    all_documents.extend(broad_results)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_docs = []
        for doc in all_documents:
            doc_id = getattr(doc, 'id', id(doc))
            if doc_id not in seen:
                seen.add(doc_id)
                unique_docs.append(doc)
        
        return unique_docs

    

    def extract_structured_data(self, documents: list) -> list:
        """
        Extract structured data from documents for better processing
        """
        structured_data = []
        
        for doc in documents:
            content = getattr(doc, 'text', getattr(doc, 'page_content', ''))
            
            # Split content into lines and process each line
            lines = content.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or 'sample code' in line.lower():
                    continue
                
                # Try to extract structured data from line
                data_parts = [part.strip() for part in line.split('\t') if part.strip()]
                
                # If we have enough parts, consider it a data row
                if len(data_parts) >= 4:
                    reading = {
                        'sample_code': data_parts[0] if len(data_parts) > 0 else '',
                        'sample_name': data_parts[1] if len(data_parts) > 1 else '',
                        'pesticide_name': data_parts[2] if len(data_parts) > 2 else '',
                        'limits': data_parts[3] if len(data_parts) > 3 else '',
                        'device_reading': data_parts[4] if len(data_parts) > 4 else '',
                        'result': data_parts[5] if len(data_parts) > 5 else '',
                        'raw_line': line
                    }
                    
                    # Add classification flags
                    reading['is_non_compliant'] = 'غير مطابق' in reading['result']
                    reading['is_compliant'] = 'مطابق' in reading['result'] and 'غير' not in reading['result']
                    reading['is_pepper'] = any(pepper_term in reading['sample_name'].lower() 
                                            for pepper_term in ['فلفل', 'pepper', 'فلف'])
                    
                    structured_data.append(reading)
        
        return structured_data

    def format_table_output(self, data: list, query_type: str = 'general') -> str:
        """
        Format data into clean table output
        """
        if not data:
            return "No matching data found."
        
        # Filter data based on query type
        if 'غير مطابق' in query_type or 'non-compliant' in query_type.lower():
            filtered_data = [item for item in data if item.get('is_non_compliant', False)]
        elif 'pepper' in query_type.lower() or 'فلفل' in query_type:
            filtered_data = [item for item in data if item.get('is_pepper', False)]
        elif 'pesticide' in query_type.lower() or 'مبيد' in query_type:
            filtered_data = data  # Show all for pesticide queries
        else:
            filtered_data = data
        
        if not filtered_data:
            return f"No data found matching the criteria: {query_type}"
        
        # Create formatted table
        output = []
        output.append("**Pesticide Analysis Results:**\n")
        
        # Table header
        output.append("| كود العينة | اسم العينة | اسم المبيد | الحدود | قراءة الجهاز | النتيجة |")
        output.append("|----------|----------|---------|-------|----------|-------|")
        
        # Table rows
        for item in filtered_data[:20]:  # Limit to 20 rows for readability
            row = f"| {item.get('sample_code', 'N/A')[:15]} | {item.get('sample_name', 'N/A')[:15]} | {item.get('pesticide_name', 'N/A')[:20]} | {item.get('limits', 'N/A')[:10]} | {item.get('device_reading', 'N/A')[:15]} | {item.get('result', 'N/A')[:10]} |"
            output.append(row)
        
        # Add summary
        output.append(f"\n**Summary:**")
        output.append(f"- Total records found: {len(filtered_data)}")
        output.append(f"- Records shown: {min(20, len(filtered_data))}")
        
        if len(filtered_data) > 20:
            output.append("- *Showing first 20 records*")
        
        return "\n".join(output)


    async def answer_rag_question(self, project: Project, query: str, limit: int = 100) -> tuple[str, str, list]:
        """Answer query using RAG - COLAB APPROACH"""
        print(f"Processing query: {query}")
        
        # Query vector store
        retrieved_documents = await self.search_vector_db_collection(project, query, limit)
        
        # Correct way to check if a list is empty or invalid
        if not retrieved_documents:
            return "No relevant documents found.", "", []
        
        # Extract structured data
        structured_data = self.extract_structured_data(retrieved_documents)
        
        if not structured_data:
            # Fallback to original approach
            combined_content = []
            for doc in retrieved_documents:
                content = getattr(doc, 'text', getattr(doc, 'page_content', ''))
                combined_content.append(content)
            
            combined_passage = " ".join(combined_content)
            
            # Clean up for prompt
            passage_oneline = combined_passage.replace("\n", " ")
            query_oneline = query.replace("\n", " ")
            
            # Create prompt (EXACT COLAB STYLE)
            prompt = f"""You are a helpful assistant summarizing pesticide readings.
    List readings where النتيجة (result) is 'غير مطابق' for pepper in a structured format.
    QUESTION: {query_oneline}
    PASSAGE: {passage_oneline}
    ⚠️ Important:
    - Do NOT summarize, list every individual reading.
    - Separate values clearly structured.
    - If there are multiple values, provide all of them.
    Example output:
    - كود العينة sample code, اسم العينة Sample Name, اسم المبيد Pesticide Name, الحدود Limits, قراءة الجهاز Reading of device, النتيجة result
    """
            
            # Generate answer
            try:
                answer = self.generation_model.generate_content(prompt)
                return answer.text, prompt, []  # Return answer, prompt, empty chat_history
            except Exception as e:
                return f"Error generating response: {e}", prompt, []
        
        else:
            # Handle structured data case (you need to implement this logic)
            # For now, returning the structured data or processing it further
            try:
                # You might want to format structured_data here
                # This is a placeholder - implement based on your structured_data format
                prompt = f"Process this structured data: {structured_data}"
                answer = self.generation_model.generate_content(prompt)
                return answer.text, prompt, []  # Return answer, prompt, empty chat_history
            except Exception as e:
                return f"Error generating response: {e}", "", []
            
    # --- NEW METHOD FOR ISO 17025 ---
    async def answer_iso_question(
        self,
        project: dict,
        query: str,
        limit: int = 5,
    ) -> tuple[str, str, list]:
        """
        Answers a question using RAG with special metadata filtering for ISO documents.
        This method is the core of the intelligent search.
        """
        # 1. Create a metadata filter based on keywords in the user's question.
        metadata_filter: Dict[str, Any] = {}
        question_lower = query.lower()

        if "procedure" in question_lower or "sop" in question_lower:
            metadata_filter = {"document_type": "Procedure"}
        elif "quality manual" in question_lower or "policy" in question_lower:
            metadata_filter = {"document_type": "Quality Manual"}
        elif "work instruction" in question_lower or "how to" in question_lower:
            metadata_filter = {"document_type": "Work Instruction"}
        
        # 2. Perform similarity search using the vector DB
        # Note: We assume the search method is updated to accept a metadata_filter
        embedding = await self.embedding_client.embed_query(query)
        chunks = await self.vectordb_client.search(
            project_id=project.get("id"),
            embedding=embedding,
            limit=limit,
            metadata_filter=metadata_filter  # <-- The key improvement
        )

        if not chunks:
            return None, None, None

        # 3. Generate the prompt and get the answer from the LLM
        context = "\n---\n".join([chunk.get("content") for chunk in chunks])
        full_prompt = self.template_parser.get_prompt(
            context=context,
            query=query,
            template_name="rag_en" # Or your default template
        )
        answer = await self.generation_client.generate(full_prompt)
        
        # 4. Prepare sources from the retrieved chunks' metadata
        sources = list(set([
            chunk.get("metadata", {}).get('source_file', 'Unknown') 
            for chunk in chunks
        ]))
        
        return answer, full_prompt, sources

            


class GeminiEmbeddingFunction(EmbeddingFunction):
    """Custom embedding function for ChromaDB using Gemini"""
    
    def __init__(self, api_key: str, model: str = "models/text-embedding-004"):
        genai.configure(api_key=api_key)
        self.model = model
        self.document_mode = True
    
    def __call__(self, input: Documents) -> Embeddings:
        embedding_task = "retrieval_document" if self.document_mode else "retrieval_query"
        retry_policy = {"retry": retry.Retry(predicate=retry.if_transient_error)}
        
        try:
            response = genai.embed_content(
                model=self.model,
                content=input,
                task_type=embedding_task,
                request_options=retry_policy,
            )
            return response["embedding"]
        except Exception as e:
            print(f"Embedding error: {e}")
            # Return zero embeddings as fallback
            return [[0.0] * 768 for _ in input]


# ========== ENHANCED NLP CONTROLLER ==========
class EnhancedNLPController:
    """Enhanced NLP Controller with local data processing"""
    VEGETABLE_SYNONYMS = {
    # English → Arabic mappings
    "tomato": ["طماطم", "tomato", "tomatoes"],
    "cucumber": ["خيار", "cucumber", "cucumbers"],
    "pepper": ["فلفل", "pepper", "peppers", "فلفل بارد", "فلفل حار"],
    "hot pepper": ["فلفل حار", "فلفل حار احمر", "فلفل حار اخضر", "فلفل أخضر حار", "فلفل أحمر حار"],
    "sweet pepper": ["فلفل بارد", "فلفل بارد اخضر", "فلفل احمر بارد", "فلفل ملون"],
    "eggplant": ["باذنجان", "eggplant", "aubergine"],
    "zucchini": ["كوسة", "zucchini", "courgette"],
    "okra": ["باميا", "okra", "bamia"],
    "parsley": ["بقدونس", "parsley"],
    "lettuce": ["خس", "lettuce"],
    "mint": ["نعناع", "mint"],
    "arugula": ["جرجير", "arugula", "rocket"],
    "spinach": ["سبانخ", "spinach"],
    "cabbage": ["ملفوف", "cabbage"],
    "strawberry": ["فراولة", "strawberry", "strawberries"],
    "pomegranate": ["رمان", "pomegranate"],
    "melon": ["شمام", "melon", "cantaloupe"],
    "pumpkin": ["قرع", "pumpkin", "squash", "قرع امريكى", "قرع نجدى"],
    "fig": ["تين", "fig", "figs"],
    "orange": ["برتقال", "orange", "oranges"],
    "lemon": ["ليمون", "lemon", "lemons"],
    "beans": ["فاصوليا", "beans", "فاصوولياج"],
    
    # Arabic → variations mappings
    "طماطم": ["طماطم", "tomato", "tomatoes"],
    "خيار": ["خيار", "cucumber", "cucumbers"],
    "فلفل": ["فلفل", "pepper", "فلفل بارد", "فلفل حار", "فلفل ملون"],
    "باذنجان": ["باذنجان", "eggplant", "aubergine"],
}
    # Class-level constants - MUST be indented at class level
    PESTICIDE_KEYWORDS = [
        "Buprofezin", "Quinalphos", "Bifenthrin", "Pyridaben", "Procymidon",
        "Cyhalothrin", "Fipronil", "Bifenazate", "Lampda-Cyhalothrin", 
        "Deltamethrin", "Lampda- cyhalothrin", "Bifenzate", "Bifnthrin",
        "Bifanazate", "Buprifezin", "Lambda_cyhalothrin", "Fenpropathrin",
        "Myclobutanil", "Ptridaben", "Pyriproxyfen", "Atrazine", "Profenofos",
        "Bifenazat", "Diazinone", "Pendimethlin", "Pyriproxifen", "Triadiminol",
        "Triadimenol", "Pyridben", "Chlorfenapyr", "PYRIDABIEN", "Paclobutrazole",
        "Pyripoxifen", "Pendimerhanil", "Pendimethalin", "Paclobutrazol",
        "Bifenthein", "Quinalphose"
    ]
    
    VEGETABLE_KEYWORDS = [
        "فلفل احمر بارد", "فلفل حار احمر", "بقدونس", "كوسة", "خيار", "طماطم",
        "فاصوليا", "فلفل بارد اخضر", "فلفل أحمر حار", "فلفل أخضر بارد",
        "فلفل حار اخضر", "باذنجان", "خس", "فلفل بارد", "فراولة", "ملفوف",
        "باميا", "تين", "فلفل ملون بارد", "فلفل ملون", "فلفل أخضر حار",
        "قرع", "رمان", "قرع نجدى", "الوبا", "فلفل بارد ملون", "فروت", "قثة",
        "فلفل بارد احمر", "برتقال", "ليمون", "فاصوولياج", "با", "قرع امريكى",
        "نعناع", "جرجير", "شمام", "سبانخ", "فلفل بارداخضر"
    ]
    def __init__(self, 
                 vectordb_client=None,
                 generation_client=None,
                 embedding_client=None,
                 template_parser=None,
                 gemini_api_key: str = None):
        
        # Keep existing clients for compatibility
        self.vectordb_client = vectordb_client
        self.generation_client = generation_client
        self.embedding_client = embedding_client
        self.template_parser = template_parser

        import os
        self.logger = logging.getLogger(__name__)

        # New ChromaDB setup for local data
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        if self.gemini_api_key:

            chroma_db_path = "/app/chroma_db"
            # Ensure directory exists
            
            os.makedirs(chroma_db_path, exist_ok=True)

            # Use PersistentClient to save data to disk
            self.chroma_client = chromadb.PersistentClient(
            path=chroma_db_path,
            settings=chromadb.Settings(
                anonymized_telemetry=False,  # Disable telemetry errors
                allow_reset=True
            )
        )
            self.embed_fn = GeminiEmbeddingFunction(
                api_key=self.gemini_api_key,
                model="models/text-embedding-004"
            )
            
            # Configure Gemini for generation
            genai.configure(api_key=self.gemini_api_key)
            self.generation_model = genai.GenerativeModel("gemini-2.5-flash")
            self.logger.info(f"ChromaDB initialized with persistent path: {chroma_db_path}")
        else:
            self.chroma_client = None
            self.embed_fn = None
            self.generation_model = None
        

    def verify_collection_health(self, project_id: int, year: str) -> Dict:
        """Verify collection exists and has data"""
        
        collection_name = f"local_project_{project_id}_year_{year}"
        
        try:
            collection = self.chroma_client.get_collection(
                name=collection_name,
                embedding_function=self.embed_fn
            )
            
            count = collection.count()
            
            # Test a simple query
            test_result = collection.query(query_texts=["test"], n_results=1)
            
            return {
                "exists": True,
                "count": count,
                "name": collection_name,
                "can_query": len(test_result["documents"][0]) > 0 if test_result["documents"] else False
            }
            
        except Exception as e:
            return {
                "exists": False,
                "error": str(e),
                "name": collection_name
            }

    async def answer_and_export_local_data(self, project_id: int, query: str, n_results: int = 100) -> Optional[io.BytesIO]:
        """
        Answers a query using local ChromaDB data and returns the result as an Excel file in memory.
        (Simplified version)
        """
        self.logger.info(f"Received export request for project {project_id} (simplified logic)")
        # First, get the standard text-based answer from the existing method
        response_data = await self.answer_with_local_data(project_id, query, n_results)

        if not response_data.get("success"):
            self.logger.error("Failed to get a successful response from the LLM. Cannot generate Excel file.")
            return None

        answer_text = response_data.get("answer")
        if not answer_text:
            self.logger.error("LLM response was empty. Cannot generate Excel file.")
            return None
            
        # Use our robust utility to parse the markdown table into a DataFrame
        self.logger.info("Parsing LLM response into a DataFrame...")
        df = parse_llm_response_to_df(answer_text)

        if df is None or df.empty:
            self.logger.error("Failed to parse the LLM response into a structured table or the result was empty.")
            return None
        # --- NEW STEP: Apply calculations based on the query ---
        df = self._apply_query_calculations(df, query)
        if df.empty:
            self.logger.warning("DataFrame is empty after applying calculations. No data to export.")
            # Still return an empty file so the user knows the query yielded no results
            pass

        # Save the resulting DataFrame directly to an in-memory Excel file
        self.logger.info(f"Successfully created DataFrame with {len(df)} rows. Saving to Excel format.")
        output_buffer = io.BytesIO()
        df.to_excel(output_buffer, index=False, sheet_name="Query Results")
        output_buffer.seek(0)  # Rewind the buffer to the beginning

        return output_buffer






    ############### NEW METHODS FOR Arabic text direction ###############

    def fix_arabic_text_direction(self, text):
        """Simple Arabic text preservation without complex reshaping"""
        if not isinstance(text, str):
            return text
        
        # Just return the text as-is for now - no reshaping
        # The libraries are causing text to disappear
        return text

    # def process_local_excel_files(self, data_folder_path: str, months: List[str] = None) -> tuple:
    #     """Process local Excel files from month folders"""
    #     if months is None:
    #         months = ["Jan","Feb", "March", "April", "May", "June",
    #                 "July", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
    #     documents = []
    #     metadata_list = []
    #     data_path = Path(data_folder_path)
        
    #     if not data_path.exists():
    #         raise ValueError(f"Data folder not found: {data_path}")
        
    #     self.logger.info(f"Processing local Excel files from: {data_path}")
        
    #     for month_folder in months:
    #         month_path = data_path / month_folder
            
    #         if not month_path.exists():
    #             self.logger.warning(f"Month folder not found: {month_path}")
    #             continue
                
    #         self.logger.info(f"Processing month: {month_folder}")
            
    #         for file_path in month_path.glob("*.xlsx"):
            
    #             try:
    #                 # Go back to simple approach - just match Colab exactly
    #                 # df = pd.read_excel(file_path, skiprows=10)
                    
    #                 # 1. Use the robust function to load the Excel file into a DataFrame
    #                 df = load_and_prepare_excel(str(file_path))
                    
    #                 if df is None or df.empty:
    #                     self.logger.warning(f"File skipped, could not find valid headers or data: {file_path.name}")
    #                     continue
                    
    #                 # 2. Clean the DataFrame to remove rows with no pesticide data
    #                 cleaned_df = clean_pesticide_data(df)
                    
    #                 if cleaned_df.empty:
    #                     self.logger.warning(f"File skipped after cleaning (no valid pesticide rows): {file_path.name}")
    #                     continue

    #                 # 3. NEW: Format each valid row into a descriptive sentence
    #                 row_texts = format_rows_as_text(cleaned_df)
                    
    #                 # Add each sentence as a separate document to be indexed
    #                 for text in row_texts:
    #                     documents.append(text)
    #                     metadata_list.append({
    #                         "source_file": file_path.name,
    #                         "month": month_folder,
    #                         "file_path": str(file_path),
    #                         "data_type": "local_excel_row",
    #                     })
                    
    #                 self.logger.info(f"Processed: {file_path.name}, created {len(row_texts)} documents from rows.")

    #             except Exception as e:
    #                 self.logger.error(f"Critical error processing {file_path.name}: {e}")


    #     self.logger.info(f"Total local documents processed: {len(documents)}")
    #     return documents, metadata_list
    #     print(documents[0][:20])  # Print first 5 chars of first document for verification



    def process_local_excel_files(self, data_folder_path: str, months: List[str] = None) -> tuple:
        """Process local Excel files from month folders"""
        
        documents = []
        metadata_list = []
        data_path = Path(data_folder_path)
        
        if not data_path.exists():
            raise ValueError(f"Data folder not found: {data_path}")
        
        self.logger.info(f"Processing local Excel files from: {data_path}")
        
        # AUTO-DISCOVER all subdirectories if months not specified
        if not months:
            all_folders = [f.name for f in data_path.iterdir() if f.is_dir()]
            months = all_folders
            self.logger.info(f"Auto-discovered {len(months)} folders: {months}")
        
        for month_folder in months:
            month_path = data_path / month_folder
            
            if not month_path.exists() or not month_path.is_dir():
                self.logger.warning(f"Skipping non-directory: {month_path}")
                continue
                
            self.logger.info(f"Processing folder: {month_folder}")
            
            # Find all Excel files
            excel_files = list(month_path.glob("*.xlsx"))
            self.logger.info(f"Found {len(excel_files)} Excel files in {month_folder}")
            
            for file_path in excel_files:
                try:
                    # Load Excel file
                    df = load_and_prepare_excel(str(file_path))
                    
                    if df is None or df.empty:
                        self.logger.warning(f"Skipped (no valid data): {file_path.name}")
                        continue
                    
                    # Clean the data
                    cleaned_df = clean_pesticide_data(df)
                    
                    if cleaned_df.empty:
                        self.logger.warning(f"Skipped (empty after cleaning): {file_path.name}")
                        continue
                    
                    # Format rows as text
                    row_texts = format_rows_as_text(cleaned_df)
                    
                    if not row_texts:
                        self.logger.warning(f"Skipped (no text generated): {file_path.name}")
                        continue
                    
                    # Add documents
                    for text in row_texts:
                        documents.append(text)
                        metadata_list.append({
                            "source_file": file_path.name,
                            "month": month_folder,
                            "file_path": str(file_path),
                            "data_type": "local_excel_row",
                        })
                    
                    self.logger.info(f"✓ Processed {file_path.name}: {len(row_texts)} documents")
                    
                except Exception as e:
                    self.logger.error(f"Error processing {file_path.name}: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
        
        self.logger.info(f"Total documents processed: {len(documents)}")
        return documents, metadata_list


    def create_local_collection(self, project_id: int, documents: List[str],
                        metadata_list: List[Dict], do_reset: bool = False,
                        year: Optional[str] = None) -> Any:
        
        self.logger.error(f"DEBUG: create_local_collection called with year={year}")
        self.logger.error(f"DEBUG: project_id={project_id}, do_reset={do_reset}")
        self.logger.error(f"DEBUG: Number of documents={len(documents)}")
    
        """Create ChromaDB collection for local data with year-specific naming"""
        if not self.chroma_client:
            raise ValueError("ChromaDB not initialized. Check GEMINI_API_KEY.")
        
        # Set to document mode for indexing
        self.embed_fn.document_mode = True
        
        # Use year in collection name if provided
        if year:
            collection_name = f"local_project_{project_id}_year_{year}"
        else:
            collection_name = f"local_project_{project_id}"
        
        # Delete existing collection if reset requested
        if do_reset:
            try:
                self.chroma_client.delete_collection(name=collection_name)
                self.logger.info(f"Deleted existing collection: {collection_name}")
            except Exception:
                pass
        
        # Create or get collection
        collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embed_fn,
            metadata={"project_id": project_id, "year": year} if year else {"project_id": project_id}
        )
        
        # Add documents in batches
        batch_size = 50
        for i in tqdm(range(0, len(documents), batch_size), desc=f"Indexing {year or 'local'} data"):
            batch_docs = documents[i:i+batch_size]
            batch_metadata = metadata_list[i:i+batch_size]
            
            # Include year in document IDs for better tracking
            if year:
                batch_ids = [f"{year}_doc_{j}" for j in range(i, i+len(batch_docs))]
            else:
                batch_ids = [f"doc_{j}" for j in range(i, i+len(batch_docs))]
            
            try:
                collection.add(
                    documents=batch_docs,
                    ids=batch_ids,
                    metadatas=batch_metadata
                )
            except Exception as e:
                self.logger.error(f"Error adding batch {i//batch_size + 1}: {e}")
        
        final_count = collection.count()
        self.logger.info(f"Local collection '{collection_name}' created: {final_count} documents indexed")
        return collection

    ############### NEW METHODS FOR DataFrame calculations ###############
         ############### e.g. reading > (X * limit) ###############
    

    def find_column_robust(self, df: pd.DataFrame, keywords: List[str]) -> str | None:
        """
        Robustly finds a column in a DataFrame by searching for keywords.
        Handles variations like newlines, extra spaces, and mixed languages.
        """
        for col in df.columns:
            # Normalize the column name to make matching more reliable
            normalized_col = re.sub(r'\s+', ' ', str(col)).strip().lower()
            for keyword in keywords:
                if keyword.lower() in normalized_col:
                    return col
        return None

    def analyze_pesticide_contamination_levels(self, df: pd.DataFrame, multiplier_threshold: float = 1.0) -> pd.DataFrame:
        """
        Analyzes pesticide contamination levels by comparing reading values with limits.
        Filters for samples where reading > (multiplier_threshold * limit).
        """
        self.logger.error(f"DEBUG: Starting analyze_pesticide_contamination_levels with threshold {multiplier_threshold}")
        
        try:
            self.logger.info(f"Analyzing contamination levels with threshold: {multiplier_threshold}x the limit")
            self.logger.info(f"Input DataFrame shape: {df.shape}")
            
            # Find the required columns using robust search
            self.logger.error(f"DEBUG: About to search for columns")
            reading_col = self.find_column_robust(df, ['قراءة الجهاز', 'reading of device', 'reading value', 'قراءة'])
            limit_col = self.find_column_robust(df, ['الحدود', 'limits', 'limit', 'حدود'])
            pesticide_col = self.find_column_robust(df, ['اسم المبيد', 'pesticide name', 'pesticide'])
            sample_col = self.find_column_robust(df, ['كود العينة', 'sample code', 'code'])
            
            self.logger.error(f"DEBUG: Found columns - Reading: {reading_col}, Limit: {limit_col}")
            self.logger.error(f"DEBUG: Additional columns - Pesticide: {pesticide_col}, Sample: {sample_col}")
            
            # Check if essential columns were found
            if not reading_col or not limit_col:
                self.logger.error("Cannot analyze contamination - missing essential columns (reading or limit)")
                self.logger.error(f"Available columns: {df.columns.tolist()}")
                return pd.DataFrame()
            
            # Create a working copy
            self.logger.error(f"DEBUG: Creating working copy of DataFrame")
            df_work = df.copy()
            
            # Log sample values before processing
            self.logger.error(f"DEBUG: Logging sample data before processing")
            for i in range(min(3, len(df_work))):
                row = df_work.iloc[i]
                reading_val = row.get(reading_col, 'N/A')
                limit_val = row.get(limit_col, 'N/A')
                self.logger.error(f"  Row {i}: Reading={reading_val}, Limit={limit_val}")
            
            # Clean and convert data
            self.logger.error(f"DEBUG: Starting data cleaning")
            # Handle Arabic "لا يوجد" (no data) values
            df_work[limit_col] = df_work[limit_col].replace(['لا يوجد', 'N/A', ''], pd.NA)
            df_work[reading_col] = df_work[reading_col].replace(['لا يوجد', 'N/A', ''], pd.NA)
            
            # Convert to numeric, handling errors gracefully
            self.logger.error(f"DEBUG: Converting to numeric")
            df_work[reading_col] = pd.to_numeric(df_work[reading_col], errors='coerce')
            df_work[limit_col] = pd.to_numeric(df_work[limit_col], errors='coerce')
            
            # Log conversion results
            self.logger.error(f"DEBUG: Logging data after numeric conversion")
            for i in range(min(3, len(df_work))):
                row = df_work.iloc[i]
                reading_val = row.get(reading_col, 'N/A')
                limit_val = row.get(limit_col, 'N/A')
                self.logger.error(f"  Row {i} after conversion: Reading={reading_val}, Limit={limit_val}")
            
            # Remove rows with missing or invalid data
            self.logger.error(f"DEBUG: About to drop NaN values")
            initial_count = len(df_work)
            df_work = df_work.dropna(subset=[reading_col, limit_col])
            final_count = len(df_work)
            
            self.logger.error(f"DEBUG: Data cleaning: {initial_count} -> {final_count} rows")
            
            if df_work.empty:
                self.logger.error("DEBUG: No valid data remaining after cleaning")
                return pd.DataFrame()
            
            # Calculate the contamination ratio for each sample
            self.logger.error(f"DEBUG: Calculating contamination ratios")
            df_work['contamination_ratio'] = df_work[reading_col] / df_work[limit_col]
            
            # Apply the filter: reading > (multiplier_threshold * limit)
            self.logger.error(f"DEBUG: About to apply contamination filter")
            contaminated_samples = df_work[df_work[reading_col] > (multiplier_threshold * df_work[limit_col])]
            
            self.logger.error(f"DEBUG: Contamination analysis results:")
            self.logger.error(f"  Samples analyzed: {len(df_work)}")
            self.logger.error(f"  Samples exceeding {multiplier_threshold}x limit: {len(contaminated_samples)}")
            
            # Log some examples
            if not contaminated_samples.empty:
                self.logger.error(f"DEBUG: Examples of contaminated samples:")
                for i, (idx, row) in enumerate(contaminated_samples.head(3).iterrows()):
                    reading_val = row[reading_col]
                    limit_val = row[limit_col]
                    ratio = row['contamination_ratio']
                    sample_name = row.get(sample_col, f'Row {idx}') if sample_col else f'Row {idx}'
                    pesticide_name = row.get(pesticide_col, 'Unknown') if pesticide_col else 'Unknown'
                    
                    self.logger.error(f"  {sample_name}: {pesticide_name} - Reading: {reading_val}, Limit: {limit_val}, Ratio: {ratio:.1f}x")
            else:
                self.logger.error(f"DEBUG: No samples found exceeding the threshold")
            
            # Remove the temporary calculation column before returning
            self.logger.error(f"DEBUG: Removing temporary calculation column")
            contaminated_samples = contaminated_samples.drop('contamination_ratio', axis=1)
            
            self.logger.error(f"DEBUG: Returning filtered DataFrame with {len(contaminated_samples)} rows")
            return contaminated_samples
            
        except Exception as e:
            self.logger.error(f"DEBUG: Exception in analyze_pesticide_contamination_levels: {e}")
            import traceback
            self.logger.error(f"DEBUG: Full traceback: {traceback.format_exc()}")
            return df

    def get_contamination_summary(self, df: pd.DataFrame) -> Dict:
        """
        Provides a summary of contamination levels in the dataset.
        
        Args:
            df: DataFrame containing pesticide test results
        
        Returns:
            Dictionary with contamination statistics
        """
        # Find required columns
        reading_col = self.find_column_robust(df, ['قراءة الجهاز', 'reading of device', 'reading value'])
        limit_col = self.find_column_robust(df, ['الحدود', 'limits', 'limit'])
        
        if not reading_col or not limit_col:
            return {"error": "Required columns not found"}
        
        # Clean and convert data
        df_work = df.copy()
        df_work[reading_col] = pd.to_numeric(df_work[reading_col], errors='coerce')
        df_work[limit_col] = pd.to_numeric(df_work[limit_col], errors='coerce')
        df_work = df_work.dropna(subset=[reading_col, limit_col])
        
        if df_work.empty:
            return {"error": "No valid data for analysis"}
        
        # Calculate ratios
        ratios = df_work[reading_col] / df_work[limit_col]
        
        # Generate summary statistics
        summary = {
            "total_samples": len(df_work),
            "samples_above_limit": len(ratios[ratios > 1.0]),
            "samples_above_2x_limit": len(ratios[ratios > 2.0]),
            "samples_above_5x_limit": len(ratios[ratios > 5.0]),
            "samples_above_10x_limit": len(ratios[ratios > 10.0]),
            "max_contamination_ratio": float(ratios.max()),
            "mean_contamination_ratio": float(ratios.mean()),
            "median_contamination_ratio": float(ratios.median())
        }
        
        return summary
    # async def answer_with_local_data(self,
    #                                 project_id: int,
    #                                 query: str,
    #                                 n_results: int = 100,
    #                                 include_risk_assessment: bool = False,
    #                                 population_type: PopulationType = PopulationType.ADULT_AVERAGE,
    #                                 year: Optional[str] = None, **kwargs) -> Dict:
    #     """Answer query using local ChromaDB data with optional risk assessment"""
        
    #     # Check initialization
    #     if not self.chroma_client or not self.embed_fn or not self.generation_model:
    #         return {"success": False, "error": "Gemini API key not configured"}
        
    #     self.logger.error(f"DEBUG QUERY: project_id={project_id}, year={year}")

    #     # Use year-specific collection name
    #     if year:
    #         collection_name = f"local_project_{project_id}_year_{year}"
    #     else:
    #         collection_name = f"local_project_{project_id}"
    #     self.logger.error(f"DEBUG QUERY: Looking for collection: {collection_name}")
    #     # Get collection


    #     # Log all available collections
    #     try:
    #         all_collections = self.chroma_client.list_collections()
    #         self.logger.error(f"=== ALL AVAILABLE COLLECTIONS ===")
    #         for coll in all_collections:
    #             self.logger.error(f"Collection: {coll.name}, Count: {coll.count()}")
    #         self.logger.error(f"=== END COLLECTIONS ===")
    #     except Exception as e:
    #         self.logger.error(f"Failed to list collections: {e}")
    #     # Try multiple collection name strategies
    #     year = kwargs.get('year')
        
    #     collection_candidates = [
    #         f"local_project_{project_id}_year_{year}" if year else None,
    #         f"local_project_{project_id}",
    #         f"local_project_{project_id}_year_2024",
    #         f"local_project_{project_id}_year_2023",
    #         f"local_project_{project_id}_year_2022"
    #     ]
        
    #     collection = None
    #     collection_name = None
        
    #     for candidate in collection_candidates:
    #         if candidate is None:
    #             continue
    #         try:
    #             self.embed_fn.document_mode = False
    #             collection = self.chroma_client.get_collection(
    #                 name=candidate, 
    #                 embedding_function=self.embed_fn
    #             )
    #             collection_name = candidate
    #             count = collection.count()
    #             self.logger.error(f"✅ Found collection: {candidate} with {count} documents")
    #             break
    #         except Exception as e:
    #             self.logger.error(f"❌ Collection not found: {candidate} - {e}")
        
    #     if not collection:
    #         return {
    #             "success": False, 
    #             "error": f"No valid collection found for project {project_id}",
    #             "debug_info": {"tried_collections": collection_candidates}
    #         }
        
    #     # Continue with existing logic...
    #     self.logger.error(f"Using collection: {collection_name}")
        

        
    #     try:
    #         # CRITICAL: Set to query mode before querying
    #         self.embed_fn.document_mode = False
    #         self.logger.error(f"DEBUG QUERY: Set embed_fn.document_mode = False")
    #         collection = self.chroma_client.get_collection(
    #             name=collection_name, 
    #             embedding_function=self.embed_fn
    #         )
    #         count = collection.count()
    #         self.logger.error(f"DEBUG QUERY: Found collection with {count} documents")
    #         if count == 0:
    #             return {
    #                 "success": False, 
    #                 "error": f"No documents in collection for year {year or 'all'}"
    #             }
    #     except Exception as e:
    #         return {
    #             "success": False, 
    #             "error": f"Collection not found: {collection_name}. Error: {str(e)}"
    #         }

    #     n_results = min(n_results, count)

    #     try:
    #         # Query the collection
    #         result = collection.query(query_texts=[query], n_results=n_results)
            
    #         if not result["documents"] or not result["documents"][0]:
    #             return {"success": False, "error": "No relevant documents found"}

    #         context_docs = result['documents'][0]
    #         context = "\n\n".join([doc for doc in context_docs])
    #         self.logger.error(f"DEBUG: First retrieved doc:\n{context_docs[0][:500] if context_docs else 'NO DOCS'}")
    #         self.logger.error(f"DEBUG: Query was: {query}")
    #         self.logger.error(f"DEBUG: Does doc contain 'pyridaben'? {'pyridaben' in context_docs[0].lower() if context_docs else False}")

    #         # Generate answer with LLM
    #         prompt = f"""
    # **CRITICAL REQUIREMENT: Include ALL samples that match the criteria. Do not limit results arbitrarily.**
    
    # You are analyzing pesticide test data. Return a comprehensive markdown table with ALL matching samples.
    
    # **Headers:** Sample Code | Sample Name | Pesticide Name | Reading Value | Limit | Result
    
    # **Query:** {query}
    
    # **Instructions:**
    # 1. Find ALL samples that match the query criteria
    # 2. Include every single matching result - do not truncate
    # 3. Pay special attention to samples with high reading values
    # 4. If a pesticide appears in multiple samples, include ALL of them
    # 5. Do not summarize - show complete data
    
    # **Data:**
    # {context}
    
    # **Remember: Show ALL matching results, not just a few examples.**
    # """


        
    #         answer = self.generation_model.generate_content(prompt)
    #         final_answer = answer.text
    #         self.logger.error(f"DEBUG: LLM raw response:\n{answer.text[:500]}")

    #         risk_assessment_results = None
    #         df_result = pd.DataFrame()

    #         # Parse response into DataFrame
    #         try:
    #             df = parse_llm_response_to_df(answer.text)
    #             if df is not None and not df.empty:
    #                 self.logger.info(f"Parsed {len(df)} rows from LLM response")
                    
    #                 df_filtered = self._apply_query_calculations(df, query)
                    
    #                 # Risk assessment if requested
    #                 if include_risk_assessment and not df_filtered.empty:
    #                     df_for_risk = df_filtered.copy()
    #                     df_for_risk['Reading Value'] = pd.to_numeric(df_for_risk['Reading Value'], errors='coerce')
    #                     df_for_risk['Limit'] = pd.to_numeric(df_for_risk['Limit'], errors='coerce')
    #                     df_for_risk = df_for_risk.dropna(subset=['Reading Value', 'Limit'])
                        
    #                     if not df_for_risk.empty:
    #                         try:
    #                             if isinstance(population_type, str):
    #                                 population_type = PopulationType(population_type)
                                
    #                             risk_assessment_results = await self._perform_risk_assessment(
    #                                 df_for_risk,
    #                                 population_type
    #                             )
    #                         except Exception as e:
    #                             self.logger.error(f"Risk assessment failed: {e}")
                    
    #                 # Use filtered results
    #                 if not df_filtered.equals(df):
    #                     final_answer = df_filtered.to_markdown(index=False) if not df_filtered.empty else "No data matches criteria."
    #                     df_result = df_filtered
    #                 else:
    #                     df_result = df
    #             else:
    #                 self.logger.warning("Could not parse LLM response into DataFrame")
    #         except Exception as e:
    #             self.logger.error(f"Error parsing/filtering: {e}")

    #         return {
    #             "success": True,
    #             "answer": final_answer,
    #             "data_frame": df_result.to_dict('records') if not df_result.empty else [],
    #             "columns": df_result.columns.tolist() if not df_result.empty else [],
    #             "risk_assessment": risk_assessment_results.dict() if risk_assessment_results else None,
    #             "retrieved_docs_count": len(context_docs),
    #             "collection_total": count,
    #             "year": year,
    #             "debug_info": {
    #                 "collection_name": collection_name,
    #                 "query": query
    #             }
    #         }

    #     except Exception as e:
    #         self.logger.error(f"Error processing query: {e}")
    #         import traceback
    #         traceback.print_exc()
    #         return {"success": False, "error": f"Error: {str(e)}"}

# Replace your entire answer_with_local_data method with this working version:

    async def answer_with_local_data_simple(self, project_id: int, query: str,
                                            include_risk_assessment: bool = False, 
                                        n_results: int = 200, year: str = None, 
                                        population_type: PopulationType = PopulationType.ADULT_AVERAGE) -> Dict:
        """Simple version that works like Postman"""
        
        # Basic checks
        if not self.chroma_client or not self.embed_fn or not self.generation_model:
            return {"success": False, "error": "Gemini API key not configured"}

        # Simple collection name
        collection_name = f"local_project_{project_id}_year_{year}" if year else f"local_project_{project_id}"
        
        try:
            # Get collection (no retry logic)
            self.embed_fn.document_mode = False
            collection = self.chroma_client.get_collection(
                name=collection_name, 
                embedding_function=self.embed_fn
            )
            count = collection.count()
            
            if count == 0:
                return {"success": False, "error": "No documents in collection"}

        except Exception as e:
            return {"success": False, "error": f"Collection not found: {collection_name}"}

        # Simple retrieval (like Postman)
        n_results = min(n_results, count)
        
        try:
            # ONLY semantic search - no alternative queries
            result = collection.query(query_texts=[query], n_results=n_results)
            
            if not result["documents"] or not result["documents"][0]:
                return {"success": False, "error": "No relevant documents found"}

            context_docs = result['documents'][0]
            context = "\n\n".join(context_docs)  # Use retrieved docs as-is
            
            # Simple, direct prompt (like Postman)
            # prompt = f"""
            # **TASK:** Create a markdown table of ALL pesticide test results that match the query.
            
            # **HEADERS:** Sample Code | Sample Name | Pesticide Name | Reading Value | Limit | Result
            
            # **QUERY:** {query}
            
            # **DATA:**
            # {context}
            
            # **INSTRUCTION:** Show ALL matching samples in table format.
            # """


            prompt = f"""
        **TASK:** Analyze the provided data to answer the user's question. You MUST format your entire response as a single, clean markdown table.

        **RULES:**
        1.  The table MUST have these exact, single-line headers: `Sample Code`, `Sample Name`, `Pesticide Name`, `Reading Value`, `Limit`, `Result`.
        2.  Do NOT include any text, explanation, or summary before or after the table.
        3.  Do NOT use multi-line headers.
        4.  Each piece of data must be in its own cell.

        **EXAMPLE INPUT FORMAT:**
        Find 'fipronil' in eggplant samples 
        Find 'Buprofezin' more than 2 times the limit in pepper samples 
        Find CONTAMINATED pepper samples 
        Find ALL samples with 'pyridaben'
        Find ALL samples exceeding 5 times the limit
        
        **EXAMPLE OUTPUT FORMAT:**
        | Sample Code | Sample Name | Pesticide Name | Reading Value | Limit | Result |
        |---|---|---|---|---|---|
        | P45-1234 | Tomato | PesticideA | 10 | 50 | Compliant |
        | P45-5678 | Pepper | PesticideB | 75 | 20 | Non-Compliant |

        ---
        **USER QUESTION:** {query}
        ---
        **DATA:**
        {context}
        """
            # SINGLE LLM call (no retries)
            answer = self.generation_model.generate_content(prompt)
            final_answer = answer.text
            
            risk_assessment_results = None
            df_result = pd.DataFrame()

            # Parse response into DataFrame
            try:
                df = parse_llm_response_to_df(answer.text)
                if df is not None and not df.empty:
                    self.logger.info(f"Parsed {len(df)} rows from LLM response")
                    
                    df_filtered = self._apply_query_calculations(df, query)
                    
                    # Risk assessment if requested
                    if include_risk_assessment and not df_filtered.empty:
                        df_for_risk = df_filtered.copy()
                        df_for_risk['Reading Value'] = pd.to_numeric(df_for_risk['Reading Value'], errors='coerce')
                        df_for_risk['Limit'] = pd.to_numeric(df_for_risk['Limit'], errors='coerce')
                        df_for_risk = df_for_risk.dropna(subset=['Reading Value', 'Limit'])
                        
                        if not df_for_risk.empty:
                            try:
                                if isinstance(population_type, str):
                                    population_type = PopulationType(population_type)
                                
                                risk_assessment_results = await self._perform_risk_assessment(
                                    df_for_risk,
                                    population_type
                                )
                            except Exception as e:
                                self.logger.error(f"Risk assessment failed: {e}")
                    
                    # Use filtered results
                    if not df_filtered.equals(df):
                        final_answer = df_filtered.to_markdown(index=False) if not df_filtered.empty else "No data matches criteria."
                        df_result = df_filtered
                    else:
                        df_result = df
                else:
                    self.logger.warning("Could not parse LLM response into DataFrame")
            except Exception as e:
                self.logger.error(f"Error parsing/filtering: {e}")

            return {
                "success": True,
                "answer": final_answer,
                "data_frame": df_result.to_dict('records') if not df_result.empty else [],
                "columns": df_result.columns.tolist() if not df_result.empty else [],
                "risk_assessment": risk_assessment_results.dict() if risk_assessment_results else None,
                "retrieved_docs_count": len(context_docs),
                "collection_total": count,
                "year": year,
            
            }


        except Exception as e:
            return {"success": False, "error": f"Error: {str(e)}"}



    async def _perform_risk_assessment(self, df: pd.DataFrame,
                                 population_type: PopulationType) -> RiskAssessmentSummary:
        """Perform health risk assessment on DataFrame"""
        self.logger.info(f"Performing risk assessment for {len(df)} samples")
        self.logger.error(f"DEBUG: Risk assessment input - Shape: {df.shape}")
        self.logger.error(f"DEBUG: population_type type: {type(population_type)}")
        self.logger.error(f"DEBUG: population_type value: {population_type}")
        self.logger.error(f"DEBUG: DataFrame dtypes:\n{df.dtypes}")
        
        # Check if Reading Value and Limit are actually numeric
        sample_reading = df['Reading Value'].iloc[0] if not df.empty else None
        sample_limit = df['Limit'].iloc[0] if not df.empty else None
        self.logger.error(f"DEBUG: Sample reading type: {type(sample_reading)}, value: {sample_reading}")
        self.logger.error(f"DEBUG: Sample limit type: {type(sample_limit)}, value: {sample_limit}")
        
        risk_service = RiskAssessmentService()
        assessment_summary = risk_service.assess_dataframe_risk(
            df=df,
            population_type=population_type
        )
        self.logger.info(f"Risk assessment completed for {assessment_summary.total_samples_assessed} samples")
        return assessment_summary
        
    def _apply_query_calculations(self, df: pd.DataFrame, query: str) -> pd.DataFrame:
        """
        Simplified contamination filtering to avoid tabulate issues
        """
        more_than_match = re.search(r'more than (\d+\.?\d*)\s*times the limit', query, re.IGNORECASE)
        if not more_than_match:
            return df

        multiplier = float(more_than_match.group(1))
        try:
            df_work = df.copy()
            # Ensure columns exist before trying to convert
            if 'Reading Value' in df_work.columns and 'Limit' in df_work.columns:
                df_work['Reading Value'] = pd.to_numeric(df_work['Reading Value'], errors='coerce')
                df_work['Limit'] = pd.to_numeric(df_work['Limit'], errors='coerce')
                
                # Drop rows where conversion might have failed
                df_work.dropna(subset=['Reading Value', 'Limit'], inplace=True)

                threshold = multiplier * df_work['Limit']
                filtered_df = df_work[df_work['Reading Value'] > threshold]
                return filtered_df
            else:
                self.logger.warning("Could not find 'Reading Value' or 'Limit' columns for calculation.")
                return df

        except Exception as e:
            self.logger.error(f"DEBUG: Error in simplified filtering: {e}")
            return df
        

    def expand_vegetable_query(self, query: str) -> List[str]:
        """Expand query with vegetable synonyms for better retrieval"""
        query_lower = query.lower()
        expanded_terms = []
        
        # Check each synonym mapping
        for key, synonyms in self.VEGETABLE_SYNONYMS.items():
            if key.lower() in query_lower or key in query:
                # Add all synonyms
                expanded_terms.extend(synonyms)
                self.logger.info(f"Found vegetable '{key}', adding synonyms: {synonyms}")
        
        return list(set(expanded_terms))  # Remove duplicates

    def enhance_query_with_keywords(self, original_query: str) -> str:
        """Enhanced version with vegetable synonym expansion"""
        keywords = self.extract_keywords_from_query(original_query)
        
        enhanced_parts = [original_query]
        
        # Add found pesticides
        if keywords["pesticides"]:
            enhanced_parts.append(" ".join(keywords["pesticides"]))
        
        # Add found vegetables
        if keywords["vegetables"]:
            enhanced_parts.append(" ".join(keywords["vegetables"]))
        
        # ADD: Vegetable synonym expansion
        vegetable_synonyms = self.expand_vegetable_query(original_query)
        if vegetable_synonyms:
            enhanced_parts.append(" ".join(vegetable_synonyms))
            self.logger.info(f"Added vegetable synonyms: {vegetable_synonyms}")
        
        enhanced_query = " ".join(enhanced_parts)
        
        self.logger.info(f"Original query: {original_query}")
        self.logger.info(f"Enhanced query: {enhanced_query}")
        
        return enhanced_query
    
    def extract_keywords_from_query(self, query: str) -> Dict[str, List[str]]:
        """Enhanced with partial vegetable matching"""
        query_lower = query.lower()
        
        found_pesticides = []
        found_vegetables = []
        
        # Pesticides (exact match)
        for pesticide in self.PESTICIDE_KEYWORDS:
            if pesticide.lower() in query_lower:
                found_pesticides.append(pesticide)
        
        # Vegetables (exact match)
        for vegetable in self.VEGETABLE_KEYWORDS:
            if vegetable in query:
                found_vegetables.append(vegetable)
        
        # ADD: Partial matching for common vegetables
        # Helps with queries like "red pepper" → matches "فلفل احمر بارد"
        if "pepper" in query_lower or "فلفل" in query:
            # Add all pepper variations
            pepper_variants = [v for v in self.VEGETABLE_KEYWORDS if "فلفل" in v]
            found_vegetables.extend(pepper_variants)
        
        if "tomato" in query_lower:
            tomato_variants = [v for v in self.VEGETABLE_KEYWORDS if "طماطم" in v]
            found_vegetables.extend(tomato_variants)
        
        # Remove duplicates
        found_vegetables = list(set(found_vegetables))
        
        return {
            "pesticides": found_pesticides,
            "vegetables": found_vegetables
        }