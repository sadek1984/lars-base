# routes/iso_routes.py

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from controllers.NLPController import EnhancedNLPController
from processors.iso_document_processor import parse_document_metadata
from langchain.text_splitter import RecursiveCharacterTextSplitter
from datetime import datetime
import os
import logging
import re
from typing import List

logger = logging.getLogger(__name__)

# ✅ SINGLE ROUTER DEFINITION WITH PREFIX
router = APIRouter(
    prefix="/api/v1/iso",
    tags=["ISO 17025 Management"]
)

def fix_metadata_for_chromadb(metadata_dict):
    """تحويل metadata ليتوافق مع ChromaDB"""
    fixed_metadata = {}
    for key, value in metadata_dict.items():
        if isinstance(value, list):
            fixed_metadata[key] = ", ".join(map(str, value))
        elif isinstance(value, (dict, tuple)):
            fixed_metadata[key] = str(value)
        elif value is None:
            fixed_metadata[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            fixed_metadata[key] = value
        else:
            fixed_metadata[key] = str(value)
    return fixed_metadata


@router.post("/upload/{project_id}")  # ✅ Removed duplicate /iso
async def upload_iso_document(
    project_id: str,
    file: UploadFile = File(...),
    document_type: str = Form(default="Unknown")
):
    """Upload ISO 17025 documents (PDF, DOCX, XLSX)"""
    file_path = None
    
    try:
        logger.info(f"📄 Uploading ISO document: {file.filename} for project {project_id}")
        
        # Save file temporarily
        file_path = f"/tmp/{file.filename}"
        content = await file.read()
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        # Parse document
        parsed_data = parse_document_metadata(file_path, document_type)
        doc_text = parsed_data["text"]
        doc_metadata = parsed_data["metadata"]
        
        # Initialize NLP controller
        nlp_controller = EnhancedNLPController(
            gemini_api_key=os.getenv("GEMINI_API_KEY")
        )
        
        if not nlp_controller.chroma_client:
            raise HTTPException(status_code=500, detail="ChromaDB not available")
        
        # Split text into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, 
            chunk_overlap=150
        )
        chunks = text_splitter.split_text(doc_text)
        
        # Create SEPARATE collection for ISO docs
        collection_name = f"iso_project_{project_id}"
        
        nlp_controller.embed_fn.document_mode = True
        collection = nlp_controller.chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=nlp_controller.embed_fn,
            metadata={"type": "iso", "project_id": project_id}
        )
        
        # Prepare metadata
        base_metadata = fix_metadata_for_chromadb(doc_metadata)
        base_metadata.update({
            "source_file": file.filename,
            "document_type": document_type,
            "project_id": str(project_id),
            "upload_timestamp": datetime.now().isoformat(),
            "collection_type": "iso"
        })
        
        # Create chunks with metadata
        chunk_ids = [f"iso_{file.filename}_{i}" for i in range(len(chunks))]
        chunk_metadata = [
            {**base_metadata, "chunk_index": i} 
            for i in range(len(chunks))
        ]
        
        # Add to collection
        collection.add(
            documents=chunks,
            ids=chunk_ids,
            metadatas=chunk_metadata
        )
        
        logger.info(f"✅ Indexed {len(chunks)} chunks from {file.filename}")
        
        return {
            "message": f"ISO document '{file.filename}' uploaded successfully",
            "project_id": project_id,
            "document_type": document_type,
            "document_id": doc_metadata.get("document_id", "Unknown"),
            "chunks_indexed": len(chunks),
            "iso_clauses": doc_metadata.get("related_clauses", []),
            "main_sections": doc_metadata.get("main_sections", []),
            "referenced_documents": doc_metadata.get("referenced_documents", []),
            "status": "success"
        }
                
    except Exception as e:
        logger.error(f"❌ Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


@router.post("/query/{project_id}")  # ✅ Removed duplicate /iso
async def query_iso_documents(
    project_id: str,
    query_data: dict
):
    """Query ISO documents for a specific project"""
    
    try:
        query_text = query_data.get("text", "")
        logger.info(f"🔍 ISO query for project {project_id}: {query_text}")
        
        nlp_controller = EnhancedNLPController(
            gemini_api_key=os.getenv("GEMINI_API_KEY")
        )
        
        if not nlp_controller.chroma_client:
            raise HTTPException(status_code=500, detail="ChromaDB not available")
        
        # Query ISO collection
        collection_name = f"iso_project_{project_id}"
        
        try:
            nlp_controller.embed_fn.document_mode = False
            collection = nlp_controller.chroma_client.get_collection(
                name=collection_name,
                embedding_function=nlp_controller.embed_fn
            )
        except:
            raise HTTPException(
                status_code=404, 
                detail=f"No ISO documents found for project {project_id}"
            )
        
        # Search
        results = collection.query(
            query_texts=[query_text],
            n_results=5
        )
        
        if not results["documents"] or not results["documents"][0]:
            return {
                "project_id": project_id,
                "query": query_text,
                "answer": "لم يتم العثور على معلومات ذات صلة في مستندات ISO المرفوعة",
                "status": "no_results"
            }
        
        # Build context
        context = "\n---\n".join(results["documents"][0])
        
        # Get sources from metadata
        sources = []
        for meta in results["metadatas"][0]:
            source_info = {
                "file": meta.get("source_file", "Unknown"),
                "type": meta.get("document_type", "Unknown"),
                "doc_id": meta.get("document_id", "Unknown"),
                "clauses": meta.get("related_clauses", "").split(", ") if meta.get("related_clauses") else []
            }
            sources.append(source_info)
        
        # Generate answer
        prompt = f"""
        بناءً على مستندات ISO 17025 التالية، أجب على السؤال:

        السياق: {context}
        
        السؤال: {query_text}
        
        أجب بتنسيق واضح ومفصل مع ذكر:
        1. الإجابة المباشرة
        2. البنود المرجعية من ISO 17025 إن وجدت
        3. المستندات المرتبطة
        """
        
        answer = nlp_controller.generation_model.generate_content(prompt)
        
        return {
            "project_id": project_id,
            "query": query_text,
            "answer": answer.text,
            "sources": sources,
            "total_chunks": len(results["documents"][0]),
            "status": "success"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def detect_query_language(query: str) -> str:
    """كشف لغة الاستعلام"""
    arabic_pattern = re.compile(r'[\u0600-\u06FF]')
    if arabic_pattern.search(query):
        return "arabic"
    else:
        return "english"

def create_language_specific_prompt(query: str, context: str, language: str) -> str:
    """إنشاء prompt حسب اللغة"""
    
    if language == "arabic":
        return f"""
        بناءً على مستندات ISO 17025 التالية، أجب على السؤال بوضوح وإيجاز.

        السياق: {context}
        السؤال: {query}

        تعليمات مهمة:
        - أجب بالعربية
        - كن مباشر ومختصر
        - ركز على ما يطلبه السؤال فقط
        - استخدم تنسيق واضح بدون رموز خاصة

        الجواب:
        """
    else:
        return f"""
        Based on the following ISO 17025 documents, answer the question clearly and concisely.

        Context: {context}
        Question: {query}

        Important instructions:
        - Answer in English
        - Be direct and concise  
        - Focus only on what the question asks for
        - Use clear formatting without special characters

        Answer:
        """

def clean_answer_text(text: str) -> str:
    """تنظيف النص من الرموز الغريبة"""
    # إزالة الـ markdown asterisks
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold** → bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)      # *italic* → italic
    
    # إزالة \n الغريبة
    text = text.replace('\\n', '\n')
    
    # إزالة المسافات الزائدة
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text

########## تصفية المصادر بناءً على المساهمة الفعلية ##########

def verify_content_contribution(chunk_text, answer_text, threshold=0.15):  # خفض threshold
    """التحقق من مساهمة chunk معين في الإجابة"""
    
    # إزالة كلمات شائعة
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did'}
    
    # تنظيف النصوص
    chunk_words = set([w.lower().strip('.,!?;:()[]') for w in chunk_text.split() if w.lower() not in stop_words and len(w) > 2])
    answer_words = set([w.lower().strip('.,!?;:()[]') for w in answer_text.split() if w.lower() not in stop_words and len(w) > 2])
    
    # حساب التداخل
    overlap = len(chunk_words.intersection(answer_words))
    
    # شروط أكثر مرونة
    if overlap >= 3:  # 3 كلمات مطابقة على الأقل
        return True
    
    # أو نسبة تداخل معقولة
    if len(chunk_words) > 0:
        contribution_ratio = overlap / len(chunk_words)
        return contribution_ratio >= threshold
    
    return False

def calculate_document_priority(query, chunk_metadata):
    """حساب أولوية المستند مع معالجة للأنواع غير المعروفة"""
    
    doc_type = chunk_metadata.get("document_type", "Unknown")
    source_file = chunk_metadata.get("source_file", "").lower()
    query_lower = query.lower()
    
    # إذا كان النوع Unknown، حاول استنتاجه من اسم الملف
    if doc_type == "Unknown":
        if "work instruction" in source_file or "wi-" in source_file:
            doc_type = "Work Instruction"
        elif "procedure" in source_file or "proc-" in source_file:
            doc_type = "Procedure"
        elif "quality" in source_file or "manual" in source_file or "qm-" in source_file:
            doc_type = "Quality Manual"
        elif "form" in source_file or "record" in source_file:
            doc_type = "Form/Record"
    
    # باقي منطق حساب الأولوية...
    technical_keywords = ["مواصفات", "specifications", "كيف", "how", "طريقة", "method", "إعداد", "preparation", "standard", "primary", "stock"]
    policy_keywords = ["سياسة", "policy", "إدارة", "management", "متطلبات", "requirements"]
    
    is_technical_query = any(kw in query_lower for kw in technical_keywords)
    is_policy_query = any(kw in query_lower for kw in policy_keywords)
    
    priority_scores = {
        "Work Instruction": 10 if is_technical_query else 5,
        "Procedure": 8 if is_technical_query else 7,
        "Quality Manual": 3 if is_technical_query else 10,
        "Form/Record": 6 if is_technical_query else 4,
        "Unknown": 5  # قيمة متوسطة
    }
    
    return priority_scores.get(doc_type, 5)

def rerank_chunks_by_relevance(chunks, query):
    """إعادة ترتيب chunks حسب الصلة والأولوية"""
    
    ranked_chunks = []
    
    for chunk in chunks:
        priority_score = calculate_document_priority(query, chunk["metadata"])
        word_matches = chunk.get("word_matches", 0)
        
        # نتيجة مُجمعة: أولوية المستند + مطابقة الكلمات
        combined_score = priority_score * 2 + word_matches * 3
        
        ranked_chunks.append({
            **chunk,
            "priority_score": priority_score,
            "combined_score": combined_score
        })
    
    # ترتيب حسب النتيجة المُجمعة
    ranked_chunks.sort(key=lambda x: x["combined_score"], reverse=True)
    
    return ranked_chunks

def hybrid_search(collection, query_text, n_results=15):
    """بحث مختلط محسن مع فلترة أفضل"""
    
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results
    )
    
    query_keywords = set(query_text.lower().split())
    scored_results = []
    
    for i, doc in enumerate(results["documents"][0]):
        doc_words = set(doc.lower().split())
        keyword_matches = len(query_keywords.intersection(doc_words))
        
        # فقط chunks التي تحتوي على كلمة مفتاحية واحدة على الأقل
        if keyword_matches > 0:
            scored_results.append({
                "document": doc,
                "metadata": results["metadatas"][0][i],
                "embedding_rank": i,
                "word_matches": keyword_matches,
                "combined_score": keyword_matches * 3 + (n_results - i)
            })
    
    scored_results.sort(key=lambda x: x["combined_score"], reverse=True)
    return scored_results[:10]
#     _______________________________________________________________________________

@router.post("/reupload_with_type/{project_id}")
async def reupload_with_correct_types(project_id: str):
    """إعادة تحديد أنواع المستندات الموجودة"""
    
    try:
        collection_name = f"local_project_{project_id}"
        from controllers.NLPController import EnhancedNLPController
            
        nlp_controller = EnhancedNLPController(
            gemini_api_key=os.getenv("GEMINI_API_KEY")
        )
        
        collection = nlp_controller.chroma_client.get_collection(name=collection_name)
        
        # الحصول على جميع chunks
        all_data = collection.get()
        
        updates = []
        for i, metadata in enumerate(all_data["metadatas"]):
            source_file = metadata.get("source_file", "").lower()
            
            # تحديد النوع من اسم الملف
            if "work instruction" in source_file:
                new_type = "Work Instruction"
            elif "quality" in source_file or "manual" in source_file:
                new_type = "Quality Manual"
            elif "proc" in source_file:
                new_type = "Procedure"
            else:
                new_type = metadata.get("document_type", "Unknown")
            
            # تحديث metadata
            updated_metadata = metadata.copy()
            updated_metadata["document_type"] = new_type
            
            updates.append({
                "id": all_data["ids"][i],
                "metadata": updated_metadata
            })
        
        # تطبيق التحديثات
        for update in updates:
            collection.update(
                ids=[update["id"]],
                metadatas=[update["metadata"]]
            )
        
        return {
            "message": f"Updated {len(updates)} chunks with correct document types",
            "project_id": project_id
        }
        
    except Exception as e:
        return {"error": str(e)}
    

