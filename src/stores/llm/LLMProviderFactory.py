 
from .LLMEnum import LLMEnums
from .providers import OpenAIProvider, CoHereProvider

class LLMProviderFactory:
    def __init__(self, config: dict):
        self.config = config

    def create(self, provider: str):
        if provider == LLMEnums.OPENAI.value:
            return OpenAIProvider(
                api_key = self.config.OPENAI_API_KEY,
                api_url = self.config.OPENAI_API_URL,
                default_input_max_characters=self.config.INPUT_DAFAULT_MAX_CHARACTERS,
                default_generation_max_output_tokens=self.config.GENERATION_DAFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DAFAULT_TEMPERATURE
            )

        if provider == LLMEnums.COHERE.value:
            return CoHereProvider(
                api_key = self.config.COHERE_API_KEY,
                default_input_max_characters=self.config.INPUT_DAFAULT_MAX_CHARACTERS,
                default_generation_max_output_tokens=self.config.GENERATION_DAFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DAFAULT_TEMPERATURE
            )

        return None


# src/stores/llm/LLMProviderFactory.py - محدّث لدعم HuggingFace

# from .LLMEnum import LLMEnums
# from .providers import OpenAIProvider, CoHereProvider
# from .providers.HuggingFaceProvider import HuggingFaceProvider
# import logging

# class LLMProviderFactory:
#     def __init__(self, config: dict):
#         self.config = config
#         self.logger = logging.getLogger(__name__)

#     def create(self, provider: str):
#         """إنشاء مزود LLM حسب النوع المطلوب"""
        
#         self.logger.info(f"Creating LLM provider: {provider}")
        
#         if provider == LLMEnums.OPENAI.value:
#             return self._create_openai_provider()
            
#         elif provider == LLMEnums.COHERE.value:
#             return self._create_cohere_provider()
            
#         elif provider == "huggingface" or provider == "hf":
#             return self._create_huggingface_provider()
            
#         else:
#             self.logger.error(f"Unknown provider: {provider}")
#             return None

#     def _create_openai_provider(self):
#         """إنشاء مزود OpenAI"""
#         try:
#             return OpenAIProvider(
#                 api_key=self.config.OPENAI_API_KEY,
#                 api_url=getattr(self.config, 'OPENAI_API_URL', None),
#                 default_input_max_characters=getattr(self.config, 'INPUT_DAFAULT_MAX_CHARACTERS', 1000),
#                 default_generation_max_output_tokens=getattr(self.config, 'GENERATION_DAFAULT_MAX_TOKENS', 1000),
#                 default_generation_temperature=getattr(self.config, 'GENERATION_DAFAULT_TEMPERATURE', 0.1)
#             )
#         except Exception as e:
#             self.logger.error(f"Failed to create OpenAI provider: {e}")
#             return None

#     def _create_cohere_provider(self):
#         """إنشاء مزود Cohere"""
#         try:
#             return CoHereProvider(
#                 api_key=self.config.COHERE_API_KEY,
#                 default_input_max_characters=getattr(self.config, 'INPUT_DAFAULT_MAX_CHARACTERS', 1000),
#                 default_generation_max_output_tokens=getattr(self.config, 'GENERATION_DAFAULT_MAX_TOKENS', 1000),
#                 default_generation_temperature=getattr(self.config, 'GENERATION_DAFAULT_TEMPERATURE', 0.1)
#             )
#         except Exception as e:
#             self.logger.error(f"Failed to create Cohere provider: {e}")
#             return None

#     def _create_huggingface_provider(self):
#         """إنشاء مزود HuggingFace"""
#         try:
#             model_name = getattr(self.config, 'HF_MODEL_NAME', 'intfloat/multilingual-e5-small')
#             cache_dir = getattr(self.config, 'HF_CACHE_DIR', './models')
            
#             return HuggingFaceProvider(
#                 model_name=model_name,
#                 default_input_max_characters=getattr(self.config, 'INPUT_DAFAULT_MAX_CHARACTERS', 1000),
#                 default_generation_max_output_tokens=getattr(self.config, 'GENERATION_DAFAULT_MAX_TOKENS', 1000),
#                 default_generation_temperature=getattr(self.config, 'GENERATION_DAFAULT_TEMPERATURE', 0.1),
#                 cache_dir=cache_dir
#             )
#         except ImportError:
#             self.logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
#             return None
#         except Exception as e:
#             self.logger.error(f"Failed to create HuggingFace provider: {e}")
#             return None

#     def get_available_providers(self):
#         """إرجاع قائمة المزودين المتاحين"""
#         available = []
        
#         # فحص OpenAI
#         if hasattr(self.config, 'OPENAI_API_KEY') and self.config.OPENAI_API_KEY:
#             available.append({
#                 'name': 'openai',
#                 'type': 'api',
#                 'supports': ['generation', 'embedding'],
#                 'cost': 'paid'
#             })
        
#         # فحص Cohere
#         if hasattr(self.config, 'COHERE_API_KEY') and self.config.COHERE_API_KEY:
#             available.append({
#                 'name': 'cohere',
#                 'type': 'api', 
#                 'supports': ['generation', 'embedding'],
#                 'cost': 'freemium'
#             })
        
#         # فحص HuggingFace
#         try:
#             import sentence_transformers
#             available.append({
#                 'name': 'huggingface',
#                 'type': 'local',
#                 'supports': ['embedding'],
#                 'cost': 'free'
#             })
#         except ImportError:
#             pass
            
#         return available

#     def auto_select_best_provider(self, task_type: str = "embedding"):
#         """اختيار أفضل مزود تلقائياً"""
#         available = self.get_available_providers()
        
#         if task_type == "embedding":
#             # أولوية للـ embedding: HuggingFace > OpenAI > Cohere
#             for provider in ['huggingface', 'openai', 'cohere']:
#                 for available_provider in available:
#                     if (available_provider['name'] == provider and 
#                         'embedding' in available_provider['supports']):
#                         return provider
                        
#         elif task_type == "generation":
#             # أولوية للـ generation: OpenAI > Cohere
#             for provider in ['openai', 'cohere']:
#                 for available_provider in available:
#                     if (available_provider['name'] == provider and 
#                         'generation' in available_provider['supports']):
#                         return provider
        
#         return None