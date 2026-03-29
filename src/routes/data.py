from fastapi import FastAPI, APIRouter, Depends, UploadFile, File, status, Request
from fastapi.responses import JSONResponse
import os
from helper.config import get_settings, Settings
from controllers import DataControllers, ProjectControllers, ProcessControllers
import aiofiles
from models import ResponseSignal
import logging
from .schemes .data import ProcessRequest
from models.ProjectModel import ProjectModel
from models.db_schemes import DataChunk, Asset
from models.ChunkModel import ChunkModel
from models.AssetModel import AssetModel
from models.enums.AssetTypeEnum import AssetTypeEnum
from controllers import NLPController

logger = logging.getLogger('uvicorn.error')

data_router = APIRouter(
    prefix='/api/v1/data',
    tags=['api_v1', 'data'],
)
debug_router = APIRouter(
    prefix='/api/v1/debug',
    tags=['debug'],
)

@data_router.post('/upload/{project_id}')  # ✅ Fixed Path
async def upload_data(request: Request, project_id: int, file: UploadFile = File(...),  
                      app_settings: Settings = Depends(get_settings)):
    project_model = await ProjectModel.create_instance(
        db_client=request.app.db_client
    )
    project = await project_model.get_project_or_create_one(
        project_id=project_id
    )
    # Check and validate the file properties in controllers
    data_controller = DataControllers()
    is_valid, result_signal = data_controller.validate_uploaded_file(file=file)
    if not is_valid:  # ✅ Check error case first
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": result_signal
            }
        )

    #return {"signal": result_signal, "valid": is_valid, "filename": file.filename, "project_id": project_id}

    project_dir_path = ProjectControllers().get_project_path(project_id=str(project_id))

    file_path, file_id = data_controller.generate_unique_filepath(
        orig_file_name=file.filename,
        project_id=str(project_id))
    try:
        async with aiofiles.open(file_path,"wb") as f:
            while chunk := await file.read(app_settings.FILE_DEFAULT_CHUNK_SIZE):
                await f.write (chunk)
    except Exception as e:
        logger.error(f"Error while uploading file: {e}")
        return JSONResponse (
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
            "signal": ResponseSignal.FILE_UPLOAD_FAILED.value})

    # store the assets into the database
    asset_model = await AssetModel.create_instance(db_client=request.app.db_client)
    asset_resource = Asset(
        asset_project_id=project.project_id,  # ObjectId
        asset_type=AssetTypeEnum.FILE.value,
        asset_name=file_id,
        asset_size=os.path.getsize(file_path),
    )
    # asset_record = await asset_model.create_asset(asset=asset_resource)
    # FIX
    try:
        asset_record = await asset_model.create_asset(asset=asset_resource)
    except Exception as e:
        logger.error(f"Asset creation failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": ResponseSignal.ASSET_CREATION_FAILED.value}
        )

    return JSONResponse(
        content={
            "signal": ResponseSignal.FILE_UPLOAD_SUCCESS.value,
            "file_id": str(asset_record.asset_id),
            #"project_id": str(project._id)
            }
            )


@data_router.post('/process/{project_id}')
async def process_endpoint(request:Request, project_id: int, process_request: ProcessRequest):

    chunk_size = process_request.chunk_size
    overlap_size = process_request.overlap_size
    do_reset = process_request.do_reset

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

    asset_model = await AssetModel.create_instance(
        db_client=request.app.db_client)
    project_files_ids = {}
    if process_request.file_id:
        asset_record = await asset_model.get_asset_record(
            asset_project_id=project.project_id, 
            asset_name=process_request.file_id)
        if asset_record is None:
            return JSONResponse (
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"signal": ResponseSignal. FILE_ID_ERROR.value,}
            )
        project_files_ids = {
            asset_record.asset_id: asset_record.asset_name
            }

    else:

        project_files = await asset_model.get_all_project_assets(
            asset_project_id=project.project_id, asset_type=AssetTypeEnum.FILE.value,)
        project_files_ids = {
            record.asset_id: record.asset_name 
            for record in project_files
            }

    if len(project_files_ids) == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": ResponseSignal.NO_FILES_ERROR.value})
        
    process_controller = ProcessControllers(project_id=str(project_id))
    no_records = 0
    no_files = 0
    chunk_model = await ChunkModel.create_instance(
            db_client=request.app.db_client
        )  
    
    
    # if do_reset == 1:
    #     _ = await chunk_model.delete_chunks_by_project_id(
    #         project_id=project.id
    #     )
    if do_reset == 1:
        
        # delete associated vectors collection
        collection_name = nlp_controller.create_collection_name(project_id=project.project_id)
        collection_name = nlp_controller.create_collection_name(project_id=project.project_id)
        _ = await request.app.vectordb_client.delete_collection(collection_name=collection_name)

        # delete existing chunks
        deleted_count = await chunk_model.delete_chunks_by_project_id(
            project_id=project.project_id
        )
        print(f"Deleted {deleted_count} existing chunks due to reset")

        # RIGHT AT THE START of the for loop, before processing files
    print(f"=== PROCESSING INFO ===")
    print(f"Number of files to process: {len(project_files_ids)}")
    print(f"File IDs: {list(project_files_ids.values())}")
    print(f"do_reset value: {do_reset}")
    print("=== START FILE PROCESSING ===")
        #     ---------------------------------------------

    for asset_id, file_id in project_files_ids.items():
        file_content = process_controller.get_file_content(file_id=file_id)
        if file_content is None:
            logger.error(f"Error while processing file: {file_id}")
            continue 
        file_chunks = process_controller.process_file_content(
        file_content=file_content,
        file_id=file_id,
        chunk_size=chunk_size,
        overlap_size=overlap_size
        )
        print(f"DEBUG: About to save {len(file_chunks)} chunks for project ID: {project_id}")

        # ADD MORE DEBUGGING HERE - AFTER splitting into chunks
        print(f"Number of chunks created: {len(file_chunks) if file_chunks else 0}")
        if file_chunks:
            for i, chunk in enumerate(file_chunks[:3]):  # Show first 3 chunks
                print(f"Chunk {i}: '{chunk.page_content[:100]}...' (length: {len(chunk.page_content)})")
        print("=== END DEBUG INFO ===")
        
                #     ---------------------------------------------


        if file_chunks is None or len(file_chunks) == 0:
            return JSONResponse (
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                "signal": ResponseSignal.PROCESSING_FAILED. value}
            )
        file_chunks_records = [
            DataChunk(
                chunk_text=chunk.page_content,
                chunk_metadata=chunk.metadata,
                chunk_order=i+1,
                chunk_project_id=project.project_id ,
                chunk_asset_id=asset_id
            ) 
            for i, chunk in enumerate(file_chunks)
        ]

        no_records += await chunk_model.insert_many_chunks(chunks=file_chunks_records)
        no_files += 1
    return JSONResponse(
        content={
            "signal": ResponseSignal.PROCESSING_SUCCESS.value,
            "inserted_chunks": no_records,
            "processed_files": no_files
        } 
    ) 



