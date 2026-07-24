"""
core_query_engine.py
====================
محرك استعلامات موحد خالٍ من Streamlit
يمكن استخدامه من:
- التطبيق الرئيسي (ai_assistant.py)
- البوت الصوتي (voice_bot_enhanced.py)

Features:
- Pattern matching for common queries
- LLM fallback for unknown queries
- Egyptian & Saudi Arabic dialect support
"""
import re
import duckdb
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import os
import logging

# ── Centralized mappings (replaces local dictionaries) ──
from modules.mappings import (
    SAMPLE_CORRECTIONS,
    SAMPLE_EN_TO_AR,
    NEIGHBORHOOD_CORRECTIONS,
    PESTICIDE_AR_TO_EN,
    CATEGORY_EN,
    normalize_arabic_query,
    get_pesticide_variants,
    get_pesticide_sql_filter,
)

# Semantic pattern recognizer (optional - graceful fallback if not available)
try:
    from semantic_pattern_recognizer import get_semantic_recognizer
    HAS_SEMANTIC = True
except ImportError:
    HAS_SEMANTIC = False
    get_semantic_recognizer = lambda: None

# Intent-based query router (optional - graceful fallback if not available)
try:
    from modules.intent_router import IntentRouter, Intent, QueryEntities
    HAS_INTENT_ROUTER = True
except ImportError:
    HAS_INTENT_ROUTER = False
    IntentRouter = None
    Intent = None
    QueryEntities = None

# Database path — delegate to data_access so all modules use the same resolution
from modules.data_access import _DUCKDB_PATH as DB_PATH
from modules.prompt_loader import load_prompt

# LLM Configuration
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b-it-qat")



from modules.advanced_handlers import AdvancedHandlersMixin

