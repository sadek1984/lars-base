"""
keyword_patterns.py — extracted from core_query_engine.py (2026-09-18, Phase 3 split).

Tier 3: the keyword pattern cascade (patterns 0–14 plus the
lettered question-bank patterns). The single biggest hot-spot for
adding new query patterns.
Methods are byte-identical to their pre-split versions; this module only
relocates them. KeywordPatternsMixin is mixed into CoreQueryEngine — methods refer to
engine state (self._get_connection(), detection helpers, handlers) via self.
"""
import re
from typing import Optional, Tuple

from modules.query.text_norm import COUNT_NOUNS, compliance_intent, count_for_nouns, norm, number_value, tokens

import pandas as pd


class KeywordPatternsMixin:
    @staticmethod
    def _top_n(query: str, default: Optional[int] = None) -> Optional[int]:
        """N for "top N" questions, digits or words: the number right after
        أعلى ("أعلى ٥", "أعلى خمسة"), else a number that quantifies a count
        noun ("أخطر خمس أحياء", "الأحياء الخمسة"), else `default`.
        Numbers that quantify nothing ("الحد الآمن الواحد") are ignored."""
        toks = tokens(query)
        for i, t in enumerate(toks[:-1]):
            if t in ("اعلى", "اكثر", "اخطر", "افضل", "اقل"):
                v = number_value(toks[i + 1])
                if v is not None:
                    return v
        # Entity nouns only: "آخر ٣ أشهر" is a period, not a top-N.
        counts = count_for_nouns(query, COUNT_NOUNS["pesticides"] | COUNT_NOUNS["places"]
                                 | COUNT_NOUNS["products"])
        return counts[0] if counts else default

    # "Top N pesticides" phrasings (normalized text). "أكثر من N مبيدات" means
    # "more than N pesticides" (a per-sample count) and is not a ranking.
    _PEST = r"(?:مبيد|مبيدات|المبيدات)"
    _TOP_PESTICIDE_PATTERNS = (
        re.compile(r"ترتيب\s+المبيدات"),
        re.compile(r"(?:^|\s)(?:اكثر|الاكثر)\s+(?!من\s)(?:\S+\s+)?" + _PEST + r"(?:\s|$|؟)"),
        re.compile(_PEST + r"\s+الاكثر\s+(?:ظهورا|تكرارا|شيوعا|انتشارا)"),
        re.compile(_PEST + r"\s+(?:التي|اللي)\s+سببت\s+عدم\s+المطابقه"),
    )
    _PESTICIDES_IN_SAMPLES = re.compile(_PEST + r"\s+(?:اللي\s+)?في\s+العينات")

    def _dispatch_top_pesticides(self, ctx: dict) -> Optional[Tuple[str, Optional[pd.DataFrame]]]:
        """Top N pesticides overall or in non-compliant samples (Batch 5a).
        Runs before the Tier-0 compliance override and the router's
        N-pesticides intent, which would otherwise take "أكثر ٥ مبيدات في
        العينات غير المطابقة" as "samples with 5 pesticides". Returns None
        when a specific pesticide is named (e.g. A023), or for a "compliant
        samples" scope, which is not defined."""
        query = ctx['query']
        if ctx['detected_pesticide']:
            return None
        q = norm(query)
        verdict = compliance_intent(query)
        ranking = any(p.search(q) for p in self._TOP_PESTICIDE_PATTERNS) or (
            verdict == 'non_compliant' and bool(self._PESTICIDES_IN_SAMPLES.search(q)))
        # "عدم المطابقة" means non-compliance; the shared compliance_intent reads
        # it as 'compliant' ("عدم" is not in its negator list), so check it here.
        non_compliant = verdict == 'non_compliant' or 'عدم المطابقه' in q
        if not ranking or (verdict == 'compliant' and not non_compliant):
            return None
        scope = 'non_compliant' if non_compliant else 'all'
        counts = count_for_nouns(query, COUNT_NOUNS["pesticides"])
        n = counts[0] if counts else self._top_n(query, default=5)
        return self._handle_top_pesticides(ctx, scope, max(1, min(int(n), 50)))

    def _dispatch_rate_breakdown(self, ctx: dict) -> Optional[Tuple[str, Optional[pd.DataFrame]]]:
        """Rate / performance questions broken down by municipality, neighborhood
        or month ("أداء كل بلدية", "أخطر ٥ أحياء من حيث نسبة المخالفة",
        "اتجاه نسبة المطابقة على مدى الأشهر"). Runs before the Tier-0
        compliance override, which otherwise catches 'المطابقة' and returns the
        generic all-products table. Returns None when the question names a
        specific municipality/neighborhood (comparisons are handled elsewhere)."""
        query = ctx['query']
        resolution = ctx.get('resolution')
        rate_words = ('نسبة المخالفة', 'نسبة مخالفة', 'نسبة المطابقة', 'نسبة الرسوب', 'أداء', 'أخطر')
        if not any(w in query for w in rate_words):
            return None
        if ctx['detected_samples'] or ctx['detected_neighborhoods'] or (
                resolution is not None and (resolution.municipalities or resolution.categories)):
            return None
        n = self._top_n(query)

        if any(w in query for w in ('كل بلدية', 'لكل بلدية', 'البلديات')):
            return self._handle_top_n_by_metric('municipality', 'rate', n,
                                                min_samples=self.MIN_SAMPLES_FOR_RATE)
        if any(w in query for w in ('الأحياء', 'أحياء', 'كل حي', 'لكل حي')):
            return self._handle_top_n_by_metric('neighborhood', 'rate', n,
                                                min_samples=self.MIN_SAMPLES_FOR_RATE)
        if any(w in query for w in ('الأشهر', 'كل شهر', 'شهرياً', 'على مدى', 'اتجاه')) and 'أي شهر' not in query:
            return self._handle_time_series_breakdown('month')
        return None

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
        detected_period       = ctx['detected_period']
        _detected_category_key = ctx['category_key']
        resolution = ctx.get('resolution')

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
            return self._handle_comprehensive_neighborhood(query, detected_samples, detected_neighborhoods, date_filter=detected_period)
        
        # Pattern 0B: Category/types in neighborhood (WITHOUT limit keywords)
        # "what are the types of spices in al_iskan"
        # This catches queries that Pattern 0 misses because they
        # don't mention limits. We route to the SAME handler — it
        # already shows types + counts + limits in its output.
        category_names = ['spices', 'vegetables', 'fruits', 'greens', 'nuts', 'grains', 'dates']
        has_category = any(cat in query_lower for cat in category_names)
        has_type_question = any(kw in query_lower for kw in category_keywords)
        
        if (has_category or (has_type_question and detected_samples)) and detected_neighborhoods:
            return self._handle_comprehensive_neighborhood(query, detected_samples, detected_neighborhoods, date_filter=detected_period)
        
        # Continue with other patterns if not comprehensive
        # Pattern 1: Samples with N pesticides (supports multiple counts)
        pesticide_count_keywords = ['pesticide', 'pesticides', 'مبيد', 'مبيدات', 'متبقيات', 'متبقي']
        zero_pesticide_keywords = [
            'zero pesticide', 'clean', 'free of pesticides', 'no pesticide',
            'خالية من المبيدات', 'خالية تماما من المبيدات', 'خالية تماماً من المبيدات',
            'بدون مبيدات', 'خالي من المبيدات',
        ]
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
                        return self._handle_multiple_n_pesticides(pesticide_counts, detected_samples, date_filter=detected_period)
                else:
                    n_pesticides = int(all_numbers[-1])
                    if 0 <= n_pesticides <= 50:
                        return self._handle_n_pesticides(n_pesticides, detected_samples, date_filter=detected_period)
        # Pattern EXCEED_MULT: "N times the limit"
        # Regexes run on the shared normalized text (text_norm.norm), like `in`.
        mult_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:ضعف|اضعاف|x|times)', norm(query_lower + " " + query))
        exceed_kws = ['أضعاف الحد', 'ضعف الحد', 'times the limit', 'times the mrl', 'اضعاف', 'ضعف']
        if any(kw in query for kw in exceed_kws):
            if mult_match:
                multiplier = float(mult_match.group(1))
            else:
                # Bare "ضعف" with no digit means "double" (multiplier = 2),
                # same pattern as "مبيدين" implying 2 without a numeral.
                multiplier = 2.0
            return self._handle_exceedance_multiplier(detected_samples, multiplier, _detected_category_key,
                                                      pesticide=detected_pesticide)
        # Pattern PROXIMITY: "between X% and Y% of the limit"
        pct_matches = re.findall(r'(\d+)\s*٪|(\d+)\s*%', norm(query))
        pct_nums = [int(a or b) for a, b in pct_matches]
        proximity_kws = ['قريبة من الحد', 'تحت الحد المسموح لكن فوق']
        if len(pct_nums) >= 1 and any(kw in query for kw in proximity_kws):
            low, high = (sorted(pct_nums[:2]) if len(pct_nums) >= 2 else (pct_nums[0], 100))
            return self._handle_limit_proximity_band(detected_samples, low, high)

        # Pattern GLOBAL_RATE: violation % per pesticide/product, no sample filter
        if 'نسبة المخالفة لكل مبيد' in query:
            return self._handle_global_violation_rate('pesticide')
        if 'نسبة المخالفة لكل منتج' in query:
            return self._handle_global_violation_rate('product')

        # Pattern ZERO_VIOL: entities with zero violations ever
        if 'ظهرت ولم تسبب أي مخالفة' in query:
            return self._handle_zero_violations('pesticide')
        if 'لم تسجل أي مخالفة' in query and ('منتج' in query or 'عينات' in query):
            return self._handle_zero_violations('product')
        if 'الخالية من المخالفات' in query and 'حي' in query:
            return self._handle_zero_violations('neighborhood')
        if 'لم تسجل فيها أي اكتشافات' in query:
            return self._handle_zero_detection_products()

        # Pattern A044/D022: sample count / % share per product category
        if 'إجمالي عدد العينات لكل نوع منتج' in query:
            return self._handle_category_totals(show_pct=False)
        if 'نسبة كل نوع منتج من إجمالي العينات' in query:
            return self._handle_category_totals(show_pct=True)

        # Pattern D023: category's share of total violations
        if 'نسبة عينات التوابل من إجمالي المخالفات' in query or \
           ('نسبة' in query and 'التوابل' in query and 'إجمالي المخالفات' in query):
            return self._handle_category_violation_share('spice')

        # Pattern B050: top N readings by % exceedance
        if 'أعلى' in query and ('قراءات' in query) and ('تجاوزاً' in query or 'بالنسبة المئوية' in query):
            n = self._top_n(query, default=10)
            return self._handle_top_exceedance_readings(n)

        # Pattern REPORT: general "تقرير" (report) dispatcher — routes to
        # either the compliance/violation table (if the report is scoped
        # to non-compliant samples) or the KPI summary (general report),
        # threading through whatever date filter was detected (relative
        # period OR absolute month name, both handled in _extract_context).
        report_kws = ['تقرير']
        if any(kw in query for kw in report_kws):
            violation_kws_in_report = ['مخالف', 'راسب', 'غير مطابق']
            is_violation_report = any(kw in query for kw in violation_kws_in_report)

            if is_violation_report:
                return self._handle_count_samples_compliance_table(
                    detected_samples, detected_neighborhoods, True,
                    date_filter=detected_period,
                    municipalities=resolution.municipalities if resolution is not None else None,
                )
            return self._handle_kpi_summary(
                date_filter=detected_period,
                samples=detected_samples,
                neighborhoods=detected_neighborhoods,
            )

        kpi_kws = ['ملخص تنفيذي', 'المؤشرات الرئيسية', 'في صفحة واحدة']
        if any(kw in query for kw in kpi_kws):
            return self._handle_kpi_summary()

        # Pattern TOP_N: top N products/facilities by rate or count
        n = self._top_n(query) if 'أعلى' in query else None
        if n:
            if ('نسبة الرسوب' in query or 'نسبة المخالفة' in query) and 'منتج' in query:
                return self._handle_top_n_by_metric('product', 'rate', n)
            if 'عدد المخالفات' in query and 'منتج' in query:
                return self._handle_top_n_by_metric('product', 'count', n)
            if 'منشآت' in query or 'منشأة' in query:
                return self._handle_top_n_by_metric('facility', 'count', n)

        # Pattern CAT_COMPARE: category vs category (count/violations/avg pesticides)
        cat_compare_pairs = [
            (('توابل', 'خضراوات'), 'spice', 'vegetable'),
            (('توابل', 'خضار'), 'spice', 'vegetable'),
            (('خضراوات', 'فواكه'), 'vegetable', 'fruit'),
            (('خضار', 'فواكه'), 'vegetable', 'fruit'),
        ]
        for (word_a, word_b), cat_a, cat_b in cat_compare_pairs:
            if word_a in query and word_b in query:
                metric = "count"
                if 'مخالف' in query:
                    metric = "violations"
                elif 'متوسط' in query and 'مبيد' in query:
                    metric = "avg_pesticides"
                return self._handle_category_comparison(cat_a, cat_b, metric)
        # Pattern MISSING_MRL: data-quality metrics on missing limit_value
        if ('غير مطابقة' in query or 'المخالفة' in query or 'مخالفة' in query) and 'حد مسجل' in query:
            return self._handle_missing_mrl_stats('noncompliant_no_mrl')
        if 'تعذّر تقييمها' in query and 'عدم وجود حد' in query and 'نسبة' not in query:
            return self._handle_missing_mrl_stats('unevaluable_count')
        if 'نسبة العينات' in query and 'تعذّر تقييمها' in query:
            return self._handle_missing_mrl_stats('unevaluable_pct')
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
                detected_samples, detected_neighborhoods, threshold, _detected_category_key,
                date_filter=detected_period,
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
                                                            limit_filter=limit_filter, limit_desc=limit_desc,
                                                            date_filter=detected_period)
             elif explicit_both:
                 return self._handle_sample_pesticide_limit(detected_samples, detected_pesticide, is_above_limit, both=True, date_filter=detected_period)
             else:
                 return self._handle_sample_pesticide_limit(detected_samples, detected_pesticide, is_above_limit, date_filter=detected_period)

        if is_count_query and detected_samples and (is_above_limit or is_below_limit):
            return self._handle_count_samples_limit(detected_samples, detected_neighborhoods, is_above_limit, date_filter=detected_period)
        
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
                                                              is_non_compliant_query, date_filter=detected_period)
        
        # Pattern 3: List pesticides in sample type
        # "what are the pesticides in tomatoes"
        pesticide_list_patterns = ['pesticides found in', 'pesticides detected in', 'what pesticides in', 'list pesticides in']
        if any(p in query_lower for p in pesticide_list_patterns) and detected_samples:
            return self._handle_list_pesticides(detected_samples, date_filter=detected_period)
        
        # Pattern 4: Pesticides in neighborhoods
        # "what pesticides are in al iskan neighborhood"
        if detected_neighborhoods and ('pesticide' in query_lower or 'pesticides' in query_lower):
            show_separately = any(phrase in query_lower for phrase in ['individually', 'separately', 'for each'])
            return self._handle_neighborhood_pesticides(detected_neighborhoods, show_separately, date_filter=detected_period)
        # Pattern MISSING_FIELD: "نسبة السجلات الناقصة في حقل X" / "كم عينة ليس لها بلدية"
        # Checked before MUNICIPALITY so 'بلدية مسجّلة' is not read as a municipality name.
        if 'ناقصة' in query or 'ناقص' in query or 'ليس لها' in query:
            if 'حي' in query or 'الحى' in query:
                return self._handle_missing_field_pct('neighborhood')
            if 'بلدية' in query:
                return self._handle_missing_field_pct('municipality')

        # Pattern MUNICIPALITY: pesticides / breakdown / comparison by بلدية.
        # Municipalities come from the resolver (exact DB values), never from
        # slicing the words after 'بلدية'.
        # Associations stored in the same column ('جمعية البطين الزراعية') resolve
        # without the word بلدية, so a resolved value alone also triggers this.
        if resolution is not None and (resolution.mentions_municipality or resolution.municipalities):
            muns = resolution.municipalities
            wants_breakdown = 'أنواع' in query or 'مفصلة' in query or 'حسب نوع' in query
            # Two named municipalities ("مين أعلى بلدية، شرق بريدة ولا غرب بريدة")
            # are a comparison even without "قارن"; answering for the first one
            # only would silently narrow the question.
            is_compare = 'قارن' in query or 'مقابل' in query or len(muns) >= 2
            if is_compare and len(muns) >= 2:
                metric = 'pesticides' if 'المبيدات' in query or 'مبيدات' in query else 'violation_rate'
                return self._handle_municipality_comparison(muns[0], muns[1], metric=metric)
            if muns and not is_compare:
                asks_pesticides = 'مبيد' in query
                if wants_breakdown or (not asks_pesticides and not resolution.mentions_municipality):
                    # "ما هي العينات المأخوذة من جمعية …" → samples by product
                    return self._handle_municipality_breakdown(muns[0])
                return self._handle_municipality_pesticides(muns[0])
            if resolution.all_municipalities and wants_breakdown:
                return self._handle_municipality_breakdown(None)
            if not muns and (is_compare or wants_breakdown or 'مبيدات' in query or 'المبيدات' in query):
                return self._unresolved_municipality_message(), None

        # Pattern HEADLINE_TOTALS: "كم إجمالي العينات" — dataset-wide sample and
        # record totals, only when the question names no entity or condition.
        totals_kws = ('إجمالي العينات', 'اجمالي العينات', 'كم إجمالي', 'كم اجمالي',
                      'كم عدد العينات', 'العدد الكلي للعينات', 'كم عينة فريدة')
        condition_words = ('مخالف', 'فوق', 'تحت', 'راسب', 'مطابق', 'تجاوز', 'مبيد',
                           'الحد', 'ليس لها', 'ناقص', 'حي ', 'نوع')
        has_entity = bool(
            detected_samples or detected_neighborhoods or detected_pesticide or _detected_category_key
            or (resolution is not None and (resolution.municipalities or resolution.facilities
                                            or resolution.categories or resolution.products))
        )
        if (any(k in query for k in totals_kws) and not has_entity
                and not any(w in query for w in condition_words)):
            return self._handle_headline_totals(date_filter=detected_period)
        # Pattern TIME_SERIES: monthly/weekly/quarterly/half-year breakdown
        if 'شهرياً' in query or 'كل شهر' in query or 'مفحوصة شهرياً' in query:
            return self._handle_time_series_breakdown('month')
        if 'أسبوعياً' in query or 'كل أسبوع' in query:
            return self._handle_time_series_breakdown('week')
        if ('الربع الأول' in query and 'الربع الثاني' in query) or 'ربع سنوي' in query:
            return self._handle_time_series_breakdown('quarter')
        if ('النصف الأول' in query and 'النصف الثاني' in query):
            return self._handle_time_series_breakdown('half')
        if 'أعلى نسبة مخالفة' in query and 'شهر' in query:
            return self._handle_time_series_extreme('month')

        # Pattern GROUP_FILTER: category/sample + specific chemical group name
        # Only Organophosphate is wired here — Organochlorine is intentionally
        # absent (see _check_out_of_scope for that redirect).
        group_filter_map = {'أورجانوفوسفورس': 'أورجانوفوسفورس', 'ارجانوفوسفورس': 'أورجانوفوسفورس'}
        for kw, group_key in group_filter_map.items():
            if kw in query:
                return self._handle_group_filter(group_key, detected_samples)

        # Pattern MULTI_GROUP: samples with more than one chemical group
        if 'أكثر من مجموعة كيميائية' in query or 'اكثر من مجموعة كيميائية' in query:
            return self._handle_multi_group_samples(2)

        # Pattern GROUP_INTERSECTION: two named groups appearing together
        if ('نيونيكوتينويد' in query and 'كارباميت' in query and
                ('معاً' in query or 'معا' in query)):
            return self._handle_group_intersection('نيونيكوتينويد', 'كارباميت')

        # Pattern GROUP_BY_NEIGHBORHOOD: chemical group distribution across neighborhoods
        if 'توزيع المجموعات' in query and ('الأحياء' in query or 'أحياء' in query):
            return self._handle_group_by_neighborhood()

        # Pattern 5: Find samples containing pesticide
        # "tomato samples containing bifenthrin"
        if detected_pesticide and detected_samples:
            return self._handle_find_pesticide_in_sample(detected_pesticide, detected_samples, date_filter=detected_period)
        
        # Pattern 6: Neighborhood ranking
        # "ranking of neighborhoods by violations"
        ranking_kws_ar = ['ترتيب', 'الأكثر', 'الاكثر', 'أخطر', 'اخطر']
        # "breakdown per neighborhood" implies the same grouped output as a
        # ranking request, even with no explicit ranking word — e.g.
        # "كم عدد المخالفات في كل حي" has no 'ترتيب'/'الأكثر' but still
        # wants the same GROUP BY الحى result _handle_neighborhood_ranking
        # already produces.
        breakdown_kws_ar = ['في كل حي', 'لكل حي', 'مفصلة']
        neighborhood_kws_ar = ['حي', 'الأحياء', 'الاحياء', 'أحياء', 'احياء']
        if (any(kw in query_lower for kw in ['rank', 'ranking', 'worst', 'most violations']) or
                any(kw in query for kw in ranking_kws_ar) or
                any(kw in query for kw in breakdown_kws_ar)) and \
           (any(kw in query_lower for kw in ['neighborhood', 'neighborhoods']) or
                any(kw in query for kw in neighborhood_kws_ar)):
            return self._handle_neighborhood_ranking(date_filter=detected_period)
        
        # Pattern 7: Comprehensive analysis
        # "comprehensive analysis of tomatoes"
        comprehensive_keywords = ['comprehensive analysis', 'comprehensive report', 'statistics for', 'summary of']
        if any(kw in query_lower for kw in comprehensive_keywords) and detected_samples:
            return self._handle_comprehensive_analysis(detected_samples, date_filter=detected_period)
        
        # Pattern 8: Pesticide statistics (max, min, range, median, average)
        # "what is the median concentration of imidacloprid in tomatoes"
        stats_keywords_found = []
        for stat_type, keywords in self.stats_keywords.items():
            if any(kw in query_lower for kw in keywords):
                stats_keywords_found.append(stat_type)
        
        if stats_keywords_found and detected_pesticide:
            return self._handle_pesticide_stats(detected_pesticide, detected_samples, stats_keywords_found,
                                                date_filter=detected_period,
                                                category=None if detected_samples else _detected_category_key)

        # Pattern HRI: Health Risk Index
        hri_kws_en = [
            'health risk index', 'health risk', 'hri', 'risk index',
            'مؤشر الخطر الصحي', 'مؤشر الخطر', 'المخاطر الصحية',
            'معامل الخطر', 'hq',
        ]
        if 'أعلى' in query and 'استهلاكاً' in query and any(
            kw in query_lower for kw in hri_kws_en
        ):
            n = self._top_n(query, default=3)
            return self._handle_hri_top_consumed(n)

        if 'متوسط عدد المبيدات' in query and ('الحد الآمن' in query or 'الآمن' in query):
            return self._handle_avg_pesticides_high_risk_samples(1.0)

        if 'أعلى' in query and 'استهلاكاً' in query and any(kw in query_lower for kw in hri_kws_en):
            n = self._top_n(query, default=3)
            return self._handle_hri_top_consumed(n)
        if any(kw in query_lower for kw in hri_kws_en) and detected_samples:
            group = resolution.pesticide_group if resolution is not None else None
            return self._handle_health_risk_index(detected_samples, pesticide_group=group)

        # Pattern QI: Quality Index
        qi_kws_en = [
            'quality index', 'quality score', 'quality indicator',
            'مؤشر الجودة', 'مؤشر جودة', 'درجة الجودة',
        ]
        if any(kw in query_lower for kw in qi_kws_en) and detected_samples:
            return self._handle_quality_index(detected_samples)

        # Pattern CG: Chemical Groups / Classify pesticides
        cg_kws_en = [
            'chemical group', 'chemical groups', 'classify pesticide',
            'pesticide class', 'group classification',
            'المجموعة الكيميائية', 'المجموعات الكيميائية', 'مجموعة كيميائية',
            'تصنيف المبيدات', 'التصنيف الكيميائي',
        ]
        cg_exclude_kws = [
            'الأكثر تسبباً', 'الأكثر تسببا', 'أكثر من مجموعة', 'اكثر من مجموعة',
            'نسبة المخالفة لكل مجموعة', 'توزيع المجموعات',
            # English equivalents — needed because Gemini Live pre-translates
            # voice queries to English before calling search_pesticide_data,
            # so an Arabic-only exclusion list never catches these via voice.
            'causing the most', 'causing most', 'most violations',
            'highest violations', 'more than one group', 'more than one chemical group',
            'violation percentage for each', 'violation percentage per',
            'violation rate for each', 'violation rate per',
            'distribution of chemical group', 'distribution across neighborhood',
            'groups across neighborhood',
        ]
        is_cg_excluded = any(kw in query for kw in cg_exclude_kws)
        if any(kw in query_lower for kw in cg_kws_en) and not is_cg_excluded:
            min_pest = 0
            nums = re.findall(r'(\d+)', query_normalized)
            threshold_kws_cg = ['more than', 'greater than']
            if nums and any(kw in query_lower for kw in threshold_kws_cg):
                min_pest = int(nums[0])
            return self._handle_chemical_groups(detected_samples, min_pesticides=min_pest)

        _cat_en_map = {
            'vegetable': 'vegetable', 'vegetables': 'vegetable',
            'fruit': 'fruit', 'fruits': 'fruit',
            'spice': 'spice', 'spices': 'spice',
            'nut': 'nut', 'nuts': 'nut',
            'grain': 'grain', 'grains': 'grain', 'leafy': 'leafy',
            # Arabic — needed since Pattern CAT_LIMIT (فوق الحد وتحت الحد)
            # and Pattern CAT_PEST both rely on this map, and queries are
            # frequently Arabic-only (e.g. "للتوابل" never matched 'spice').
            'توابل': 'spice', 'التوابل': 'spice',
            'خضار': 'vegetable', 'الخضار': 'vegetable', 'خضروات': 'vegetable',
            'فواكه': 'fruit', 'الفواكه': 'fruit', 'فاكهة': 'fruit',
            'مكسرات': 'nut', 'المكسرات': 'nut',
            'حبوب': 'grain', 'الحبوب': 'grain',
            'ورقيات': 'leafy', 'الورقيات': 'leafy',
        }
        _cat_key_process = None
        if resolution is not None:
            # Resolved DB category ('Spices'); the handlers filter "نوع العينة" = ?
            _cat_key_process = resolution.categories[0] if resolution.categories else None
        else:
            for kw, cat in _cat_en_map.items():
                if kw in query_lower:
                    _cat_key_process = cat
                    break
        if detected_pesticide and _cat_key_process and not detected_samples:
            return self._handle_category_pesticide(detected_pesticide, _cat_key_process, [])

        # Pattern CAT_LIMIT: Category above AND below limit summary
        # "spices above and below permissible limits"
        cat_both_kws_en = [
            'above and below', 'above or below', 'above & below',
            'فوق الحد وتحت الحد', 'فوق وتحت الحد', 'فوق الحد و تحت الحد',
        ]
        is_cat_both = any(kw in query_lower for kw in cat_both_kws_en)
        if is_cat_both and _cat_key_process:
            _test_type = None
            if 'mycotoxin' in query_lower:
                _test_type = 'mycotoxin'
            elif 'pesticide' in query_lower:
                _test_type = 'pesticide'
            _by_pesticide = 'المبيدات' in query or 'السموم' in query
            return self._handle_category_limit_summary(_cat_key_process, detected_samples, _test_type,
                                                       by_pesticide=_by_pesticide)

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
                return self._handle_samples_with_pesticide(detected_pesticide, date_filter=detected_period)
        
        # Pattern 11: Unique sample count
        # "how many unique cucumber samples"
        if detected_samples and any(kw in query_lower for kw in ['unique', 'distinct', 'sample code']):
            return self._handle_unique_samples_count(detected_samples, detected_neighborhoods, date_filter=detected_period)
        
        # Pattern 12: Just search for pesticide (no sample filter)
        # "Find fipronil"
        search_keywords = ['find', 'search', 'locate']
        search_keywords_ar = ['ابحث', 'دور', 'اوجد', 'أوجد']
        if detected_pesticide and (
            any(kw in query_lower for kw in search_keywords)
            or any(kw in query for kw in search_keywords_ar)
        ):
            return self._handle_find_pesticide_all(detected_pesticide, date_filter=detected_period)
        
        # Pattern 14: Simple sample count (NO CONDITIONS)
        # "how many tomato samples"
        # This MUST be after limit/compliance patterns to avoid conflicts
        count_keywords = ['count', 'how many', 'samples']
        if detected_samples and any(kw in query_lower for kw in count_keywords):
            # Only trigger if NOT a limit/compliance query (those are handled above)
            return self._handle_simple_sample_count(detected_samples, detected_neighborhoods, date_filter=detected_period)
        
        # Pattern 14: LLM Fallback for unknown queries
        # If we have LLM configured, try to generate SQL
        if self.llm_client is not None:
            llm_response = self._handle_llm_query(query, detected_samples, detected_neighborhoods, detected_pesticide)
            if llm_response[0]:
                return llm_response

        # Pattern C009: pesticide-count distribution, no sample filter
        if ('توزيع عدد المبيدات' in query or 'توزيع المبيدات لكل عينة' in query) and not detected_samples:
            return self._handle_comprehensive_analysis([])
        
        # Pattern E010: stats for every pesticide in a given sample type
        if 'لكل مبيد' in query and detected_samples and any(
            kw in query_lower for kw in ['min', 'max', 'median', 'mean']
        ):
            return self._handle_comprehensive_analysis(detected_samples)

        # Pattern D013: top facilities by violation count (no explicit N)
        if 'المنشآت الأكثر تكراراً' in query or 'الأكثر تكراراً في المخالفات' in query:
            return self._handle_top_n_by_metric('facility', 'count', 10)

        # Pattern A040: pesticides never detected in a category
        if ('لم تظهر' in query or 'لم يظهر' in query) and resolution is not None and resolution.categories:
            return self._handle_never_detected_in_category(resolution.categories[0])
        if resolution is None and 'لم تظهر إطلاقاً' in query and 'فواكه' in query:
            return self._handle_never_detected_in_category('fruit')

        # Pattern B036: classification-vs-calculation violation count diff
        if 'المخالفات حسب التصنيف' in query and 'حسب الحساب' in query:
            return self._handle_compliance_column_diff()

        # Pattern B045: total violations, optional date filter, no sample
        if 'كم عدد المخالفات في' in query and not detected_samples and detected_period:
            return self._handle_total_violations(date_filter=detected_period)

        # Pattern B047: facilities exceeding a violation-count threshold
        facility_thresh_match = re.search(r'اكثر من\s*(\d+)\s*مر', norm(query))
        if facility_thresh_match and 'منشآت' in query:
            return self._handle_facility_violation_threshold(int(facility_thresh_match.group(1)))

        # Pattern B049: category rate vs overall average
        if 'مقارنة بالمعدل العام' in query and 'التوابل' in query:
            return self._handle_category_vs_overall_rate('spice')

        # Pattern C020: chemical group causing most violations
        if 'المجموعة الكيميائية الأكثر تسبباً' in query or 'المجموعات الكيميائية الأكثر تسبباً' in query:
            return self._handle_chemical_group_top_violator()

        # Pattern C022: violation % per chemical group
        if 'نسبة المخالفة لكل مجموعة كيميائية' in query:
            return self._handle_chemical_group_rates()

        # Pattern E011: %MRL per residue in a sample type
        if 'نسبة التركيز إلى الحد' in query or '%MRL' in query and 'متبقي' in query:
            return self._handle_mrl_pct_per_residue(detected_samples)

        # Pattern E012: avg %MRL per product, global
        if 'متوسط نسبة %MRL لكل منتج' in query or ('متوسط' in query and 'MRL' in query and 'منتج' in query):
            return self._handle_avg_mrl_pct_per_product()

        # Pattern E030: QI averaged per product, global
        if 'مؤشر الجودة لكل منتج' in query:
            return self._handle_quality_index_by_product()

        # Pattern E033: samples with highest HRI, ranked
        if 'أعلى مؤشر خطر صحي' in query:
            return self._handle_top_hri_samples(detected_samples)


        return None
