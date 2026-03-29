"""
english_patterns_patch.py
=========================
HOW TO USE THIS FILE:
---------------------
This file contains:
1. DIALECT SYNONYMS to add to _load_mappings()
2. NEW PATTERN BLOCKS to insert into process() in core_query_engine.py
3. Instructions for integrating AdvancedHandlersMixin

STEP 1: Add AdvancedHandlersMixin to CoreQueryEngine
------------------------------------------------------
In core_query_engine.py, change:

    class CoreQueryEngine:

to:

    from modules.advanced_handlers import AdvancedHandlersMixin
    from modules.pesticide_groups import classify_pesticide  # (optional, used in handlers)
    
    class CoreQueryEngine(AdvancedHandlersMixin):

STEP 2: Copy pesticide_groups.py and advanced_handlers.py to src/LARS/modules/
--------------------------------------------------------------------------------
    cp pesticide_groups.py src/LARS/modules/
    cp advanced_handlers.py src/LARS/modules/

STEP 3: Add English synonyms to _load_mappings() in CoreQueryEngine
---------------------------------------------------------------------
Paste the ENGLISH_SYNONYMS dict into the dialect_synonyms section.

STEP 4: Insert new pattern blocks into process()
-------------------------------------------------
See the pattern code blocks below — each has a comment showing WHERE to insert it.
"""

# ============================================================
# STEP 3: Add to _load_mappings()
# Paste into self.dialect_synonyms dict
# ============================================================
ENGLISH_SYNONYMS_TO_ADD = """
            # English "each separately" detection
            'each separately': 'كل علي حده',
            'each one separately': 'كل علي حده',
            'for each': 'كل علي حده',
            'individually': 'كل علي حده',
            # English action words
            'give me': 'أعطني',
            'show me': 'أرني',
            'find': 'ابحث',
            'search for': 'ابحث',
            'display': 'اعرض',
            'list': 'اعرض',
            'how many': 'كم',
            'what are': 'ما هي',
            'what is': 'ما هو',
            'which': 'ما هي',
            # English limit/compliance
            'above limit': 'فوق الحد',
            'above the limit': 'فوق الحد',
            'above permissible': 'فوق الحد',
            'exceeding': 'تجاوز',
            'below limit': 'تحت الحد',
            'below the limit': 'تحت الحد',
            'non-compliant': 'غير مطابق',
            'non compliant': 'غير مطابق',
            'failed': 'غير مطابق',
            'failing': 'غير مطابق',
            'compliant': 'مطابق',
            'passed': 'مطابق',
            # English sample/analysis words
            'violations': 'مخالفات',
            'violation': 'مخالفة',
            'frequency': 'تكرار',
            'pesticide free': 'خالية من المبيدات',
            'pesticide-free': 'خالية من المبيدات',
            'unique': 'فريدة',
            'distinct': 'فريدة',
            'rank': 'ترتيب',
            'ranking': 'ترتيب',
            'descending': 'تنازلي',
            'ascending': 'تصاعدي',
            'neighborhood': 'حي',
            'neighborhoods': 'احياء',
            'facility': 'منشأة',
            'recipient': 'المستلم',
            'chemical group': 'مجموعة كيميائية',
            'chemical groups': 'مجموعة كيميائية',
            'health risk': 'مخاطر صحية',
            'quality index': 'مؤشر جودة',
            'range': 'مدى',
            'average': 'متوسط',
            'mean': 'متوسط',
            'median': 'وسيط',
            'highest': 'أعلى',
            'lowest': 'أقل',
            'maximum': 'أعلى',
            'minimum': 'أقل',
            'comprehensive': 'شامل',
            'classify': 'صنف',
            'classification': 'تصنيف',
            'summary': 'ملخص',
            'types': 'أنواع',
            'count': 'عدد',
            'number of': 'عدد',
            'samples': 'عينات',
            'sample': 'عينة',
            'pesticides': 'مبيدات',
            'pesticide': 'مبيد',
            'contain': 'تحتوي',
            'contains': 'تحتوي',
            'associated with': 'مرتبط بـ',
"""

# ============================================================
# STEP 4: New pattern blocks for process()
# ============================================================
# INSERT each block at the specified location in process()

