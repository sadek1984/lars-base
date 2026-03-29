from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional, Dict, Any
from pydantic import Field

class Settings(BaseSettings):
    APP_NAME: str
    APP_VERSION: str
    OPENAI_API_KEY: str
    FILE_ALLOWED_TYPES: list
    FILE_MAX_SIZE: int
    FILE_DEFAULT_CHUNK_SIZE: int

    database_url: Optional[str] = None
    data_source_uri: Optional[str] = None  
    data_source_user: Optional[str] = None
    data_source_pass: Optional[str] = None
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None

    GENERATION_BACKEND: str = "COHERE"
    EMBEDDING_BACKEND: str = "COHERE"  # huggingface, openai, cohere

    OPENAI_API_KEY: str = None
    OPENAI_API_URL: str = None
    COHERE_API_KEY: str = None

    # إعدادات HuggingFace 🆕
    # HF_MODEL_NAME: str = "intfloat/multilingual-e5-small"  # النموذج الافتراضي
    # HF_CACHE_DIR: str = "./models"  # مجلد حفظ النماذج

    GENERATION_MODEL_ID_LITERAL: List[str] = None
    GENERATION_MODEL_ID: str = None
    EMBEDDING_MODEL_ID: str = None
    EMBEDDING_MODEL_SIZE: int = None
    INPUT_DAFAULT_MAX_CHARACTERS: int = None
    GENERATION_DAFAULT_MAX_TOKENS: int = None
    GENERATION_DAFAULT_TEMPERATURE: float = None
    GEMINI_API_KEY: str = None
    GEMINI_MODEL: str = Field(default="gemini-1.5-flash")


    VECTOR_DB_BACKEND_LITERAL: List[str] = None
    VECTOR_DB_BACKEND: str
    VECTOR_DB_PATH: str 
    VECTOR_DB_DISTANCE_METHOD: str = None
    VECTOR_DB_PGVEC_INDEX_THRESHOLD: int = 100

    PRIMARY_LANG: str = "en"
    DEFAULT_LANG: str = "en"

    POSTGRES_USERNAME: str 
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_MAIN_DATABASE: str

    sample_code: str
    sample_name: str
    pesticide_name: str
    limits: str
    device_reading: str
    result: str
    source_file: str 
    row_index: int

    MAIN_FOLDER_PATH: str
    MONTHS_IN_ORDER: List[str]

    # --> ADD ALL OF THESE MISSING FIELDS <--
    enable_query_cache: bool = True
    query_cache_ttl: int = 3600
    embedding_cache_size: int = 1000
    min_valid_fields: int = 3
    max_nan_ratio: float = 0.3
    retrieval_top_k_multiplier: int = 2
    min_relevance_score: float = 0.5
    use_reranking: bool = True
    gemini_temperature: float = 0.0
    gemini_max_output_tokens: int = 2048
    gemini_top_k: int = 40
    gemini_top_p: float = 0.95
    excel_skiprows: int = 11
    excel_engine: Optional[str] = None # Or a specific default like 'openpyxl'
    
    # The traceback showed 16 errors, you may need to add the last two
    # if they are in your .env file.
    # Replace with the actual names from your error if they are different.
    some_other_setting: str = "default_value"
    another_missing_setting: int = 123

    enable_retrieval_monitoring: bool = True
    log_retrieval_stats: bool = True



    model_config = SettingsConfigDict(env_file=".env")

def get_settings():
    return Settings()