# Add this to your FastAPI router

@debug_router.get('/excel-processing/{project_id}/{file_id}')  # Fixed route name
async def debug_excel_processing(request: Request, project_id: int, file_id: str):
    """Debug Excel processing endpoint with correct route"""
    try:
        from controllers.ProcessControllers import ProcessControllers
        
        process_controller = ProcessControllers(project_id=str(project_id))
        
        # Debug Excel structure
        file_path = os.path.join(process_controller.project_path, file_id)
        excel_debug = process_controller.excel_processor.debug_excel_structure(file_path)
        
        # Debug content processing
        content_debug = process_controller.debug_processed_content(file_id)
        
        return JSONResponse(content={
            "file_id": file_id,
            "excel_structure": excel_debug,
            "content_processing": content_debug,
            "status": "success"
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "file_id": file_id}
        )


# Also add a quick test endpoint
@data_router.get('/test-search/{project_id}')
async def test_search_functionality(
    request: Request, 
    project_id: int,
    query: str = "pepper non-compliant"
):
    """Test search functionality with debug information"""
    
    try:
        from controllers.NLPController import NLPController
        
        # Get project
        project_model = await ProjectModel.create_instance(db_client=request.app.db_client)
        project = await project_model.get_project_or_create_one(project_id=project_id)
        
        # Create NLP controller (adjust based on your setup)
        nlp_controller = NLPController(
            vectordb_client=request.app.vectordb_client,
            generation_client=getattr(request.app, 'generation_client', None),
            embedding_client=getattr(request.app, 'embedding_client', None),
            template_parser=getattr(request.app, 'template_parser', None)
        )
        
        # Test different search strategies
        search_results = {}
        
        # Test 1: Direct query
        direct_results = await nlp_controller.search_vector_db_collection(project, query, limit=10)
        search_results["direct_query"] = {
            "query": query,
            "results_count": len(direct_results) if direct_results else 0,
            "sample_results": [
                {
                    "text_preview": getattr(doc, 'text', str(doc))[:100] + "...",
                    "metadata": getattr(doc, 'metadata', {})
                }
                for doc in (direct_results[:3] if direct_results else [])
            ]
        }
        
        # Test 2: Search with individual terms
        search_terms = ["pepper", "فلفل", "non-compliant", "غير مطابق", "pesticide", "مبيد"]
        for term in search_terms:
            term_results = await nlp_controller.search_vector_db_collection(project, term, limit=5)
            search_results[f"term_{term}"] = {
                "results_count": len(term_results) if term_results else 0,
                "sample_results": [
                    {
                        "text_preview": getattr(doc, 'text', str(doc))[:100] + "...",
                        "metadata": getattr(doc, 'metadata', {})
                    }
                    for doc in (term_results[:2] if term_results else [])
                ]
            }
        
        # Test 3: Intent analysis
        intent_info = nlp_controller.analyze_query_intent(query)
        
        # Test 4: Collection info
        collection_info = await nlp_controller.get_vector_db_collection_info(project)
        
        return JSONResponse(content={
            "query": query,
            "intent_analysis": intent_info,
            "collection_info": collection_info,
            "search_results": search_results
        })
        
    except Exception as e:
        logger.error(f"Test search failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )