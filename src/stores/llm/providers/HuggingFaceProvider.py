# # src/stores/llm/providers/HuggingFaceProvider.py

# from ..LLMInterface import LLMInterface
# from ..LLMEnum import DocumentTypeEnum
# import logging
# from typing import List, Union
# import os

# class HuggingFaceProvider(LLMInterface):
#     def __init__(self, 
#                  model_name: str = "all-MiniLM-L6-v2",
#                  default_input_max_characters: int = 1000,
#                  default_generation_max_output_tokens: int = 1000,
#                  default_generation_temperature: float = 0.1,
#                  cache_dir: str = "./models"):
#         """
#         HuggingFace Provider متوافق مع LLM Factory
        
#         Args:
#             model_name: اسم النموذج (all-MiniLM-L6-v2, all-mpnet-base-v2, etc.)
#             default_input_max_characters: الحد الأقصى لطول النص
#             cache_dir: مجلد حفظ النماذج
#         """
#         self.model_name = model_name
#         self.default_input_max_characters = default_input_max_characters
#         self.default_generation_max_output_tokens = default_generation_max_output_tokens
#         self.default_generation_temperature = default_generation_temperature
#         self.cache_dir = cache_dir
        
#         # متغيرات متوافقة مع LLM Factory
#         self.generation_model_id = None
#         self.embedding_model_id = model_name
#         self.embedding_size = None
#         self.client = None  # لن نستخدمه لكن متطلب للتوافق
        
#         # إنشاء مجلد الكاش
#         os.makedirs(cache_dir, exist_ok=True)
        
#         self.logger = logging.getLogger(__name__)
        
#         # تحميل النموذج
#         self._load_model()

#     def _load_model(self):
#         """تحميل نموذج HuggingFace"""
#         try:
#             from sentence_transformers import SentenceTransformer
            
#             self.logger.info(f"Loading HuggingFace model: {self.model_name}")
#             self.model = SentenceTransformer(
#                 self.model_name, 
#                 cache_folder=self.cache_dir
#             )
            
#             # تحديد حجم الـ embedding
#             self.embedding_size = self.model.get_sentence_embedding_dimension()
            
#             self.logger.info(f"✅ HuggingFace model loaded successfully!")
#             self.logger.info(f"   - Model: {self.model_name}")
#             self.logger.info(f"   - Embedding size: {self.embedding_size}")
#             self.logger.info(f"   - Cache dir: {self.cache_dir}")
            
#         except ImportError as e:
#             self.logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
#             raise e
#         except Exception as e:
#             self.logger.error(f"Failed to load HuggingFace model: {e}")
#             raise e

#     def set_generation_model(self, model_id: str):
#         """تعيين نموذج التوليد - لا يُستخدم في HuggingFace للـ embedding"""
#         self.generation_model_id = model_id
#         self.logger.warning("HuggingFace provider is for embedding only, generation not supported")

#     def set_embedding_model(self, model_id: str, embedding_size: int):
#         """تعيين نموذج الـ embedding"""
#         if model_id != self.embedding_model_id:
#             self.logger.info(f"Switching embedding model from {self.embedding_model_id} to {model_id}")
#             self.embedding_model_id = model_id
#             self.model_name = model_id
#             # إعادة تحميل النموذج الجديد
#             self._load_model()
        
#         # التحقق من حجم الـ embedding
#         if embedding_size != self.embedding_size:
#             self.logger.warning(f"Requested embedding size {embedding_size} doesn't match model size {self.embedding_size}")

#     def process_text(self, text: str):
#         """معالجة وتنظيف النص"""
#         if not text or not isinstance(text, str):
#             return ""
#         return text[:self.default_input_max_characters].strip()

#     def generate_text(self, prompt: str, chat_history: list = [], 
#                      max_output_tokens: int = None, temperature: float = None):
#         """توليد النص - غير مدعوم في HuggingFace Provider"""
#         self.logger.error("Text generation not supported in HuggingFace Provider")
#         self.logger.info("Use OpenAI or Cohere for text generation")
#         return None

#     def embed_text(self, text: Union[str, List[str]], document_type: str = None):
#         """إنتاج الـ embeddings باستخدام HuggingFace"""
#         if not hasattr(self, 'model'):
#             self.logger.error("HuggingFace model not loaded")
#             return None

#         # تحويل النص إلى قائمة
#         if isinstance(text, str):
#             text = [text]

#         if not text or len(text) == 0:
#             self.logger.warning("No text provided for embedding")
#             return None

#         try:
#             # تنظيف النصوص
#             cleaned_texts = [self.process_text(t) for t in text if t and t.strip()]
            
#             if not cleaned_texts:
#                 self.logger.warning("No valid texts after cleaning")
#                 return None

#             self.logger.info(f"Embedding {len(cleaned_texts)} texts with HuggingFace")
            
#             # إنتاج الـ embeddings
#             embeddings = self.model.encode(
#                 cleaned_texts, 
#                 convert_to_numpy=True,
#                 show_progress_bar=len(cleaned_texts) > 10  # إظهار progress bar للنصوص الكثيرة
#             )
            
#             # تحويل إلى list للتوافق مع APIs الأخرى
#             embeddings_list = embeddings.tolist()
            
#             self.logger.info(f"✅ Successfully generated {len(embeddings_list)} embeddings")
#             return embeddings_list

#         except Exception as e:
#             self.logger.error(f"Error generating embeddings: {e}")
#             return None

#     def construct_prompt(self, prompt: str, role: str):
#         """بناء الـ prompt - للتوافق فقط"""
#         return {
#             "role": role,
#             "text": prompt,
#         }

#     def get_model_info(self):
#         """معلومات عن النموذج"""
#         return {
#             "provider": "huggingface",
#             "model_name": self.model_name,
#             "embedding_size": self.embedding_size,
#             "cache_dir": self.cache_dir,
#             "supports_generation": False,
#             "supports_embedding": True,
#             "is_local": True,
#             "is_free": True
#         }

#     def validate_setup(self):
#         """التحقق من صحة الإعداد"""
#         try:
#             # اختبار بسيط
#             test_result = self.embed_text(["test sentence"])
            
#             if test_result and len(test_result) > 0:
#                 self.logger.info("✅ HuggingFace provider validation successful")
#                 return True
#             else:
#                 self.logger.error("❌ HuggingFace provider validation failed")
#                 return False
#         except Exception as e:
#             self.logger.error(f"❌ HuggingFace provider validation error: {e}")
#             return False