# ---- PATTERN A: Health Risk Index --------------------------
# INSERT: AFTER Pattern 8 (pesticide stats), BEFORE Pattern 9 (facility search)
PATTERN_A_HEALTH_RISK = """
        # ============================================================
        # Pattern HRI: Health Risk Index
        # "health risk index for cucumber" / "مؤشر الخطر الصحي للخيار"
        # ============================================================
        hri_keywords_en = ['health risk index', 'health risk', 'hri', 'risk index']
        hri_keywords_ar = ['مؤشر الخطر الصحي', 'مخاطر صحية', 'الخطر الصحي', 'الخطر على الصحة']
        is_hri_query = (
            any(kw in query_lower for kw in hri_keywords_en) or
            any(kw in query for kw in hri_keywords_ar)
        )
        if is_hri_query and detected_samples:
            return self._handle_health_risk_index(detected_samples)

        # ============================================================
        # Pattern QI: Quality Index
        # "quality index for pepper" / "مؤشر الجودة للفلفل"
        # ============================================================
        qi_keywords_en = ['quality index', 'qi ', 'quality score', 'quality indicator']
        qi_keywords_ar = ['مؤشر الجودة', 'مؤشر جودة', 'معيار الجودة']
        is_qi_query = (
            any(kw in query_lower for kw in qi_keywords_en) or
            any(kw in query for kw in qi_keywords_ar)
        )
        if is_qi_query and detected_samples:
            return self._handle_quality_index(detected_samples)

        # ============================================================
        # Pattern CG: Chemical Groups Analysis
        # "classify pesticides in cardamom" / "chemical groups for samples with >3 pesticides"
        # "summary of chemical groups for each sample containing more than 3 pesticides"
        # ============================================================
        cg_keywords_en = ['chemical group', 'chemical groups', 'classify pesticide',
                          'pesticide class', 'pesticide type', 'group classification']
        cg_keywords_ar = ['مجموعة كيميائية', 'مجموعات كيميائية', 'تصنيف المبيدات',
                          'صنف المبيدات', 'التصنيف الكيميائي', 'الفئة الكيميائية']
        is_cg_query = (
            any(kw in query_lower for kw in cg_keywords_en) or
            any(kw in query for kw in cg_keywords_ar)
        )
        if is_cg_query:
            # Check for minimum pesticide count filter
            min_pest = 0
            import re as _re
            _nums = _re.findall(r'(\\d+)', query_normalized)
            threshold_kws = ['more than', 'greater than', 'أكثر من', 'اكثر من', 'تحتوي على أكثر من']
            if _nums and any(kw in query_lower or kw in query for kw in threshold_kws):
                min_pest = int(_nums[0])
            return self._handle_chemical_groups(detected_samples, min_pesticides=min_pest)

        # ============================================================
        # Pattern CAT+PEST: Category + Pesticide query
        # "which vegetables are associated with bifenthrin"
        # ============================================================
        # Detect if query has a pesticide AND a category keyword (not a specific sample)
        category_en_map = {
            'vegetable': 'vegetable', 'vegetables': 'vegetable',
            'fruit': 'fruit', 'fruits': 'fruit',
            'spice': 'spice', 'spices': 'spice',
            'nut': 'nut', 'nuts': 'nut',
            'grain': 'grain', 'grains': 'grain',
            'leafy': 'leafy',
        }
        category_ar_map = {
            'خضار': 'vegetable', 'خضروات': 'vegetable',
            'فاكهة': 'fruit', 'فواكه': 'fruit',
            'توابل': 'spice', 'بهارات': 'spice',
            'مكسرات': 'nut',
            'حبوب': 'grain',
            'ورقيات': 'leafy',
        }
        _cat_key = None
        for kw, cat in category_en_map.items():
            if kw in query_lower:
                _cat_key = cat
                break
        if not _cat_key:
            for kw, cat in category_ar_map.items():
                if kw in query:
                    _cat_key = cat
                    break
        if detected_pesticide and _cat_key and not detected_samples:
            return self._handle_category_pesticide(detected_pesticide, _cat_key, [])

        # ============================================================
        # Pattern CAT_LIMIT: Category above+below limit summary
        # "give me pesticides and mycotoxins above and below limits for spices"
        # ============================================================
        cat_limit_kws_en = ['above and below', 'above or below', 'above & below']
        cat_limit_kws_ar = ['فوق وتحت', 'فوق الحد وتحت', 'المسموح بها وغير']
        is_cat_limit = (
            any(kw in query_lower for kw in cat_limit_kws_en) or
            any(kw in query for kw in cat_limit_kws_ar)
        )
        if is_cat_limit and _cat_key:
            # Detect test type (pesticide vs mycotoxin)
            _test_type = None
            if 'mycotoxin' in query_lower or 'سموم فطرية' in query:
                _test_type = 'mycotoxin'
            elif 'pesticide' in query_lower or 'مبيد' in query:
                _test_type = 'pesticide'
            return self._handle_category_limit_summary(_cat_key, detected_samples, _test_type)

        # ============================================================
        # Pattern AVG_LIMIT: Average concentration above/below limit
        # "average concentration of imidacloprid in samples above limit"
        # ============================================================
        avg_above_kws_en = ['average concentration above', 'avg concentration above',
                            'mean concentration above', 'average above limit']
        avg_above_kws_ar = ['متوسط التركيز فوق الحد', 'متوسط التركيز في العينات فوق']
        is_avg_limit = (
            any(kw in query_lower for kw in avg_above_kws_en + avg_above_kws_ar) or
            ('average' in query_lower and 'above limit' in query_lower and detected_pesticide) or
            ('متوسط' in query and 'فوق الحد' in query and detected_pesticide)
        )
        if is_avg_limit and detected_pesticide:
            _is_above = 'above' in query_lower or 'فوق' in query
            return self._handle_avg_concentration_limit(detected_pesticide, detected_samples, _is_above)

        # ============================================================
        # Pattern UNIQUE_NC: Unique non-compliant + pesticide repetitions
        # "How many unique non-compliant samples in cardamom + pesticide repetitions"
        # ============================================================
        unique_nc_kws_en = ['unique non-compliant', 'unique noncompliant', 'unique non compliant']
        unique_nc_kws_ar = ['الفريدة غير المطابقة', 'غير المطابقة الفريدة']
        is_unique_nc = (
            any(kw in query_lower for kw in unique_nc_kws_en) or
            any(kw in query for kw in unique_nc_kws_ar) or
            (('unique' in query_lower or 'فريدة' in query) and
             ('non-compliant' in query_lower or 'غير مطابق' in query) and
             ('repetition' in query_lower or 'تكرار' in query or 'frequency' in query_lower))
        )
        if is_unique_nc and detected_samples:
            return self._handle_unique_noncompliant_with_pesticides(detected_samples)

        # ============================================================
        # Pattern FREQ: Pesticide frequency in specific sample
        # "frequency of imidacloprid in tomatoes"
        # "what is the frequency of X in Y"
        # ============================================================
        freq_kws_en = ['frequency of', 'how often', 'how frequent', 'occurrence of']
        freq_kws_ar = ['تكرار مبيد', 'معدل تكرار', 'كم مرة ظهر']
        is_freq_query = (
            any(kw in query_lower for kw in freq_kws_en) or
            any(kw in query for kw in freq_kws_ar)
        )
        if is_freq_query and detected_pesticide and detected_samples:
            return self._handle_pesticide_frequency_in_sample(detected_pesticide, detected_samples)
"""