@router.post("/debug_search/{project_id}")
async def debug_search(
    project_id: str,
    query_data: dict
):
    """Debug search to see what chunks are being retrieved"""
    try:
        query_text = query_data.get("text", "")
        
        from controllers.NLPController import EnhancedNLPController
        nlp_controller = EnhancedNLPController(
            gemini_api_key=os.getenv("GEMINI_API_KEY")
        )
        
        collection_name = f"local_project_{project_id}"
        collection = nlp_controller.chroma_client.get_collection(
            name=collection_name,
            embedding_function=nlp_controller.embed_fn
        )
        
        # بحث موسع للتشخيص
        results = collection.query(
            query_texts=[query_text],
            n_results=15,  # زيادة العدد
            include=["documents", "metadatas", "distances"]
        )
        
        debug_info = []
        for i, doc in enumerate(results["documents"][0]):
            debug_info.append({
                "rank": i + 1,
                "distance": results["distances"][0][i],
                "source": results["metadatas"][0][i].get("source_file", "Unknown"),
                "chunk_preview": doc[:200] + "...",
                "contains_keywords": {
                    "primary": "primary" in doc.lower(),
                    "stock": "stock" in doc.lower(), 
                    "standard": "standard" in doc.lower()
                }
            })
        
        return {
            "query": query_text,
            "total_results": len(debug_info),
            "debug_results": debug_info
        }
        
    except Exception as e:
        return {"error": str(e)}


