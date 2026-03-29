# routes/nlp.py - FIXED VERSION

from fastapi import FastAPI, APIRouter, status, Request, Depends, Query
from fastapi.responses import JSONResponse
from routes.schemes.nlp import PushRequest, SearchRequest
from models.ProjectModel import ProjectModel
from models.ChunkModel import ChunkModel
from controllers import NLPController, EnhancedNLPController
from models import ResponseSignal
from tqdm.auto import tqdm
from controllers.ProjectControllers import ProjectControllers
from controllers.ProcessControllers import DirectPesticideController
from pydantic import BaseModel
from typing import Optional, List
import os
from fastapi.responses import StreamingResponse
from routes.schemes.nlp import PostLocalQuery, PostLocalIndex, PostDocQuery, PostDocIndex
from models.risk_assessment_models import LocalAnswerRequest
from pydantic import Field
from models.risk_assessment_models import RiskAssessmentSummary, PopulationType
from datetime import datetime
import re
import logging
import traceback

# FIXED IMPORT - No Streamlit dependencies
from utils.request_logger import RequestResponseLogger, extract_year_from_text

logger = logging.getLogger('uvicorn.error')

nlp_router = APIRouter(
    prefix="/api/v1/nlp",
    tags=["api_v1", "nlp"],
)

class LocalIndexRequest(BaseModel):
    data_folder_path: str
    months: Optional[List[str]] = None
    do_reset: Optional[bool] = False
    year: str

class LocalAnswerRequest(BaseModel):
    query: str
    n_results: Optional[int] = 200
    llm_provider: str = Field(default="openai")
    prompt_template: Optional[str] = Field(default="en")
    include_risk_assessment: Optional[bool] = Field(default=False, description="Flag to run health risk assessment on the results")
    population_type: Optional[PopulationType] = Field(default=PopulationType.ADULT_AVERAGE, description="Target population for risk assessment")



@nlp_router.post("/index/push/{project_id}")
async def index_project(request: Request, project_id: int, push_request: PushRequest):

    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    chunk_model = await ChunkModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_project_or_create_one(
        project_id=project_id
    )

    if not project:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": ResponseSignal.PROJECT_NOT_FOUND_ERROR.value
            }
        )
    
    nlp_controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser=request.app.template_parser,
    )

    has_records = True
    page_no = 1
    inserted_items_count = 0
    idx = 0

     # create collection if not exists
    collection_name = nlp_controller.create_collection_name(project_id=project.project_id)

    _ = await request.app.vectordb_client.create_collection(
        collection_name=collection_name,
        embedding_size=request.app.embedding_client.embedding_size,
        do_reset=push_request.do_reset,
    )

    # setup batching
    total_chunks_count = await chunk_model.get_total_chunks_count(project_id=project.project_id)
    pbar = tqdm(total=total_chunks_count, desc="Vector Indexing", position=0)
    # Add this debugging line right after
    print(f"DEBUG: Found {(total_chunks_count)} chunks in the database for project {project_id}.")


    while has_records:
        page_chunks = await chunk_model.get_poject_chunks(project_id=project.project_id, page_no=page_no)
        if len(page_chunks):
            page_no += 1
        
        if not page_chunks or len(page_chunks) == 0:
            has_records = False
            break 

        chunks_ids = [c.chunk_id for c in page_chunks]
        idx += len(page_chunks)
        
        is_inserted = await nlp_controller.index_into_vector_db(
            project=project,
            chunks=page_chunks,
             chunks_ids=chunks_ids
        )

        if not is_inserted:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "signal": ResponseSignal.INSERT_INTO_VECTORDB_ERROR.value
                }
            )

        pbar.update(len(page_chunks))
        inserted_items_count += len(page_chunks)
        
    return JSONResponse(
        content={
            "signal": ResponseSignal.INSERT_INTO_VECTORDB_SUCCESS.value,
            "inserted_items_count": inserted_items_count
        }
    )
@nlp_router.get("/index/info/{project_id}")
async def get_project_index_info(request: Request, project_id: str):
    
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_project_or_create_one(
        project_id=project_id
    )

    nlp_controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser=request.app.template_parser, 
    )

    collection_info = await nlp_controller.get_vector_db_collection_info(project=project)

    return JSONResponse(
        content={
            "signal": ResponseSignal.VECTORDB_COLLECTION_RETRIEVED.value,
            "collection_info": collection_info
        }
    )
    

@nlp_router.post("/index/search/{project_id}")
async def search_index(request: Request, project_id: int, search_request: SearchRequest):
    
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_project_or_create_one(
        project_id=project_id
    )

    nlp_controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser=request.app.template_parser,
    )
    

    results = await nlp_controller.search_vector_db_collection(
        project=project, text=search_request.text, limit=search_request.limit
    )

    if not results:
        return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "signal": ResponseSignal.VECTORDB_SEARCH_ERROR.value
                }
            )
    
    return JSONResponse(
        content={
            "signal": ResponseSignal.VECTORDB_SEARCH_SUCCESS.value,
            "results": [ result.dict()  for result in results ]
        }
    )

@nlp_router.post("/index/answer/{project_id}")
async def answer_rag(request: Request, project_id: int, search_request: SearchRequest):
    
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )

    project = await project_model.get_project_or_create_one(
        project_id=project_id
    )

    nlp_controller = NLPController(
        vectordb_client=request.app.vectordb_client,
        generation_client=request.app.generation_client,
        embedding_client=request.app.embedding_client,
        template_parser=request.app.template_parser,
    )

    answer, full_prompt, chat_history = await nlp_controller.answer_rag_question(
        project=project,
        query=search_request.text,
        limit=search_request.limit,
    )

    if not answer:
        return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "signal": ResponseSignal.RAG_ANSWER_ERROR.value
                }
        )
    
    return JSONResponse(
        content={
            "signal": ResponseSignal.RAG_ANSWER_SUCCESS.value,
            "answer": answer,
            "full_prompt": full_prompt,
            "chat_history": chat_history
        }
    )

    

# 4. Add this simple endpoint
@nlp_router.post("/simple/answer/{project_id}")
async def simple_answer(request: Request, project_id: int, search_request: SearchRequest):
    """
    Enhanced simple endpoint with better formatting
    """
    try:
        project_model = await ProjectModel.create_instance(db_client=request.app.db_client)
        project = await project_model.get_project_or_create_one(project_id=project_id)
        project_path = ProjectControllers().get_project_path(project_id=str(project_id))
        
        # Use enhanced direct approach
        direct_controller = DirectPesticideController(project_path)
        answer = direct_controller.answer_query(
            query=search_request.text,
            generation_client=request.app.generation_client
        )
        
        return JSONResponse(content={
            "signal": "success",
            "answer": answer,
            "approach": "enhanced_direct_processing",
            "query": search_request.text
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"signal": "error", "message": str(e)}
        )

# 4. Quick Data Validation Helper
def validate_and_clean_pesticide_data(raw_data: str) -> str:
    """
    Quick validation and cleaning of pesticide data output
    """
    lines = raw_data.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines and separators
        if not line or line.startswith('---') or line.startswith('==='):
            continue
        
        # Clean up table formatting
        if '|' in line:
            # Ensure proper table formatting
            parts = [part.strip() for part in line.split('|')]
            if len(parts) > 2:  # Valid table row
                cleaned_line = '| ' + ' | '.join(parts[1:-1]) + ' |'
                cleaned_lines.append(cleaned_line)
        else:
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

@nlp_router.post("/local/index/{project_id}")
async def index_local_data_simple(request: Request, project_id: int, 
                                 index_request: LocalIndexRequest):
    """Simple indexing that works"""
    try:
        # Basic validation
        if index_request.year not in ["2022", "2023", "2024", "2025"]:
            return JSONResponse(status_code=400, content={
                "signal": "INVALID_YEAR",
                "message": f"Invalid year: {index_request.year}"
            })
        
        # Basic controller
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        enhanced_controller = EnhancedNLPController(gemini_api_key=gemini_api_key)
        
        # Simple path construction
        year_folder_path = f"{index_request.data_folder_path}/{index_request.year}"
        
        # Process files
        documents, metadata = enhanced_controller.process_local_excel_files(
            data_folder_path=year_folder_path,
            months=index_request.months
        )
        
        if not documents:
            return JSONResponse(status_code=400, content={
                "signal": "NO_LOCAL_DATA_FOUND",
                "message": f"No Excel files found in {year_folder_path}"
            })
        
        # Create collection
        collection = enhanced_controller.create_local_collection(
            project_id=project_id,
            documents=documents,
            metadata_list=metadata,
            do_reset=index_request.do_reset,
            year=index_request.year
        )
        
        return JSONResponse(content={
            "signal": "LOCAL_INDEX_SUCCESS",
            "indexed_documents": len(documents),
            "project_id": project_id,
            "year": index_request.year,
            "collection_name": f"local_project_{project_id}_year_{index_request.year}"
        })
            
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "signal": "LOCAL_INDEX_ERROR",
            "error": str(e)
        })