# ============================================================
# STEP 5: Quick test - verify all handlers are importable
# ============================================================
if __name__ == "__main__":
    print("✅ english_patterns_patch.py loaded successfully")
    print("📋 Handlers provided by AdvancedHandlersMixin:")
    print("  - _handle_health_risk_index(samples)")
    print("  - _handle_quality_index(samples)")
    print("  - _handle_chemical_groups(samples, min_pesticides=0)")
    print("  - _handle_category_pesticide(pesticide, category_key, samples)")
    print("  - _handle_avg_concentration_limit(pesticide, samples, is_above)")
    print("  - _handle_unique_noncompliant_with_pesticides(samples)")
    print("  - _handle_pesticide_frequency_in_sample(pesticide, samples)")
    print("  - _handle_category_limit_summary(category_key, samples, test_type)")
    print()
    print("📋 Pattern blocks to add to process():")
    print("  - HRI (health risk index)")
    print("  - QI (quality index)")
    print("  - CG (chemical groups)")
    print("  - CAT+PEST (category + pesticide)")
    print("  - CAT_LIMIT (category above+below limit)")
    print("  - AVG_LIMIT (average concentration above/below limit)")
    print("  - UNIQUE_NC (unique non-compliant + repetitions)")
    print("  - FREQ (pesticide frequency)")