async def simple_text_search(request, project_id: str, query: str):
    """بحث نصي بسيط كبديل لـ vector search"""
    try:
        # استخدام العقدة المحلية ChromaDB
        from controllers.NLPController import EnhancedNLPController
        
        nlp_controller = EnhancedNLPController(
            gemini_api_key=os.getenv("GEMINI_API_KEY")
        )
        
        # استخدام local data إذا كان متاح
        if nlp_controller.chroma_client:
            result = await nlp_controller.answer_with_local_data(
                project_id=int(project_id) if project_id.isdigit() else 4,
                query=query,
                n_results=5
            )
            
            if result.get("success"):
                return {
                    "project_id": project_id,
                    "query": query,
                    "answer": result["answer"],
                    "sources": ["Local ChromaDB"],
                    "status": "success_local"
                }
        
        # إجابة تجريبية إذا فشل كل شيء
        return {
            "project_id": project_id,
            "query": query,
            "answer": f"تم استلام الاستعلام: {query}. النظام قيد التطوير.",
            "sources": [],
            "status": "fallback"
        }
        
    except Exception as e:
        logger.error(f"Fallback search failed: {e}")
        return {
            "project_id": project_id,
            "query": query,
            "answer": "عذراً، حدث خطأ في معالجة الاستعلام",
            "sources": [],
            "status": "error"
        }

def detect_document_type_from_query(query: str) -> dict:
    """تحديد نوع المستند من الاستعلام"""
    query_lower = query.lower()
    
    if any(word in query_lower for word in ["procedure", "sop", "إجراء"]):
        return {"document_type": "Procedure"}
    elif any(word in query_lower for word in ["policy", "manual", "سياسة", "دليل"]):
        return {"document_type": "Quality Manual"} 
    elif any(word in query_lower for word in ["instruction", "how to", "تعليمات", "كيف"]):
        return {"document_type": "Work Instruction"}
    
    return {}  # بحث في جميع الأنواع

def create_iso_hierarchical_prompt(query: str, context: str, chunks: list) -> str:
    """إنشاء prompt للإجابة الهرمية"""
    
    # تحديد نوع المستند الأساسي
    doc_types = [chunk.get("metadata", {}).get("document_type", "Unknown") for chunk in chunks]
    primary_doc_type = max(set(doc_types), key=doc_types.count) if doc_types else "Unknown"
    
    prompt = f"""
    أجب على السؤال بالتنسيق الهرمي التالي لنظام ISO 17025:

    **المستوى:** {primary_doc_type}
    **النص المسترجع:** [اقتبس المعلومة المطلوبة من النص]
    **العلاقة:** [اشرح كيف ترتبط بالمستوى الأعلى - مثل SOP مرتبط بدليل الجودة]
    **السبب/السياق:** [أهمية هذه المعلومة في إطار ISO 17025]

    السياق من المستندات:
    {context}

    السؤال: {query}
    
    أجب باللغة العربية مع الاحتفاظ بالمصطلحات التقنية الإنجليزية عند الضرورة.
    """
    
    return prompt

# routes/iso.py - إضافة endpoint للمعالجة الهرمية
@router.post("/upload_hierarchy/{project_id}")
async def upload_iso_hierarchy(
    project_id: str,
    folder_path: str = Form(...)
):
    """رفع وفهرسة كامل هيكل ISO 17025"""
    try:
        from processors.iso_hierarchical_processor import ISO17025HierarchicalProcessor
        
        processor = ISO17025HierarchicalProcessor()
        hierarchy_data = processor.process_iso_folder_structure(folder_path)
        
        # فهرسة هرمية في ChromaDB
        from controllers.NLPController import EnhancedNLPController
        nlp_controller = EnhancedNLPController(
            gemini_api_key=os.getenv("GEMINI_API_KEY")
        )
        
        indexed_docs = await index_hierarchical_documents(
            nlp_controller, hierarchy_data, project_id
        )
        
        return {
            "message": "ISO 17025 hierarchy processed successfully",
            "project_id": project_id,
            "documents_processed": len(hierarchy_data["documents"]),
            "relationships_discovered": len(hierarchy_data["relationships"]),
            "hierarchy_levels": [1, 2, 3, 4],
            "status": "hierarchical_success"
        }
        
    except Exception as e:
        logger.error(f"Hierarchy processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/query_hierarchical/{project_id}")
