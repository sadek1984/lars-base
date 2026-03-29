"""
unified_query_processor.py
=========================
معالج استعلامات هجين متعدد الطبقات

⚠️  DEPRECATED — do not add new logic here.
    This module duplicates CoreQueryEngine (core_query_engine.py), which is
    the single canonical query processor.  All new query handling belongs in
    CoreQueryEngine.  This file is kept only to avoid breaking any callers
    that still import UnifiedQueryProcessor; they should be migrated to use
    CoreQueryEngine.process_with_gemini_fallback() instead.
"""
import re
import duckdb
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from modules.mappings import (
    SAMPLE_CORRECTIONS,
    SAMPLE_AR_TO_EN,
    SAMPLE_EN_TO_AR,
    PESTICIDE_AR_TO_EN,
    NEIGHBORHOOD_CORRECTIONS,
    normalize_arabic_query,
)

# Try to import OpenAI, but make it optional
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    OpenAI = None


class QueryIntent(Enum):
    """أنواع الاستعلامات"""
    FIND_PESTICIDE = "find_pesticide"
    COUNT_SAMPLES = "count_samples"
    LIST_PESTICIDES = "list_pesticides"
    STATISTICS = "statistics"
    COMPARISON = "comparison"
    NEIGHBORHOOD_ANALYSIS = "neighborhood_analysis"
    ESTABLISHMENT_QUERY = "establishment_query"
    RANKING = "ranking"
    COMPLEX_AGGREGATION = "complex_aggregation"
    UNKNOWN = "unknown"


@dataclass
class QueryContext:
    """سياق الاستعلام المستخرج"""
    intent: QueryIntent
    pesticides: List[str]
    samples: List[str]
    neighborhoods: List[str]
    filters: Dict[str, Any]
    aggregations: List[str]
    confidence: float


