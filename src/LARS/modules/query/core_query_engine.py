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
- Time-period detection (last N days/weeks/months/years) applied across
  all handlers that make sense with a date filter
"""
import re
import duckdb
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import os
import logging

# ── Centralized mappings (replaces local dictionaries) ──
from modules.query.mappings import (
    SAMPLE_CORRECTIONS,
    SAMPLE_EN_TO_AR,
    NEIGHBORHOOD_CORRECTIONS,
    PESTICIDE_AR_TO_EN,
    CATEGORY_EN,
    normalize_arabic_query,
    get_pesticide_variants,
    get_pesticide_sql_filter,
    get_pesticide_sql_filter_params,
    normalize_arabic_text
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
    from modules.query.intent_router import IntentRouter, Intent, QueryEntities
    HAS_INTENT_ROUTER = True
except ImportError:
    HAS_INTENT_ROUTER = False
    IntentRouter = None
    Intent = None
    QueryEntities = None

# Database path — delegate to data_access so all modules use the same resolution
from modules.data.data_access import _DUCKDB_PATH as DB_PATH
from modules.utils.prompt_loader import load_prompt


from modules.query.advanced_handlers import AdvancedHandlersMixin
from modules.query.entity_detection import EntityDetectionMixin
from modules.query.entity_resolver import EntityResolver
from modules.query.messages import CANNOT_COMPUTE_RATE_MESSAGE, POLITE_ERROR_MESSAGE


class DatabaseUnavailableError(RuntimeError):
    """The DuckDB file is missing or cannot be opened (user-actionable)."""
from modules.query.time_period import TimePeriodMixin
from modules.query.routing import RoutingMixin
from modules.query.keyword_patterns import KeywordPatternsMixin
from modules.query.llm_fallback import LLMFallbackMixin

class CoreQueryEngine(
    AdvancedHandlersMixin,
    EntityDetectionMixin,
    TimePeriodMixin,
    RoutingMixin,
    KeywordPatternsMixin,
    LLMFallbackMixin,
):
    """
    محرك استعلامات مركزي موحد - بدون Streamlit
    Unified Query Engine - Streamlit-free
    
    Supports:
    - All query patterns from ai_assistant.py
    - LLM fallback for unknown queries
    - Dialect normalization (Egyptian + Saudi Arabic)
    - Time-period filters (last N days/weeks/months/years)
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
        self._resolver = None
        self._resolution_cache: Tuple[Optional[str], Any] = (None, None)
        
        # Initialize semantic pattern recognizer (optional)
        self.semantic_recognizer = get_semantic_recognizer() if HAS_SEMANTIC else None
        if self.semantic_recognizer:
            print("✅ Semantic Pattern Recognizer loaded!")
        else:
            print("ℹ️ Semantic Pattern Recognizer not available, using keyword matching only")
        
        # Initialize intent-based query router (optional)
        if HAS_INTENT_ROUTER:
            self.router = IntentRouter(dialect_synonyms=self.dialect_synonyms,
                                       resolver_provider=self._get_resolver)
            print("✅ Intent Router loaded!")
        else:
            self.router = None
            print("ℹ️ Intent Router not available, using pattern matching only")
    
    
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
        the centralized ``modules.query.mappings`` module.
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
    
    def _get_resolver(self):
        """EntityResolver over this DB's real values, built once. None if the DB is unavailable."""
        if self._resolver is None:
            try:
                con = self._get_connection()
                try:
                    self._resolver = EntityResolver(con)
                finally:
                    con.close()
            except Exception as exc:
                logging.warning(f"EntityResolver unavailable, using dictionary fallback: {exc}")
                return None
        return self._resolver

    def _resolve(self, query: str):
        """Resolution for `query`, cached for the current question (several extractors ask)."""
        resolver = self._get_resolver()
        if resolver is None:
            return None
        cached_q, cached_res = self._resolution_cache
        if cached_q != query:
            cached_res = resolver.resolve(query)
            self._resolution_cache = (query, cached_res)
        return cached_res

    def _unresolved_product_message(self, terms: List[str]) -> str:
        names = "، ".join(f"«{t}»" for t in terms)
        return (f"⚠️ لم أجد {names} ضمن أسماء العينات في البيانات الحالية. "
                f"تأكد من اسم المنتج، أو اسأل عن فئة (خضار، فواكه، توابل، مكسرات، حبوب).")

    def _unresolved_municipality_message(self) -> str:
        resolver = self._get_resolver()
        known = "، ".join(resolver.db_municipalities) if resolver else ""
        return f"⚠️ لم أتعرف على البلدية المذكورة في السؤال. البلديات المتاحة في البيانات: {known}"

    @staticmethod
    def _in_clause(column: str, values: List[str]) -> Tuple[str, List[str]]:
        """`"column" IN (?, ...)` plus its params — for exact resolved DB values."""
        return f'"{column}" IN ({", ".join("?" for _ in values)})', list(values)

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Return a read-only DuckDB connection.

        Raises RuntimeError with a user-readable message if the database
        file is missing or the connection fails, instead of propagating a
        cryptic DuckDB exception.
        """
        db_path = Path(self.db_path)
        if not db_path.exists():
            raise DatabaseUnavailableError(
                f"Database file not found: {db_path}\n"
                "Upload your data via the Data Management page to continue."
            )
        try:
            return duckdb.connect(str(db_path), read_only=True)
        except Exception as exc:
            # The DuckDB detail goes to the log (via __cause__), not to the user.
            raise DatabaseUnavailableError(
                f"Could not open database '{db_path.name}'. Please try again shortly "
                "or re-upload the data via the Data Management page."
            ) from exc
    


    
    
    


    def _resolved_facilities(self, query: str) -> List[str]:
        """Facility names (exact DB values) named in `query`, via the resolver."""
        res = self._resolve(query)
        return list(res.facilities) if res is not None else []

    def _handle_facility_search(self, facilities: List[str]) -> Tuple[str, pd.DataFrame]:
        """Detected residues in the given facilities (exact "اسم المنشاة" values
        resolved from the question — never text sliced around keywords)."""
        facility_sql, params = self._in_clause("اسم المنشاة", facilities)
        facility_name = " + ".join(facilities)
        con = self._get_connection()
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
        AND {facility_sql}
        ORDER BY TRY_STRPTIME("التاريخ", '%d/%m/%Y') DESC NULLS LAST
        LIMIT 50
        """
        
        df = con.execute(sql, params).df()
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
                                          detected_neighborhoods: List[str],
                                          date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
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
        date_clause = date_filter or ""
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
            {date_clause}
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
    
    


    def process(self, query: str) -> Tuple[str, Optional[pd.DataFrame]]:
        """
        Answer `query`. Wraps _process_unguarded() so that no handler failure
        ever reaches the user as raw error text: any exception is logged with
        its traceback and replaced by POLITE_ERROR_MESSAGE, and every result
        passes the percentage sanity guard.
        """
        try:
            response_text, df = self._process_unguarded(query)
        except DatabaseUnavailableError as db_err:
            logging.error(f"DB unavailable during query: {db_err.__cause__ or db_err}")
            return str(db_err), None
        except Exception:
            logging.exception(f"Query failed: {query!r}")
            return POLITE_ERROR_MESSAGE, None
        return self._guard_percentages(response_text, df)

    # Rate/percentage columns must lie in [0, 100]. Percent-of-MRL and
    # exceedance columns are excluded: 250% of the MRL is a legitimate value.
    _PCT_COLUMN_RE = re.compile(r"pct|rate|نسبة", re.IGNORECASE)
    _PCT_EXEMPT_RE = re.compile(r"mrl|exceed|ratio", re.IGNORECASE)

    def _guard_percentages(self, response_text: str, df: Optional[pd.DataFrame]):
        """Replace the answer with CANNOT_COMPUTE_RATE_MESSAGE if any percentage
        column holds a value outside 0–100 — a sign the rate was computed over
        the wrong denominator. Logs the offending column instead of showing it."""
        if df is None or df.empty:
            return response_text, df
        for col in df.columns:
            name = str(col)
            if not self._PCT_COLUMN_RE.search(name) or self._PCT_EXEMPT_RE.search(name):
                continue
            values = pd.to_numeric(df[col], errors="coerce").dropna()
            if not values.empty and (values.min() < 0 or values.max() > 100):
                logging.error(
                    f"Percentage out of range in column {name!r}: "
                    f"min={values.min()} max={values.max()} — answer suppressed"
                )
                return CANNOT_COMPUTE_RATE_MESSAGE, None
        return response_text, df

    def _process_unguarded(self, query: str) -> Tuple[str, Optional[pd.DataFrame]]:
        """
        Process a query and return (response_text, DataFrame | None).

        Three-tier routing, in priority order:
        1. Semantic pattern recognition  — embedding-based, confidence ≥ 0.75
        2. Intent-based routing          — entity extraction + intent classifier
        3. Keyword pattern cascade       — _dispatch_keyword_patterns()

        A time-period filter (detected_period) is extracted once in
        _extract_context() and threaded into every tier / handler that
        supports it. A human-readable date-range label (detected_period_label)
        is appended to the final response text exactly once, regardless of
        which tier produced the answer.
        """
        ctx = self._extract_context(query)
        query_normalized = ctx['query_normalized']
        query_lower      = ctx['query_lower']
        detected_samples      = ctx['detected_samples']
        detected_neighborhoods = ctx['detected_neighborhoods']
        detected_pesticide    = ctx['detected_pesticide']
        detected_period       = ctx['detected_period']
        period_label          = ctx['detected_period_label']

        result: Optional[Tuple[str, Optional[pd.DataFrame]]] = None

        self._last_query = query  # for _handle_out_of_scope's language detection

        # ── Tier -1: Out-of-scope gate — runs BEFORE any tier, including
        # Tier 2's intent router, so a superficial keyword match deep inside
        # a tier (e.g. the word "مبيدين" appearing inside an unrelated MOA
        # question) can never hijack an out-of-scope query into a wrong
        # answer. See core_query_engine.py's _check_out_of_scope() below.
        oos_result = self._check_out_of_scope(query, query_lower)
        if oos_result is not None:
            return oos_result

        # ── Unresolved entity gate: a product was named but matches nothing in
        # the data. Answer that honestly instead of letting a handler run a
        # filter that can only return 0 rows.
        resolution = ctx.get('resolution')
        if (resolution is not None and resolution.product_terms_unresolved
                and not resolution.products and not resolution.categories):
            return self._unresolved_product_message(resolution.product_terms_unresolved), None

        # ── Tier 0: Explicit compliance-status override ──────────────────────
        # Official lab verdict (sample_result) keywords — "غير مطابقة" / "راسبة" /
        # "مطابقة" etc. — must route straight to the compliance-table handler and
        # bypass semantic/intent tiers, which tend to misclassify these as
        # generic "above/below limit" (is_above_limit) queries. is_above_limit is
        # a *technical* per-pesticide reading vs its MRL; sample_result is the
        # chemist's *official* pass/fail decision — they are not the same thing.
        non_compliant_ar_kws = [
            'غير مطابقة', 'الغير مطابقة', 'غير المطابقة',
            'راسبة', 'الراسبة', 'راسب', 'رواسب', 'فاشلة', 'فشلت', 'مرفوضة',
        ]
        compliant_ar_kws = ['مطابقة', 'ناجحة', 'مقبولة']
        is_non_compliant_ar = any(kw in query for kw in non_compliant_ar_kws)
        is_compliant_ar = (not is_non_compliant_ar) and any(kw in query for kw in compliant_ar_kws)

        if is_non_compliant_ar or is_compliant_ar:
            result = self._handle_count_samples_compliance_table(
                detected_samples, detected_neighborhoods, is_non_compliant_ar,
                date_filter=detected_period,
                municipalities=resolution.municipalities if resolution is not None else None,
            )

        # ── Tier 1: Semantic pattern recognition ──────────────────────────────
        if result is None and self.semantic_recognizer:
            semantic_result = self.semantic_recognizer.recognize(query)
            if semantic_result and semantic_result['confidence'] >= 0.75:
                pattern_type = semantic_result['pattern_type']
                logging.debug(f"Semantic match: {pattern_type} ({semantic_result['confidence']:.2f})")
                result = self._route_by_semantic_pattern(
                    pattern_type, query, query_normalized, query_lower,
                    detected_samples, detected_neighborhoods, detected_pesticide,
                    date_filter=detected_period,
                )

        # ── Tier 2: Intent-based routing ──────────────────────────────────────
        if result is None and self.router:
            intent, entities = self.router.analyze(query)
            if intent != Intent.UNKNOWN:
                logging.info(
                    f"🎯 Intent: {intent.name} | samples={entities.samples} "
                    f"neighborhoods={entities.neighborhoods} category={entities.category} "
                    f"pesticide={entities.pesticide} period={detected_period}"
                )
                result = self._dispatch_by_intent(intent, entities, date_filter=detected_period)

        # ── Tier 3: Keyword pattern cascade ───────────────────────────────────
        if result is None:
            try:
                result = self._dispatch_keyword_patterns(ctx)
            except DatabaseUnavailableError as db_err:
                # DB missing or corrupt — show a clear message instead of a stack trace
                logging.error(f"DB connection error during query: {db_err.__cause__ or db_err}")
                return str(db_err), None

        # ── Fallback: nothing matched ───────────────────────────────────────────
        if result is None:
            result = (self._handle_unknown_query(query), None)

        response_text, df = result

        # ── Append date-range label once, regardless of which tier answered ───
        if period_label:
            response_text += f"\n\n📅 **الفترة الزمنية:** {period_label}"

        return response_text, df

   


    
    # Handlers
    
    def _handle_n_pesticides(self, n: int, samples: List[str],
                              date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """Samples with exactly N pesticides."""
        if n == 0:
            return self._handle_multiple_n_pesticides([0], samples, date_filter=date_filter)
        con = self._get_connection()
        
        sample_filter = ""
        if samples:
            sample_filter = f"AND {self._build_sample_filter(samples)}"
        date_clause = date_filter or ""
        
        sql = f"""
        SELECT 
            "كود العينة" AS sample_code,
            "اسم العينة" AS sample_name,
            COUNT(*) AS pesticide_count
        FROM chemistry_tidy
        WHERE is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        {sample_filter}
        {date_clause}
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

    def _handle_multiple_n_pesticides(self, counts: List[int], samples: List[str],
                                       date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """
        عينات بأعداد مختلفة من المبيدات (يشمل 0 = خالية)
        يدعم: "العينات الخالية من المبيدات و التي تحتوي علي مبيد واحد و ثلاث مبيدات"
        """
        con = self._get_connection()
    
        sample_filter = ""
        if samples:
            sample_filter = f"AND {self._build_sample_filter(samples)}"
        date_clause = date_filter or ""
    
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
                {date_clause}
            )
            SELECT 
                "كود العينة" as sample_code,
                "اسم العينة" as sample_name,
                0 as pesticide_count
            FROM chemistry_tidy
            WHERE "كود العينة" NOT IN (SELECT "كود العينة" FROM detected_samples)
            {sample_filter}
            {date_clause}
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
            {date_clause}
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
                                     is_above: bool, date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
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
        
        date_clause = date_filter or ""
        
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
            {date_clause}
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
                                          is_non_compliant: bool, date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
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
        
        date_clause = date_filter or ""
        
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
        {date_clause}
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

    def _handle_count_samples_compliance_table(self, samples: List[str], neighborhoods: List[str],
                                                 is_non_compliant: bool,
                                                 date_filter: Optional[str] = None,
                                                 municipalities: Optional[List[str]] = None,
                                                 ) -> Tuple[str, pd.DataFrame]:
        """
        Manager-style compliance summary based on sample_result (official lab
        verdict), NOT is_above_limit (technical per-pesticide exceedance).

        Returns one row per sample_type with sample_count / non_compliant /
        compliant columns — the shape managers ask for, e.g.:

            sample_type     sample_count  above_limit  below_limit
            Tomato          172           57           115
            Cherry Tomato   25            12           13
            Cluster Tomato  1             0            1

        Note: despite the historical "above_limit"/"below_limit" column
        naming convention used elsewhere in this file, THIS handler counts
        against sample_result, so its output columns are named
        non_compliant / compliant to avoid confusion with the technical
        is_above_limit metric used by _handle_count_samples_limit.
        """
        con = self._get_connection()

        params: List[str] = []
        sample_filter = ""
        if samples:
            sample_sql, sample_params = self._in_clause("اسم العينة", samples)
            sample_filter = f"AND {sample_sql}"
            params += sample_params

        neighborhood_filter = ""
        if neighborhoods:
            hood_variants = []
            for n in neighborhoods:
                hood_variants += sorted({n, n.replace('ا', 'إ'), n.replace('ا', 'أ'),
                                         n.replace('إ', 'ا'), n.replace('أ', 'ا')})
            neighborhood_filter = "AND (" + " OR ".join('"الحى" LIKE ?' for _ in hood_variants) + ")"
            params += [f"%{v}%" for v in hood_variants]

        # Municipality / association (exact DB values from the resolver), e.g.
        # 'جمعية البطين الزراعية' — previously ignored, so the answer covered all data.
        municipality_filter = ""
        if municipalities:
            mun_sql, mun_params = self._in_clause("اسم البلدية", municipalities)
            municipality_filter = f"AND {mun_sql}"
            params += mun_params

        date_clause = date_filter or ""

        sql = f"""
        SELECT
            "اسم العينة" AS sample_type,
            COUNT(DISTINCT "كود العينة") AS sample_count,
            COUNT(DISTINCT CASE WHEN sample_result = 'Non-Compliant' THEN "كود العينة" END) AS non_compliant,
            COUNT(DISTINCT CASE WHEN sample_result = 'Compliant' THEN "كود العينة" END) AS compliant
        FROM chemistry_tidy
        WHERE 1=1
        {sample_filter}
        {neighborhood_filter}
        {municipality_filter}
        {date_clause}
        GROUP BY "اسم العينة"
        ORDER BY sample_count DESC
        """
        df = con.execute(sql, params).df()
        # Headline totals are counted over the whole filter, not summed per
        # product: some sample codes appear under more than one product name,
        # so the per-product sum over-counts (e.g. 560 vs 530 distinct).
        totals = con.execute(f"""
        SELECT
            COUNT(DISTINCT "كود العينة") AS sample_count,
            COUNT(DISTINCT CASE WHEN sample_result = 'Non-Compliant' THEN "كود العينة" END) AS non_compliant,
            COUNT(DISTINCT CASE WHEN sample_result = 'Compliant' THEN "كود العينة" END) AS compliant
        FROM chemistry_tidy
        WHERE 1=1
        {sample_filter}
        {neighborhood_filter}
        {municipality_filter}
        {date_clause}
        """, params).df().iloc[0]
        con.close()

        type_display = " + ".join(samples) if samples else "All types"
        if neighborhoods:
            type_display += f" in {' + '.join(neighborhoods)}"
        if municipalities:
            type_display += f" — {' + '.join(municipalities)}"
        if date_filter:
            type_display += " (filtered by period)"

        if df.empty:
            return f"⚠️ No samples found for **{type_display}**", df

        status_text = 'Non-Compliant' if is_non_compliant else 'Compliant'
        total_count = int(totals['sample_count'])
        total_target = int(totals['non_compliant'] if is_non_compliant else totals['compliant'])

        response = f"📊 **{status_text} samples (official sample_result) — {type_display}**\n\n"
        response += f"✅ Total unique samples: **{total_count}**\n"
        response += f"📌 **{status_text}: {total_target}**\n\n"
        response += df.to_markdown(index=False)

        return response, df
    
    def _handle_list_pesticides(self, samples: List[str],
                                 date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """List pesticides found in a sample type."""
        con = self._get_connection()
        
        sample_filter = self._build_sample_filter(samples)
        date_clause = date_filter or ""
        
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
        {date_clause}
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
                                         show_separately: bool,
                                         date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """Pesticides detected in neighborhoods."""
        con = self._get_connection()
        date_clause = date_filter or ""
        
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
                {date_clause}
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
            {date_clause}
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
                                          samples: List[str],
                                          date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """Find a specific pesticide in samples — returns unique sample-level rows."""
        con = self._get_connection()
        
        pest_sql, pest_params = get_pesticide_sql_filter_params(pesticide)
        sample_sql, sample_params = self._in_clause("اسم العينة", samples)
        date_clause = date_filter or ""
        
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
        AND ({pest_sql})
        AND {sample_sql}
        {date_clause}
        ORDER BY "كود العينة" DESC
        LIMIT 100
        """
        
        df = con.execute(sql, pest_params + sample_params).df()
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
    
    def _handle_neighborhood_ranking(self, date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """Rank neighborhoods by samples with at least one exceedance.
        violation_rate_pct = violating samples / samples (never records / samples)."""
        con = self._get_connection()
        date_clause = date_filter or ""
        
        sql = f"""
        SELECT 
            "الحى"                             AS neighborhood,
            COUNT(DISTINCT "كود العينة")        AS total_samples,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations,
            COUNT(DISTINCT CASE WHEN is_above_limit = 1 THEN "كود العينة" END) AS violating_samples,
            ROUND(100.0 * COUNT(DISTINCT CASE WHEN is_above_limit = 1 THEN "كود العينة" END) /
                  NULLIF(COUNT(DISTINCT "كود العينة"), 0), 2) AS violation_rate_pct
        FROM chemistry_tidy
        WHERE "الحى" IS NOT NULL AND "الحى" != ''
        {date_clause}
        GROUP BY "الحى"
        ORDER BY violating_samples DESC, violation_rate_pct DESC
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
    
    def _handle_comprehensive_analysis(self, samples: List[str],
                                        date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """Comprehensive analysis of a sample type."""
        con = self._get_connection()
        
        sample_filter = self._build_sample_filter(samples)
        type_display = " + ".join(samples)
        date_clause = date_filter or ""
        
        distribution_sql = f"""
        WITH sample_pesticide_counts AS (
            SELECT 
                "كود العينة" AS sample_code,
                COUNT(CASE WHEN is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA') THEN 1 END) AS pesticide_count,
                SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS failing_count
            FROM chemistry_tidy
            WHERE {sample_filter}
            {date_clause}
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
        {date_clause}
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
                                 stats_requested: List[str],
                                 date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """Statistics for a specific pesticide."""
        con = self._get_connection()
        
        sample_filter = ""
        if samples:
            sample_filter = f"AND {self._build_sample_filter(samples)}"
        date_clause = date_filter or ""
        
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
        {date_clause}
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
    
    def _handle_samples_with_pesticide(self, pesticide: str,
                                        date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """All sample types containing a specific pesticide."""
        con = self._get_connection()
        date_clause = date_filter or ""
        
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
        {date_clause}
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
                                      neighborhoods: List[str],
                                      date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """Count unique sample codes."""
        con = self._get_connection()
        
        conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        sample_filter = f"({' OR '.join(conditions)})"
        
        neighborhood_filter = ""
        if neighborhoods:
            hood_conditions = [f"\"الحى\" LIKE '%{n}%'" for n in neighborhoods]
            neighborhood_filter = f"AND ({' OR '.join(hood_conditions)})"
        
        date_clause = date_filter or ""
        
        sql = f"""
        SELECT 
            "اسم العينة" AS sample_type,
            COUNT(DISTINCT "كود العينة") AS unique_samples,
            COUNT(*) AS total_records,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS above_limit_records
        FROM chemistry_tidy
        WHERE {sample_filter}
        {neighborhood_filter}
        {date_clause}
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
    
    def _handle_find_pesticide_all(self, pesticide: str,
                                    date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """Search for a pesticide across all sample types."""
        con = self._get_connection()
        date_clause = date_filter or ""
        
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
        {date_clause}
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
                                        both: bool = False, limit_filter: str = None, limit_desc: str = None,
                                        date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
        """
        عينات تحتوي على مبيد X فوق/تحت الحد أو غير مطابقة
        "عينات الطماطم التي تحتوي على مبيد البابروفيزن فوق الحد"
        "عينات الطماطم التي تحتوي على مبيد البابروفيزن غير مطابقة" (uses sample_result)
        """
        con = self._get_connection()
        
        # Build filters — DB stores English sample names
        sample_filter = self._build_sample_filter(samples)
        date_clause = date_filter or ""
        
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
        {date_clause}
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
            {date_clause}
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
                                     neighborhoods: List[str],
                                     date_filter: Optional[str] = None) -> Tuple[str, pd.DataFrame]:
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
        
        date_clause = date_filter or ""
        
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
            {date_clause}
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
    
    
    def _handle_violations_threshold(
        self,
        samples: List[str],
        neighborhoods: List[str],
        threshold: int,
        category_key: Optional[str] = None,
        date_filter: Optional[str] = None,
    ) -> Tuple[str, Optional[pd.DataFrame]]:
        """
        Find sample types with MORE THAN `threshold` violations (is_above_limit records).

        Args:
            samples:       Specific Arabic sample names (may be empty if category).
            neighborhoods: Optional neighborhood filter.
            threshold:     Minimum violation count (exclusive: > threshold).
            category_key:  Generic category ('vegetable', 'fruit', 'spice', 'nut', …).
                           When set, sample types are resolved from the DB.
            date_filter:   Optional SQL date filter fragment from _detect_time_period().
        """
        # Products (exact DB values) or the resolved "نوع العينة" category.
        sample_sql, params, _ = self._category_or_samples_filter(category_key, samples)
        if sample_sql is None:
            return f"⚠️ فئة غير معروفة في البيانات: {category_key}", None
        sample_filter = f"AND {sample_sql}"

        # ── Neighborhood filter ──
        neighborhood_filter = ""
        if neighborhoods:
            hood_variants = []
            for n in neighborhoods:
                hood_variants += sorted({n, n.replace("ا", "إ"), n.replace("ا", "أ"),
                                         n.replace("إ", "ا"), n.replace("أ", "ا")})
            neighborhood_filter = "AND (" + " OR ".join('"الحى" LIKE ?' for _ in hood_variants) + ")"
            params = params + [f"%{v}%" for v in hood_variants]

        date_clause = date_filter or ""

        # ── Main SQL: violation count per sample name ──
        # violations = exceeding detection records (the threshold's unit);
        # the rate is sample-level: samples with any exceedance / samples.
        sql = f"""
        SELECT
            "اسم العينة" AS sample_name,
            COUNT(*) AS total_records,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations,
            COUNT(DISTINCT "كود العينة") AS samples,
            COUNT(DISTINCT CASE WHEN is_above_limit = 1 THEN "كود العينة" END) AS violating_samples,
            ROUND(
                100.0 * COUNT(DISTINCT CASE WHEN is_above_limit = 1 THEN "كود العينة" END)
                / NULLIF(COUNT(DISTINCT "كود العينة"), 0),
                1
            ) AS violation_rate_pct
        FROM chemistry_tidy
        WHERE is_detected = 1
            AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
            {sample_filter}
            {neighborhood_filter}
            {date_clause}
        GROUP BY "اسم العينة"
        HAVING SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) > ?
        ORDER BY violations DESC
        """

        con = self._get_connection()
        df = con.execute(sql, params + [threshold]).df()
        con.close()

        # ── Pretty column names for display ──
        if not df.empty:
            df = df.rename(columns={"sample_name": "sample_type"})

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
        response += "• How many non-compliant/failed tomato samples last 3 months?\n"
        return response


def get_trust_badge(generated_sql: Optional[str]) -> str:
    """
    Returns a trust-level badge based on which tier answered the query.
    Tier 1 (template/pattern matched) never populates generated_sql.
    Tier 2 (LLM SQL generation) always does.
    """
    if generated_sql is None:
        return "✅ Verified query"
    return "🤖 AI-generated (verify results)"