async def query_iso_hierarchical(
    project_id: str,
    query_data: dict
):
    """استعلام هرمي ذكي لـ ISO 17025"""
    try:
        from engines.iso_hierarchical_search import ISO17025HierarchicalSearch
        from controllers.NLPController import EnhancedNLPController
        
        nlp_controller = EnhancedNLPController(
            gemini_api_key=os.getenv("GEMINI_API_KEY")
        )
        
        search_engine = ISO17025HierarchicalSearch(nlp_controller)
        
        result = await search_engine.hierarchical_search(
            query=query_data.get("text", ""),
            project_id=project_id
        )
        if isinstance(result, dict) and "hierarchical_answer" in result:
            result["hierarchical_answer"] = clean_answer_text(result["hierarchical_answer"])
        
        return {
            "project_id": project_id,
            "query": query_data.get("text", ""),
            "hierarchical_answer": result,
            "status": "hierarchical_success"
        }
        
    except Exception as e:
        logger.error(f"Hierarchical query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
async def index_hierarchical_documents(nlp_controller, hierarchy_data, project_id):
    """فهرسة المستندات الهرمية"""
    try:
        collection_name = f"local_project_{project_id}"
        collection = nlp_controller.chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=nlp_controller.embed_fn
        )
        
        indexed_count = 0
        
        for doc_data in hierarchy_data["documents"]:
            # تقسيم النص إلى chunks
            from langchain.text_splitter import RecursiveCharacterTextSplitter
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
            chunks = text_splitter.split_text(doc_data["text"])
            
            # إعداد metadata للفهرسة
            base_metadata = {
                "source_file": doc_data["metadata"]["source_file"],
                "document_type": doc_data["metadata"]["document_type"],
                "hierarchy_level": doc_data["hierarchy_level"],
                "hierarchy_role": doc_data["hierarchy_role"],
                "project_id": str(project_id)
            }
            
            # فهرسة chunks
            chunk_ids = [f"hier_{doc_data['metadata']['source_file']}_{i}" for i in range(len(chunks))]
            chunk_metadata = [
                {**base_metadata, "chunk_index": i} 
                for i in range(len(chunks))
            ]
            
            collection.add(
                documents=chunks,
                ids=chunk_ids,
                metadatas=chunk_metadata
            )
            
            indexed_count += len(chunks)
        
        return indexed_count
        
    except Exception as e:
        logger.error(f"Hierarchical indexing failed: {e}")
        raise e
        

