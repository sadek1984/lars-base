"""
routing.py — extracted from core_query_engine.py (2026-09-18, Phase 3 split).

Tier dispatch: semantic-pattern routing, intent dispatch,
the out-of-scope gate, and the poisoning / inspection-priority /
category domain gates. Decides WHO answers, never HOW.
Methods are byte-identical to their pre-split versions; this module only
relocates them. RoutingMixin is mixed into CoreQueryEngine — methods refer to
engine state (self._get_connection(), detection helpers, handlers) via self.
"""
import logging
import re
from typing import List, Optional, Tuple

import pandas as pd

from modules.query.mappings import get_pesticide_sql_filter_params

# Intent router (optional - graceful fallback, same guard as core_query_engine)
try:
    from modules.query.intent_router import IntentRouter, Intent, QueryEntities
    HAS_INTENT_ROUTER = True
except ImportError:
    HAS_INTENT_ROUTER = False
    IntentRouter = None
    Intent = None
    QueryEntities = None


class RoutingMixin:
    def _route_by_semantic_pattern(self, pattern_type: str, query: str, query_normalized: str,
                                   query_lower: str, detected_samples: List[str],
                                   detected_neighborhoods: List[str], 
                                   detected_pesticide: Optional[str],
                                   date_filter: Optional[str] = None) -> Optional[Tuple[str, pd.DataFrame]]:
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
                return self._handle_count_samples_limit(samples, detected_neighborhoods, True, date_filter=date_filter)
            
            elif pattern_type == 'count_below_limit':
                samples = detected_samples if detected_samples else ['']
                return self._handle_count_samples_limit(samples, detected_neighborhoods, False, date_filter=date_filter)
            
            elif pattern_type == 'simple_count':
                if detected_samples:
                    # Return both above and below (is_above=None means show both)
                    return self._handle_count_samples_limit(detected_samples, detected_neighborhoods, None, date_filter=date_filter)
            
            elif pattern_type == 'comprehensive_analysis':
                if detected_samples:
                    return self._handle_comprehensive_analysis(detected_samples[0], date_filter=date_filter)
            
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
                            limit_filter=limit_filter, limit_desc=limit_desc, date_filter=date_filter
                        )
                    
                    return self._handle_find_pesticide_in_sample(detected_pesticide, detected_samples, date_filter=date_filter)
            
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
                        limit_filter=limit_filter, limit_desc=limit_desc, date_filter=date_filter
                    )
            
            elif pattern_type == 'list_pesticides':
                if detected_samples:
                    return self._handle_list_pesticides(detected_samples, date_filter=date_filter)
            
            elif pattern_type == 'neighborhood_pesticides':
                if detected_neighborhoods:
                    return self._handle_neighborhood_pesticides(detected_neighborhoods, show_separately, date_filter=date_filter)
            
            elif pattern_type == 'samples_with_n_pesticides':
                # Extract number from query
                import re
                numbers = re.findall(r'\d+', query)
                if numbers:
                    n_pesticides = int(numbers[0])
                    if 1 <= n_pesticides <= 50:
                        return self._handle_n_pesticides(n_pesticides, detected_samples, date_filter=date_filter)
            
            elif pattern_type == 'statistics':
                if detected_samples:
                    return self._handle_statistics(detected_samples[0], query)
            
            elif pattern_type == 'comprehensive_neighborhood_analysis':
                # This pattern handles queries like "ما هي انواع التوابل في حي الاسكان وما عددها وفوق/تحت الحد"
                # It requires neighborhood detection and will analyze all sample types in that neighborhood
                if detected_neighborhoods:
                    # Call the comprehensive neighborhood handler directly
                    # (it's implemented starting at line 603 in process())
                    return self._handle_comprehensive_neighborhood(query, detected_samples, detected_neighborhoods, date_filter=date_filter)
            
            elif pattern_type == 'facility_search':
                # Extract facility name from query
                return self._handle_facility_search(query)
            
            # Pattern recognized but couldn't be handled - fall back to keyword matching
            return None
            
        except Exception as e:
            logging.warning(f"Error in semantic routing: {e}")
            return None

    def _dispatch_by_intent(self, intent, entities, date_filter: Optional[str] = None) -> Optional[Tuple[str, Optional[pd.DataFrame]]]:
        """Route an intent + entities to the correct handler.
        
        Args:
            intent: Intent enum from IntentRouter
            entities: QueryEntities object with extracted information
            date_filter: SQL date filter fragment from _detect_time_period(), or None
        
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
                    query, entities.samples, entities.neighborhoods, date_filter=date_filter
                )
            
            if intent == Intent.NEIGHBORHOOD_PESTICIDES:
                return self._handle_neighborhood_pesticides(
                    entities.neighborhoods, entities.wants_separately, date_filter=date_filter
                )
            
            if intent == Intent.NEIGHBORHOOD_RANKING:
                return self._handle_neighborhood_ranking(date_filter=date_filter)
            
            # ── N pesticides ──
            if intent == Intent.COUNT_N_PESTICIDES and entities.n_pesticides:
                if len(entities.n_pesticides) > 1 and entities.wants_separately:
                    return self._handle_multiple_n_pesticides(entities.n_pesticides, entities.samples, date_filter=date_filter)
                return self._handle_n_pesticides(entities.n_pesticides[-1], entities.samples, date_filter=date_filter)
            
            # ── Pesticide queries ──
            if intent == Intent.FIND_PESTICIDE_IN_SAMPLE and entities.pesticide and entities.samples:
                if entities.wants_limit_breakdown:
                    return self._handle_sample_pesticide_limit(
                        entities.samples, entities.pesticide, 
                        entities.is_above_limit if entities.is_above_limit is not None else True,
                        date_filter=date_filter
                    )
                return self._handle_find_pesticide_in_sample(entities.pesticide, entities.samples, date_filter=date_filter)
            if intent == Intent.FIND_PESTICIDE_IN_CATEGORY and entities.pesticide and entities.category:
                # "ما هي الخضروات التي…" / "في أي التوابل…" ask WHICH products → one row per product
                which_products = entities.wants_types or bool(
                    re.search(r"(^|\s)(في\s+)?[أا]ي\s", entities.raw_query or ""))
                return self._handle_pesticide_in_category(entities.pesticide, entities.category,
                                                          date_filter=date_filter,
                                                          group_by_product=which_products)
            if intent == Intent.FIND_PESTICIDE_ALL and entities.pesticide:
                return self._handle_find_pesticide_all(entities.pesticide, date_filter=date_filter)
            
            if intent == Intent.LIST_PESTICIDES_IN_SAMPLE and entities.samples:
                return self._handle_list_pesticides(entities.samples, date_filter=date_filter)
            
            if intent == Intent.PESTICIDE_STATISTICS and entities.pesticide:
                return self._handle_pesticide_stats(
                    entities.pesticide, entities.samples, entities.stat_types, date_filter=date_filter
                )
            
            # ── Sample counting ──
            if intent == Intent.COUNT_SAMPLES_LIMIT and entities.samples:
                return self._handle_count_samples_limit(
                    entities.samples, entities.neighborhoods, entities.is_above_limit, date_filter=date_filter
                )
            
            if intent == Intent.COUNT_SAMPLES_SIMPLE and entities.samples:
                return self._handle_simple_sample_count(entities.samples, entities.neighborhoods, date_filter=date_filter)
            
            if intent == Intent.UNIQUE_COUNT and entities.samples:
                return self._handle_unique_samples_count(entities.samples, entities.neighborhoods, date_filter=date_filter)
            
            # ── Other ──
            if intent == Intent.COMPREHENSIVE_ANALYSIS and entities.samples:
                return self._handle_comprehensive_analysis(entities.samples, date_filter=date_filter)
            
            if intent == Intent.FACILITY_SEARCH:
                return self._handle_facility_search(query)
            
            if intent == Intent.RECIPIENT_SEARCH:
                return self._handle_facility_search(query)  # Same handler for now

            if intent.name.startswith("POISONING_"):
                text, df, _ = self._handle_poisoning(intent, query, entities)
                return text, df
            if intent.name.startswith("INSPECTION_PRIORITY_"):
                text, df, _ = self._handle_inspection_priority(intent, query, entities)
                return text, df

        except Exception as ex:
            logging.warning(f"Intent dispatch error for {intent}: {ex}")
        
        return None  # UNKNOWN → falls through to patterns/LLM

    def _handle_poisoning(self, intent, query, entities=None):
        from modules.poisoning import handle_poisoning
        con = self._get_connection()
        text, df, meta = handle_poisoning(con, intent, entities)
        return text, df, None

    def _handle_pesticide_in_category(self, pesticide: str, category_keyword: str,
                                   date_filter: Optional[str] = None,
                                   group_by_product: bool = False) -> Tuple[str, pd.DataFrame]:
        """Pesticide detections within a food category, filtered on the stored
        "نوع العينة" value (the router passes the resolved DB category).
        group_by_product=True answers "which products" with one row per product,
        so a large category is not truncated by the detection-row LIMIT."""
        sample_filter, cat_params, cat_name = self._category_or_samples_filter(category_keyword, [])
        if sample_filter is None:
            return f"⚠️ فئة غير معروفة في البيانات: {category_keyword}", pd.DataFrame()
        pest_sql, pest_params = get_pesticide_sql_filter_params(pesticide)
        params = pest_params + cat_params
        con = self._get_connection()
        date_clause = date_filter or ""

        if group_by_product:
            sql = f"""
            SELECT
                "اسم العينة" AS sample_name,
                COUNT(*) AS detections,
                COUNT(DISTINCT "كود العينة") AS unique_samples,
                COUNT(DISTINCT CASE WHEN sample_result = 'Non-Compliant' THEN "كود العينة" END) AS non_compliant
            FROM chemistry_tidy
            WHERE is_detected = 1
            AND ({pest_sql})
            AND {sample_filter}
            {date_clause}
            GROUP BY "اسم العينة"
            ORDER BY detections DESC
            """
            df = con.execute(sql, params).df()
            con.close()
            if df.empty:
                return f"⚠️ لم يتم رصد **{pesticide}** في **{cat_name}**", df
            response = f"🔍 **{pesticide} في {cat_name}:** ظهر في **{len(df)}** منتج\n\n"
            response += (f"✅ {int(df['unique_samples'].sum())} عينة فريدة | "
                         f"{int(df['detections'].sum())} سجل اكتشاف\n\n")
            response += df.to_markdown(index=False)
            return response, df

        sql = f"""
        SELECT
            "كود العينة"  AS sample_code,
            "اسم العينة" AS sample_name,
            pesticide_name AS pesticide,
            concentration  AS concentration,
            limit_value    AS mrl,
            ROUND(exceedance_ratio, 2) AS ratio,
            sample_result  AS status
        FROM chemistry_tidy
        WHERE is_detected = 1
        AND ({pest_sql})
        AND {sample_filter}
        {date_clause}
        ORDER BY "كود العينة" DESC
        LIMIT 100
        """
        df = con.execute(sql, params).df()
        con.close()

        if not df.empty:
            unique_samples = df['sample_code'].nunique()
            compliant     = len(df[df['status'] == 'Compliant'])
            non_compliant = len(df[df['status'] == 'Non-Compliant'])
            response = f"🔍 **{pesticide} في {cat_name}:**\n\n"
            response += f"✅ عثرنا على **{unique_samples}** عينة فريدة | **{len(df)}** سجل اكتشاف\n"
            response += f"📊 {compliant} مطابقة | {non_compliant} غير مطابقة\n\n"
            response += df.to_markdown(index=False)
        else:
            response = f"⚠️ لم يتم رصد **{pesticide}** في **{cat_name}**"

        return response, df

    def _handle_inspection_priority(self, intent, query, entities=None):
        from modules.inspection.inspection_priority import (
            is_available, get_top, search_entity,
            to_text, to_voice_summary, component_breakdown,
            extract_priority_params,
        )
        con = self._get_connection()

        if not is_available(con=con):
            return ("طبقة أولوية التفتيش غير مبنية بعد. شغّل build_risk_scores.py أولًا.",
                    None, None)

        params = extract_priority_params(query)
        level = params["level"]
        top_n = params["top_n"]

        # ── ليه المنشأة X أولوية؟ ──
        if intent.name == "INSPECTION_PRIORITY_REASON":
            from modules.inspection.inspection_priority import extract_entity_name_for_reason
            name = extract_entity_name_for_reason(query)
            match = search_entity(name, level="establishment", con=con)
            if match.empty:
                match = search_entity(name, level=level, con=con)
            if match.empty:
                return ("لم أجد منشأة بهذا الاسم في جدول الأولويات.", None, None)
            row = match.iloc[0].to_dict()
            text = (f"**{row['entity_name']}** — درجة أولوية {row['risk_score']:.0f}\n\n"
                    f"{row['reason_ar']}")
            return text, component_breakdown(row), None

        if intent.name == "INSPECTION_PRIORITY_ROUTE":
            from modules.inspection.inspection_priority import (
                get_recommended_route, to_route_text, to_route_voice,
            )
            route = get_recommended_route(min_confidence="medium", con=con)
            text = to_route_text(route)
            df = pd.DataFrame(route.get("establishments", [])) if route.get("found") else None
            return text, df, {"voice_summary": to_route_voice(route)}

        # ── أي حي يستحق زيارة عاجلة؟ ──
        if intent.name == "INSPECTION_PRIORITY_URGENT_NEIGHBORHOOD":
            level = "neighborhood"

        # ── الحالة الافتراضية: أعلى N ──
        df = get_top(level=level, n=top_n, min_confidence="medium", con=con)
        if df.empty:
            df = get_top(level=level, n=top_n, con=con)

        return to_text(df, level, con=con), df, None

    def _handle_out_of_scope(self, reason_type: str, detail_ar: str = "", detail_en: str = "") -> str:
        """
        Returns a language-consistent 'can't answer as posed' response.
        Detects Arabic vs English from the query text itself (via presence
        of Arabic script) and returns ONLY that language — no mixing.
        Callers should pass both detail_ar and detail_en when the detail
        differs by language; if only one is given, it's used as a fallback
        for both (acceptable for short technical terms like pesticide names
        that don't need translation).
        """
        is_arabic = any('\u0600' <= c <= '\u06ff' for c in getattr(self, "_last_query", ""))
        detail_en = detail_en or detail_ar
        detail_ar = detail_ar or detail_en

        templates_ar = {
            "subjective_recommendation": (
                "⚠️ لا يمكنني اقتراح توصيات أو أولويات — هذا يتطلب حكماً بشرياً "
                "بناءً على السياق التشغيلي. يمكنني عرض البيانات التي قد تُبنى عليها "
                "هذه القرارات، مثل: أعلى المنتجات من حيث نسبة المخالفة، أو الأحياء "
                "الأكثر مخالفة."
            ),
            "data_not_tracked": f"⚠️ لا تحتوي قاعدة البيانات على {detail_ar}. هذا النوع من البيانات غير مُسجَّل في النظام الحالي.",
            "needs_method_definition": f"⚠️ هذا السؤال يحتاج إلى تعريف منهجية محددة قبل الإجابة عليه ({detail_ar}). هذا قيد المراجعة حالياً وليس متاحاً بعد.",
            "too_compound": "⚠️ هذا السؤال يجمع عدة أجزاء معاً. جرّب تقسيمه إلى أسئلة أصغر — مثلاً اسأل أولاً عن قائمة المبيدات في العينة، ثم عن نسبة المخالفات لكل مبيد على حده.",
        }
        templates_en = {
            "subjective_recommendation": (
                "I can't generate recommendations or priorities — that requires "
                "operational judgment. I can show the underlying data instead, "
                "like top products by violation rate, or the most non-compliant "
                "neighborhoods."
            ),
            "data_not_tracked": f"This data isn't tracked in the current system — there's no {detail_en} field in the dataset.",
            "needs_method_definition": f"This needs a defined method before it can be answered ({detail_en}). Not available yet — flagged for review.",
            "too_compound": "This combines several sub-questions — try splitting it, e.g. ask for the pesticide list first, then the violation rate per pesticide separately.",
        }

        if is_arabic:
            return templates_ar.get(reason_type, self._handle_unknown_query(""))
        return templates_en.get(reason_type, self._handle_unknown_query(""))

    def _check_out_of_scope(self, query: str, query_lower: str) -> Optional[Tuple[str, Optional[pd.DataFrame]]]:
        """
        Checked FIRST, before any tier. Catches genuinely out-of-scope
        requests (subjective recommendations, untracked data, undefined
        methodology, MOA-level questions your data can't answer) so they
        can never be misrouted by a coincidental keyword match deeper in
        the pipeline — e.g. Tier 2's "مبيدين" dual-form shortcut hijacking
        a mechanism-of-action question into "samples with 2 pesticides".
        Returns None if the query is in-scope (falls through to Tier 0+).
        """
        recommendation_kws = [
            'التوصيات', 'توصيات مقترحة', 'تستحق زيادة', 'تحتاج حملة',
            'recommend', 'recommendation',
        ]
        if any(kw in query_lower or kw in query for kw in recommendation_kws):
            return self._handle_out_of_scope("subjective_recommendation"), None

        capacity_kws = ['الطاقة الاستيعابية', 'اختناق', 'bottleneck', 'capacity']
        if any(kw in query_lower or kw in query for kw in capacity_kws):
            return self._handle_out_of_scope(
                "data_not_tracked",
                detail_ar="بيانات الطاقة الاستيعابية أو معدل الإنتاجية للمختبر",
                detail_en="lab capacity or throughput data",
            ), None
        

        # Mechanism-of-action — confirmed pesticide_groups.py has no MOA
        # data, only classify_pesticide() at the chemical-group level.
        moa_kws = [
            'آلية السمّية', 'آلية السمية', 'نفس آلية',
            'mechanism of action', 'moa',
            'mechanism of toxicity', 'toxicity mechanism',
            'same mechanism', 'mode of action', 'same mode of action',
        ]
        if any(kw in query for kw in moa_kws):
            return self._handle_out_of_scope(
                "needs_method_definition",
                detail_ar="البيانات الحالية تصنّف حسب المجموعة الكيميائية فقط، وليس آلية السمّية على مستوى أدق",
                detail_en="current data only classifies by chemical group, not mechanism of toxicity at a finer level",
            ), None

        organochlorine_kws = ['أورجانوكلورين', 'ارجانوكلورين', 'organochlorine']
        if any(kw in query for kw in organochlorine_kws):
            return self._handle_out_of_scope(
                "data_not_tracked",
                detail_ar="تصنيف 'أورجانوكلورين' كمجموعة كيميائية منفصلة — البيانات الحالية لا تميزها عن باقي المجموعات",
                detail_en="a separate 'organochlorine' classification — current data doesn't distinguish it from other groups",
            ), None

        undefined_method_kws_ar = {
            'موسمي': "كيف يُعرَّف 'الموسمي'",
            'قيمة شاذة': "كيف تُعرَّف 'القيمة الشاذة' — IQR أم z-score",
            'القيم الشاذة': "كيف تُعرَّف 'القيمة الشاذة' — IQR أم z-score",
            'outlier': "كيف تُعرَّف 'القيمة الشاذة' — IQR أم z-score",
            'علاقة بين': "طريقة حساب الارتباط الإحصائي (معامل بيرسون مثلاً)",
            'correlation': "طريقة حساب الارتباط الإحصائي (معامل بيرسون مثلاً)",
        }
        undefined_method_kws_en = {
            'موسمي': "how 'seasonal' is defined",
            'قيمة شاذة': "how 'outlier' is defined — IQR or z-score",
            'القيم الشاذة': "how 'outlier' is defined — IQR or z-score",
            'outlier': "how 'outlier' is defined — IQR or z-score",
            'علاقة بين': "the correlation method (e.g. Pearson's r)",
            'correlation': "the correlation method (e.g. Pearson's r)",
        }
        for kw in undefined_method_kws_ar:
            if kw in query_lower or kw in query:
                return self._handle_out_of_scope(
                    "needs_method_definition",
                    detail_ar=undefined_method_kws_ar[kw],
                    detail_en=undefined_method_kws_en[kw],
                ), None

        risk_category_kws = ['الفئات الغذائية الأعلى خطورة', 'أعلى خطورة']
        if any(kw in query for kw in risk_category_kws):
            return self._handle_out_of_scope(
                "needs_method_definition",
                detail_ar="يحتاج مؤشر الخطر الصحي (HRI) لكل فئة أولاً، ثم تحديد حد أدنى للخطورة",
                detail_en="needs the Health Risk Index (HRI) computed per category first, then a defined risk threshold",
            ), None

        compound_kws = ['من حيث العدد وتركيز', 'وكم منها متسبب']
        if any(kw in query for kw in compound_kws):
            return self._handle_out_of_scope("too_compound"), None

        return None