class UnifiedQueryProcessor:
    """معالج استعلامات هجين متعدد الطبقات"""
    
    def __init__(self, db_path: str, llm_client: Optional[Any] = None):
        self.db_path = db_path
        self.llm = llm_client
        
        # Initialize LLM if not provided
        if self.llm is None and HAS_OPENAI:
            try:
                self.llm = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
            except:
                self.llm = None
        self.sample_types = {
            'ar_to_pattern': SAMPLE_CORRECTIONS,
            'en_to_ar': SAMPLE_EN_TO_AR,
        }
        self.pesticides = {
            'ar_to_en': PESTICIDE_AR_TO_EN,
            'en_variants': {},  # Keep if you need English variant matching
        }
        self.neighborhoods = NEIGHBORHOOD_CORRECTIONS

        # SQL Templates
        self.sql_templates = self._load_sql_templates()
        
        # Pattern matchers
        self.pattern_matchers = self._compile_pattern_matchers()
    
    def process(self, query: str) -> Tuple[str, Optional[pd.DataFrame]]:
        """
        معالجة الاستعلام عبر الطبقات المتعددة
        
        Layer 1: Quick Pattern Matching (90% of queries)
        Layer 2: Intent Classification + Entity Extraction
        Layer 3: SQL Generation (Template + LLM)
        Layer 4: Query Validation & Execution
        Layer 5: Response Generation
        """
        print(f"🔍 Processing query: {query[:100]}...")
        
        # Normalize query
        query_normalized = normalize_arabic_query(query)
        
        # ============================================================
        # Layer 1: Quick Pattern Matching
        # ============================================================
        result = self._try_pattern_matching(query_normalized)
        if result:
            print("✅ Matched via Pattern Matching (Layer 1)")
            return result
        
        # ============================================================
        # Layer 2: Intent Classification + Entity Extraction
        # ============================================================
        context = self._classify_and_extract(query_normalized)
        print(f"📊 Intent: {context.intent.value}, Confidence: {context.confidence:.2f}")
        
        # ============================================================
        # Layer 3: SQL Generation
        # ============================================================
        if context.confidence > 0.7:
            # Use template-based generation
            sql = self._generate_sql_from_template(context)
        else:
            # Use LLM for complex queries
            sql = self._generate_sql_with_llm(query_normalized, context)
        
        if not sql:
            return self._handle_unknown_query(query), None
        
        # ============================================================
        # Layer 4: Execute
        # ============================================================
        df = self._execute_sql(sql)
        
        # ============================================================
        # Layer 5: Generate Response
        # ============================================================
        response = self._generate_response(context, df, query)
        
        return response, df
    
    # ============================================================
    # Layer 1: Pattern Matching
    # ============================================================
    
    def _compile_pattern_matchers(self) -> List[Dict]:
        """تجميع أنماط الكشف السريع"""
        # IMPORTANT: Order matters! More specific patterns should come first.
        # 'samples_with_n_pesticides' must come before 'count_samples_limit'
        # because both can match queries with "عدد" but the former is more specific.
        return [
            {
                'name': 'find_pesticide_in_sample',
                'pattern': self._create_find_pattern(),
                'handler': self._handle_find_pesticide
            },
            {
                # More specific: queries about N pesticides (e.g., "عينات بـ 6 مبيدات")
                'name': 'samples_with_n_pesticides',
                'pattern': r'(?:عدد|عينات|samples?|تحتوي|contain).*?(\d+)\s*(?:مبيد|مبيدات|pesticide)',
                'handler': self._handle_n_pesticides
            },
            {
                # Less specific: count samples above/below limit (no pesticide count)
                'name': 'count_samples_limit',
                'pattern': self._create_count_pattern(),
                'handler': self._handle_count_samples
            },
            {
                'name': 'list_pesticides',
                'pattern': r'(?:ماهي|المبيدات|what|pesticides).*(?:في|in)',
                'handler': self._handle_list_pesticides
            },
            {
                'name': 'neighborhood_pesticides',
                'pattern': r'(?:المبيدات|مبيدات).*(?:حي|أحياء|neighborhood)',
                'handler': self._handle_neighborhood_pesticides
            },
            {
                'name': 'ranking_neighborhoods',
                'pattern': r'(?:ترتيب|ranking|الاكثر|الأكثر).*(?:حي|أحياء|احياء)',
                'handler': self._handle_neighborhood_ranking
            }
        ]
    
    def _create_find_pattern(self) -> str:
        """نمط البحث عن مبيد"""
        find_keywords = r'(?:find|ابحث|اعثر|اوجد|search)'
        in_keywords = r'(?:في|in|inside)'
        return f'{find_keywords}.*{in_keywords}'
    
    def _create_count_pattern(self) -> str:
        """نمط عد العينات"""
        count_kw = r'(?:count|عدد|كم|how many|ماهي)'
        limit_kw = r'(?:فوق|تحت|above|below|exceeding|limit|الحد)'
        return f'{count_kw}.*{limit_kw}'
    
    def _try_pattern_matching(self, query: str) -> Optional[Tuple[str, pd.DataFrame]]:
        """محاولة المطابقة السريعة"""
        for matcher in self.pattern_matchers:
            if re.search(matcher['pattern'], query, re.IGNORECASE):
                try:
                    return matcher['handler'](query)
                except Exception as e:
                    print(f"⚠️ Pattern handler failed: {e}")
                    continue
        return None
    
    # ============================================================
    # Layer 2: Intent Classification + Entity Extraction
    # ============================================================
    
    def _classify_and_extract(self, query: str) -> QueryContext:
        """تصنيف النية واستخراج الكيانات"""
        
        # Extract entities first (rule-based - fast and accurate)
        pesticides = self._extract_pesticides(query)
        samples = self._extract_samples(query)
        neighborhoods = self._extract_neighborhoods(query)
        filters = self._extract_filters(query)
        aggregations = self._extract_aggregations(query)
        
        # Classify intent using rules first, then LLM if needed
        intent, confidence = self._classify_intent(query, pesticides, samples, neighborhoods)
        
        return QueryContext(
            intent=intent,
            pesticides=pesticides,
            samples=samples,
            neighborhoods=neighborhoods,
            filters=filters,
            aggregations=aggregations,
            confidence=confidence
        )
    
    def _extract_pesticides(self, query: str) -> List[str]:
        """استخراج المبيدات بطريقة حتمية"""
        detected = []
        
        # Arabic names
        for ar_name, en_name in self.pesticides['ar_to_en'].items():
            if ar_name in query:
                if en_name not in detected:
                    detected.append(en_name)
        
        # English names with variants
        query_lower = query.lower()
        for en_name, variants in self.pesticides['en_variants'].items():
            for variant in variants:
                if variant in query_lower:
                    if en_name not in detected:
                        detected.append(en_name)
        
        return detected
    
    def _extract_samples(self, query: str) -> List[str]:
        """استخراج أنواع العينات"""
        detected = []
        
        for ar_name, pattern in self.sample_types['ar_to_pattern'].items():
            if ar_name in query:
                if pattern not in detected:
                    detected.append(pattern)
        
        query_lower = query.lower()
        for en_name, ar_pattern in self.sample_types['en_to_ar'].items():
            if en_name in query_lower:
                if ar_pattern not in detected:
                    detected.append(ar_pattern)
        
        return detected
    
    def _extract_neighborhoods(self, query: str) -> List[str]:
        """استخراج الأحياء"""
        detected = []
        
        for ar_name, normalized in self.neighborhoods.items():
            if ar_name in query:
                if normalized not in detected:
                    detected.append(normalized)
        
        return detected
    
    def _extract_filters(self, query: str) -> Dict[str, Any]:
        """استخراج الفلاتر"""
        filters = {}
        
        # Compliance filter
        if any(kw in query.lower() or kw in query 
               for kw in ['فوق الحد', 'above limit', 'exceeding', 'non compliant', 'غير مطابق', 'مخالف', 'راسب']):
            filters['is_compliant'] = 0
        elif any(kw in query.lower() or kw in query 
                 for kw in ['تحت الحد', 'below limit', 'within', 'compliant', 'مطابق', 'ناجح', 'سليم']):
            filters['is_compliant'] = 1
        
        # Ratio filter
        ratio_match = re.search(r'(?:more than|أكثر من)\s*(\d+)\s*(?:times|x|ضعف|أضعاف)', 
                               query, re.IGNORECASE)
        if ratio_match:
            filters['exceedance_ratio'] = f"> {ratio_match.group(1)}"
        
        # Separately flag
        if any(kw in query for kw in ['كل علي حده', 'كل على حده', 'separately', 'each']):
            filters['show_separately'] = True
        
        # Unique flag
        if any(kw in query for kw in ['فريدة', 'الفريدة', 'unique', 'distinct']):
            filters['unique_only'] = True
        
        # Year filter
        year_match = re.search(r'(20\d{2})', query)
        if year_match:
            filters['year'] = int(year_match.group(1))
        
        return filters
    
    def _extract_aggregations(self, query: str) -> List[str]:
        """استخراج العمليات الإحصائية المطلوبة"""
        aggs = []
        
        agg_keywords = {
            'count': ['عدد', 'كم', 'count', 'number'],
            'avg': ['متوسط', 'average', 'mean'],
            'max': ['اعلى', 'أعلى', 'max', 'maximum', 'highest'],
            'min': ['اقل', 'أقل', 'min', 'minimum', 'lowest'],
            'median': ['وسيط', 'median'],
            'sum': ['اجمالي', 'إجمالي', 'total', 'sum'],
            'range': ['المدى', 'range']
        }
        
        for agg_type, keywords in agg_keywords.items():
            if any(kw in query for kw in keywords):
                aggs.append(agg_type)
        
        return aggs if aggs else ['count']
    
    def _classify_intent(self, query: str, pesticides: List[str], 
                        samples: List[str], neighborhoods: List[str]) -> Tuple[QueryIntent, float]:
        """تصنيف النية باستخدام قواعد + LLM"""
        
        query_lower = query.lower()
        
        # Find pesticide pattern
        if (('find' in query_lower or 'ابحث' in query or 'اوجد' in query) and 
            (pesticides or samples)):
            return QueryIntent.FIND_PESTICIDE, 0.95
        
        # Count pattern
        if any(kw in query for kw in ['عدد', 'كم', 'count', 'how many']):
            if any(kw in query for kw in ['مبيد', 'pesticide']):
                return QueryIntent.COUNT_SAMPLES, 0.9
            if samples:
                return QueryIntent.COUNT_SAMPLES, 0.85
        
        # List pattern
        if ('ماهي' in query or 'المبيدات' in query) and samples:
            return QueryIntent.LIST_PESTICIDES, 0.9
        
        # Statistics pattern
        if any(kw in query for kw in ['اعلى', 'اقل', 'متوسط', 'وسيط', 'max', 'min', 'avg']):
            return QueryIntent.STATISTICS, 0.9
        
        # Neighborhood pattern
        if neighborhoods or 'حي' in query or 'احياء' in query or 'أحياء' in query:
            return QueryIntent.NEIGHBORHOOD_ANALYSIS, 0.85
        
        # Ranking pattern
        if any(kw in query for kw in ['ترتيب', 'ranking', 'تنازلي', 'تصاعدي', 'الاكثر', 'الأكثر']):
            return QueryIntent.RANKING, 0.85
        
        # Establishment pattern
        if any(kw in query for kw in ['منشأة', 'منشاة', 'المستلم', 'establishment']):
            return QueryIntent.ESTABLISHMENT_QUERY, 0.85
        
        # Use LLM for unclear cases
        if self.llm:
            return self._classify_with_llm(query)
        
        return QueryIntent.UNKNOWN, 0.3
    
    def _classify_with_llm(self, query: str) -> Tuple[QueryIntent, float]:
        """تصنيف باستخدام LLM"""
        prompt = f"""Classify this query about pesticide data into one intent:
1. FIND_PESTICIDE - searching for pesticide in samples
2. COUNT_SAMPLES - counting samples with conditions
3. LIST_PESTICIDES - listing pesticides in a sample type
4. STATISTICS - calculating statistics
5. NEIGHBORHOOD_ANALYSIS - analyzing by neighborhoods
6. ESTABLISHMENT_QUERY - querying by establishment
7. RANKING - ranking items
8. UNKNOWN - cannot determine

Query: "{query}"

Respond with just: Intent: <name>, Confidence: <0-1>"""
        
        try:
            response = self.llm.chat.completions.create(
                model="gemma3:4b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=50
            )
            
            result = response.choices[0].message.content.strip()
            
            intent_match = re.search(r'Intent:\s*(\w+)', result)
            conf_match = re.search(r'Confidence:\s*([\d.]+)', result)
            
            if intent_match:
                intent_str = intent_match.group(1).upper()
                confidence = float(conf_match.group(1)) if conf_match else 0.5
                
                intent_map = {
                    'FIND_PESTICIDE': QueryIntent.FIND_PESTICIDE,
                    'COUNT_SAMPLES': QueryIntent.COUNT_SAMPLES,
                    'LIST_PESTICIDES': QueryIntent.LIST_PESTICIDES,
                    'STATISTICS': QueryIntent.STATISTICS,
                    'NEIGHBORHOOD_ANALYSIS': QueryIntent.NEIGHBORHOOD_ANALYSIS,
                    'ESTABLISHMENT_QUERY': QueryIntent.ESTABLISHMENT_QUERY,
                    'RANKING': QueryIntent.RANKING,
                }
                
                return intent_map.get(intent_str, QueryIntent.UNKNOWN), confidence
        
        except Exception as e:
            print(f"⚠️ LLM classification failed: {e}")
        
        return QueryIntent.UNKNOWN, 0.3
    
    # ============================================================
    # Layer 3: SQL Generation
    # ============================================================
    
    def _generate_sql_from_template(self, context: QueryContext) -> Optional[str]:
        """توليد SQL من القوالب"""
        
        template_key = context.intent.value
        
        if template_key not in self.sql_templates:
            return None
        
        template = self.sql_templates[template_key]
        
        try:
            sql = template.format(
                pesticides=self._format_pesticide_filter(context.pesticides),
                samples=self._format_sample_filter(context.samples),
                neighborhoods=self._format_neighborhood_filter(context.neighborhoods),
                compliance_filter=self._format_compliance_filter(context.filters),
                ratio_filter=self._format_ratio_filter(context.filters),
                limit=context.filters.get('limit', 50)
            )
            return sql
        except Exception as e:
            print(f"⚠️ Template filling failed: {e}")
            return None
    
    def _generate_sql_with_llm(self, query: str, context: QueryContext) -> Optional[str]:
        """توليد SQL باستخدام LLM للاستعلامات المعقدة"""
        
        if not self.llm:
            return None
            
        from modules.translation_utils import get_language_system_prompt, detect_language
        
        schema_info = self._get_schema_info()
        
        context_str = f"""
Query Context:
- Intent: {context.intent.value}
- Pesticides: {', '.join(context.pesticides) if context.pesticides else 'None'}
- Samples: {', '.join(context.samples) if context.samples else 'None'}
- Neighborhoods: {', '.join(context.neighborhoods) if context.neighborhoods else 'None'}
- Filters: {context.filters}
"""

        lang = detect_language(query)
        lang_instructions = get_language_system_prompt(lang)
        
        prompt = f"""Generate a DuckDB SQL query.

Schema:
{schema_info}

{context_str}

Question: "{query}"

{lang_instructions}

Rules:
1. Use double quotes for Arabic columns: "اسم العينة"
2. Use ILIKE for case-insensitive
3. is_compliant = 1 means compliant, 0 means violation
4. Add LIMIT 50

Generate ONLY the SQL:"""
        
        try:
            response = self.llm.chat.completions.create(
                model="gemma3:4b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=500
            )
            
            sql = response.choices[0].message.content.strip()
            sql = sql.replace('```sql', '').replace('```', '').strip()
            
            if self._validate_sql(sql):
                return sql
            else:
                print("⚠️ Generated SQL failed validation")
                return None
        
        except Exception as e:
            print(f"⚠️ LLM SQL generation failed: {e}")
            return None
    
    def _validate_sql(self, sql: str) -> bool:
        """التحقق من صحة SQL"""
        if not sql:
            return False
        
        sql_lower = sql.lower()
        
        if 'select' not in sql_lower:
            return False
        
        if 'from' not in sql_lower:
            return False
        
        # No dangerous operations
        dangerous = ['drop', 'delete', 'insert', 'update', 'truncate', 'alter']
        if any(op in sql_lower for op in dangerous):
            return False
        
        # Dry run
        try:
            con = duckdb.connect(self.db_path, read_only=True)
            con.execute(f"EXPLAIN {sql}")
            con.close()
            return True
        except:
            return False
    
    # ============================================================
    # Layer 4: Execution
    # ============================================================
    
    def _execute_sql(self, sql: str) -> pd.DataFrame:
        """تنفيذ SQL مع معالجة الأخطاء"""
        try:
            con = duckdb.connect(self.db_path, read_only=True)
            df = con.execute(sql).df()
            con.close()
            
            print(f"✅ Query executed: {len(df)} rows returned")
            return df
        
        except Exception as e:
            print(f"❌ SQL execution failed: {e}")
            print(f"SQL: {sql}")
            return pd.DataFrame()
    
    # ============================================================
    # Layer 5: Response Generation
    # ============================================================
    
    def _generate_response(self, context: QueryContext, 
                          df: pd.DataFrame, query: str) -> str:
        """توليد رد مناسب بناءً على النتائج"""
        
        if df.empty:
            return self._generate_empty_response(context, query)
        
        if context.intent == QueryIntent.FIND_PESTICIDE:
            return self._format_find_response(df, context)
        elif context.intent == QueryIntent.COUNT_SAMPLES:
            return self._format_count_response(df, context)
        elif context.intent == QueryIntent.LIST_PESTICIDES:
            return self._format_list_response(df, context)
        elif context.intent == QueryIntent.STATISTICS:
            return self._format_statistics_response(df, context)
        elif context.intent == QueryIntent.RANKING:
            return self._format_ranking_response(df, context)
        elif context.intent == QueryIntent.NEIGHBORHOOD_ANALYSIS:
            return self._format_neighborhood_response(df, context)
        else:
            return self._format_generic_response(df, context)
    
    def _generate_empty_response(self, context: QueryContext, query: str) -> str:
        """رد عند عدم وجود نتائج"""
        
        response = "⚠️ **لم أجد نتائج مطابقة لسؤالك.**\n\n"
        response += "💡 **اقتراحات:**\n"
        
        if context.pesticides:
            response += f"• تأكد من كتابة اسم المبيد: {', '.join(context.pesticides)}\n"
        
        if context.samples:
            response += f"• تأكد من نوع العينة: {', '.join(context.samples)}\n"
        
        response += "• جرب صياغة السؤال بطريقة مختلفة\n"
        
        return response
    
    def _format_find_response(self, df: pd.DataFrame, context: QueryContext) -> str:
        """تنسيق رد البحث عن مبيد"""
        
        pesticide_display = ', '.join(context.pesticides) if context.pesticides else "المبيدات"
        sample_display = ' + '.join(context.samples) if context.samples else "جميع العينات"
        
        response = f"🔍 **نتائج البحث: {pesticide_display} في {sample_display}**\n\n"
        
        total = len(df)
        
        if 'status' in df.columns:
            compliant = len(df[df['status'] == 'مطابق'])
            non_compliant = total - compliant
            
            response += f"📊 **الإحصائيات:**\n"
            response += f"• إجمالي النتائج: {total}\n"
            response += f"• مطابق: {compliant}\n"
            response += f"• غير مطابق: {non_compliant}\n\n"
        else:
            response += f"📊 إجمالي النتائج: {total}\n\n"
        
        if len(df) <= 10:
            response += "📋 **التفاصيل:**\n"
            response += df.to_markdown(index=False)
        else:
            response += "📋 **عينة من النتائج (أول 10):**\n"
            response += df.head(10).to_markdown(index=False)
            response += f"\n\n💾 *الملف المرفق يحتوي على جميع الـ {total} نتيجة*"
        
        return response
    
    def _format_count_response(self, df: pd.DataFrame, context: QueryContext) -> str:
        """تنسيق رد العد"""
        
        response = "📊 **نتائج العد:**\n\n"
        
        if 'total_samples' in df.columns:
            total = int(df['total_samples'].sum())
            response += f"• إجمالي العينات: {total}\n"
            
            if 'above_limit' in df.columns:
                above = int(df['above_limit'].sum())
                response += f"• فوق الحد: {above}\n"
            
            if 'below_limit' in df.columns:
                below = int(df['below_limit'].sum())
                response += f"• تحت الحد: {below}\n"
        
        response += "\n📋 **التفاصيل:**\n"
        response += df.to_markdown(index=False)
        
        return response
    
    def _format_list_response(self, df: pd.DataFrame, context: QueryContext) -> str:
        """تنسيق رد القائمة"""
        
        sample_display = ' + '.join(context.samples) if context.samples else "العينات"
        
        response = f"🧪 **المبيدات في {sample_display}:**\n\n"
        
        if 'عدد_التكرار' in df.columns:
            total_detections = int(df['عدد_التكرار'].sum())
            unique_pesticides = len(df)
            
            response += f"📊 **الملخص:**\n"
            response += f"• عدد المبيدات المختلفة: {unique_pesticides}\n"
            response += f"• إجمالي الاكتشافات: {total_detections}\n"
            
            if 'عدد_المخالفات' in df.columns:
                total_violations = int(df['عدد_المخالفات'].sum())
                response += f"• إجمالي المخالفات: {total_violations}\n"
            
            response += "\n"
        
        response += "📋 **التفاصيل:**\n"
        response += df.to_markdown(index=False)
        
        return response
    
    def _format_statistics_response(self, df: pd.DataFrame, context: QueryContext) -> str:
        """تنسيق رد الإحصائيات"""
        
        response = "📊 **الإحصائيات:**\n\n"
        
        if not df.empty:
            row = df.iloc[0]
            
            for col in df.columns:
                col_display = col.replace('_', ' ').title()
                value = row[col]
                
                if isinstance(value, float):
                    response += f"• {col_display}: {value:.4f}\n"
                else:
                    response += f"• {col_display}: {value}\n"
        
        return response
    
    def _format_ranking_response(self, df: pd.DataFrame, context: QueryContext) -> str:
        """تنسيق رد الترتيب"""
        
        response = "🏆 **الترتيب:**\n\n"
        response += df.to_markdown(index=False)
        
        return response
    
    def _format_neighborhood_response(self, df: pd.DataFrame, context: QueryContext) -> str:
        """تنسيق رد الأحياء"""
        
        neighborhoods_display = ' + '.join(context.neighborhoods) if context.neighborhoods else "الأحياء"
        
        response = f"🏘️ **المبيدات في {neighborhoods_display}:**\n\n"
        
        if not df.empty:
            response += f"✅ وجدت {len(df)} سجل\n\n"
            response += df.to_markdown(index=False)
        else:
            response += "⚠️ لم أجد مبيدات في هذه الأحياء."
        
        return response
    
    def _format_generic_response(self, df: pd.DataFrame, context: QueryContext) -> str:
        """تنسيق عام"""
        
        response = "✅ **النتائج:**\n\n"
        
        if len(df) <= 15:
            response += df.to_markdown(index=False)
        else:
            response += df.head(15).to_markdown(index=False)
            response += f"\n\n💾 *الملف المرفق يحتوي على جميع الـ {len(df)} نتيجة*"
        
        return response
    
    def _handle_unknown_query(self, query: str) -> str:
        """معالجة الاستعلامات غير المعروفة"""
        
        response = "⚠️ **عذراً، لم أتمكن من فهم سؤالك بشكل كامل.**\n\n"
        
        response += "📝 **أمثلة على الأسئلة:**\n"
        response += "• ابحث عن الفيبرونيل في الطماطم\n"
        response += "• ما عدد عينات الخيار فوق الحد؟\n"
        response += "• ماهي المبيدات في الهيل؟\n"
        response += "• عينات تحتوي على 5 مبيدات\n"
        response += "• المبيدات في حي الإسكان\n"
        response += "• ترتيب الأحياء حسب المخالفات\n"
        
        return response
    
    # ============================================================
    # Pattern Handlers (Layer 1)
    # ============================================================
    
    def _handle_find_pesticide(self, query: str) -> Tuple[str, pd.DataFrame]:
        """معالج سريع للبحث عن مبيد"""
        pesticides = self._extract_pesticides(query)
        samples = self._extract_samples(query)
        filters = self._extract_filters(query)
        
        sql = """
        SELECT 
            "كود العينة" as sample_code,
            "اسم العينة" as sample_name,
            pesticide_name,
            concentration,
            limit_value,
            ROUND(exceedance_ratio, 2) as ratio,
            CASE WHEN is_compliant = 1 THEN 'مطابق' ELSE 'غير مطابق' END as status
        FROM chemistry_tidy
        WHERE is_detected = 1
        """
        
        if pesticides:
            conditions = [f"pesticide_name ILIKE '%{p}%'" for p in pesticides]
            sql += f" AND ({' OR '.join(conditions)})"
        
        if samples:
            conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
            sql += f" AND ({' OR '.join(conditions)})"
        
        if filters.get('is_compliant') is not None:
            sql += f" AND is_compliant = {filters['is_compliant']}"
        
        sql += " ORDER BY exceedance_ratio DESC LIMIT 50"
        
        df = self._execute_sql(sql)
        
        context = QueryContext(
            intent=QueryIntent.FIND_PESTICIDE,
            pesticides=pesticides,
            samples=samples,
            neighborhoods=[],
            filters=filters,
            aggregations=['count'],
            confidence=0.95
        )
        
        response = self._format_find_response(df, context)
        return response, df
    
    def _handle_count_samples(self, query: str) -> Tuple[str, pd.DataFrame]:
        """معالج سريع للعد"""
        samples = self._extract_samples(query)
        filters = self._extract_filters(query)
        
        if not samples:
            return "⚠️ لم أتمكن من تحديد نوع العينة.", pd.DataFrame()
        
        sql = """
        SELECT 
            "اسم العينة" as sample_type,
            COUNT(DISTINCT "كود العينة") as total_samples,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as above_limit,
            SUM(CASE WHEN is_above_limit = 0 AND is_detected = 1 THEN 1 ELSE 0 END) as below_limit
        FROM chemistry_tidy
        WHERE is_detected = 1
        """
        
        conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        sql += f" AND ({' OR '.join(conditions)})"
        sql += " GROUP BY \"اسم العينة\" ORDER BY total_samples DESC"
        
        df = self._execute_sql(sql)
        
        context = QueryContext(
            intent=QueryIntent.COUNT_SAMPLES,
            pesticides=[],
            samples=samples,
            neighborhoods=[],
            filters=filters,
            aggregations=['count'],
            confidence=0.9
        )
        
        response = self._format_count_response(df, context)
        return response, df
    
    def _handle_n_pesticides(self, query: str) -> Tuple[str, pd.DataFrame]:
        """معالج العينات بعدد مبيدات محدد"""
        match = re.search(r'(\d+)\s*(?:مبيد|مبيدات|pesticide)', query, re.IGNORECASE)
        if not match:
            return "⚠️ لم أتمكن من تحديد عدد المبيدات.", pd.DataFrame()
        
        n = int(match.group(1))
        samples = self._extract_samples(query)
        
        sql = f"""
        SELECT 
            "كود العينة" as sample_code,
            "اسم العينة" as sample_name,
            COUNT(*) as pesticide_count
        FROM chemistry_tidy
        WHERE is_detected = 1
        AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        """
        
        if samples:
            conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
            sql += f" AND ({' OR '.join(conditions)})"
        
        sql += f"""
        GROUP BY "كود العينة", "اسم العينة"
        HAVING COUNT(*) = {n}
        ORDER BY "كود العينة" DESC
        LIMIT 50
        """
        
        df = self._execute_sql(sql)
        
        sample_display = ' + '.join(samples) if samples else "جميع الأنواع"
        response = f"🔢 **عينات {sample_display} بـ {n} مبيدات:**\n\n"
        
        if not df.empty:
            response += f"✅ وجدت {len(df)} عينة\n\n"
            response += df.to_markdown(index=False)
        else:
            response += f"⚠️ لم أجد عينات بـ {n} مبيدات"
        
        return response, df
    
    def _handle_list_pesticides(self, query: str) -> Tuple[str, pd.DataFrame]:
        """معالج قائمة المبيدات"""
        samples = self._extract_samples(query)
        
        if not samples:
            return "⚠️ لم أتمكن من تحديد نوع العينة.", pd.DataFrame()
        
        conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        sample_filter = f"({' OR '.join(conditions)})"
        
        sql = f"""
        SELECT 
            pesticide_name as المبيد,
            COUNT(*) as عدد_التكرار,
            ROUND(AVG(concentration), 4) as متوسط_التركيز,
            ROUND(MAX(concentration), 4) as أعلى_تركيز,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as عدد_المخالفات
        FROM chemistry_tidy
        WHERE is_detected = 1
        AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        AND {sample_filter}
        GROUP BY pesticide_name
        ORDER BY عدد_التكرار DESC
        LIMIT 30
        """
        
        df = self._execute_sql(sql)
        
        context = QueryContext(
            intent=QueryIntent.LIST_PESTICIDES,
            pesticides=[],
            samples=samples,
            neighborhoods=[],
            filters={},
            aggregations=['count'],
            confidence=0.9
        )
        
        response = self._format_list_response(df, context)
        return response, df
    
    def _handle_neighborhood_pesticides(self, query: str) -> Tuple[str, pd.DataFrame]:
        """معالج المبيدات في الأحياء"""
        neighborhoods = self._extract_neighborhoods(query)
        
        if not neighborhoods:
            return "⚠️ لم أتمكن من تحديد الأحياء.", pd.DataFrame()
        
        conditions = [f"\"الحى\" LIKE '%{n}%'" for n in neighborhoods]
        neighborhood_filter = f"({' OR '.join(conditions)})"
        
        sql = f"""
        SELECT 
            "الحى" as الحي,
            pesticide_name as المبيد,
            COUNT(*) as عدد_الكشف,
            SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) as عدد_المخالفات,
            ROUND(AVG(concentration), 4) as متوسط_التركيز
        FROM chemistry_tidy
        WHERE is_detected = 1 
        AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        AND {neighborhood_filter}
        GROUP BY "الحى", pesticide_name
        ORDER BY "الحى", عدد_الكشف DESC
        LIMIT 50
        """
        
        df = self._execute_sql(sql)
        
        context = QueryContext(
            intent=QueryIntent.NEIGHBORHOOD_ANALYSIS,
            pesticides=[],
            samples=[],
            neighborhoods=neighborhoods,
            filters={},
            aggregations=['count'],
            confidence=0.9
        )
        
        response = self._format_neighborhood_response(df, context)
        return response, df
    
    def _handle_neighborhood_ranking(self, query: str) -> Tuple[str, pd.DataFrame]:
        """معالج ترتيب الأحياء"""
        sql = """
        SELECT 
            "الحى" as الحي,
            COUNT(DISTINCT "كود العينة") as عدد_العينات,
            SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) as عدد_المخالفات,
            ROUND(SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) * 100.0 / 
                  NULLIF(COUNT(DISTINCT "كود العينة"), 0), 2) as نسبة_المخالفات
        FROM chemistry_tidy
        WHERE "الحى" IS NOT NULL AND "الحى" != ''
        GROUP BY "الحى"
        ORDER BY عدد_المخالفات DESC
        LIMIT 20
        """
        
        df = self._execute_sql(sql)
        
        response = "🏘️ **ترتيب الأحياء حسب المخالفات (تنازلي):**\n\n"
        
        if not df.empty:
            response += df.to_markdown(index=False)
        else:
            response += "⚠️ لم أجد بيانات."
        
        return response, df
    
    # ============================================================
    # Helpers
    # ============================================================
    
    def _normalize_query(self, query: str) -> str:
        """تطبيع الاستعلام"""
        arabic_numerals = {'٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
                          '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'}
        for ar, en in arabic_numerals.items():
            query = query.replace(ar, en)
        
        num_words = {'واحد': '1', 'اثنين': '2', 'ثلاثة': '3', 'اربعة': '4',
                    'خمسة': '5', 'ستة': '6', 'سبعة': '7', 'ثمانية': '8',
                    'تسعة': '9', 'عشرة': '10'}
        for word, num in num_words.items():
            query = query.replace(word, num)
        
        return query
    
    def _load_neighborhood_mappings(self) -> Dict:
        """تحميل خرائط الأحياء"""
        return {
            'الإسكان': 'الإسكان', 'الاسكان': 'الإسكان', 'اسكان': 'الإسكان',
            'الريان': 'الريان', 'ريان': 'الريان',
            'النهضة': 'النهضة', 'نهضة': 'النهضة',
            'الأخضر': 'الأخضر', 'الاخضر': 'الأخضر', 'اخضر': 'الأخضر',
            'الروضة': 'الروضة', 'روضة': 'الروضة',
            'النخيل': 'النخيل', 'نخيل': 'النخيل',
        }
    
    def _load_sql_templates(self) -> Dict[str, str]:
        """تحميل قوالب SQL"""
        return {
            'find_pesticide': """
                SELECT 
                    "كود العينة" as sample_code,
                    "اسم العينة" as sample_name,
                    pesticide_name,
                    concentration,
                    limit_value,
                    ROUND(exceedance_ratio, 2) as ratio,
                    CASE WHEN is_compliant = 1 THEN 'مطابق' ELSE 'غير مطابق' END as status
                FROM chemistry_tidy
                WHERE is_detected = 1
                {pesticides}
                {samples}
                {compliance_filter}
                {ratio_filter}
                ORDER BY exceedance_ratio DESC
                LIMIT {limit}
            """,
            
            'count_samples': """
                SELECT 
                    "اسم العينة" as sample_type,
                    COUNT(DISTINCT "كود العينة") as total_samples,
                    SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as above_limit,
                    SUM(CASE WHEN is_above_limit = 0 AND is_detected = 1 THEN 1 ELSE 0 END) as below_limit
                FROM chemistry_tidy
                WHERE is_detected = 1
                {samples}
                GROUP BY "اسم العينة"
                ORDER BY total_samples DESC
            """,
            
            'list_pesticides': """
                SELECT 
                    pesticide_name as المبيد,
                    COUNT(*) as عدد_التكرار,
                    ROUND(AVG(concentration), 4) as متوسط_التركيز,
                    ROUND(MAX(concentration), 4) as أعلى_تركيز,
                    SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as عدد_المخالفات
                FROM chemistry_tidy
                WHERE is_detected = 1
                {samples}
                AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
                GROUP BY pesticide_name
                ORDER BY عدد_التكرار DESC
                LIMIT {limit}
            """,
            
            'neighborhood_analysis': """
                SELECT 
                    "الحى" as الحي,
                    pesticide_name as المبيد,
                    COUNT(*) as عدد_الكشف,
                    SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) as عدد_المخالفات
                FROM chemistry_tidy
                WHERE is_detected = 1
                {neighborhoods}
                AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
                GROUP BY "الحى", pesticide_name
                ORDER BY عدد_الكشف DESC
                LIMIT {limit}
            """,
        }
    
    def _get_schema_info(self) -> str:
        """الحصول على معلومات المخطط"""
        return """
Table: chemistry_tidy
Columns:
- "كود العينة" (INTEGER): Sample code
- "التاريخ" (TIMESTAMP): Date
- "اسم العينة" (VARCHAR): Sample name
- "نوع العينة" (VARCHAR): Sample type
- "الحى" (VARCHAR): Neighborhood
- pesticide_name (VARCHAR): Pesticide name
- concentration (DOUBLE): Concentration value
- limit_value (DOUBLE): Regulatory limit
- is_compliant (INTEGER): 1=compliant, 0=violation
- is_detected (INTEGER): 1=detected, 0=not detected
- exceedance_ratio (DOUBLE): concentration/limit_value
"""
    
    def _format_pesticide_filter(self, pesticides: List[str]) -> str:
        """تنسيق فلتر المبيدات"""
        if not pesticides:
            return ""
        conditions = [f"pesticide_name ILIKE '%{p}%'" for p in pesticides]
        return f"AND ({' OR '.join(conditions)})"
    
    def _format_sample_filter(self, samples: List[str]) -> str:
        """تنسيق فلتر العينات"""
        if not samples:
            return ""
        from modules.mappings import SAMPLE_AR_TO_EN
        conditions = []
        for s in samples:
            en_s = SAMPLE_AR_TO_EN.get(s, s)
            conditions.append(f"(\"اسم العينة\" LIKE '%{s}%' OR LOWER(\"اسم العينة\") LIKE '%{en_s.lower()}%')")
        return f"AND ({' OR '.join(conditions)})"
    
    def _format_neighborhood_filter(self, neighborhoods: List[str]) -> str:
        """تنسيق فلتر الأحياء"""
        if not neighborhoods:
            return ""
        conditions = [f"\"الحى\" LIKE '%{n}%'" for n in neighborhoods]
        return f"AND ({' OR '.join(conditions)})"
    
    def _format_compliance_filter(self, filters: Dict) -> str:
        """تنسيق فلتر المطابقة"""
        if 'is_compliant' not in filters:
            return ""
        return f"AND is_compliant = {filters['is_compliant']}"
    
    def _format_ratio_filter(self, filters: Dict) -> str:
        """تنسيق فلتر النسبة"""
        if 'exceedance_ratio' not in filters:
            return ""
        return f"AND exceedance_ratio {filters['exceedance_ratio']}"