@router.post("/upload_multiple/{project_id}")
async def upload_multiple_files(
    project_id: str,
    files: List[UploadFile] = File(...),
    document_type_1: str = Form(default="Unknown"),
    document_type_2: str = Form(default="Unknown"), 
    document_type_3: str = Form(default="Unknown"),
    document_type_4: str = Form(default="Unknown")
):
    """رفع ملفات متعددة مع تتبع مفصل للتشخيص"""
    try:
        logger.info(f"=== UPLOAD DEBUG START ===")
        logger.info(f"Received {len(files)} files for project {project_id}")
        
        # تجميع الأنواع
        document_types = [document_type_1, document_type_2, document_type_3, document_type_4]
        logger.info(f"Document types: {document_types}")
        
        # إنشاء مجلد مؤقت
        temp_folder = f"/tmp/iso_project_{project_id}"
        os.makedirs(temp_folder, exist_ok=True)
        logger.info(f"Created temp folder: {temp_folder}")
        
        # إنشاء المجلدات الفرعية
        subfolders = {
            "Quality Manual": "1_quality_manual",
            "Procedure": "2_procedures", 
            "Work Instruction": "3_work_instructions",
            "Form/Record": "4_forms_and_records"
        }
        
        for subfolder in subfolders.values():
            subfolder_path = f"{temp_folder}/{subfolder}"
            os.makedirs(subfolder_path, exist_ok=True)
            logger.info(f"Created subfolder: {subfolder_path}")
        
        # حفظ الملفات في المجلدات المناسبة
        saved_files = []
        for i, file in enumerate(files):
            doc_type = document_types[i] if i < len(document_types) else "Unknown"
            logger.info(f"Processing file {i}: {file.filename}, type: {doc_type}")
            
            if doc_type in subfolders:
                subfolder = subfolders[doc_type]
                file_path = f"{temp_folder}/{subfolder}/{file.filename}"
                
                try:
                    content = await file.read()
                    with open(file_path, "wb") as buffer:
                        buffer.write(content)
                    
                    # التحقق من حفظ الملف
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        logger.info(f"File saved successfully: {file_path}, size: {file_size} bytes")
                        
                        saved_files.append({
                            "filename": file.filename,
                            "type": doc_type,
                            "path": file_path,
                            "size": file_size
                        })
                    else:
                        logger.error(f"File NOT saved: {file_path}")
                        
                except Exception as file_error:
                    logger.error(f"Error saving file {file.filename}: {file_error}")
            else:
                logger.warning(f"Unknown document type '{doc_type}' for file {file.filename}")
        
        logger.info(f"Total files saved: {len(saved_files)}")
        
        # فحص محتويات المجلد قبل المعالجة الهرمية
        logger.info("=== FOLDER CONTENTS BEFORE PROCESSING ===")
        for root, dirs, files_in_dir in os.walk(temp_folder):
            logger.info(f"Directory: {root}")
            for filename in files_in_dir:
                full_path = os.path.join(root, filename)
                size = os.path.getsize(full_path)
                logger.info(f"  File: {filename}, Size: {size} bytes")
        
        # المعالجة الهرمية
        try:
            from processors.iso_hierarchical_processor import ISO17025HierarchicalProcessor
            
            processor = ISO17025HierarchicalProcessor()
            logger.info("Starting hierarchical processing...")
            
            hierarchy_data = processor.process_iso_folder_structure(temp_folder)
            logger.info(f"Hierarchy data: {len(hierarchy_data['documents'])} documents found")
            
            if hierarchy_data["documents"]:
                for i, doc in enumerate(hierarchy_data["documents"]):
                    logger.info(f"Document {i}: {doc['metadata']['source_file']}, level: {doc.get('hierarchy_level', 'Unknown')}")
            else:
                logger.warning("No documents found in hierarchy data!")
            
            # فهرسة هرمية
            from controllers.NLPController import EnhancedNLPController
            nlp_controller = EnhancedNLPController(
                gemini_api_key=os.getenv("GEMINI_API_KEY")
            )
            
            indexed_count = await index_hierarchical_documents(
                nlp_controller, hierarchy_data, project_id
            )
            
            logger.info(f"Indexed {indexed_count} chunks")
            status_message = "Hierarchical processing completed"
            
        except Exception as hierarchy_error:
            logger.error(f"Hierarchical processing failed: {hierarchy_error}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            # fallback للمعالجة العادية
            status_message = f"Hierarchical failed, using standard processing: {str(hierarchy_error)}"
            indexed_count = 0
        
        # تنظيف المجلد المؤقت
        import shutil
        shutil.rmtree(temp_folder)
        logger.info("Cleaned up temp folder")
        logger.info(f"=== UPLOAD DEBUG END ===")
        
        return {
            "message": f"Multiple files uploaded: {status_message}",
            "project_id": project_id,
            "files_received": len(files),
            "files_processed": len(saved_files),
            "chunks_indexed": indexed_count,
            "processed_files": saved_files,
            "debug_info": {
                "temp_folder": temp_folder,
                "document_types_received": document_types
            },
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"Multiple upload failed: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # تنظيف في حالة الخطأ
        if 'temp_folder' in locals() and os.path.exists(temp_folder):
            import shutil
            shutil.rmtree(temp_folder)
        
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/debug_logs/{project_id}")
async def get_debug_logs(project_id: str):
    """استرجاع آخر logs للتشخيص"""
    try:
        # قراءة logs من الذاكرة أو ملف
        # هذا مثال بسيط
        return {
            "project_id": project_id,
            "message": "Check FastAPI logs in console for detailed debug info",
            "suggestion": "Run upload again and watch the logs"
        }
    except Exception as e:
        return {"error": str(e)}
    

@router.post("/upload_smart_multiple/{project_id}")
async def upload_smart_multiple_files(
    project_id: str,
    files: List[UploadFile] = File(...)
):
    """رفع ملفات متعددة مع اكتشاف تلقائي للنوع"""
    try:
        logger.info(f"=== SMART UPLOAD START ===")
        logger.info(f"Received {len(files)} files for project {project_id}")
        
        # إنشاء مجلد مؤقت
        temp_folder = f"/tmp/iso_project_{project_id}"
        os.makedirs(temp_folder, exist_ok=True)
        
        # إنشاء المجلدات الفرعية
        subfolders = {
            "Quality Manual": "1_quality_manual",
            "Procedure": "2_procedures", 
            "Work Instruction": "3_work_instructions",
            "Form/Record": "4_forms_and_records"
        }
        
        for subfolder in subfolders.values():
            os.makedirs(f"{temp_folder}/{subfolder}", exist_ok=True)
        
        # معالجة كل ملف مع اكتشاف النوع
        saved_files = []
        for file in files:
            # اكتشاف النوع من اسم الملف
            doc_type = detect_document_type_from_filename(file.filename)
            logger.info(f"File: {file.filename}, Detected type: {doc_type}")
            
            if doc_type in subfolders:
                subfolder = subfolders[doc_type]
                file_path = f"{temp_folder}/{subfolder}/{file.filename}"
                
                content = await file.read()
                with open(file_path, "wb") as buffer:
                    buffer.write(content)
                
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    logger.info(f"File saved: {file_path}, size: {file_size}")
                    
                    saved_files.append({
                        "filename": file.filename,
                        "detected_type": doc_type,
                        "path": file_path,
                        "size": file_size
                    })
        
        logger.info(f"Total files saved: {len(saved_files)}")
        
        # المعالجة الهرمية
        from processors.iso_hierarchical_processor import ISO17025HierarchicalProcessor
        processor = ISO17025HierarchicalProcessor()
        hierarchy_data = processor.process_iso_folder_structure(temp_folder)
        
        logger.info(f"Hierarchy processing found {len(hierarchy_data['documents'])} documents")
        
        # فهرسة
        from controllers.NLPController import EnhancedNLPController
        nlp_controller = EnhancedNLPController(
            gemini_api_key=os.getenv("GEMINI_API_KEY")
        )
        
        indexed_count = await index_hierarchical_documents(
            nlp_controller, hierarchy_data, project_id
        )
        
        # تنظيف
        import shutil
        shutil.rmtree(temp_folder)
        
        logger.info(f"Successfully indexed {indexed_count} chunks")
        
        return {
            "message": "Smart multiple upload completed",
            "project_id": project_id,
            "files_processed": len(saved_files),
            "chunks_indexed": indexed_count,
            "file_details": saved_files,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"Smart upload failed: {e}")
        if 'temp_folder' in locals() and os.path.exists(temp_folder):
            import shutil
            shutil.rmtree(temp_folder)
        raise HTTPException(status_code=500, detail=str(e))

def detect_document_type_from_filename(filename: str) -> str:
    """اكتشاف نوع المستند من اسم الملف"""
    filename_lower = filename.lower()
    
    # Quality Manual
    if any(keyword in filename_lower for keyword in ["quality", "manual", "qm-", "qm_"]):
        return "Quality Manual"
    
    # Work Instructions  
    elif any(keyword in filename_lower for keyword in ["work instruction", "wi-", "wi_", "instruction"]):
        return "Work Instruction"
    
    # Procedures
    elif any(keyword in filename_lower for keyword in ["proc-", "proc_", "procedure", "sop"]):
        return "Procedure"
    
    # Forms and Records
    elif any(keyword in filename_lower for keyword in ["form", "record", "rec-", "rec_"]):
        return "Form/Record"
    
    # اكتشاف خاص للملفات المرفوعة
    elif "gc-ms" in filename_lower and ("work" in filename_lower or "instruction" in filename_lower):
        return "Work Instruction"
    elif "quality" in filename_lower and "manual" in filename_lower:
        return "Quality Manual"
    
    # افتراضي
    else:
        return "Work Instruction"  # معظم الملفات 
    