# @nlp_router.post("/local/answer/{project_id}")
# async def local_answer_endpoint(request: Request, project_id: int,
#                                answer_request: LocalAnswerRequest,
#                                year: Optional[str] = Query(default=None)):
#     """Enhanced version with keyword and synonym expansion"""
    
#     try:
#         target_year = year or "2022"
        
#         gemini_api_key = os.getenv("GEMINI_API_KEY")
#         if not gemini_api_key:
#             return JSONResponse(status_code=400, content={
#                 "signal": "GEMINI_API_KEY_MISSING",
#                 "message": "Please set GEMINI_API_KEY environment variable"
#             })

#         # Initialize controller
#         enhanced_controller = EnhancedNLPController(gemini_api_key=gemini_api_key)
        
#         # ENHANCE QUERY with keywords and synonyms
#         enhanced_query = enhanced_controller.enhance_query_with_keywords(
#             answer_request.query
#         )
        
#         # Use the answer_with_local_data_simple method
#         response = await enhanced_controller.answer_with_local_data_simple(
#             project_id=project_id,
#             query=enhanced_query,  # Use enhanced query
#             n_results=answer_request.n_results,
#             year=target_year
#         )
        
#         if not response.get("success"):
#             return JSONResponse(status_code=400, content={
#                 "signal": "QUERY_FAILED",
#                 "error": response.get("error")
#             })

#         return JSONResponse(content={
#             "signal": "LOCAL_ANSWER_SUCCESS",
#             **response  # Include all response data
#         })

#     except Exception as e:
#         import traceback
#         error_details = traceback.format_exc()
#         print(f"ERROR: {error_details}")
        
#         return JSONResponse(status_code=500, content={
#             "signal": "LOCAL_ANSWER_ERROR",
#             "error": str(e),
#             "details": error_details
#         })