class CoreQueryEngine(AdvancedHandlersMixin):
    """
    محرك استعلامات مركزي موحد - بدون Streamlit
    Unified Query Engine - Streamlit-free
    
    Supports:
    - All query patterns from ai_assistant.py
    - LLM fallback for unknown queries
    - Dialect normalization (Egyptian + Saudi Arabic)
    """
    
    def __init__(self, db_path: str = None, llm_client=None, enable_llm_fallback: bool = True):
        """
        Initialize the query engine.
        
        Args:
            db_path: Path to DuckDB database
            llm_client: Optional pre-configured LLM client
            enable_llm_fallback: Whether to use LLM for unknown queries
        """
        self.db_path = db_path or str(DB_PATH)
        self.llm_client = llm_client
        self.enable_llm_fallback = enable_llm_fallback
        
        # Initialize LLM if enabled and not provided
        if enable_llm_fallback and llm_client is None:
            self._init_llm()
        
        self._load_mappings()
        self._load_schema_info()
        
        # Initialize semantic pattern recognizer (optional)
        self.semantic_recognizer = get_semantic_recognizer() if HAS_SEMANTIC else None
        if self.semantic_recognizer:
            print("✅ Semantic Pattern Recognizer loaded!")
        else:
            print("ℹ️ Semantic Pattern Recognizer not available, using keyword matching only")
        
        # Initialize intent-based query router (optional)
        if HAS_INTENT_ROUTER:
            self.router = IntentRouter(dialect_synonyms=self.dialect_synonyms)
            print("✅ Intent Router loaded!")
        else:
            self.router = None
            print("ℹ️ Intent Router not available, using pattern matching only")
    
    def _init_llm(self):
        """Initialize LLM client for fallback queries"""
        try:
            from ollama import Client
            self.llm_client = Client(host=OLLAMA_URL)
            # Test connection
            self.llm_client.list()
        except Exception as e:
            print(f"⚠️ LLM initialization failed: {e}")
            self.llm_client = None
    
    def _load_schema_info(self):
        """Load database schema for LLM context"""
        try:
            con = self._get_connection()
            # Get column names from chemistry_tidy
            cols_df = con.execute("DESCRIBE chemistry_tidy").df()
            self.schema_columns = cols_df['column_name'].tolist()
            
            # Get sample types
            sample_types_df = con.execute('''
                SELECT DISTINCT "اسم العينة" FROM chemistry_tidy 
                WHERE "اسم العينة" IS NOT NULL LIMIT 50
            ''').df()
            self.available_sample_types = sample_types_df['اسم العينة'].tolist()
            
            # Get neighborhoods
            neighborhoods_df = con.execute('''
                SELECT DISTINCT "الحى" FROM chemistry_tidy 
                WHERE "الحى" IS NOT NULL LIMIT 50
            ''').df()
            self.available_neighborhoods = neighborhoods_df['الحى'].tolist()
            
            con.close()
        except Exception as e:
            print(f"⚠️ Schema loading failed: {e}")
            self.schema_columns = []
            self.available_sample_types = []
            self.available_neighborhoods = []
    
    def _load_mappings(self):
        """Load query mappings.

        Dialect synonyms and action/limit keywords are defined here
        because they are specific to the query engine. All entity
        dictionaries (samples, pesticides, neighborhoods) come from
        the centralized ``modules.mappings`` module.
        """
        # Dialect Synonyms (KEEP — engine-specific)
        self.dialect_synonyms = {
            'give me': 'show',
            'show me': 'show',
            'list': 'show',
            'display': 'show',
            'get': 'show',
            'find': 'search',
            'look for': 'search',
            'locate': 'search',
            'how many': 'count',
            'number of': 'count',
            'above limit': 'exceeding',
            'over limit': 'exceeding',
            'below limit': 'within limit',
            'within': 'within limit',
            'non-compliant': 'Non-Compliant',
            'non compliant': 'Non-Compliant',
            'failed': 'Non-Compliant',
            'failing': 'Non-Compliant',
            'compliant': 'Compliant',
            'passed': 'Compliant',
            'each separately': 'individually',
            'for each': 'individually',
        }

        # Action keywords (KEEP — engine-specific)
        self.action_keywords = {
            'search': ['find', 'search', 'locate'],
            'show': ['show', 'display', 'list'],
            'give': ['give', 'provide'],
            'want': ['want', 'need'],
            'count': ['count', 'how many', 'number'],
            'what': ['what', 'which'],
        }

        # Limit/Compliance keywords (KEEP — engine-specific)
        self.above_limit_keywords = [
            'above limit', 'exceeding', 'over limit', 'violation',
            'non-compliant', 'non compliant', 'noncompliant', 'failed', 'failing', 'exceed',
        ]
        self.below_limit_keywords = [
            'below limit', 'within limit', 'compliant', 'passing', 'safe', 'passed',
        ]

        # Statistics keywords (KEEP — engine-specific)
        self.stats_keywords = {
            'max': ['max', 'maximum', 'highest'],
            'min': ['min', 'minimum', 'lowest'],
            'avg': ['average', 'mean', 'avg'],
            'median': ['median'],
            'range': ['range', 'spread'],
            'count': ['count', 'frequency'],
            'unique': ['unique', 'distinct'],
        }

        # Entity dictionaries — FROM CENTRALIZED MAPPINGS
        self.sample_types = SAMPLE_CORRECTIONS
        self.english_sample_types = SAMPLE_EN_TO_AR
        self.neighborhood_patterns = NEIGHBORHOOD_CORRECTIONS
        self.arabic_pesticide_map = PESTICIDE_AR_TO_EN
    
    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Return a read-only DuckDB connection.

        Raises RuntimeError with a user-readable message if the database
        file is missing or the connection fails, instead of propagating a
        cryptic DuckDB exception.
        """
        db_path = Path(self.db_path)
        if not db_path.exists():
            raise RuntimeError(
                f"Database file not found: {db_path}\n"
                "Upload your data via the Data Management page to continue."
            )
        try:
            return duckdb.connect(str(db_path), read_only=True)
        except Exception as exc:
            raise RuntimeError(
                f"Could not open database '{db_path.name}': {exc}"
            ) from exc
    

    def _build_sample_filter(self, samples: list) -> str:
        """
        Build SQL WHERE clause for "اسم العينة".

        YOUR DATABASE stores ARABIC names ('طماطم', 'خيار', ...).
        _detect_sample_types() returns English canonical values ('Tomato').
        This method converts them back to Arabic substrings for the LIKE.

        Falls back to English substring search too, so the filter works
        even if the DB is later migrated to English names.
        """
        if not samples:
            return "1=1"

        # Build reverse map: English canonical → list of Arabic query keys
        # e.g. 'Tomato' → ['طماطم', 'طماطم شيري']  (only the base match matters)
        from modules.mappings import SAMPLE_CORRECTIONS

        en_to_ar: dict = {}
        for ar_key, en_val in SAMPLE_CORRECTIONS.items():
            en_to_ar.setdefault(en_val, []).append(ar_key)

        conditions = []
        for s in samples:
            # ── A: Arabic LIKE (what your DB actually has) ──────────────
            arabic_variants = en_to_ar.get(s, [])
            # Use TRIM() on the column side to handle accidental spaces
            for ar in arabic_variants:
                conditions.append(
                    f"TRIM(\"اسم العينة\") LIKE '%{ar}%'"
                )

            # ── B: English LIKE fallback (future-proof) ─────────────────
            conditions.append(f"\"اسم العينة\" LIKE '%{s}%'")

            # ── C: Category column (نوع العينة) ─────────────────────────
            conditions.append(f"\"نوع العينة\" LIKE '%{s}%'")

        return f"({' OR '.join(conditions)})"


    def _normalize_query(self, query: str) -> str:
        """Normalize query: apply dialect synonyms for English."""
        query_lower = query.lower().strip()
        for dialect, standard in self.dialect_synonyms.items():
            query_lower = query_lower.replace(dialect, standard)
        return query_lower
    
    def _detect_sample_types(self, query: str) -> List[str]:
        """
        Detect sample types from query.
        DB stores ENGLISH names in "اسم العينة" (e.g. 'Tomato', 'Pistachios').
        Returns English DB values directly.
        """
        detected = []
        query_lower = query.lower()
        remaining_lower = query_lower  # track consumed text to avoid sub-matches

        # Sort by length descending — match "cherry tomato" before "tomato"
        for key in sorted(self.sample_types.keys(), key=len, reverse=True):
            db_value = self.sample_types[key]
            if key in remaining_lower:
                detected.append(db_value)
                # Remove matched key to prevent sub-matches
                remaining_lower = remaining_lower.replace(key, " " * len(key), 1)

        # Category expansion — uses English "نوع العينة" values from DB
        # CATEGORY_EN imported from modules.mappings — single source of truth
        if not detected:
            matched_cat = None
            for kw, cat in CATEGORY_EN.items():
                if kw in query_lower:
                    matched_cat = cat
                    break
            if matched_cat:
                # Return a special sentinel so process() knows it's a category
                detected = [f"__cat__{matched_cat}"]

        return list(set(detected))
    
    def _detect_neighborhoods(self, query: str) -> List[str]:
        """
        Detect neighborhood names. DB stores Arabic values (الإسكان, الريان etc.)
        Supports English transliterations and Arabic matching.
        """
        detected = []
        query_lower = query.lower()

        # Sort by length descending
        for key in sorted(self.neighborhood_patterns.keys(), key=len, reverse=True):
            db_val = self.neighborhood_patterns[key]
            # Arabic strings are checked against exact query, English against lower
            has_arabic = any('\u0600' <= c <= '\u06ff' for c in key)
            if has_arabic:
                if key in query:
                    detected.append(db_val)
            else:
                if key in query_lower:
                    detected.append(db_val)

        return list(set(detected))
    
    def _detect_pesticide(self, query: str) -> Optional[str]:
        """كشف المبيد (English only detection)"""
        query_lower = query.lower()
        
        # 1. Search English values directly
        # Sort values by length descending to match longer names first
        unique_en_pesticides = sorted(list(set(self.arabic_pesticide_map.values())), key=len, reverse=True)
        for en_name in unique_en_pesticides:
            if en_name.lower() in query_lower:
                return en_name
                
        # 2. Add common ones that might be missing from AR_TO_EN keys
        pesticide_names_common = [
            'bifenthrin', 'chlorpyrifos', 'imidacloprid', 'deltamethrin', 'cypermethrin',
            'abamectin', 'acetamiprid', 'thiamethoxam', 'carbendazim', 'buprofezin',
            'profenofos', 'metalaxyl', 'fipronil', 'emamectin', 'pyriproxyfen',
            'azoxystrobin', 'difenoconazole', 'lambda-cyhalothrin', 'spinosad'
        ]
        for en_name in pesticide_names_common:
            if en_name in query_lower:
                return en_name
                
        return None
    
    def _handle_facility_search(self, query: str) -> Tuple[str, pd.DataFrame]:
        """البحث عن العينات في منشأة معينة"""
        con = self._get_connection()
        
        # استخراج اسم المنشأة من الاستعلام
        # إزالة الكلمات المفتاحية الشائعة
        facility_keywords = ['ابحث', 'عن', 'العينات', 'في', 'منشأة', 'منشاة', 'مصنع', 'مطعم', 
                            'محل', 'متجر', 'عينات', 'بحث', 'search', 'facility', 'samples']
        
        words = query.split()
        facility_name_parts = []
        
        for word in words:
            if word.lower() not in facility_keywords and len(word) > 2:
                facility_name_parts.append(word)
        
        facility_name = ' '.join(facility_name_parts)
        
        if not facility_name:
            return "⚠️ لم أتمكن من استخراج اسم المنشأة من السؤال. يرجى تحديد اسم المنشأة.", pd.DataFrame()
        
        # البحث في قاعدة البيانات
        sql = f"""
        SELECT 
            "كود العينة"  AS sample_code,
            "اسم المنشاة" AS facility_name,
            "اسم العينة"  AS sample_type,
            "التاريخ"     AS date,
            "الحى"        AS neighborhood,
            pesticide_name AS pesticide,
            concentration  AS concentration,
            limit_value    AS mrl,
            CASE WHEN is_above_limit = 1 THEN 'Above limit' ELSE 'Within limit' END AS status
        FROM chemistry_tidy
        WHERE is_detected = 1
        AND "اسم المنشاة" LIKE '%{facility_name}%'
        ORDER BY "التاريخ" DESC
        LIMIT 50
        """
        
        df = con.execute(sql).df()
        con.close()
        
        if not df.empty:
            unique_samples = df['sample_code'].nunique() if 'sample_code' in df.columns else len(df)
            above_limit    = len(df[df['status'] == 'Above limit']) if 'status' in df.columns else 0
            
            response = f"🏭 **Facility search results: {facility_name}**\n\n"
            response += f"✅ Unique samples: **{unique_samples}**\n"
            response += f"🔬 Total detections: **{len(df)}**\n"
            response += f"🔴 Above limit: **{above_limit}**\n"
            response += f"🟢 Within limit: **{len(df) - above_limit}**\n\n"
            response += df.to_markdown(index=False)
        else:
            response = f"⚠️ No samples found in a facility matching '{facility_name}'"
        
        return response, df
    
    def _handle_comprehensive_neighborhood(self, query: str, detected_samples: List[str], 
                                          detected_neighborhoods: List[str]) -> Tuple[str, pd.DataFrame]:
        """تحليل شامل للعينات في حي معين مع عرض الأنواع والعدد وفوق/تحت الحد"""
        con = self._get_connection()
        
        # Build neighborhood filter (mandatory)
        hood_conditions = []
        for n in detected_neighborhoods:
            variants = [n]
            if 'ا' in n:
                variants.append(n.replace('ا', 'إ'))
                variants.append(n.replace('ا', 'أ'))
            if 'إ' in n:
                variants.append(n.replace('إ', 'ا'))
            if 'أ' in n:
                variants.append(n.replace('أ', 'ا'))
            for v in set(variants):
                hood_conditions.append(f"\"الحى\" LIKE '%{v}%'")
        neighborhood_filter = f"AND ({' OR '.join(hood_conditions)})"
        
        # Build category filter based on keywords — DB stores English in "نوع العينة"
        category_filter = ""
        category_name = "العينات"
        
        if 'توابل' in query or 'التوابل' in query or 'بهارات' in query or 'spice' in query.lower():
            category_filter = "AND \"نوع العينة\" = 'Spices'"
            category_name = "التوابل (Spices)"
        elif 'خضار' in query or 'الخضار' in query or 'خضروات' in query or 'vegetable' in query.lower():
            category_filter = "AND \"نوع العينة\" = 'Vegetables'"
            category_name = "الخضار (Vegetables)"
        elif 'فاكهة' in query or 'فواكه' in query or 'fruit' in query.lower():
            category_filter = "AND \"نوع العينة\" = 'Fruits'"
            category_name = "الفواكه (Fruits)"
        elif 'ورقيات' in query or 'الورقيات' in query or 'leafy' in query.lower():
            category_filter = "AND \"نوع العينة\" = 'Leafy Greens'"
            category_name = "الورقيات (Leafy Greens)"
        elif 'مكسرات' in query or 'المكسرات' in query or 'nut' in query.lower():
            category_filter = "AND \"نوع العينة\" = 'Nuts'"
            category_name = "المكسرات (Nuts)"
        elif 'حبوب' in query or 'الحبوب' in query or 'grain' in query.lower():
            category_filter = "AND \"نوع العينة\" = 'Grains'"
            category_name = "الحبوب (Grains)"
        elif detected_samples:
            # Specific samples requested — use English DB values from _detect_sample_types
            conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in detected_samples]
            category_filter = f"AND ({' OR '.join(conditions)})"
            category_name = " + ".join(detected_samples)
        
        hood_display = " + ".join(detected_neighborhoods)
        logging.info(f"📊 تحليل شامل لـ {category_name} في حي {hood_display}")
        
        # Comprehensive SQL
        sql = f"""
        WITH sample_status AS (
            SELECT 
                "كود العينة" as sample_code,
                "اسم العينة" as sample_name,
                "الحى" as neighborhood,
                MAX(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as has_violation,
                MAX(CASE WHEN is_detected = 1 THEN 1 ELSE 0 END) as has_detection,
                COUNT(CASE WHEN is_detected = 1 THEN 1 END) as pesticide_count
            FROM chemistry_tidy
            WHERE 1=1
            {neighborhood_filter}
            {category_filter}
            GROUP BY "كود العينة", "اسم العينة", "الحى"
        )
        SELECT 
            neighborhood,
            sample_name AS sample_type,
            COUNT(*) AS total_count,
            SUM(has_violation) AS above_limit,
            SUM(CASE WHEN has_violation = 0 THEN 1 ELSE 0 END) AS below_limit,
            SUM(CASE WHEN has_detection = 0 THEN 1 ELSE 0 END) AS pesticide_free
        FROM sample_status
        GROUP BY neighborhood, sample_name
        ORDER BY neighborhood, total_count DESC
        """
        
        df = con.execute(sql).df()
        con.close()

        if not df.empty:
            response = f"�� **Comprehensive Analysis — {category_name} in {hood_display}**\n\n"
            for hood, group in df.groupby('neighborhood'):
                total       = int(group['total_count'].sum())
                total_above = int(group['above_limit'].sum())
                total_below = int(group['below_limit'].sum())
                total_clean = int(group['pesticide_free'].sum())

                response += f"### 📍 {hood}\n"
                response += f"✅ **Total samples:** {total}\n"
                response += f"🔴 **Above limit:** {total_above} (contain at least one violating pesticide)\n"
                response += f"🟢 **Below limit:** {total_below} (compliant)\n"
                response += f"   • of which **{total_clean}** are completely pesticide-free\n"
                response += f"   • and **{total_below - total_clean}** contain pesticides within allowed limits\n\n"
                response += group.drop(columns='neighborhood').to_markdown(index=False)
                response += "\n\n"

            return response, df
        else:
            response = f"⚠️ No {category_name} samples found in {hood_display}"
            return response, pd.DataFrame()
    
    def _route_by_semantic_pattern(self, pattern_type: str, query: str, query_normalized: str,
                                   query_lower: str, detected_samples: List[str],
                                   detected_neighborhoods: List[str], 
                                   detected_pesticide: Optional[str]) -> Optional[Tuple[str, pd.DataFrame]]:
        """
        Route query to appropriate handler based on semantic pattern type.
        Returns None if pattern cannot be handled (falls back to keyword matching).
        """
        try:
            # Check for 'كل على حده' (show separately)
            show_separately = any(phrase in query for phrase in ['كل علي حده', 'كل على حده', 'بشكل منفصل'])
            
            # Determine above/below limit from query
            is_above = None  # None = both
            above_keywords = ['فوق', 'above', 'exceed', 'تجاوز', 'غير مطابق', 'راسب', 'مخالف', 'فاشل']
            below_keywords = ['تحت', 'below', 'within', 'مطابق', 'ناجح', 'سليم']
            
            if any(kw in query for kw in above_keywords) and not any(kw in query_lower for kw in ['مطابق', 'تحت']):
                is_above = True
            elif any(kw in query for kw in below_keywords) and not any(kw in query for kw in above_keywords):
                is_above = False
            
            # Route based on pattern type
            if pattern_type == 'count_above_limit':
                # _handle_count_samples_limit(samples: List, neighborhoods: List, is_above: bool)
                samples = detected_samples if detected_samples else ['']
                return self._handle_count_samples_limit(samples, detected_neighborhoods, True)
            
            elif pattern_type == 'count_below_limit':
                samples = detected_samples if detected_samples else ['']
                return self._handle_count_samples_limit(samples, detected_neighborhoods, False)
            
            elif pattern_type == 'simple_count':
                if detected_samples:
                    # Return both above and below (is_above=None means show both)
                    return self._handle_count_samples_limit(detected_samples, detected_neighborhoods, None)
            
            elif pattern_type == 'comprehensive_analysis':
                if detected_samples:
                    return self._handle_comprehensive_analysis(detected_samples[0])
            
            elif pattern_type == 'pesticide_specific':
                if detected_pesticide and detected_samples:
                    # Check if it actually contains limit/compliance keywords (misclassified pattern)
                    limit_keywords = ['فوق', 'الحد', 'تجاوز', 'مخالف', 'غير مطابق', 'راسب', 'above', 'limit']
                    if any(kw in query for kw in limit_keywords):
                        # Redirect to _handle_sample_pesticide_limit logic
                        non_compliant_keywords = ['غير مطابق', 'الغير مطابقة', 'راسب', 'مخالف', 'non-compliant']
                        is_non_compliant = any(kw in query for kw in non_compliant_keywords)
                        
                        if is_non_compliant:
                            limit_filter = "AND sample_result = 'Non-Compliant'"
                            limit_desc = "غير مطابقة"
                        else:
                            limit_filter = None
                            limit_desc = None
                            
                        return self._handle_sample_pesticide_limit(
                            detected_samples, detected_pesticide, True,
                            limit_filter=limit_filter, limit_desc=limit_desc
                        )
                    
                    return self._handle_find_pesticide_in_sample(detected_pesticide, detected_samples)
            
            elif pattern_type == 'pesticide_limit_specific':
                if detected_pesticide and detected_samples:
                    # Check for non-compliant keywords
                    # Check for non-compliant keywords vs above limit
                    non_compliant_keywords = ['غير مطابق', 'الغير مطابقة', 'راسب', 'مخالف', 'non-compliant']
                    is_non_compliant = any(kw in query for kw in non_compliant_keywords)
                    
                    if is_non_compliant:
                        # Use sample_result logic — DB stores 'Non-Compliant'
                        limit_filter = "AND sample_result = 'Non-Compliant'"
                        limit_desc = "غير مطابقة"
                        is_above = True
                    else:
                        # Default to above limit logic (is_above=True)
                        limit_filter = None
                        limit_desc = None
                        is_above = True
                        
                    return self._handle_sample_pesticide_limit(
                        detected_samples, detected_pesticide, is_above,
                        limit_filter=limit_filter, limit_desc=limit_desc
                    )
            
            elif pattern_type == 'list_pesticides':
                if detected_samples:
                    return self._handle_list_pesticides(detected_samples)
            
            elif pattern_type == 'neighborhood_pesticides':
                if detected_neighborhoods:
                    return self._handle_neighborhood_pesticides(detected_neighborhoods, show_separately)
            
            elif pattern_type == 'samples_with_n_pesticides':
                # Extract number from query
                import re
                numbers = re.findall(r'\d+', query)
                if numbers:
                    n_pesticides = int(numbers[0])
                    if 1 <= n_pesticides <= 50:
                        return self._handle_n_pesticides(n_pesticides, detected_samples)
            
            elif pattern_type == 'statistics':
                if detected_samples:
                    return self._handle_statistics(detected_samples[0], query)
            
            elif pattern_type == 'comprehensive_neighborhood_analysis':
                # This pattern handles queries like "ما هي انواع التوابل في حي الاسكان وما عددها وفوق/تحت الحد"
                # It requires neighborhood detection and will analyze all sample types in that neighborhood
                if detected_neighborhoods:
                    # Call the comprehensive neighborhood handler directly
                    # (it's implemented starting at line 603 in process())
                    return self._handle_comprehensive_neighborhood(query, detected_samples, detected_neighborhoods)
            
            elif pattern_type == 'facility_search':
                # Extract facility name from query
                return self._handle_facility_search(query)
            
            # Pattern recognized but couldn't be handled - fall back to keyword matching
            return None
            
        except Exception as e:
            logging.warning(f"Error in semantic routing: {e}")
            return None
    
    def _dispatch_by_intent(self, intent, entities) -> Optional[Tuple[str, Optional[pd.DataFrame]]]:
        """Route an intent + entities to the correct handler.
        
        Args:
            intent: Intent enum from IntentRouter
            entities: QueryEntities object with extracted information
        
        Returns:
            (response_text, dataframe) tuple or None if intent is UNKNOWN
        
        The handlers are the EXISTING methods — no changes needed to them.
        This dispatcher just translates intent+entities into method calls.
        """
        if not HAS_INTENT_ROUTER or intent is None:
            return None
        
        try:
            query = entities.normalized_query
            
            # ── Neighborhood + Category analysis ──
            if intent == Intent.COMPREHENSIVE_NEIGHBORHOOD or intent == Intent.LIST_TYPES_IN_NEIGHBORHOOD:
                return self._handle_comprehensive_neighborhood(
                    query, entities.samples, entities.neighborhoods
                )
            
            if intent == Intent.NEIGHBORHOOD_PESTICIDES:
                return self._handle_neighborhood_pesticides(
                    entities.neighborhoods, entities.wants_separately
                )
            
            if intent == Intent.NEIGHBORHOOD_RANKING:
                return self._handle_neighborhood_ranking()
            
            # ── N pesticides ──
            if intent == Intent.COUNT_N_PESTICIDES and entities.n_pesticides:
                if len(entities.n_pesticides) > 1 and entities.wants_separately:
                    return self._handle_multiple_n_pesticides(entities.n_pesticides, entities.samples)
                return self._handle_n_pesticides(entities.n_pesticides[-1], entities.samples)
            
            # ── Pesticide queries ──
            if intent == Intent.FIND_PESTICIDE_IN_SAMPLE and entities.pesticide and entities.samples:
                if entities.wants_limit_breakdown:
                    return self._handle_sample_pesticide_limit(
                        entities.samples, entities.pesticide, 
                        entities.is_above_limit if entities.is_above_limit is not None else True
                    )
                return self._handle_find_pesticide_in_sample(entities.pesticide, entities.samples)
            
            if intent == Intent.FIND_PESTICIDE_ALL and entities.pesticide:
                return self._handle_find_pesticide_all(entities.pesticide)
            
            if intent == Intent.LIST_PESTICIDES_IN_SAMPLE and entities.samples:
                return self._handle_list_pesticides(entities.samples)
            
            if intent == Intent.PESTICIDE_STATISTICS and entities.pesticide:
                return self._handle_pesticide_stats(
                    entities.pesticide, entities.samples, entities.stat_types
                )
            
            # ── Sample counting ──
            if intent == Intent.COUNT_SAMPLES_LIMIT and entities.samples:
                return self._handle_count_samples_limit(
                    entities.samples, entities.neighborhoods, entities.is_above_limit
                )
            
            if intent == Intent.COUNT_SAMPLES_SIMPLE and entities.samples:
                return self._handle_simple_sample_count(entities.samples, entities.neighborhoods)
            
            if intent == Intent.UNIQUE_COUNT and entities.samples:
                return self._handle_unique_samples_count(entities.samples, entities.neighborhoods)
            
            # ── Other ──
            if intent == Intent.COMPREHENSIVE_ANALYSIS and entities.samples:
                return self._handle_comprehensive_analysis(entities.samples)
            
            if intent == Intent.FACILITY_SEARCH:
                return self._handle_facility_search(query)
            
            if intent == Intent.RECIPIENT_SEARCH:
                return self._handle_facility_search(query)  # Same handler for now
        
        except Exception as ex:
            logging.warning(f"Intent dispatch error for {intent}: {ex}")
        
        return None  # UNKNOWN → falls through to patterns/LLM
    
    def _extract_context(self, query: str) -> dict:
        """
        Normalize the query and detect all entities (samples, neighborhoods, pesticide).

        Strips category sentinels (__cat__<key>) from detected_samples so that
        standard handlers always receive concrete sample names. The sentinel is
        preserved separately as 'category_key' for handlers that need it (e.g.
        Pattern 1B / violations-threshold).

        Returns a context dict consumed by process() routing tiers.
        """
        query_normalized = self._normalize_query(query)
        query_lower = query_normalized.lower()

        detected_samples_raw = self._detect_sample_types(query)
        detected_neighborhoods = self._detect_neighborhoods(query)
        detected_pesticide = self._detect_pesticide(query)

        category_key = None
        detected_samples = []
        for s in detected_samples_raw:
            if s.startswith("__cat__"):
                category_key = s.replace("__cat__", "")
            else:
                detected_samples.append(s)

        return {
            'query': query,
            'query_normalized': query_normalized,
            'query_lower': query_lower,
            'detected_samples': detected_samples,
            'detected_samples_raw': detected_samples_raw,
            'detected_neighborhoods': detected_neighborhoods,
            'detected_pesticide': detected_pesticide,
            'category_key': category_key,
        }

    def process(self, query: str) -> Tuple[str, Optional[pd.DataFrame]]:
        """
        Process a query and return (response_text, DataFrame | None).

        Three-tier routing, in priority order:
          1. Semantic pattern recognition  — embedding-based, confidence ≥ 0.75
          2. Intent-based routing          — entity extraction + intent classifier
          3. Keyword pattern cascade       — _dispatch_keyword_patterns()
        """
        ctx = self._extract_context(query)
        query_normalized = ctx['query_normalized']
        query_lower      = ctx['query_lower']
        detected_samples      = ctx['detected_samples']
        detected_neighborhoods = ctx['detected_neighborhoods']
        detected_pesticide    = ctx['detected_pesticide']

        # ── Tier 0: Explicit compliance-status override ──────────────────────
        # "غير مطابقة" / "مطابقة" + neighborhood(s) must route straight to the
        # compliance handler — bypass semantic/intent tiers, which tend to
        # misclassify these as generic "comprehensive neighborhood" queries.
        non_compliant_ar_kws = ['غير مطابقة', 'الغير مطابقة', 'غير المطابقة']
        compliant_ar_kws = ['مطابقة']
        is_non_compliant_ar = any(kw in query for kw in non_compliant_ar_kws)
        is_compliant_ar = (not is_non_compliant_ar) and any(kw in query for kw in compliant_ar_kws)

        if (is_non_compliant_ar or is_compliant_ar) and detected_neighborhoods:
            return self._handle_count_samples_compliance(
                detected_samples, detected_neighborhoods, is_non_compliant_ar
            )

        # ── Tier 1: Semantic pattern recognition ──────────────────────────────
        if self.semantic_recognizer:
            semantic_result = self.semantic_recognizer.recognize(query)
            if semantic_result and semantic_result['confidence'] >= 0.75:
                pattern_type = semantic_result['pattern_type']
                logging.debug(f"Semantic match: {pattern_type} ({semantic_result['confidence']:.2f})")
                result = self._route_by_semantic_pattern(
                    pattern_type, query, query_normalized, query_lower,
                    detected_samples, detected_neighborhoods, detected_pesticide
                )
                if result is not None:
                    return result

        # ── Tier 2: Intent-based routing ──────────────────────────────────────
        if self.router:
            intent, entities = self.router.analyze(query)
            if intent != Intent.UNKNOWN:
                logging.info(
                    f"🎯 Intent: {intent.name} | samples={entities.samples} "
                    f"neighborhoods={entities.neighborhoods} category={entities.category} "
                    f"pesticide={entities.pesticide}"
                )
                result = self._dispatch_by_intent(intent, entities)
                if result is not None:
                    return result

        # ── Tier 3: Keyword pattern cascade ───────────────────────────────────
        try:
            result = self._dispatch_keyword_patterns(ctx)
        except RuntimeError as db_err:
            # DB missing or corrupt — show a clear message instead of a stack trace
            logging.error(f"DB connection error during query: {db_err}")
            return str(db_err), None
        if result is not None:
            return result

        return self._handle_unknown_query(query), None

    def _dispatch_keyword_patterns(
        self, ctx: dict
    ) -> Optional[Tuple[str, Optional[pd.DataFrame]]]:
        """
        Tier 3: Keyword-based pattern matching cascade.

        Checks patterns 0–14 in priority order and returns the first match, or
        None to signal that no pattern matched (process() falls back to
        _handle_unknown_query).
        """
        query              = ctx['query']
        query_normalized   = ctx['query_normalized']
        query_lower        = ctx['query_lower']
        detected_samples      = ctx['detected_samples']
        detected_samples_raw  = ctx['detected_samples_raw']
        detected_neighborhoods = ctx['detected_neighborhoods']
        detected_pesticide    = ctx['detected_pesticide']
        _detected_category_key = ctx['category_key']

        # Pattern 0: Comprehensive neighborhood + sample type analysis
        # "what are the types of spices in al_iskan and how many above/below limit"
        # This includes samples with NO pesticides detected (MUST BE FIRST)
        category_keywords = ['types', 'what are']
        limit_keywords = ['above', 'below', 'limit']
        
        # Check if it's a comprehensive query asking about types + counts + limits + neighborhood
        is_comprehensive_hood_query = (
            any(kw in query_lower for kw in category_keywords) and 
            detected_neighborhoods and
            (any(kw in query_lower for kw in limit_keywords) or 'count' in query_lower)
        )
        
        if is_comprehensive_hood_query:
            return self._handle_comprehensive_neighborhood(query, detected_samples, detected_neighborhoods)
        
        # Pattern 0B: Category/types in neighborhood (WITHOUT limit keywords)
        # "what are the types of spices in al_iskan"
        # This catches queries that Pattern 0 misses because they
        # don't mention limits. We route to the SAME handler — it
        # already shows types + counts + limits in its output.
        category_names = ['spices', 'vegetables', 'fruits', 'greens', 'nuts', 'grains', 'dates']
        has_category = any(cat in query_lower for cat in category_names)
        has_type_question = any(kw in query_lower for kw in category_keywords)
        
        if (has_category or (has_type_question and detected_samples)) and detected_neighborhoods:
            return self._handle_comprehensive_neighborhood(query, detected_samples, detected_neighborhoods)
        
        # Continue with other patterns if not comprehensive
        # Pattern 1: Samples with N pesticides (supports multiple counts)
        pesticide_count_keywords = ['pesticide', 'pesticides']
        zero_pesticide_keywords = ['zero pesticide', 'clean', 'free of pesticides', 'no pesticide']
        has_zero_request = any(kw in query_lower for kw in zero_pesticide_keywords)
        
        if any(kw in query_lower for kw in pesticide_count_keywords) or has_zero_request:
            # Extract all numbers from the query
            all_numbers = re.findall(r'(\d+)', query_normalized)
            
            if has_zero_request and '0' not in all_numbers:
                all_numbers.insert(0, '0')
            
            if all_numbers:
                is_multiple = any(kw in query_lower for kw in ['each', 'separately', 'individually'])
                has_multiple_with_and = len(all_numbers) > 1 and 'and' in query_lower
                
                if (is_multiple or has_multiple_with_and) and len(all_numbers) > 1:
                    pesticide_counts = [int(n) for n in all_numbers if int(n) <= 50]
                    if pesticide_counts:
                        return self._handle_multiple_n_pesticides(pesticide_counts, detected_samples)
                else:
                    n_pesticides = int(all_numbers[-1])
                    if 0 <= n_pesticides <= 50:
                        return self._handle_n_pesticides(n_pesticides, detected_samples)
        
        # Pattern 1B: Violations threshold — "find vegetables with more than 10 violations"
        # Matches: category/sample + (more than | over | above) + number + violation
        violation_threshold_kws_en = [
            'more than', 'over', 'greater than', 'above', 'at least', 'exceeding',
        ]
        violation_kws = ['violation', 'violations']

        has_threshold_kw = any(kw in query_lower for kw in violation_threshold_kws_en)
        has_violation_kw = any(kw in query_lower for kw in violation_kws)

        # Extract numeric threshold
        threshold_numbers = re.findall(r'\d+', query_normalized)

        if has_threshold_kw and has_violation_kw and threshold_numbers:
            threshold = int(threshold_numbers[0])
            return self._handle_violations_threshold(
                detected_samples, detected_neighborhoods, threshold, _detected_category_key
            )


        # Pattern 2: Count samples above/below limit (pesticide concentration)
        # "how many tomato samples exceed limits"
        # This checks if ANY pesticide in the sample exceeds its limit
        count_phrases = ['count', 'how many', 'number of']
        # Expanded keywords for ABOVE LIMIT (non-compliant/failing)
        above_limit_phrases = [
            'more than limit', 'exceeding', 'above limit', 'over limit',
            'reading more', 'exceed', 'failing', 'violated', 'violation', 'non-compliant'
        ]
        # Expanded keywords for BELOW LIMIT (compliant/passing)
        below_limit_phrases = [
            'below limit', 'under limit', 'within limit', 
            'compliant', 'passing', 'safe'
        ]
        
        is_count_query = any(phrase in query_lower for phrase in count_phrases)
        is_above_limit = any(phrase in query_lower for phrase in above_limit_phrases)
        is_below_limit = any(phrase in query_lower for phrase in below_limit_phrases)
        
        # IMPORTANT DISTINCTION:
        # - "Non-Compliant" = sample_result (chemist's final decision)
        # - is_above_limit = True (technical exceedance)
        # These are DIFFERENT! A sample can be above limit but still compliant.
        
        # Keywords for SAMPLE RESULT (chemist decision)
        non_compliant_result_keywords = [
            'non-compliant', 'non compliant', 'failed'
        ]
        compliant_result_keywords_for_pesticide = [
            'compliant', 'passed'
        ]
        
        # Check if asking about compliance (sample_result) vs limit (is_above_limit)
        is_non_compliant_query = any(kw in query_lower for kw in non_compliant_result_keywords)
        # Only consider compliant query if no limit keywords are present
        is_compliant_query = (any(kw in query_lower for kw in compliant_result_keywords_for_pesticide) 
                              and not is_non_compliant_query
                              and not is_above_limit
                              and not is_below_limit)
        use_sample_result = is_non_compliant_query or is_compliant_query
        
        # Check for explicit "both" request (above and below limit)
        explicit_both = ('above limit' in query_lower and 'below limit' in query_lower)
        explicit_both = explicit_both and not is_non_compliant_query
        
        if is_count_query and detected_samples and detected_pesticide and (is_above_limit or is_below_limit or use_sample_result):
             # This is a specific query: Sample + Pesticide + Limit/Compliance
             if use_sample_result:
                 if is_non_compliant_query:
                     limit_filter = "AND sample_result = 'Non-Compliant'"
                     limit_desc = "Non-Compliant"
                 else:
                     limit_filter = "AND sample_result = 'Compliant'"
                     limit_desc = "Compliant"
                 return self._handle_sample_pesticide_limit(detected_samples, detected_pesticide, is_above_limit, 
                                                            limit_filter=limit_filter, limit_desc=limit_desc)
             elif explicit_both:
                 return self._handle_sample_pesticide_limit(detected_samples, detected_pesticide, is_above_limit, both=True)
             else:
                 return self._handle_sample_pesticide_limit(detected_samples, detected_pesticide, is_above_limit)

        if is_count_query and detected_samples and (is_above_limit or is_below_limit):
            return self._handle_count_samples_limit(detected_samples, detected_neighborhoods, is_above_limit)
        
        # Pattern 2B: Count compliant/non-compliant samples (sample_result)
        # "how many non-compliant cucumber samples"
        # This uses the official sample_result column, NOT pesticide limits
        compliant_keywords = ['compliant', 'passed']
        non_compliant_keywords = ['non-compliant', 'non compliant', 'failed']
        
        # Check if asking about compliance status (not limit)
        is_non_compliant_query = any(kw in query_lower for kw in non_compliant_keywords)
        is_compliant_query = any(kw in query_lower for kw in compliant_keywords) and not is_non_compliant_query
        
        if detected_samples and (is_non_compliant_query or is_compliant_query):
            # Check it's not a limit query
            if not is_above_limit and not is_below_limit:
                return self._handle_count_samples_compliance(detected_samples, detected_neighborhoods, 
                                                              is_non_compliant_query)
        
        # Pattern 3: List pesticides in sample type
        # "what are the pesticides in tomatoes"
        pesticide_list_patterns = ['pesticides found in', 'pesticides detected in', 'what pesticides in', 'list pesticides in']
        if any(p in query_lower for p in pesticide_list_patterns) and detected_samples:
            return self._handle_list_pesticides(detected_samples)
        
        # Pattern 4: Pesticides in neighborhoods
        # "what pesticides are in al iskan neighborhood"
        if detected_neighborhoods and ('pesticide' in query_lower or 'pesticides' in query_lower):
            show_separately = any(phrase in query_lower for phrase in ['individually', 'separately', 'for each'])
            return self._handle_neighborhood_pesticides(detected_neighborhoods, show_separately)
        
        # Pattern 5: Find samples containing pesticide
        # "tomato samples containing bifenthrin"
        if detected_pesticide and detected_samples:
            return self._handle_find_pesticide_in_sample(detected_pesticide, detected_samples)
        
        # Pattern 6: Neighborhood ranking
        # "ranking of neighborhoods by violations"
        if any(kw in query_lower for kw in ['rank', 'ranking', 'worst', 'most violations']) and \
           any(kw in query_lower for kw in ['neighborhood', 'neighborhoods']):
            return self._handle_neighborhood_ranking()
        
        # Pattern 7: Comprehensive analysis
        # "comprehensive analysis of tomatoes"
        comprehensive_keywords = ['comprehensive analysis', 'comprehensive report', 'statistics for', 'summary of']
        if any(kw in query_lower for kw in comprehensive_keywords) and detected_samples:
            return self._handle_comprehensive_analysis(detected_samples)
        
        # Pattern 8: Pesticide statistics (max, min, range, median, average)
        # "what is the median concentration of imidacloprid in tomatoes"
        stats_keywords_found = []
        for stat_type, keywords in self.stats_keywords.items():
            if any(kw in query_lower for kw in keywords):
                stats_keywords_found.append(stat_type)
        
        if stats_keywords_found and detected_pesticide:
            return self._handle_pesticide_stats(detected_pesticide, detected_samples, stats_keywords_found)
        
        # Pattern HRI: Health Risk Index
        hri_kws_en = ['health risk index', 'health risk', 'hri', 'risk index']
        if any(kw in query_lower for kw in hri_kws_en) and detected_samples:
            return self._handle_health_risk_index(detected_samples)

        # Pattern QI: Quality Index
        qi_kws_en = ['quality index', 'quality score', 'quality indicator']
        if any(kw in query_lower for kw in qi_kws_en) and detected_samples:
            return self._handle_quality_index(detected_samples)

        # Pattern CG: Chemical Groups / Classify pesticides
        cg_kws_en = ['chemical group', 'chemical groups', 'classify pesticide',
                     'pesticide class', 'group classification']
        if any(kw in query_lower for kw in cg_kws_en):
            min_pest = 0
            nums = re.findall(r'(\d+)', query_normalized)
            threshold_kws_cg = ['more than', 'greater than']
            if nums and any(kw in query_lower for kw in threshold_kws_cg):
                min_pest = int(nums[0])
            return self._handle_chemical_groups(detected_samples, min_pesticides=min_pest)

        # Pattern CAT_PEST: Category + Pesticide (vegetables with bifenthrin)
        _cat_en_map = {
            'vegetable': 'vegetable', 'vegetables': 'vegetable',
            'fruit': 'fruit', 'fruits': 'fruit',
            'spice': 'spice', 'spices': 'spice',
            'nut': 'nut', 'nuts': 'nut',
            'grain': 'grain', 'grains': 'grain', 'leafy': 'leafy',
        }
        # Pattern CAT_PEST: Category + Pesticide (vegetables with bifenthrin)
        _cat_en_map = {
            'vegetable': 'vegetable', 'vegetables': 'vegetable',
            'fruit': 'fruit', 'fruits': 'fruit',
            'spice': 'spice', 'spices': 'spice',
            'nut': 'nut', 'nuts': 'nut',
            'grain': 'grain', 'grains': 'grain', 'leafy': 'leafy',
        }
        _cat_key_process = None
        for kw, cat in _cat_en_map.items():
            if kw in query_lower:
                _cat_key_process = cat
                break
        if detected_pesticide and _cat_key_process and not detected_samples:
            return self._handle_category_pesticide(detected_pesticide, _cat_key_process, [])

        # Pattern CAT_LIMIT: Category above AND below limit summary
        # "spices above and below permissible limits"
        cat_both_kws_en = ['above and below', 'above or below', 'above & below']
        is_cat_both = any(kw in query_lower for kw in cat_both_kws_en)
        if is_cat_both and _cat_key_process:
            _test_type = None
            if 'mycotoxin' in query_lower:
                _test_type = 'mycotoxin'
            elif 'pesticide' in query_lower:
                _test_type = 'pesticide'
            return self._handle_category_limit_summary(_cat_key_process, detected_samples, _test_type)

        # Pattern AVG_LIMIT: Average concentration above/below limit
        # "average concentration of imidacloprid above limit"
        avg_lim_kws = ['average concentration above', 'avg concentration above',
                       'mean concentration above', 'average above limit']
        is_avg_lim = (
            any(kw in query_lower for kw in avg_lim_kws) or
            ('average' in query_lower and 'above limit' in query_lower and detected_pesticide)
        )
        if is_avg_lim and detected_pesticide:
            _above = 'above' in query_lower
            return self._handle_avg_concentration_limit(detected_pesticide, detected_samples, _above)

        # Pattern FREQ: Pesticide frequency in sample
        # "frequency of imidacloprid in tomatoes"
        freq_kws_en = ['frequency of', 'how often', 'occurrence of']
        is_freq = any(kw in query_lower for kw in freq_kws_en)
        if is_freq and detected_pesticide and detected_samples:
            return self._handle_pesticide_frequency_in_sample(detected_pesticide, detected_samples)

        # Pattern UNIQUE_NC: Unique non-compliant + pesticide repetitions
        # "How many unique non-compliant samples + repetitions in cardamom"
        unc_kws_en = ['unique non-compliant', 'unique noncompliant']
        is_unc = (
            any(kw in query_lower for kw in unc_kws_en) or
            ('unique' in query_lower and 'non-compliant' in query_lower and
             ('repetition' in query_lower or 'frequency' in query_lower))
        )
        if is_unc and detected_samples:
            return self._handle_unique_noncompliant_with_pesticides(detected_samples)

        # Pattern 9: Search for samples by establishment/recipient
        # "search for samples in facility al maraee"
        recipient_keywords = ['recipient']
        establishment_keywords = ['establishment', 'facility', 'store', 'shop']
        
        # Extract recipient or establishment name
        recipient_match = re.search(r'(?:recipient)\s+([^\s]+(?:\s+[^\s]+)?)', query_lower)
        establishment_match = re.search(r'(?:facility|establishment|store|shop)\s+(.+?)(?:\s+(?:and|what|unique|$))', query_lower)
        
        if recipient_match or establishment_match or any(kw in query_lower for kw in recipient_keywords + establishment_keywords):
            name = None
            search_type = None
            
            if recipient_match:
                name = recipient_match.group(1).strip()
                search_type = 'recipient'
            elif establishment_match:
                name = establishment_match.group(1).strip()
                search_type = 'establishment'
            else:
                # Try to extract any name mentioned
                name_match = re.search(r'(?:samples in|samples from)\s+([^\s]+(?:\s+[^\s]+)?(?:\s+[^\s]+)?)', query_lower)
                if name_match:
                    name = name_match.group(1).strip()
                    search_type = 'any'
            
            if name:
                is_unique = any(kw in query_lower for kw in ['unique', 'distinct'])
                is_compliant = any(kw in query_lower for kw in self.below_limit_keywords)
                is_non_compliant = any(kw in query_lower for kw in self.above_limit_keywords)
                return self._handle_recipient_establishment_query(
                    name, search_type, detected_samples, is_unique, is_compliant, is_non_compliant
                )
        
        # Pattern 10: Samples containing specific pesticide (without sample type filter)
        # "how many samples contain fipronil"
        if detected_pesticide and not detected_samples:
            # Check if it's asking about samples with this pesticide
            if any(kw in query_lower for kw in ['samples', 'count', 'how many']):
                return self._handle_samples_with_pesticide(detected_pesticide)
        
        # Pattern 11: Unique sample count
        # "how many unique cucumber samples"
        if detected_samples and any(kw in query_lower for kw in ['unique', 'distinct', 'sample code']):
            return self._handle_unique_samples_count(detected_samples, detected_neighborhoods)
        
        # Pattern 12: Just search for pesticide (no sample filter)
        # "Find fipronil"
        search_keywords = ['find', 'search', 'locate']
        if detected_pesticide and any(kw in query_lower for kw in search_keywords):
            return self._handle_find_pesticide_all(detected_pesticide)
        
        # Pattern 14: Simple sample count (NO CONDITIONS)
        # "how many tomato samples"
        # This MUST be after limit/compliance patterns to avoid conflicts
        count_keywords = ['count', 'how many', 'samples']
        if detected_samples and any(kw in query_lower for kw in count_keywords):
            # Only trigger if NOT a limit/compliance query (those are handled above)
            return self._handle_simple_sample_count(detected_samples, detected_neighborhoods)
        
        # Pattern 14: LLM Fallback for unknown queries
        # If we have LLM configured, try to generate SQL
        if self.llm_client is not None:
            llm_response = self._handle_llm_query(query, detected_samples, detected_neighborhoods, detected_pesticide)
            if llm_response[0]:
                return llm_response
        

        return None


    
    # Handlers
    
    def _handle_n_pesticides(self, n: int, samples: List[str]) -> Tuple[str, pd.DataFrame]:
        """Samples with exactly N pesticides."""
        if n == 0:
            return self._handle_multiple_n_pesticides([0], samples)
        con = self._get_connection()
        
        sample_filter = ""
        if samples:
            sample_filter = f"AND {self._build_sample_filter(samples)}"
        
        sql = f"""
        SELECT 
            "كود العينة" AS sample_code,
            "اسم العينة" AS sample_name,
            COUNT(*) AS pesticide_count
        FROM chemistry_tidy
        WHERE is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        {sample_filter}
        GROUP BY "كود العينة", "اسم العينة"
        HAVING COUNT(*) = {n}
        ORDER BY "كود العينة" DESC
        LIMIT 100
        """
        
        df = con.execute(sql).df()
        con.close()
        
        sample_display = ' + '.join(samples) if samples else 'All types'
        
        if not df.empty:
            counts = df['sample_name'].value_counts()
            breakdown = " + ".join([f"{count} {name}" for name, count in counts.items()])
            
            pesticide_label = '1 pesticide' if n == 1 else f'{n} pesticides'
            response = f"🔢 **{sample_display} samples with {pesticide_label}:**\n\n"
            response += f"✅ Found **{len(df)}** sample(s)\n\n"
            response += f"📋 **Breakdown:** {breakdown}\n\n"
            response += df.head(20).to_markdown(index=False)
            
            if len(df) > 20:
                response += f"\n\n💾 *Attached file contains all {len(df)} results*"
        else:
            response = f"⚠️ No {sample_display} samples found with {n} pesticide(s)"
        
        return response, df
    def _handle_multiple_n_pesticides(self, counts: List[int], samples: List[str]) -> Tuple[str, pd.DataFrame]:
        """
        عينات بأعداد مختلفة من المبيدات (يشمل 0 = خالية)
        يدعم: "العينات الخالية من المبيدات و التي تحتوي علي مبيد واحد و ثلاث مبيدات"
        """
        con = self._get_connection()
    
        sample_filter = ""
        if samples:
            sample_filter = f"AND {self._build_sample_filter(samples)}"
    
        has_zero = 0 in counts
        non_zero_counts = [c for c in counts if c > 0]
    
        all_dfs = []
        summary_rows = []
        details_responses = []
    
        # ── Part A: Zero-pesticide samples ──
        if has_zero:
            zero_sql = f"""
            WITH detected_samples AS (
                SELECT DISTINCT "كود العينة"
                FROM chemistry_tidy
                WHERE is_detected = 1
                AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
                {sample_filter}
            )
            SELECT 
                "كود العينة" as sample_code,
                "اسم العينة" as sample_name,
                0 as pesticide_count
            FROM chemistry_tidy
            WHERE "كود العينة" NOT IN (SELECT "كود العينة" FROM detected_samples)
            {sample_filter}
            GROUP BY "كود العينة", "اسم العينة"
            ORDER BY "كود العينة" DESC
            """
            zero_df = con.execute(zero_sql).df()
            all_dfs.append(zero_df)
        
            if not zero_df.empty:
                type_counts = zero_df['sample_name'].value_counts()
                breakdown_parts = [f"{count} {name}" for name, count in type_counts.head(10).items()]
                breakdown = " + ".join(breakdown_parts)
                if len(type_counts) > 10:
                    breakdown += f" + {len(type_counts) - 10} more types"
            
                summary_rows.append({'pesticide_count': '0 (clean)', 'sample_count': len(zero_df)})
                details_responses.append(
                    f"#### 🛡️ Pesticide-Free Samples (0 pesticides)\n\n"
                    f"- ✅ **Count:** {len(zero_df)} sample(s)\n"
                    f"- 📋 **Types:** {breakdown}\n"
                )
            else:
                details_responses.append("#### 🛡️ Pesticide-Free\n\nNo clean samples found")
    
        # ── Part B: Non-zero pesticide counts ──
        for n in sorted(non_zero_counts):
            n_sql = f"""
            SELECT 
                "كود العينة" AS sample_code,
                "اسم العينة" AS sample_name,
                COUNT(*) AS pesticide_count
            FROM chemistry_tidy
            WHERE is_detected = 1 
            AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
            {sample_filter}
            GROUP BY "كود العينة", "اسم العينة"
            HAVING COUNT(*) = {n}
            ORDER BY "كود العينة" DESC
            """
            n_df = con.execute(n_sql).df()
            all_dfs.append(n_df)
        
            label = '1 pesticide' if n == 1 else f'{n} pesticides'
            icon = "🔹" if n == 1 else "🔸"
        
            if not n_df.empty:
                type_counts = n_df['sample_name'].value_counts()
                breakdown_parts = [f"{count} {name}" for name, count in type_counts.head(10).items()]
                breakdown = " + ".join(breakdown_parts)
                if len(type_counts) > 10:
                    breakdown += f" + {len(type_counts) - 10} more types"
            
                summary_rows.append({'pesticide_count': n, 'sample_count': len(n_df)})
                details_responses.append(
                    f"#### {icon} Samples with {label}\n\n"
                    f"- ✅ **Count:** {len(n_df)} sample(s)\n"
                    f"- 📋 **Types:** {breakdown}\n"
                )
            else:
                details_responses.append(f"#### {icon} Samples with {label}\n\nNo samples found")
    
        con.close()
    
        # ── Summary table ──
        summary_df = pd.DataFrame(summary_rows)
        if not summary_df.empty:
            summary_df = summary_df.sort_values(by='pesticide_count')
    
        # ── Build final response ──
        counts_display = ' + '.join(
            ['pesticide-free (0)' if c == 0 else f'{c} pesticide' if c == 1 else f'{c} pesticides'
             for c in sorted(counts)]
        )
        sample_display = ' + '.join(samples) if samples else 'All types'
    
        response = f"## 📊 Sample Distribution by Pesticide Count — {sample_display}\n\n"
        response += f"🔢 **Requested:** {counts_display}\n\n"
    
        if not summary_df.empty:
            response += "### 📋 Summary Table\n\n"
            response += summary_df.to_markdown(index=False)
            response += "\n\n---\n\n"
    
        response += "### 🔍 Details per Category\n\n"
        response += "\n\n---\n\n".join(details_responses)
    
        combined_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
    
        return response, combined_df
    
    def _handle_count_samples_limit(self, samples: List[str], neighborhoods: List[str], 
                                     is_above: bool) -> Tuple[str, pd.DataFrame]:
        """عد العينات فوق/تحت الحد - بناءً على كود العينة الفريد"""
        con = self._get_connection()
        
        # Sample filter — DB stores English names, use helper
        sample_filter = f"AND {self._build_sample_filter(samples)}"
        
        # Neighborhood filter
        neighborhood_filter = ""
        if neighborhoods:
            hood_conditions = []
            for n in neighborhoods:
                variants = [n]
                if 'ا' in n:
                    variants.append(n.replace('ا', 'إ'))
                    variants.append(n.replace('ا', 'أ'))
                if 'إ' in n:
                    variants.append(n.replace('إ', 'ا'))
                if 'أ' in n:
                    variants.append(n.replace('أ', 'ا'))
                for v in set(variants):
                    hood_conditions.append(f"\"الحى\" LIKE '%{v}%'")
            neighborhood_filter = f"AND ({' OR '.join(hood_conditions)})"
        
        # Use CTE to correctly count UNIQUE SAMPLES based on sample code
        # A sample is "above limit" if it has AT LEAST ONE pesticide above limit
        sql = f"""
        WITH sample_status AS (
            SELECT 
                "كود العينة" AS sample_code,
                "اسم العينة" AS sample_name,
                MAX(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS has_violation
            FROM chemistry_tidy
            WHERE is_detected = 1
            {sample_filter}
            {neighborhood_filter}
            GROUP BY "كود العينة", "اسم العينة"
        )
        SELECT 
            sample_name AS sample_type,
            COUNT(*) AS sample_count,
            SUM(has_violation) AS above_limit,
            SUM(CASE WHEN has_violation = 0 THEN 1 ELSE 0 END) AS below_limit
        FROM sample_status
        GROUP BY sample_name
        ORDER BY sample_count DESC
        """
        
        df = con.execute(sql).df()
        con.close()
        
        type_display = " + ".join(samples)
        if neighborhoods:
            type_display += f" in {' + '.join(neighborhoods)}"
        
        if not df.empty:
            total_samples = int(df['sample_count'].sum()) if 'sample_count' in df.columns else len(df)
            total_above   = int(df['above_limit'].sum())  if 'above_limit'  in df.columns else 0
            total_below   = int(df['below_limit'].sum())  if 'below_limit'  in df.columns else 0
            
            response = f"📊 **Results for {type_display}:**\n\n"
            response += f"✅ Total unique samples: **{total_samples}**\n"
            response += f"🔴 Above limit: **{total_above}** (≥1 pesticide exceeds MRL)\n"
            response += f"🟢 Below limit: **{total_below}** (all pesticides within MRL)\n\n"
            response += df.to_markdown(index=False)
        else:
            response = f"⚠️ No samples found for **{type_display}**"
        
        return response, df
    
    def _handle_count_samples_compliance(self, samples: List[str], neighborhoods: List[str], 
                                          is_non_compliant: bool) -> Tuple[str, pd.DataFrame]:
        """عد العينات المطابقة/غير المطابقة - بناءً على عمود نتيجة العينة (sample_result)"""
        con = self._get_connection()
        
        # Sample filter — DB stores English names, use helper
        sample_filter = f"AND {self._build_sample_filter(samples)}"
        
        # Neighborhood filter
        neighborhood_filter = ""
        if neighborhoods:
            hood_conditions = []
            for n in neighborhoods:
                variants = [n]
                if 'ا' in n:
                    variants.append(n.replace('ا', 'إ'))
                    variants.append(n.replace('ا', 'أ'))
                if 'إ' in n:
                    variants.append(n.replace('إ', 'ا'))
                if 'أ' in n:
                    variants.append(n.replace('أ', 'ا'))
                for v in set(variants):
                    hood_conditions.append(f"\"الحى\" LIKE '%{v}%'")
            neighborhood_filter = f"AND ({' OR '.join(hood_conditions)})"
        
        # Query using sample_result column
        sql = f"""
        SELECT 
            "الحى" AS neighborhood,
            "اسم العينة" AS sample_type,
            sample_result AS result,
            COUNT(DISTINCT "كود العينة") AS sample_count
        FROM chemistry_tidy
        WHERE 1=1
        {sample_filter}
        {neighborhood_filter}
        GROUP BY "الحى", "اسم العينة", sample_result
        ORDER BY "الحى", sample_count DESC
        """
        
        df = con.execute(sql).df()
        con.close()
        
        type_display = " + ".join(samples)
        if neighborhoods:
            type_display += f" in {' + '.join(neighborhoods)}"
        
        if not df.empty:
            status_text   = 'Non-Compliant' if is_non_compliant else 'Compliant'
            target_result = 'Non-Compliant' if is_non_compliant else 'Compliant'

            response = f"📊 **{status_text} Samples — {type_display}:**\n\n"
            for hood, group in df.groupby('neighborhood'):
                compliant     = int(group[group['result'].str.strip() == 'Compliant']['sample_count'].sum())
                non_compliant = int(group[group['result'].str.strip() == 'Non-Compliant']['sample_count'].sum())
                unknown       = int(group[group['result'].isna()]['sample_count'].sum())
                total         = int(group['sample_count'].sum())
                target_count  = non_compliant if is_non_compliant else compliant

                response += f"### 📍 {hood}\n"
                response += f"✅ Total unique samples: **{total}**\n"
                response += f"🟢 Compliant: **{compliant}**\n"
                response += f"🔴 Non-Compliant: **{non_compliant}**\n"
                if unknown > 0:
                    response += f"⚪ Unknown: **{unknown}**\n"
                response += f"\n📌 **{status_text}: {target_count}**\n\n"

                target_df = group[group['result'].str.strip() == target_result]
                if not target_df.empty:
                    response += target_df.drop(columns='neighborhood').to_markdown(index=False)
                response += "\n\n"
        else:
            response = f"⚠️ No samples found for **{type_display}**"
        
        return response, df
    
    def _handle_list_pesticides(self, samples: List[str]) -> Tuple[str, pd.DataFrame]:
        """List pesticides found in a sample type."""
        con = self._get_connection()
        
        sample_filter = self._build_sample_filter(samples)
        
        sql = f"""
        SELECT 
            pesticide_name   AS pesticide,
            COUNT(*)         AS detections,
            ROUND(AVG(concentration), 4) AS avg_concentration,
            ROUND(MAX(concentration), 4) AS max_concentration,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations
        FROM chemistry_tidy
        WHERE is_detected = 1
        AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        AND {sample_filter}
        GROUP BY pesticide_name
        ORDER BY detections DESC
        LIMIT 50
        """
        
        df = con.execute(sql).df()
        con.close()
        
        sample_display = ' + '.join(samples)
        
        if not df.empty:
            total_detections  = int(df['detections'].sum())
            total_violations  = int(df['violations'].sum())
            unique_pesticides = len(df)
            
            response = f"🧪 **Pesticides in {sample_display}:**\n\n"
            response += f"📊 **Summary:**\n"
            response += f"• Unique pesticides: **{unique_pesticides}**\n"
            response += f"• Total detections: **{total_detections}**\n"
            response += f"• Total violations: **{total_violations}**\n\n"
            response += df.to_markdown(index=False)
        else:
            response = f"⚠️ No pesticides found in **{sample_display}**"
        
        return response, df
    
    def _handle_neighborhood_pesticides(self, neighborhoods: List[str], 
                                         show_separately: bool) -> Tuple[str, pd.DataFrame]:
        """Pesticides detected in neighborhoods."""
        con = self._get_connection()
        
        all_dfs = []
        all_responses = []
        
        if show_separately:
            for n in neighborhoods:
                sql = f"""
                SELECT 
                    pesticide_name   AS pesticide,
                    COUNT(*)         AS detections,
                    ROUND(AVG(concentration), 4) AS avg_concentration,
                    SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS above_limit
                FROM chemistry_tidy
                WHERE is_detected = 1
                AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
                AND "الحى" LIKE '%{n}%'
                GROUP BY pesticide_name
                ORDER BY detections DESC
                LIMIT 20
                """
                df = con.execute(sql).df()
                all_dfs.append(df)
                
                if not df.empty:
                    total      = int(df['detections'].sum())
                    violations = int(df['above_limit'].sum())
                    all_responses.append(
                        f"📍 **Neighborhood {n}:** {len(df)} pesticide(s), {total} detection(s), {violations} violation(s)\n\n{df.to_markdown(index=False)}"
                    )
                else:
                    all_responses.append(f"📍 **Neighborhood {n}:** No pesticides found")
            
            response = "\n\n---\n\n".join(all_responses)
            combined_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
        else:
            # Combined view
            conditions = [f"\"الحى\" LIKE '%{n}%'" for n in neighborhoods]
            neighborhood_filter = f"({' OR '.join(conditions)})"
            
            sql = f"""
            SELECT 
                "الحى"           AS neighborhood,
                pesticide_name   AS pesticide,
                COUNT(*)         AS detections,
                SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) AS violations
            FROM chemistry_tidy
            WHERE is_detected = 1 
            AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
            AND {neighborhood_filter}
            GROUP BY "الحى", pesticide_name
            ORDER BY neighborhood, detections DESC
            LIMIT 50
            """
            
            combined_df = con.execute(sql).df()
            
            if not combined_df.empty:
                response = f"🏘️ **Pesticides in {' + '.join(neighborhoods)}:**\n\n"
                response += f"✅ Found {len(combined_df)} record(s)\n\n"
                response += combined_df.to_markdown(index=False)
                response += "\n\n💡 Add 'for each' to your query to view neighborhoods separately"
            else:
                response = "⚠️ No pesticides found in the specified neighborhoods"
        
        con.close()
        return response, combined_df
    
    def _handle_find_pesticide_in_sample(self, pesticide: str, 
                                          samples: List[str]) -> Tuple[str, pd.DataFrame]:
        """Find a specific pesticide in samples — returns unique sample-level rows."""
        con = self._get_connection()
        
        sample_filter = self._build_sample_filter(samples)
        
        sql = f"""
        SELECT 
            "كود العينة"     AS sample_code,
            "اسم العينة"    AS sample_name,
            pesticide_name   AS pesticide,
            concentration    AS concentration,
            limit_value      AS mrl,
            ROUND(exceedance_ratio, 2) AS ratio,
            sample_result    AS status
        FROM chemistry_tidy
        WHERE is_detected = 1 
        AND ({get_pesticide_sql_filter(pesticide)})
        AND {sample_filter}
        ORDER BY "كود العينة" DESC
        LIMIT 100
        """
        
        df = con.execute(sql).df()
        con.close()
        
        samples_display = ' + '.join(samples)
        
        if not df.empty:
            unique_samples = df['sample_code'].nunique()
            compliant     = len(df[df['status'] == 'Compliant'])
            non_compliant = len(df[df['status'] == 'Non-Compliant'])
            
            response = f"🔍 **{pesticide} in {samples_display}:**\n\n"
            response += f"✅ Found **{unique_samples}** unique sample(s) | **{len(df)}** detection record(s)\n"
            response += f"📊 {compliant} Compliant | {non_compliant} Non-Compliant\n\n"
            response += df.to_markdown(index=False)
        else:
            response = f"⚠️ **{pesticide}** was not detected in **{samples_display}**"
        
        return response, df
    
    def _handle_neighborhood_ranking(self) -> Tuple[str, pd.DataFrame]:
        """Rank neighborhoods by number of violations."""
        con = self._get_connection()
        
        sql = """
        SELECT 
            "الحى"                             AS neighborhood,
            COUNT(DISTINCT "كود العينة")        AS total_samples,
            SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) AS violations,
            ROUND(SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) * 100.0 / 
                  NULLIF(COUNT(DISTINCT "كود العينة"), 0), 2) AS violation_rate_pct
        FROM chemistry_tidy
        WHERE "الحى" IS NOT NULL AND "الحى" != ''
        GROUP BY "الحى"
        ORDER BY violations DESC
        LIMIT 20
        """
        
        df = con.execute(sql).df()
        con.close()
        
        response = "🏘️ **Neighborhood Ranking by Violations (descending):**\n\n"
        
        if not df.empty:
            response += df.to_markdown(index=False)
        else:
            response += "⚠️ No data found"
        
        return response, df
    
    def _handle_comprehensive_analysis(self, samples: List[str]) -> Tuple[str, pd.DataFrame]:
        """Comprehensive analysis of a sample type."""
        con = self._get_connection()
        
        sample_filter = self._build_sample_filter(samples)
        type_display = " + ".join(samples)
        
        distribution_sql = f"""
        WITH sample_pesticide_counts AS (
            SELECT 
                "كود العينة" AS sample_code,
                COUNT(CASE WHEN is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA') THEN 1 END) AS pesticide_count,
                SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS failing_count
            FROM chemistry_tidy
            WHERE {sample_filter}
            GROUP BY "كود العينة"
        )
        SELECT 
            pesticide_count   AS num_pesticides,
            COUNT(*)          AS sample_count,
            SUM(CASE WHEN failing_count = 0 THEN 1 ELSE 0 END) AS compliant,
            SUM(CASE WHEN failing_count > 0 THEN 1 ELSE 0 END) AS non_compliant
        FROM sample_pesticide_counts
        GROUP BY pesticide_count
        ORDER BY pesticide_count ASC
        """
        
        distribution_df = con.execute(distribution_sql).df()
        
        pesticide_stats_sql = f"""
        SELECT 
            pesticide_name AS pesticide,
            COUNT(*)       AS detections,
            ROUND(MAX(limit_value), 4) AS MRL,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations,
            ROUND(MEDIAN(concentration), 4) AS median,
            ROUND(MIN(concentration), 4)    AS min,
            ROUND(MAX(concentration), 4)    AS max
        FROM chemistry_tidy
        WHERE {sample_filter}
        AND is_detected = 1
        AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        GROUP BY pesticide_name
        ORDER BY detections DESC
        """
        
        pesticide_stats_df = con.execute(pesticide_stats_sql).df()
        con.close()
        
        response = f"📊 **Comprehensive Analysis — {type_display}**\n\n"
        
        if not distribution_df.empty:
            total        = int(distribution_df['sample_count'].sum())
            total_passed = int(distribution_df['compliant'].sum())
            total_failed = int(distribution_df['non_compliant'].sum())
            
            response += f"**📋 General Statistics:**\n"
            response += f"• Total samples: **{total}**\n"
            response += f"• Compliant: **{total_passed}**\n"
            response += f"• Non-Compliant: **{total_failed}**\n\n"
            response += "**📊 Sample Distribution by Pesticide Count:**\n"
            response += distribution_df.to_markdown(index=False)
            response += "\n\n"
        
        if not pesticide_stats_df.empty:
            failing = pesticide_stats_df[pesticide_stats_df['violations'] > 0]
            response += "**🧪 Detected Pesticide Statistics:**\n"
            response += pesticide_stats_df.head(15).to_markdown(index=False)
            if not failing.empty:
                response += f"\n\n🔴 **Pesticides causing violations ({len(failing)} types):** "
                response += ", ".join(failing['pesticide'].tolist())
        
        return response, distribution_df
    
    def _handle_pesticide_stats(self, pesticide: str, samples: List[str], 
                                 stats_requested: List[str]) -> Tuple[str, pd.DataFrame]:
        """Statistics for a specific pesticide."""
        con = self._get_connection()
        
        sample_filter = ""
        if samples:
            sample_filter = f"AND {self._build_sample_filter(samples)}"
        
        sql = f"""
        SELECT 
            pesticide_name  AS pesticide,
            COUNT(*)        AS detections,
            ROUND(MIN(concentration), 4) AS min_concentration,
            ROUND(MAX(concentration), 4) AS max_concentration,
            ROUND(AVG(concentration), 4) AS avg_concentration,
            ROUND(MEDIAN(concentration), 4) AS median_concentration,
            ROUND(MAX(concentration) - MIN(concentration), 4) AS range,
            ROUND(MAX(limit_value), 4) AS MRL,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations
        FROM chemistry_tidy
        WHERE is_detected = 1
        AND ({get_pesticide_sql_filter(pesticide)})
        {sample_filter}
        GROUP BY pesticide_name
        """
        
        df = con.execute(sql).df()
        con.close()
        
        sample_display = ' + '.join(samples) if samples else 'All sample types'
        
        if not df.empty:
            row = df.iloc[0]
            response = f"📊 **Statistics for {pesticide}**\n"
            response += f"🧪 In: {sample_display}\n\n"
            response += f"📈 **Statistics:**\n"
            response += f"• Detections: **{int(row['detections'])}**\n"
            response += f"• Min concentration: **{row['min_concentration']}** mg/kg\n"
            response += f"• Max concentration: **{row['max_concentration']}** mg/kg\n"
            response += f"• Average: **{row['avg_concentration']}** mg/kg\n"
            response += f"• Median: **{row['median_concentration']}** mg/kg\n"
            response += f"• Range: **{row['range']}** mg/kg\n"
            response += f"• MRL limit: **{row['MRL']}** mg/kg\n"
            response += f"• Violations: **{int(row['violations'])}**\n"
        else:
            response = f"⚠️ **{pesticide}** not found in **{sample_display}**"
        
        return response, df
    
    def _handle_recipient_establishment_query(self, name: str, search_type: str,
                                               samples: List[str], is_unique: bool,
                                               is_compliant: bool, is_non_compliant: bool) -> Tuple[str, pd.DataFrame]:
        """البحث عن العينات حسب المستلم أو المنشأة"""
        con = self._get_connection()
        
        # Build filters
        filters = []
        
        # Name filter (search in multiple columns)
        name_conditions = [
            f"\"اسم المستلم\" LIKE '%{name}%'",
            f"\"اسم المستلم\" ILIKE '%{name}%'",
        ]
        # Also try to search in establishment if column exists
        filters.append(f"({' OR '.join(name_conditions)})")
        
        # Sample type filter
        if samples:
            sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
            filters.append(f"({' OR '.join(sample_conditions)})")
        
        # Compliance filter
        if is_compliant and not is_non_compliant:
            filters.append("is_compliant = 1")
        elif is_non_compliant and not is_compliant:
            filters.append("is_compliant = 0")
        
        where_clause = " AND ".join(filters)
        
        if is_unique:
            sql = f"""
            SELECT DISTINCT
                "كود العينة"   AS sample_code,
                "اسم العينة"  AS sample_name,
                "اسم المستلم" AS recipient,
                sample_result        AS status
            FROM chemistry_tidy
            WHERE {where_clause}
            GROUP BY "كود العينة", "اسم العينة", "اسم المستلم"
            ORDER BY "كود العينة" DESC
            LIMIT 100
            """
        else:
            sql = f"""
            SELECT 
                "كود العينة"   AS sample_code,
                "اسم العينة"  AS sample_name,
                "اسم المستلم" AS recipient,
                pesticide_name       AS pesticide,
                concentration        AS concentration,
                sample_result        AS status
            FROM chemistry_tidy
            WHERE {where_clause}
            AND is_detected = 1
            ORDER BY "كود العينة" DESC
            LIMIT 100
            """
        
        df = con.execute(sql).df()
        con.close()
        
        status_desc = ""
        if is_compliant:
            status_desc = " Compliant"
        elif is_non_compliant:
            status_desc = " Non-Compliant"
        
        unique_desc = " unique" if is_unique else ""
        
        if not df.empty:
            response = f"🔍 **{unique_desc}{status_desc} samples for {name}:**\n\n"
            response += f"✅ Found **{len(df)}** record(s)\n\n"
            response += df.to_markdown(index=False)
        else:
            response = f"⚠️ No samples found for **{name}**"
        
        return response, df
    
    def _handle_samples_with_pesticide(self, pesticide: str) -> Tuple[str, pd.DataFrame]:
        """All sample types containing a specific pesticide."""
        con = self._get_connection()
        
        sql = f"""
        SELECT 
            "اسم العينة" AS sample_type,
            COUNT(DISTINCT "كود العينة") AS unique_samples,
            COUNT(*)  AS detections,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS above_limit,
            ROUND(AVG(concentration), 4) AS avg_concentration,
            ROUND(MAX(concentration), 4) AS max_concentration
        FROM chemistry_tidy
        WHERE is_detected = 1
        AND ({get_pesticide_sql_filter(pesticide)})
        GROUP BY "اسم العينة"
        ORDER BY detections DESC
        LIMIT 50
        """
        
        df = con.execute(sql).df()
        con.close()
        
        if not df.empty:
            total_samples    = int(df['unique_samples'].sum())
            total_detections = int(df['detections'].sum())
            total_above      = int(df['above_limit'].sum())
            
            response = f"🧪 **Sample types containing {pesticide}:**\n\n"
            response += f"📊 **Summary:**\n"
            response += f"• Total unique samples: **{total_samples}**\n"
            response += f"• Total detections: **{total_detections}**\n"
            response += f"• Violations (above MRL): **{total_above}**\n\n"
            response += df.to_markdown(index=False)
        else:
            response = f"⚠️ No samples found containing **{pesticide}**"
        
        return response, df
    
    def _handle_unique_samples_count(self, samples: List[str], 
                                      neighborhoods: List[str]) -> Tuple[str, pd.DataFrame]:
        """Count unique sample codes."""
        con = self._get_connection()
        
        conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        sample_filter = f"({' OR '.join(conditions)})"
        
        neighborhood_filter = ""
        if neighborhoods:
            hood_conditions = [f"\"الحى\" LIKE '%{n}%'" for n in neighborhoods]
            neighborhood_filter = f"AND ({' OR '.join(hood_conditions)})"
        
        sql = f"""
        SELECT 
            "اسم العينة" AS sample_type,
            COUNT(DISTINCT "كود العينة") AS unique_samples,
            COUNT(*) AS total_records,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS above_limit_records
        FROM chemistry_tidy
        WHERE {sample_filter}
        {neighborhood_filter}
        GROUP BY "اسم العينة"
        ORDER BY unique_samples DESC
        """
        
        df = con.execute(sql).df()
        con.close()
        
        sample_display = ' + '.join(samples)
        location_desc = f" in {' + '.join(neighborhoods)}" if neighborhoods else ""
        
        if not df.empty:
            total_unique = int(df['unique_samples'].sum())
            response = f"📊 **Unique samples for {sample_display}{location_desc}:**\n\n"
            response += f"✅ Total unique samples: **{total_unique}**\n\n"
            response += df.to_markdown(index=False)
        else:
            response = f"⚠️ No samples found for **{sample_display}**"
        
        return response, df
    
    def _handle_find_pesticide_all(self, pesticide: str) -> Tuple[str, pd.DataFrame]:
        """Search for a pesticide across all sample types."""
        con = self._get_connection()
        
        sql = f"""
        SELECT 
            "كود العينة" AS sample_code,
            "اسم العينة" AS sample_type,
            "الحى"           AS neighborhood,
            pesticide_name   AS pesticide,
            concentration    AS concentration,
            limit_value      AS mrl,
            ROUND(exceedance_ratio, 2) AS ratio,
            sample_result    AS status
        FROM chemistry_tidy
        WHERE is_detected = 1
        AND ({get_pesticide_sql_filter(pesticide)})
        ORDER BY concentration DESC
        LIMIT 100
        """
        
        df = con.execute(sql).df()
        con.close()
        
        if not df.empty:
            compliant     = len(df[df['status'] == 'Compliant'])
            non_compliant = len(df[df['status'] == 'Non-Compliant'])
            
            response = f"🔍 **Search results for {pesticide}:**\n\n"
            response += f"✅ Found **{len(df)}** record(s)\n"
            response += f"📊 {compliant} Compliant | {non_compliant} Non-Compliant\n\n"
            response += df.to_markdown(index=False)
        else:
            response = f"⚠️ **{pesticide}** not found in the database"
        
        return response, df
    
    def _handle_sample_pesticide_limit(self, samples: List[str], pesticide: str, is_above: bool, 
                                        both: bool = False, limit_filter: str = None, limit_desc: str = None) -> Tuple[str, pd.DataFrame]:
        """
        عينات تحتوي على مبيد X فوق/تحت الحد أو غير مطابقة
        "عينات الطماطم التي تحتوي على مبيد البابروفيزن فوق الحد"
        "عينات الطماطم التي تحتوي على مبيد البابروفيزن غير مطابقة" (uses sample_result)
        """
        con = self._get_connection()
        
        # Build filters — DB stores English sample names
        sample_filter = self._build_sample_filter(samples)
        
        # Clean pesticide name (remove 'AL' prefix if present)
        if pesticide.startswith('ال') and len(pesticide) > 4:
            pesticide = pesticide[2:]
        
        # Determine limit filter and description
        if limit_filter is not None and limit_desc is not None:
            # Custom filter provided (e.g., for sample_result queries)
            pass
        elif both:
            limit_desc = "فوق الحد و تحت الحد"
            limit_filter = ""  # No filter - show all
        else:
            limit_desc = "فوق الحد" if is_above else "تحت الحد"
            limit_filter = f"AND is_above_limit = {1 if is_above else 0}"
        
        # Smart pesticide matching logic to handle typos
        pesticide_lower = pesticide.lower()
        fuzzy_condition = ""
        
        if len(pesticide_lower) > 4:
            # Match first 4 chars to catch typos like 'buprofuzin' vs 'buprofezin'
            prefix = pesticide_lower[:4]
            fuzzy_condition = f"OR LOWER(pesticide_name) LIKE '%{prefix}%'"
        
        sql = f"""
        SELECT 
            "كود العينة" as sample_code,
            "اسم العينة" as sample_name,
            pesticide_name as اسم_المبيد,
            concentration as التركيز,
            limit_value as الحد_المسموح,
            is_above_limit as فوق_الحد,
            sample_result as نتيجة_العينة,
            "الحى" as neighborhood
        FROM chemistry_tidy
        WHERE {sample_filter}
        AND ({get_pesticide_sql_filter(pesticide)})
        AND is_detected = 1
        {limit_filter}
        ORDER BY is_above_limit DESC, concentration DESC
        LIMIT 50
        """
        
        try:
             df = con.execute(sql).df()
        except Exception:
             # Fallback query
             sql = f"""
            SELECT 
                "كود العينة" as sample_code,
                "اسم العينة" as sample_name,
                pesticide_name,
                concentration,
                limit_value,
                is_above_limit,
                "الحى" as neighborhood
            FROM chemistry_tidy
            WHERE {sample_filter}
            AND ({get_pesticide_sql_filter(pesticide)})
            AND is_detected = 1
            {limit_filter}
            ORDER BY is_above_limit DESC, concentration DESC
            LIMIT 50
            """
             df = con.execute(sql).df()
            
        con.close()
        
        sample_display = ' + '.join(samples)
        
        if not df.empty:
            count = len(df)
            
            if both:
                above_col   = 'is_above_limit'
                above_count = len(df[df[above_col] == 1]) if above_col in df.columns else 0
                below_count = len(df[df[above_col] == 0]) if above_col in df.columns else 0
                response = f"📊 **{sample_display} samples containing '{pesticide}' (above & below limit):**\n\n"
                response += f"✅ Found **{count}** sample(s): {above_count} above limit, {below_count} below limit\n\n"
            else:
                response = f"📊 **{sample_display} samples containing '{pesticide}' ({limit_desc}):**\n\n"
                response += f"✅ Found **{count}** sample(s)\n\n"
            
            response += df.to_markdown(index=False)
        else:
            response = f"⚠️ No **{sample_display}** samples found containing **'{pesticide}'** ({limit_desc})"
            
        return response, df
    
    def _handle_simple_sample_count(self, samples: List[str], 
                                     neighborhoods: List[str]) -> Tuple[str, pd.DataFrame]:
        """
        عد العينات الفريدة (بدون شروط)
        Simple sample count without limit/compliance conditions
        "ما عدد عينات الطماطم و الخيار و الكوسة"
        """
        con = self._get_connection()
        
        # Build sample filter
        sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        sample_filter = f"({' OR '.join(sample_conditions)})"
        
        # Build neighborhood filter
        neighborhood_filter = ""
        if neighborhoods:
            hood_conditions = []
            for n in neighborhoods:
                variants = [n]
                if 'ا' in n:
                    variants.append(n.replace('ا', 'إ'))
                    variants.append(n.replace('ا', 'أ'))
                if 'إ' in n:
                    variants.append(n.replace('إ', 'ا'))
                if 'أ' in n:
                    variants.append(n.replace('أ', 'ا'))
                for v in set(variants):
                    hood_conditions.append(f"\"الحى\" LIKE '%{v}%'")
            neighborhood_filter = f"AND ({' OR '.join(hood_conditions)})"
        
        # Count unique samples by sample code
        sql = f"""
        WITH sample_info AS (
            SELECT 
                "كود العينة" AS sample_code,
                "اسم العينة" AS sample_name,
                MAX(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS has_violation,
                COUNT(*) AS pesticide_count
            FROM chemistry_tidy
            WHERE {sample_filter}
            {neighborhood_filter}
            GROUP BY "كود العينة", "اسم العينة"
        )
        SELECT 
            sample_name    AS sample_type,
            COUNT(*)       AS unique_samples,
            SUM(has_violation) AS above_limit,
            SUM(CASE WHEN has_violation = 0 THEN 1 ELSE 0 END) AS below_limit
        FROM sample_info
        GROUP BY sample_name
        ORDER BY unique_samples DESC
        """
        
        df = con.execute(sql).df()
        con.close()
        
        sample_display = ' + '.join(samples)
        location_desc = f" in {' + '.join(neighborhoods)}" if neighborhoods else ""
        
        if not df.empty:
            total          = int(df['unique_samples'].sum())
            total_violated = int(df['above_limit'].sum())
            total_ok       = int(df['below_limit'].sum())
            
            response = f"📊 **Sample count — {sample_display}{location_desc}:**\n\n"
            response += f"✅ Total unique samples: **{total}**\n"
            response += f"🔴 Above limit: **{total_violated}**\n"
            response += f"🟢 Below limit: **{total_ok}**\n\n"
            response += df.to_markdown(index=False)
        else:
            response = f"⚠️ No samples found for **{sample_display}**"
        
        return response, df
    
    def _handle_llm_query(self, query: str, samples: List[str], 
                           neighborhoods: List[str], pesticide: Optional[str]) -> Tuple[str, Optional[pd.DataFrame]]:
        """
        LLM Fallback - Generate SQL using LLM
        Used when no pattern matches
        """
        if self.llm_client is None:
            return None, None
        
        try:
            # Build context
            schema_context = f"""
Available columns in chemistry_tidy table:
{', '.join(self.schema_columns[:30])}

Available sample types: {', '.join(self.available_sample_types[:15])}
Available neighborhoods: {', '.join(self.available_neighborhoods[:15])}

Key columns:
- "كود العينة": Sample code (unique identifier)
- "اسم العينة": Sample name/type
- "الحى": Neighborhood
- pesticide_name: Pesticide name (English)
- concentration: Pesticide concentration
- limit_value: MRL limit value
- is_detected: 1 if detected, 0 otherwise
- is_above_limit: 1 if concentration > limit
- sample_result: 'compliant (مطابقة)' or 'non-compliant (غير مطابقة)'
"""
            
            # Build prompt
            prompt = load_prompt(
                "sql_ollama_fallback",
                query=query,
                schema_context=schema_context,
                samples=samples if samples else "None",
                neighborhoods=neighborhoods if neighborhoods else "None",
                pesticide=pesticide if pesticide else "None",
            )
            
            # Call LLM
            response = self.llm_client.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1}
            )
            
            sql = response['message']['content'].strip()
            
            # Clean up SQL
            sql = sql.replace('```sql', '').replace('```', '').strip()
            
            # Validate SQL (basic check)
            if not sql.upper().startswith('SELECT'):
                return None, None
            
            # Execute SQL
            con = self._get_connection()
            df = con.execute(sql).df()
            con.close()
            
            if not df.empty:
                response_text = f"🤖 **نتيجة من الذكاء الاصطناعي:**\n\n"
                response_text += f"📊 **{query}**\n\n"
                response_text += df.to_markdown(index=False)
                return response_text, df
            else:
                return f"🤖 الاستعلام لم يُرجع نتائج.\n\nSQL: `{sql[:200]}...`", None
                
        except Exception as e:
            print(f"⚠️ LLM query failed: {e}")
            return None, None
    
    def _handle_violations_threshold(
        self,
        samples: List[str],
        neighborhoods: List[str],
        threshold: int,
        category_key: Optional[str] = None,
    ) -> Tuple[str, Optional[pd.DataFrame]]:
        """
        Find sample types with MORE THAN `threshold` violations (is_above_limit records).

        Args:
            samples:       Specific Arabic sample names (may be empty if category).
            neighborhoods: Optional neighborhood filter.
            threshold:     Minimum violation count (exclusive: > threshold).
            category_key:  Generic category ('vegetable', 'fruit', 'spice', 'nut', …).
                           When set, sample types are resolved from the DB.
        """
        con = self._get_connection()

        # ── Build category → DB sample-name filter ──
        # Maps category key to English keywords present in "اسم العينة" (DB stores English)
        CATEGORY_EN_KEYWORDS: Dict[str, List[str]] = {
            "Vegetables": [
                "tomato", "cucumber", "zucchini", "pepper", "eggplant",
                "beans", "okra", "potato", "carrot", "onion",
            ],
            "Fruits": [
                "strawberry", "grape", "apple", "orange", "pomegranate",
                "pear", "lemon", "lime", "berry", "date", "mango", "banana",
            ],
            "Spices": ["cardamom", "cumin", "thyme", "spice", "clove", "anise", "fennel"],
            "Nuts": ["pistachio", "nuts", "almond", "cashew", "hazelnut", "pecan", "peanut", "sesame"],
            "Grains": ["wheat", "rice", "corn", "lentil", "flour", "oat"],
            "Leafy Greens": [
                "lettuce", "parsley", "spinach", "arugula", "rocket",
                "coriander", "cilantro", "dill", "molokhia", "mint",
                "cauliflower", "broccoli", "cabbage",
            ],
        }
        # Lowercase category key → نوع العينة DB value
        CATEGORY_KEY_TO_DB: Dict[str, str] = {
            "vegetable": "Vegetables",
            "fruit": "Fruits",
            "spice": "Spices",
            "nut": "Nuts",
            "grain": "Grains",
            "leafy": "Leafy Greens",
        }

        # ── Build WHERE conditions ──
        sample_conditions = []
        if samples:
            # Specific English DB sample names were given — direct LIKE match
            for s in samples:
                sample_conditions.append(f"\"اسم العينة\" LIKE '%{s}%'")
        elif category_key:
            # Resolve category to نوع العينة DB value (English)
            db_category = CATEGORY_KEY_TO_DB.get(category_key)
            if db_category:
                # Use "نوع العينة" column which stores English category (Vegetables, Spices, etc.)
                sample_conditions.append(f"\"نوع العينة\" = '{db_category}'")
            elif category_key in CATEGORY_EN_KEYWORDS:
                # Fallback: keyword-based matching on "اسم العينة"
                en_members = CATEGORY_EN_KEYWORDS.get(category_key, [])
                sample_conditions = [f"LOWER(\"اسم العينة\") LIKE '%{en}%'" for en in en_members]

        sample_filter = f"AND ({' OR '.join(sample_conditions)})" if sample_conditions else ""

        # ── Neighborhood filter ──
        neighborhood_filter = ""
        if neighborhoods:
            hood_parts = []
            for n in neighborhoods:
                for v in {n, n.replace("ا", "إ"), n.replace("ا", "أ"),
                          n.replace("إ", "ا"), n.replace("أ", "ا")}:
                    hood_parts.append(f"\"الحى\" LIKE '%{v}%'")
            neighborhood_filter = f"AND ({' OR '.join(hood_parts)})"

        # ── Main SQL: violation count per sample name ──
        sql = f"""
        SELECT
            "اسم العينة" AS sample_name,
            COUNT(*) AS total_records,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations,
            ROUND(
                100.0 * SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) / COUNT(*),
                1
            ) AS violation_pct
        FROM chemistry_tidy
        WHERE is_detected = 1
            AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
            {sample_filter}
            {neighborhood_filter}
        GROUP BY "اسم العينة"
        HAVING SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) > {threshold}
        ORDER BY violations DESC
        """

        df = con.execute(sql).df()
        con.close()

        # ── Pretty column names for display ──
        if not df.empty:
            df.columns = ["sample_type", "total_records", "violations", "violation_rate_pct"]

        # ── Build response ──
        cat_label = category_key if category_key else (" + ".join(samples) if samples else "All types")

        if df.empty:
            response = (
                f"⚠️ No **{cat_label}** sample types found "
                f"with more than **{threshold}** violation(s)."
            )
        else:
            response = (
                f"📊 **{cat_label} sample types with more than {threshold} violation(s):**\n\n"
                f"✅ Found **{len(df)}** type(s)\n\n"
            )
            response += df.to_markdown(index=False)

        return response, df

    # LLM SQL Generation (Gemini / GPT / Ollama Fallback)

    def _get_schema_info(self) -> str:
        """Return DB schema as a formatted string for LLM prompting (schema-only, no data)."""
        try:
            con = self._get_connection()
            cols = con.execute("DESCRIBE chemistry_tidy").df()
            con.close()
        except Exception as exc:
            logging.warning(f"Schema fetch failed: {exc}")
            return (
                "Table: chemistry_tidy — key columns: كود العينة, اسم العينة, "
                "pesticide_name, concentration, limit_value, is_above_limit, "
                "is_detected, sample_result, الحى, نوع العينة"
            )

        DESCRIPTIONS: Dict[str, str] = {
            "كود العينة":       "Sample code (unique identifier)",
            "اسم العينة":       "Sample name in English (Tomato, Cucumber, Cardamom, …)",
            "نوع العينة":       "Category: Vegetables / Fruits / Spices / Nuts / Grains",
            "الحى":             "Neighborhood name (Arabic)",
            "اسم المنشاة":      "Establishment / facility name",
            "التاريخ":          "Sample date (TIMESTAMP)",
            "pesticide_name":   "Pesticide name in English",
            "concentration":    "Measured concentration (DOUBLE)",
            "limit_value":      "Maximum Residue Limit – MRL (DOUBLE)",
            "exceedance_ratio": "concentration / limit_value",
            "is_above_limit":   "1 = above MRL, 0 = within MRL",
            "is_compliant":     "1 = compliant, 0 = non-compliant (lab judgment)",
            "is_detected":      "1 = detected, 0 = not detected",
            "sample_result":    "Lab verdict: 'Compliant' | 'Non-Compliant'",
        }

        lines = [
            "**Table: chemistry_tidy**",
            "| Column | Type | Description |",
            "|--------|------|-------------|",
        ]
        for _, row in cols.iterrows():
            col = row["column_name"]
            lines.append(f"| {col} | {row['column_type']} | {DESCRIPTIONS.get(col, '')} |")
        return "\n".join(lines)

    def _build_llm_sql_prompt(
        self,
        query: str,
        detected_samples: List[str],
        detected_neighborhoods: List[str],
        detected_pesticide: Optional[str],
    ) -> str:
        """Build the schema-only SQL prompt for Gemini / GPT / Ollama."""
        return load_prompt(
            "sql_llm_fallback",
            schema=self._get_schema_info(),
            detected_samples=detected_samples or "None",
            detected_neighborhoods=detected_neighborhoods or "None",
            detected_pesticide=detected_pesticide or "None",
            query=query,
        )

    def process_with_gemini_fallback(
        self,
        query: str,
        llm_model: Any = None,
    ) -> Tuple[str, Optional[Any], Optional[str]]:
        """
        Full query processing with LLM SQL generation as a fallback.

        Processing order:
          Tier 1 — Pattern matching + intent routing  (self.process)
          Tier 2 — LLM SQL generation (Gemini / GPT / Ollama)

        Returns:
            (response_text, dataframe_or_None, generated_sql_or_None)

        The third element lets the caller display a "View SQL" expander.
        """
        # ── Tier 1: existing pattern / intent routing ──
        response_text, df = self.process(query)

        is_unknown = (
            "Sorry, I couldn't fully understand" in response_text
            or "لم أتمكن من فهم" in response_text
        )

        if not is_unknown:
            return response_text, df, None

        # ── Tier 2: LLM SQL generation ──
        active_llm = llm_model if llm_model is not None else self.llm_client
        if active_llm is None:
            return response_text, None, None

        detected_samples       = self._detect_sample_types(query)
        detected_neighborhoods = self._detect_neighborhoods(query)
        detected_pesticide     = self._detect_pesticide(query)

        prompt = self._build_llm_sql_prompt(
            query, detected_samples, detected_neighborhoods, detected_pesticide
        )

        generated_sql: Optional[str] = None
        try:
            # Determine which LLM interface to use
            if llm_model is not None:
                if hasattr(llm_model, "chat") and hasattr(llm_model.chat, "completions"):
                    # OpenAI-compatible (GPT / local Ollama via openai SDK)
                    model_name = getattr(self, "_llm_model_name", "gpt-4o-mini")
                    resp = llm_model.chat.completions.create(
                        model=model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a SQL expert. Return ONLY valid DuckDB SQL.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.0,
                    )
                    generated_text = resp.choices[0].message.content
                else:
                    # Gemini (google.generativeai GenerativeModel)
                    generated_text = llm_model.generate_content(prompt).text
            else:
                # Ollama client (self.llm_client)
                resp = self.llm_client.chat(
                    model=OLLAMA_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.1},
                )
                generated_text = resp["message"]["content"]

            # ── Extract SQL from response ──
            sql_match = re.search(
                r"```sql\n?(.*?)```", generated_text, re.DOTALL | re.IGNORECASE
            ) or re.search(r"```\n?(.*?)```", generated_text, re.DOTALL)

            if sql_match:
                generated_sql = sql_match.group(1).strip()
            else:
                generated_sql = generated_text.replace("```", "").strip()

            if not generated_sql.upper().startswith("SELECT"):
                logging.warning("LLM returned non-SELECT SQL — skipping execution")
                return response_text, None, generated_sql

            # ── Execute SQL ──
            con = self._get_connection()
            try:
                df = con.execute(generated_sql).df()
            except Exception as sql_err:
                logging.warning(f"LLM SQL execution failed: {sql_err}")
                con.close()
                return (
                    f"❌ AI-generated SQL had an error: `{sql_err}`\n\n"
                    "Try rephrasing your question.",
                    None,
                    generated_sql,
                )
            con.close()

            if not df.empty:
                response_text = (
                    f"🤖 **AI-generated result ({len(df)} rows):**\n\n"
                    + df.head(50).to_markdown(index=False)
                )
            else:
                response_text = (
                    "⚠️ The query ran successfully but returned no results. "
                    "Try rephrasing."
                )

            return response_text, df, generated_sql

        except Exception as exc:
            logging.error(f"LLM fallback failed: {exc}")
            return response_text, None, generated_sql

    def _handle_unknown_query(self, query: str) -> str:
        """Handle unknown queries"""
        response = "⚠️ **Sorry, I couldn't fully understand your question.**\n\n"
        response += "📝 **Examples of supported questions:**\n"
        response += "• How many samples of tomato, cucumber, and zucchini?\n"
        response += "• How many tomato samples are above limit?\n"
        response += "• What are the non-compliant samples?\n"
        response += "• What pesticides are in cucumber?\n"
        response += "• Pesticides in Al Iskan and Al Nahda neighborhoods\n"
        response += "• Neighborhood ranking by violations\n"
        response += "• Comprehensive analysis of tomatoes\n"
        response += "• What is the maximum concentration of imidacloprid?\n"
        response += "• Search for fipronil in beans\n"
        response += "• Samples containing 6 pesticides\n"
        return response