@nlp_router.post("/local/answer/{project_id}")
async def local_answer_endpoint(request: Request, project_id: int,
                               answer_request: LocalAnswerRequest,
                               year: Optional[str] = Query(default=None)):
    """Answer queries using locally indexed data with optional health risk assessment"""
    try:
        target_year = year or "2022"
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        
        if not gemini_api_key:
            return JSONResponse(status_code=400, content={
                "signal": "GEMINI_API_KEY_MISSING",
                "message": "Please set GEMINI_API_KEY environment variable"
            })

        # Initialize controller
        enhanced_controller = EnhancedNLPController(gemini_api_key=gemini_api_key)
        
        # Get answer from local data (NO query enhancement)
        result = await enhanced_controller.answer_with_local_data_simple(
            project_id=project_id,
            query=answer_request.query,  # Use original query
            n_results=answer_request.n_results,
            year=target_year,
            include_risk_assessment=answer_request.include_risk_assessment,
            population_type=answer_request.population_type  # Pass enum directly
        )

        if not result.get("success", False):
            return JSONResponse(status_code=400, content={
                "signal": "LOCAL_ANSWER_ERROR",
                "error": result.get("error", "Unknown error")
            })

        # Return response matching Postman structure
        return JSONResponse(content={
            "signal": "LOCAL_ANSWER_SUCCESS",
            "answer": result.get("answer", ""),
            "data_frame": result.get("data_frame", []),  # ADD THIS
            "columns": result.get("columns", []),        # ADD THIS
            "full_prompt": "",
            "retrieved_docs_count": result.get("retrieved_docs_count", 0),
            "collection_total": result.get("collection_total", 0),
            "project_id": project_id,
            "debug_info": {},
            "risk_assessment": result.get("risk_assessment")
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={
            "signal": "LOCAL_ANSWER_ERROR",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
# Also add a simple test endpoint to check raw ChromaDB data
@nlp_router.get("/local/raw-data/{project_id}")
async def get_raw_data_sample(request: Request, project_id: int):
    """Get raw sample data from ChromaDB to see actual content"""
    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        enhanced_controller = EnhancedNLPController(gemini_api_key=gemini_api_key)
        collection_name = f"local_project_{project_id}"
        
        collection = enhanced_controller.chroma_client.get_collection(
            name=collection_name,
            embedding_function=enhanced_controller.embed_fn
        )
        
        # Get first few documents without querying
        raw_data = collection.get(limit=5)
        
        sample_data = {
            "collection_count": collection.count(),
            "sample_documents": []
        }
        
        for i, (doc, metadata) in enumerate(zip(
            raw_data.get("documents", []),
            raw_data.get("metadatas", [])
        )):
            sample_data["sample_documents"].append({
                "index": i,
                "metadata": metadata,
                "content_length": len(doc),
                "content_preview": doc[:1000],  # First 1000 chars
                "contains_key_terms": {
                    "pepper": "pepper" in doc.lower() or "فلفل" in doc,
                    "pesticide": "pesticide" in doc.lower() or "مبيد" in doc,
                    "result": "result" in doc.lower() or "نتيجة" in doc
                }
            })
        
        return JSONResponse(content=sample_data)
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    

@nlp_router.post(
    "/local/query/export/{project_id}",
    summary="Query local data and get the result as an Excel file",
    tags=["Local Data Processing"],
    response_description="An Excel file containing the query results.",
)
async def query_local_data_export(project_id: int, data: PostLocalQuery):
    """
    Sends a query to the local data collection and returns a structured Excel file.
    """
    try:
        # --- THIS IS THE FIX ---
        # 1. Get the Gemini API Key, which is required by the controller.
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            return JSONResponse(
                status_code=500,
                content={"detail": "GEMINI_API_KEY is not configured on the server."}
            )
            
        # 2. Create an instance of the CORRECT controller for local data.
        enhanced_controller = EnhancedNLPController(gemini_api_key=gemini_api_key)
        
        # 3. Call the method on the created instance.
        excel_buffer = await enhanced_controller.answer_and_export_local_data(
            project_id=project_id,
            query=data.query,
            n_results=data.n_results
        )
        
        if excel_buffer is None:
            return JSONResponse(
                status_code=400, 
                content={"detail": "Could not generate Excel file. The model's response may not have been in a parsable table format."}
            )
        
        headers = {
            'Content-Disposition': 'attachment; filename="query_results.xlsx"'
        }
        
        return StreamingResponse(
            excel_buffer, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )
    except Exception as e:
        logger.error(f"Error during Excel export: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": f"An internal error occurred: {str(e)}"})



@nlp_router.get("/local/debug-path/{year}")
async def debug_data_path(year: str):
    """Debug endpoint to check folder structure"""
    import os
    from pathlib import Path
    
    base_path = f"/app/data/{year}"
    
    debug_info = {
        "year": year,
        "base_path": base_path,
        "exists": os.path.exists(base_path),
        "is_dir": os.path.isdir(base_path) if os.path.exists(base_path) else False,
        "contents": []
    }
    
    if os.path.exists(base_path):
        try:
            # List all items in the directory
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                item_info = {
                    "name": item,
                    "is_dir": os.path.isdir(item_path),
                    "is_file": os.path.isfile(item_path),
                }
                
                if os.path.isdir(item_path):
                    # If it's a directory, list its contents
                    try:
                        subcontents = os.listdir(item_path)
                        item_info["files_count"] = len([f for f in subcontents if f.endswith('.xlsx')])
                        item_info["sample_files"] = [f for f in subcontents if f.endswith('.xlsx')][:3]
                    except Exception as e:
                        item_info["error"] = str(e)
                
                debug_info["contents"].append(item_info)
        except Exception as e:
            debug_info["error"] = str(e)
    
    return JSONResponse(content=debug_info)




# @nlp_router.post("/local/index/{project_id}")
# async def index_local_data(request: Request, project_id: int, index_request: LocalIndexRequest):
#     """Index local Excel files for a project"""
#     try:
#         # Check if GEMINI_API_KEY exists
#         gemini_api_key = os.getenv("GEMINI_API_KEY")
#         if not gemini_api_key:
#             return JSONResponse(
#                 status_code=400,
#                 content={
#                     "signal": "GEMINI_API_KEY_MISSING",
#                     "message": "Please set GEMINI_API_KEY environment variable"
#                 }
#             )
        
#         # Initialize enhanced controller
#         enhanced_controller = EnhancedNLPController(
#             vectordb_client=request.app.vectordb_client,
#             generation_client=request.app.generation_client,
#             embedding_client=request.app.embedding_client,
#             template_parser=request.app.template_parser,
#             gemini_api_key=gemini_api_key
#         )
        
#         # Process local Excel files
#         documents, metadata = enhanced_controller.process_local_excel_files(
#             data_folder_path=index_request.data_folder_path,
#             months=index_request.months
#         )
        
#         if not documents:
#             return JSONResponse(
#                 status_code=400,
#                 content={
#                     "signal": "NO_LOCAL_DATA_FOUND",
#                     "message": f"No Excel files found in {index_request.data_folder_path}",
#                     "searched_months": index_request.months or "all default months"
#                 }
#             )
#         # --- ADD YOUR DEBUG CODE HERE ---
#         # This is the perfect place to inspect the documents
#         print(f"--- DEBUG: Inspecting Documents ---")
#         print(f"Found {len(documents)} documents to index.")
#         if documents:
#             print("Sample of the first document:")
#             print(f"Content: {documents[0][:500]}...") # Print the first 500 characters
#             print(f"Metadata: {metadata[0]}")
#         print(f"--- END DEBUG ---")

#         # Create ChromaDB collection
#         collection = enhanced_controller.create_local_collection(
#             project_id=project_id,
#             documents=documents,
#             metadata_list=metadata,
#             do_reset=index_request.do_reset
#         )
        
#         return JSONResponse(
#             content={
#                 "signal": "LOCAL_INDEX_SUCCESS",
#                 "indexed_documents": len(documents),
#                 "project_id": project_id,
#                 "collection_name": f"local_project_{project_id}",
#                 "data_folder": index_request.data_folder_path
#             }
#         )
            
#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return JSONResponse(
#             status_code=500,
#             content={
#                 "signal": "LOCAL_INDEX_ERROR",
#                 "error": str(e)
#             }
#         )


# @nlp_router.post("/local/answer/{project_id}")
# async def local_answer_endpoint(request: Request, project_id: int, answer_request: LocalAnswerRequest):
#     """Answer queries using locally indexed data - Enhanced with debugging"""
#     try:
#         gemini_api_key = os.getenv("GEMINI_API_KEY")
#         if not gemini_api_key:
#             return JSONResponse(
#                 status_code=400,
#                 content={
#                     "signal": "GEMINI_API_KEY_MISSING",
#                     "message": "Please set GEMINI_API_KEY environment variable"
#                 }
#             )
        
#         # Log the incoming request
#         print(f"=== LOCAL ANSWER REQUEST ===")
#         print(f"Project ID: {project_id}")
#         print(f"Query: {answer_request.query}")
#         print(f"N Results: {answer_request.n_results}")
#         print("=" * 30)
        
#         # Initialize enhanced controller
#         enhanced_controller = EnhancedNLPController(
#             vectordb_client=request.app.vectordb_client,
#             generation_client=request.app.generation_client,
#             embedding_client=request.app.embedding_client,
#             template_parser=request.app.template_parser,
#             gemini_api_key=gemini_api_key
#         )
        
#         # Get answer from local data
#         result = await enhanced_controller.answer_with_local_data(
#             project_id=project_id,
#             query=answer_request.query,
#             n_results=answer_request.n_results
#         )
        
#         # Log the result
#         print(f"=== LOCAL ANSWER RESULT ===")
#         print(f"Success: {result.get('success', False)}")
#         if result.get('success'):
#             print(f"Answer length: {len(result.get('answer', ''))}")
#             print(f"Retrieved docs: {result.get('retrieved_docs_count', 0)}")
#             print(f"Debug info: {result.get('debug_info', {})}")
#         else:
#             print(f"Error: {result.get('error', 'Unknown error')}")
#         print("=" * 30)
        
#         if not result.get("success", False):
#             return JSONResponse(
#                 status_code=400,
#                 content={
#                     "signal": "LOCAL_ANSWER_ERROR",
#                     "error": result.get("error", "Unknown error occurred"),
#                     "debug_info": result.get("debug_info", {})
#                 }
#             )
        
#         return JSONResponse(
#             content={
#                 "signal": "LOCAL_ANSWER_SUCCESS",
#                 "answer": result["answer"],
#                 "full_prompt": result.get("full_prompt", ""),
#                 "retrieved_docs_count": result.get("retrieved_docs_count", 0),
#                 "collection_total": result.get("collection_total", 0),
#                 "project_id": project_id,
#                 "debug_info": result.get("debug_info", {})
#             }
#         )
        
#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return JSONResponse(
#             status_code=500,
#             content={
#                 "signal": "LOCAL_ANSWER_ERROR",
#                 "error": str(e),
#                 "traceback": traceback.format_exc()
#             }
#         )



# 4. TEST IMMEDIATELY: Add this debug endpoint

@nlp_router.get("/debug/search-coverage/{project_id}")
async def debug_search_coverage(
    request: Request, 
    project_id: int, 
    year: str = Query(default="2022")
):
    """Quick test to see what's actually in the collection"""
    
    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        enhanced_controller = EnhancedNLPController(gemini_api_key=gemini_api_key)
        
        collection_name = f"local_project_{project_id}_year_{year}"
        enhanced_controller.embed_fn.document_mode = False
        collection = enhanced_controller.chroma_client.get_collection(
            name=collection_name, 
            embedding_function=enhanced_controller.embed_fn
        )
        
        # Get all documents and analyze
        all_docs = collection.get()
        
        # Count specific terms
        buprofezin_docs = [doc for doc in all_docs["documents"] if "buprofezin" in doc.lower()]
        high_reading_docs = [doc for doc in all_docs["documents"] if any(str(num) in doc for num in [568, 423, 409, 179, 186, 172, 125, 113])]
        
        return {
            "total_documents": len(all_docs["documents"]),
            "buprofezin_documents": len(buprofezin_docs),
            "high_reading_documents": len(high_reading_docs),
            "sample_buprofezin_docs": buprofezin_docs[:3],
            "sample_high_reading_docs": high_reading_docs[:3],
            "excel_values_found": {
                "568": any("568" in doc for doc in all_docs["documents"]),
                "423": any("423" in doc for doc in all_docs["documents"]),
                "409": any("409" in doc for doc in all_docs["documents"]),
                "179": any("179" in doc for doc in all_docs["documents"])
            }
        }
        
    except Exception as e:
        return {"error": str(e)}

# 5. VERIFY DATA INDEXING: Check if your Excel data was properly indexed

@nlp_router.get("/debug/verify-indexing/{project_id}")
async def verify_indexing_quality(
    request: Request, 
    project_id: int,
    year: str = Query(default="2024")  # Check 2024 since that's what your Excel shows
):
    """Verify if Excel data was properly indexed"""
    
    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        enhanced_controller = EnhancedNLPController(gemini_api_key=gemini_api_key)
        
        collection_name = f"local_project_{project_id}_year_{year}"
        
        try:
            enhanced_controller.embed_fn.document_mode = False
            collection = enhanced_controller.chroma_client.get_collection(
                name=collection_name, 
                embedding_function=enhanced_controller.embed_fn
            )
            
            # Search for specific values from your Excel
            excel_checks = {}
            excel_values = ["568", "423", "409", "179", "186", "172", "125", "113", "Buprofezin"]
            
            for value in excel_values:
                search_result = collection.query(query_texts=[value], n_results=10)
                excel_checks[value] = {
                    "found": len(search_result["documents"][0]) if search_result["documents"] else 0,
                    "sample_docs": search_result["documents"][0][:2] if search_result["documents"] else []
                }
            
            return {
                "collection_exists": True,
                "collection_count": collection.count(),
                "excel_value_checks": excel_checks,
                "recommendation": "If Excel values not found, re-index 2024 data"
            }
            
        except Exception as e:
            return {
                "collection_exists": False,
                "error": str(e),
                "recommendation": f"Index {year} data first - collection {collection_name} not found"
            }
        
    except Exception as e:
        return {"error": str(e)}
    

@nlp_router.get("/debug/test-pesticide-query/{project_id}")
async def test_pesticide_query(
    request: Request,
    project_id: int,
    pesticide: str = Query(default="Buprofezin"),
    year: str = Query(default="2022")
):
    """Test querying for specific pesticide to see retrieval quality"""
    
    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        enhanced_controller = EnhancedNLPController(gemini_api_key=gemini_api_key)
        
        collection_name = f"local_project_{project_id}_year_{year}"
        enhanced_controller.embed_fn.document_mode = False
        collection = enhanced_controller.chroma_client.get_collection(
            name=collection_name, 
            embedding_function=enhanced_controller.embed_fn
        )
        
        # Test different query strategies
        test_results = {}
        
        # 1. Direct pesticide name
        direct_results = collection.query(query_texts=[pesticide], n_results=20)
        test_results["direct_pesticide"] = {
            "query": pesticide,
            "found": len(direct_results["documents"][0]) if direct_results["documents"] else 0,
            "samples": direct_results["documents"][0][:3] if direct_results["documents"] else []
        }
        
        # 2. Pesticide with "contaminated"
        contam_query = f"{pesticide} contaminated"
        contam_results = collection.query(query_texts=[contam_query], n_results=20)
        test_results["contaminated_query"] = {
            "query": contam_query,
            "found": len(contam_results["documents"][0]) if contam_results["documents"] else 0,
            "samples": contam_results["documents"][0][:2] if contam_results["documents"] else []
        }
        
        # 3. Arabic non-compliant
        arabic_query = "غير مطابق"
        arabic_results = collection.query(query_texts=[arabic_query], n_results=20)
        test_results["arabic_noncompliant"] = {
            "query": arabic_query,
            "found": len(arabic_results["documents"][0]) if arabic_results["documents"] else 0,
            "samples": arabic_results["documents"][0][:2] if arabic_results["documents"] else []
        }
        
        # 4. High reading values
        high_reading_query = "reading 423"
        high_results = collection.query(query_texts=[high_reading_query], n_results=10)
        test_results["high_reading"] = {
            "query": high_reading_query,
            "found": len(high_results["documents"][0]) if high_results["documents"] else 0,
            "samples": high_results["documents"][0][:2] if high_results["documents"] else []
        }
        
        return {
            "pesticide_tested": pesticide,
            "year": year,
            "collection_total": collection.count(),
            "test_results": test_results,
            "recommendation": "Compare which query strategy retrieves the most relevant results"
        }
        
    except Exception as e:
        return {"error": str(e)}
    

@nlp_router.post("/local/comprehensive-answer/{project_id}")
async def comprehensive_answer(
    request: Request, 
    project_id: int,
    answer_request: LocalAnswerRequest,
    year: Optional[str] = Query(default=None)
):
    """Comprehensive search that finds ALL matching results"""
    
    try:
        target_year = year or "2022"
        
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        enhanced_controller = EnhancedNLPController(gemini_api_key=gemini_api_key)
        
        # Use MUCH higher retrieval and comprehensive strategies
        result = await enhanced_controller.answer_with_local_data(
            project_id=project_id,
            query=answer_request.query,
            n_results=2000,  # Much higher
            include_risk_assessment=answer_request.include_risk_assessment,
            population_type=answer_request.population_type,
            year=target_year
        )
        
        return JSONResponse(content={
            "signal": "COMPREHENSIVE_ANSWER_SUCCESS",
            "answer": result["answer"],
            "data_frame": result.get("data_frame", []),
            "retrieved_docs_count": result.get("retrieved_docs_count", 0),
            "collection_total": result.get("collection_total", 0),
            "search_strategy": "comprehensive_multi_query",
            "year_used": target_year
        })
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    

# Add this endpoint to your routes/nlp.py:

@nlp_router.get("/debug/health-check/{project_id}")
async def health_check_collection(
    request: Request,
    project_id: int,
    year: str = Query(default="2024")
):
    """Complete health check for debugging issues"""
    
    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            return {"error": "No Gemini API key", "status": "failed"}
        
        enhanced_controller = EnhancedNLPController(gemini_api_key=gemini_api_key)
        
        # Check 1: ChromaDB connection
        try:
            all_collections = enhanced_controller.chroma_client.list_collections()
            chroma_status = "connected"
        except Exception as e:
            return {"error": f"ChromaDB connection failed: {e}", "status": "failed"}
        
        # Check 2: Specific collection
        collection_name = f"local_project_{project_id}_year_{year}"
        try:
            enhanced_controller.embed_fn.document_mode = False
            collection = enhanced_controller.chroma_client.get_collection(
                name=collection_name,
                embedding_function=enhanced_controller.embed_fn
            )
            collection_count = collection.count()
            collection_status = "found"
        except Exception as e:
            return {
                "error": f"Collection '{collection_name}' not found: {e}",
                "available_collections": [c.name for c in all_collections],
                "status": "collection_missing"
            }
        
        # Check 3: Test searches for both pesticides
        test_results = {}
        test_queries = ["Buprofezin", "Bifenthrin", "buprofezin", "bifenthrin"]
        
        for test_query in test_queries:
            try:
                test_search = collection.query(query_texts=[test_query], n_results=10)
                found_count = len(test_search["documents"][0]) if test_search["documents"] else 0
                test_results[test_query] = {
                    "found": found_count,
                    "sample_docs": test_search["documents"][0][:2] if test_search["documents"] else []
                }
            except Exception as e:
                test_results[test_query] = {"error": str(e)}
        
        # Check 4: Verify data content
        sample_docs = collection.get(limit=10)
        bifenthrin_count = sum(1 for doc in sample_docs["documents"] if "bifenthrin" in doc.lower())
        buprofezin_count = sum(1 for doc in sample_docs["documents"] if "buprofezin" in doc.lower())
        
        return {
            "status": "healthy",
            "collection_name": collection_name,
            "collection_count": collection_count,
            "chroma_status": chroma_status,
            "total_collections": len(all_collections),
            "test_search_results": test_results,
            "content_analysis": {
                "bifenthrin_mentions": bifenthrin_count,
                "buprofezin_mentions": buprofezin_count,
                "sample_documents": sample_docs["documents"][:3]
            },
            "recommendations": {
                "bifenthrin_search": "Use 'Bifenthrin' (capital B) for better results",
                "data_persistence": "Collection appears healthy" if collection_count > 200 else "Low document count - may need re-indexing"
            }
        }
        
    except Exception as e:
        import traceback
        return {
            "status": "failed",
            "error": str(e),
            "traceback": traceback.format_exc()
        }
    
# Add this test endpoint to verify bifenthrin count:

@nlp_router.get("/debug/bifenthrin-count/{project_id}")
async def debug_bifenthrin_count(
    request: Request,
    project_id: int,
    year: str = Query(default="2024")
):
    """Count actual bifenthrin samples in collection"""
    
    try:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        enhanced_controller = EnhancedNLPController(gemini_api_key=gemini_api_key)
        
        collection_name = f"local_project_{project_id}_year_{year}"
        enhanced_controller.embed_fn.document_mode = False
        collection = enhanced_controller.chroma_client.get_collection(
            name=collection_name,
            embedding_function=enhanced_controller.embed_fn
        )
        
        # Get ALL documents and count bifenthrin mentions
        all_docs = collection.get()
        
        bifenthrin_docs = []
        for doc in all_docs["documents"]:
            if "bifenthrin" in doc.lower():
                bifenthrin_docs.append(doc)
        
        # Extract sample codes from bifenthrin docs
        import re
        sample_codes = []
        for doc in bifenthrin_docs:
            # Extract sample codes like P45-2520, P46-1336, etc.
            codes = re.findall(r"'([P]\d+-\d+)'", doc)
            sample_codes.extend(codes)
        
        unique_samples = list(set(sample_codes))
        
        return {
            "total_documents": len(all_docs["documents"]),
            "bifenthrin_documents": len(bifenthrin_docs),
            "unique_bifenthrin_samples": len(unique_samples),
            "sample_codes": unique_samples[:20],  # First 20 samples
            "bifenthrin_docs_sample": bifenthrin_docs[:5],  # First 5 docs
            "expected_vs_actual": {
                "you_expected": "48 results",
                "system_finds": f"{len(unique_samples)} unique samples",
                "documents_mentioning": f"{len(bifenthrin_docs)} total mentions"
            }
        }
        
    except Exception as e:
        return {"error": str(e)}