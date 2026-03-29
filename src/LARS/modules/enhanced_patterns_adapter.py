"""
enhanced_patterns_adapter.py
============================
محول محسّن يدعم جميع أنواع الأسئلة الشائعة
"""
import re
import duckdb
from typing import Dict, List, Optional, Tuple
import pandas as pd


class EnhancedPatternsAdapter:
    """محول محسّن مع دعم كامل للأنماط"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        
        # خرائط الترجمة
        self.sample_types_ar_to_pattern = {
            'طماطم': 'طماطم', 'الطماطم': 'طماطم', 'طماطة': 'طماطم',
            'خيار': 'خيار', 'الخيار': 'خيار',
            'كوسة': 'كوسة', 'كوسا': 'كوسة', 'الكوسة': 'كوسة', 'الكوسا': 'كوسة',
            'فلفل': 'فلفل', 'الفلفل': 'فلفل',
            'باذنجان': 'باذنجان', 'الباذنجان': 'باذنجان',
            'فاصوليا': 'فاصوليا', 'فصوليا': 'فاصوليا', 'فصولية': 'فاصوليا',
            'هيل': 'هيل', 'الهيل': 'هيل',
            'فستق': 'فستق', 'الفستق': 'فستق',
            'توابل': 'توابل', 'التوابل': 'توابل', 'بهارات': 'توابل',
            'مكسرات': 'مكسرات', 'المكسرات': 'مكسرات',
        }
        
        self.sample_types_en = {
            'tomato': 'طماطم', 'tomatoes': 'طماطم',
            'cucumber': 'خيار', 'cucumbers': 'خيار',
            'zucchini': 'كوسة', 'squash': 'كوسة',
            'pepper': 'فلفل', 'peppers': 'فلفل',
            'eggplant': 'باذنجان', 'aubergine': 'باذنجان',
            'beans': 'فاصوليا', 'bean': 'فاصوليا',
            'cardamom': 'هيل',
            'pistachio': 'فستق', 'pistachios': 'فستق',
            'spices': 'توابل', 'spice': 'توابل',
            'nuts': 'مكسرات',
        }
        
        self.pesticides_ar_to_en = {
            'البايفنثرن': 'bifenthrin', 'بايفنثرن': 'bifenthrin',
            'الفيبرونيل': 'fipronil', 'فيبرونيل': 'fipronil',
            'الكلوربيريفوس': 'chlorpyrifos', 'كلوربيريفوس': 'chlorpyrifos',
            'الايميداكلوبريد': 'imidacloprid', 'ايميداكلوبريد': 'imidacloprid', 'ايميداكلوبرايد': 'imidacloprid',
            'البابروفيزن': 'buprofezin', 'بابروفيزن': 'buprofezin', 'بوبروفيزين': 'buprofezin',
            'الايثيون': 'ethion', 'ايثيون': 'ethion',
            'دلتامثرين': 'deltamethrin', 'الدلتامثرين': 'deltamethrin',
            'سيبرمثرين': 'cypermethrin', 'السيبرمثرين': 'cypermethrin',
            'ثياميثوكسام': 'thiamethoxam', 'الثياميثوكسام': 'thiamethoxam',
            'كاربندازيم': 'carbendazim', 'الكاربندازيم': 'carbendazim',
            'ابامكتين': 'abamectin', 'الابامكتين': 'abamectin',
        }
        
        self.pesticides_en_variants = {
            'bifenthrin': ['bifenthrin', 'bifenazate'],
            'fipronil': ['fipronil'],
            'chlorpyrifos': ['chlorpyrifos', 'chlorpyriphos'],
            'imidacloprid': ['imidacloprid', 'imidaclopride', 'imidaclprid'],
            'buprofezin': ['buprofezin', 'buprofuzin', 'bupro'],
            'ethion': ['ethion'],
        }
        
        self.neighborhoods = {
            'الإسكان': 'الإسكان', 'الاسكان': 'الإسكان', 'اسكان': 'الإسكان',
            'الريان': 'الريان', 'ريان': 'الريان',
            'النهضة': 'النهضة', 'نهضة': 'النهضة',
            'الأخضر': 'الأخضر', 'اخضر': 'الأخضر',
            'الروضة': 'الروضة', 'روضة': 'الروضة',
            'النخيل': 'النخيل', 'نخيل': 'النخيل',
        }

    def match_and_execute(self, query: str) -> Tuple[Optional[str], Optional[pd.DataFrame]]:
        """مطابقة وتنفيذ الاستعلام"""
        
        # تطبيع الاستعلام
        query_normalized = self._normalize_query(query)
        
        # Pattern 1: البحث عن مبيد في عينة
        if self._is_find_pesticide_in_sample(query_normalized):
            return self._execute_find_pesticide_in_sample(query_normalized)
        
        # Pattern 2: عدد العينات فوق/تحت الحد
        if self._is_count_samples_limit(query_normalized):
            return self._execute_count_samples_limit(query_normalized)
        
        # Pattern 3: العينات التي تحتوي على N مبيدات
        if self._is_samples_with_n_pesticides(query_normalized):
            return self._execute_samples_with_n_pesticides(query_normalized)
        
        # Pattern 4: المبيدات في عينة معينة
        if self._is_list_pesticides_in_sample(query_normalized):
            return self._execute_list_pesticides_in_sample(query_normalized)
        
        # Pattern 5: المبيدات في أحياء
        if self._is_pesticides_in_neighborhoods(query_normalized):
            return self._execute_pesticides_in_neighborhoods(query_normalized)
        
        # Pattern 6: إحصائيات متقدمة (max, min, median, avg)
        if self._is_statistics_query(query_normalized):
            return self._execute_statistics_query(query_normalized)
        
        # Pattern 7: عينات بمنشأة/مستلم معين
        if self._is_establishment_query(query_normalized):
            return self._execute_establishment_query(query_normalized)
        
        # Pattern 8: ترتيب الأحياء حسب المخالفات
        if self._is_neighborhood_ranking(query_normalized):
            return self._execute_neighborhood_ranking(query_normalized)
        
        return None, None

    def _normalize_query(self, query: str) -> str:
        """تطبيع الاستعلام"""
        # تحويل الأرقام العربية
        arabic_numerals = {'٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4', 
                          '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'}
        for ar, en in arabic_numerals.items():
            query = query.replace(ar, en)
        
        # تحويل كلمات الأرقام العربية
        num_words = {'واحد': '1', 'اثنين': '2', 'ثلاثة': '3', 'اربعة': '4', 
                     'خمسة': '5', 'ستة': '6', 'سبعة': '7', 'ثمانية': '8', 
                     'تسعة': '9', 'عشرة': '10'}
        for word, num in num_words.items():
            query = query.replace(word, num)
        
        return query

    def _detect_sample_types(self, query: str) -> List[str]:
        """كشف أنواع العينات"""
        detected = []
        
        # Arabic
        for ar_name, pattern in self.sample_types_ar_to_pattern.items():
            if ar_name in query:
                if pattern not in detected:
                    detected.append(pattern)
        
        # English
        query_lower = query.lower()
        for en_name, ar_pattern in self.sample_types_en.items():
            if en_name in query_lower:
                if ar_pattern not in detected:
                    detected.append(ar_pattern)
        
        return detected

    def _detect_pesticide(self, query: str) -> Optional[str]:
        """كشف المبيد"""
        # Arabic
        for ar_name, en_name in self.pesticides_ar_to_en.items():
            if ar_name in query:
                return en_name
        
        # English
        query_lower = query.lower()
        for en_name, variants in self.pesticides_en_variants.items():
            for variant in variants:
                if variant in query_lower:
                    return en_name
        
        return None

    def _detect_neighborhoods(self, query: str) -> List[str]:
        """كشف الأحياء"""
        detected = []
        for ar_name, normalized in self.neighborhoods.items():
            if ar_name in query:
                if normalized not in detected:
                    detected.append(normalized)
        return detected

    # ==================== Pattern Detection ====================

    def _is_find_pesticide_in_sample(self, query: str) -> bool:
        """Pattern: ابحث عن مبيد في عينة"""
        keywords = ['find', 'ابحث', 'اعثر', 'اوجد', 'في']
        has_keyword = any(kw in query.lower() or kw in query for kw in keywords)
        has_pesticide = self._detect_pesticide(query) is not None
        has_sample = len(self._detect_sample_types(query)) > 0
        
        return has_keyword and (has_pesticide or has_sample)

    def _is_count_samples_limit(self, query: str) -> bool:
        """Pattern: ما عدد العينات فوق/تحت الحد"""
        count_keywords = ['count', 'عدد', 'كم', 'ماهي', 'what are']
        limit_keywords = ['فوق الحد', 'تحت الحد', 'above limit', 'below limit', 
                         'more than limit', 'exceeding', 'within limit']
        
        has_count = any(kw in query.lower() or kw in query for kw in count_keywords)
        has_limit = any(kw in query.lower() or kw in query for kw in limit_keywords)
        has_sample = len(self._detect_sample_types(query)) > 0
        
        return has_count and has_limit and has_sample

    def _is_samples_with_n_pesticides(self, query: str) -> bool:
        """Pattern: عينات تحتوي على N مبيدات"""
        pattern = r'(\d+)\s*(?:مبيد|مبيدات|pesticide)'
        match = re.search(pattern, query, re.IGNORECASE)
        return match is not None

    def _is_list_pesticides_in_sample(self, query: str) -> bool:
        """Pattern: ماهي المبيدات في عينة"""
        keywords = ['المبيدات', 'pesticides', 'ماهي المبيدات', 'المبيدات الموجوده',
                   'المبيدات التي ظهرت', 'pesticides in']
        has_keyword = any(kw in query for kw in keywords)
        has_sample = len(self._detect_sample_types(query)) > 0
        
        return has_keyword and has_sample

    def _is_pesticides_in_neighborhoods(self, query: str) -> bool:
        """Pattern: المبيدات في حي"""
        has_pesticide_kw = 'المبيدات' in query or 'pesticides' in query.lower()
        has_neighborhood_kw = 'حي' in query or 'neighborhood' in query.lower()
        has_neighborhoods = len(self._detect_neighborhoods(query)) > 0
        
        return has_pesticide_kw and (has_neighborhood_kw or has_neighborhoods)

    def _is_statistics_query(self, query: str) -> bool:
        """Pattern: إحصائيات (max, min, avg, median)"""
        stat_keywords = ['اعلي', 'اقل', 'متوسط', 'وسيط', 'المدي',
                        'max', 'min', 'average', 'median', 'range']
        return any(kw in query for kw in stat_keywords)

    def _is_establishment_query(self, query: str) -> bool:
        """Pattern: عينات في منشأة"""
        keywords = ['منشأة', 'منشاة', 'establishment', 'المستلم', 'recipient']
        return any(kw in query for kw in keywords)

    def _is_neighborhood_ranking(self, query: str) -> bool:
        """Pattern: ترتيب الأحياء"""
        keywords = ['ترتيب', 'تنازلي', 'تصاعدي', 'الاكثر', 'الاقل', 'ranking']
        has_keyword = any(kw in query for kw in keywords)
        has_neighborhood = 'حي' in query or 'احياء' in query or 'neighborhood' in query.lower()
        
        return has_keyword and has_neighborhood

    # ==================== Pattern Execution ====================

    def _execute_find_pesticide_in_sample(self, query: str) -> Tuple[str, pd.DataFrame]:
        """تنفيذ: البحث عن مبيد في عينة"""
        pesticide = self._detect_pesticide(query)
        samples = self._detect_sample_types(query)
        
        # Check for compliance filter
        is_non_compliant = any(kw in query.lower() or kw in query 
                               for kw in ['non compliant', 'غير مطابق', 'exceeding', 
                                         'فوق الحد', 'above limit'])
        
        # Check for ratio filter (e.g., "more than 2 times")
        ratio_match = re.search(r'more than (\d+) times', query.lower())
        ratio_value = float(ratio_match.group(1)) if ratio_match else None
        
        # Build SQL
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
        
        if pesticide:
            # Get variants
            variants = self.pesticides_en_variants.get(pesticide, [pesticide])
            variant_conditions = [f"pesticide_name ILIKE '%{v}%'" for v in variants]
            sql += f" AND ({' OR '.join(variant_conditions)})"
        
        if samples:
            if len(samples) == 1:
                sql += f" AND \"اسم العينة\" LIKE '%{samples[0]}%'"
            else:
                sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
                sql += f" AND ({' OR '.join(sample_conditions)})"
        
        if is_non_compliant:
            sql += " AND is_compliant = 0"
        
        if ratio_value:
            sql += f" AND exceedance_ratio > {ratio_value}"
        
        sql += " ORDER BY exceedance_ratio DESC LIMIT 50"
        
        df = self._execute_sql(sql)
        
        # Build response
        pesticide_display = pesticide or "المبيدات"
        sample_display = " + ".join(samples) if samples else "جميع العينات"
        
        response = f"🔍 **البحث عن {pesticide_display} في {sample_display}**\n\n"
        
        if not df.empty:
            total = len(df)
            compliant = len(df[df['status'] == 'مطابق'])
            non_compliant = len(df[df['status'] == 'غير مطابق'])
            
            response += f"✅ وجدت **{total}** نتيجة\n"
            response += f"• مطابق: {compliant}\n"
            response += f"• غير مطابق: {non_compliant}\n\n"
            
            if len(df) <= 10:
                response += df.to_markdown(index=False)
            else:
                response += df.head(10).to_markdown(index=False)
                response += f"\n\n... و {len(df)-10} نتيجة أخرى (في الملف المرفق)"
        else:
            response += "⚠️ لم أجد نتائج مطابقة."
        
        return response, df

    def _execute_count_samples_limit(self, query: str) -> Tuple[str, pd.DataFrame]:
        """تنفيذ: عد العينات فوق/تحت الحد"""
        samples = self._detect_sample_types(query)
        
        # Detect separately request
        show_separately = any(kw in query for kw in ['كل علي حده', 'كل على حده', 'separately'])
        
        if not samples:
            return "⚠️ لم أتمكن من تحديد نوع العينة.", pd.DataFrame()
        
        if show_separately and len(samples) > 1:
            # Show each separately
            all_dfs = []
            response = f"📊 **إحصائيات العينات (كل على حده):**\n\n"
            
            for sample in samples:
                sql = f"""
                SELECT 
                    "اسم العينة" as sample_type,
                    COUNT(DISTINCT "كود العينة") as total_samples,
                    SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as above_limit,
                    SUM(CASE WHEN is_above_limit = 0 AND is_detected = 1 THEN 1 ELSE 0 END) as below_limit
                FROM chemistry_tidy
                WHERE is_detected = 1
                AND "اسم العينة" LIKE '%{sample}%'
                GROUP BY "اسم العينة"
                """
                df = self._execute_sql(sql)
                
                if not df.empty:
                    total = int(df['total_samples'].sum())
                    above = int(df['above_limit'].sum())
                    below = int(df['below_limit'].sum())
                    
                    response += f"**{sample}:** {total} عينة ({above} فوق الحد، {below} تحت الحد)\n"
                    all_dfs.append(df)
            
            combined_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
            return response, combined_df
        
        else:
            # Combined
            sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
            sample_filter = f"({' OR '.join(sample_conditions)})"
            
            sql = f"""
            SELECT 
                "اسم العينة" as sample_type,
                COUNT(DISTINCT "كود العينة") as total_samples,
                SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as above_limit,
                SUM(CASE WHEN is_above_limit = 0 AND is_detected = 1 THEN 1 ELSE 0 END) as below_limit
            FROM chemistry_tidy
            WHERE is_detected = 1
            AND {sample_filter}
            GROUP BY "اسم العينة"
            ORDER BY total_samples DESC
            """
            
            df = self._execute_sql(sql)
            
            response = f"📊 **إحصائيات العينات:**\n\n"
            if not df.empty:
                total = int(df['total_samples'].sum())
                above = int(df['above_limit'].sum())
                below = int(df['below_limit'].sum())
                
                response += f"• إجمالي: {total} عينة\n"
                response += f"• فوق الحد: {above}\n"
                response += f"• تحت الحد: {below}\n\n"
                response += df.to_markdown(index=False)
            else:
                response += "⚠️ لم أجد نتائج."
            
            return response, df

    def _execute_samples_with_n_pesticides(self, query: str) -> Tuple[str, pd.DataFrame]:
        """تنفيذ: عينات تحتوي على N مبيدات"""
        # Extract numbers
        pattern = r'(\d+)\s*(?:مبيد|مبيدات|pesticide)'
        matches = re.findall(pattern, query, re.IGNORECASE)
        
        if not matches:
            return "⚠️ لم أتمكن من تحديد عدد المبيدات.", pd.DataFrame()
        
        # Convert to integers and remove duplicates
        numbers = sorted(list(set([int(m) for m in matches])))
        
        # Detect samples
        samples = self._detect_sample_types(query)
        
        # Check for "each separately"
        show_separately = any(kw in query for kw in ['كل علي حده', 'كل على حده', 'separately'])
        
        if show_separately and len(numbers) > 1:
            # Show each count separately
            response = f"📊 **عينات بعدد مبيدات مختلف (كل على حده):**\n\n"
            
            all_dfs = []
            for n in numbers:
                sql = f"""
                SELECT 
                    {n} as pesticide_count,
                    COUNT(*) as sample_count
                FROM (
                    SELECT "كود العينة"
                    FROM chemistry_tidy
                    WHERE is_detected = 1 
                    AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
                """
                
                if samples:
                    sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
                    sql += f" AND ({' OR '.join(sample_conditions)})"
                
                sql += f"""
                    GROUP BY "كود العينة"
                    HAVING COUNT(*) = {n}
                )
                """
                
                df = self._execute_sql(sql)
                
                if not df.empty:
                    count = int(df['sample_count'].iloc[0])
                    response += f"**{n} مبيد:** {count} عينة\n"
                    all_dfs.append(df)
                else:
                    response += f"**{n} مبيد:** 0 عينة\n"
            
            combined_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
            return response, combined_df
        
        else:
            # Single or combined
            n = numbers[0]
            
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
                sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
                sql += f" AND ({' OR '.join(sample_conditions)})"
            
            sql += f"""
            GROUP BY "كود العينة", "اسم العينة"
            HAVING COUNT(*) = {n}
            ORDER BY "كود العينة" DESC
            LIMIT 50
            """
            
            df = self._execute_sql(sql)
            
            sample_display = " + ".join(samples) if samples else "جميع الأنواع"
            response = f"🔢 **عينات {sample_display} التي تحتوي على {n} مبيدات:**\n\n"
            
            if not df.empty:
                response += f"✅ وجدت **{len(df)}** عينة\n\n"
                
                if len(df) <= 15:
                    response += df.to_markdown(index=False)
                else:
                    response += df.head(15).to_markdown(index=False)
                    response += f"\n\n... و {len(df)-15} عينة أخرى"
            else:
                response += f"⚠️ لم أجد عينات تحتوي على {n} مبيدات."
            
            return response, df

    def _execute_list_pesticides_in_sample(self, query: str) -> Tuple[str, pd.DataFrame]:
        """تنفيذ: قائمة المبيدات في عينة"""
        samples = self._detect_sample_types(query)
        
        if not samples:
            return "⚠️ لم أتمكن من تحديد نوع العينة.", pd.DataFrame()
        
        sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        sample_filter = f"({' OR '.join(sample_conditions)})"
        
        sql = f"""
        SELECT 
            pesticide_name as المبيد,
            COUNT(*) as عدد_التكرار,
            ROUND(AVG(concentration), 4) as متوسط_التركيز,
            ROUND(MAX(concentration), 4) as أعلى_تركيز,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as عدد_المخالفات
        FROM chemistry_tidy
        WHERE {sample_filter}
        AND is_detected = 1
        AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        GROUP BY pesticide_name
        ORDER BY عدد_التكرار DESC, عدد_المخالفات DESC
        LIMIT 30
        """
        
        df = self._execute_sql(sql)
        
        sample_display = " + ".join(samples)
        response = f"🧪 **المبيدات في {sample_display}:**\n\n"
        
        if not df.empty:
            total_detections = int(df['عدد_التكرار'].sum())
            total_violations = int(df['عدد_المخالفات'].sum())
            unique_pesticides = len(df)
            
            response += f"📊 **الملخص:**\n"
            response += f"• عدد المبيدات المختلفة: {unique_pesticides}\n"
            response += f"• إجمالي الاكتشافات: {total_detections}\n"
            response += f"• إجمالي المخالفات: {total_violations}\n\n"
            response += df.to_markdown(index=False)
        else:
            response += "⚠️ لم أجد مبيدات في هذه العينات."
        
        return response, df

    def _execute_pesticides_in_neighborhoods(self, query: str) -> Tuple[str, pd.DataFrame]:
        """تنفيذ: المبيدات في أحياء"""
        neighborhoods = self._detect_neighborhoods(query)
        
        if not neighborhoods:
            return "⚠️ لم أتمكن من تحديد الأحياء.", pd.DataFrame()
        
        # Check for "each separately"
        show_separately = any(kw in query for kw in ['كل علي حده', 'كل على حده', 'separately'])
        
        # Build neighborhood filter with variants
        all_conditions = []
        for n in neighborhoods:
            variants = [n]
            if 'ا' in n:
                variants.append(n.replace('ا', 'إ'))
                variants.append(n.replace('ا', 'أ'))
            if 'إ' in n:
                variants.append(n.replace('إ', 'ا'))
            
            for v in set(variants):
                all_conditions.append(f"\"الحى\" LIKE '%{v}%'")
        
        neighborhood_filter = f"({' OR '.join(all_conditions)})"
        
        if show_separately:
            # Show each neighborhood separately
            response = f"🏘️ **المبيدات في الأحياء (كل على حده):**\n\n"
            
            all_dfs = []
            for neighborhood in neighborhoods:
                sql = f"""
                SELECT 
                    pesticide_name as المبيد,
                    COUNT(*) as عدد_الكشف,
                    SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as فوق_الحد,
                    SUM(CASE WHEN is_above_limit = 0 THEN 1 ELSE 0 END) as تحت_الحد
                FROM chemistry_tidy
                WHERE "الحى" LIKE '%{neighborhood}%'
                AND is_detected = 1
                AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
                GROUP BY pesticide_name
                ORDER BY عدد_الكشف DESC
                LIMIT 10
                """
                
                df = self._execute_sql(sql)
                
                if not df.empty:
                    total = int(df['عدد_الكشف'].sum())
                    violations = int(df['فوق_الحد'].sum())
                    
                    response += f"**📍 {neighborhood}:**\n"
                    response += f"• {len(df)} مبيد، {total} اكتشاف، {violations} مخالفة\n"
                    response += df.head(5).to_markdown(index=False) + "\n\n"
                    
                    all_dfs.append(df)
            
            combined_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
            return response, combined_df
        
        else:
            # Combined
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
            
            neighborhoods_display = " + ".join(neighborhoods)
            response = f"🏘️ **المبيدات في {neighborhoods_display}:**\n\n"
            
            if not df.empty:
                response += f"✅ وجدت {len(df)} سجل\n\n"
                response += df.to_markdown(index=False)
            else:
                response += "⚠️ لم أجد مبيدات في هذه الأحياء."
            
            return response, df

    def _execute_statistics_query(self, query: str) -> Tuple[str, pd.DataFrame]:
        """تنفيذ: إحصائيات متقدمة"""
        pesticide = self._detect_pesticide(query)
        samples = self._detect_sample_types(query)
        
        if not pesticide:
            return "⚠️ لم أتمكن من تحديد المبيد.", pd.DataFrame()
        
        sql = f"""
        SELECT 
            pesticide_name,
            COUNT(*) as sample_count,
            ROUND(MIN(concentration), 4) as min_conc,
            ROUND(MAX(concentration), 4) as max_conc,
            ROUND(AVG(concentration), 4) as avg_conc,
            ROUND(MEDIAN(concentration), 4) as median_conc,
            ROUND(MAX(concentration) - MIN(concentration), 4) as range_conc
        FROM chemistry_tidy
        WHERE is_detected = 1
        AND pesticide_name ILIKE '%{pesticide}%'
        """
        
        if samples:
            sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
            sql += f" AND ({' OR '.join(sample_conditions)})"
        
        sql += " GROUP BY pesticide_name"
        
        df = self._execute_sql(sql)
        
        sample_display = " + ".join(samples) if samples else "جميع العينات"
        response = f"📊 **إحصائيات {pesticide} في {sample_display}:**\n\n"
        
        if not df.empty:
            row = df.iloc[0]
            response += f"• عدد العينات: {int(row['sample_count'])}\n"
            response += f"• أقل تركيز: {row['min_conc']}\n"
            response += f"• أعلى تركيز: {row['max_conc']}\n"
            response += f"• المتوسط: {row['avg_conc']}\n"
            response += f"• الوسيط: {row['median_conc']}\n"
            response += f"• المدى: {row['range_conc']}\n"
        else:
            response += "⚠️ لم أجد بيانات."
        
        return response, df

    def _execute_establishment_query(self, query: str) -> Tuple[str, pd.DataFrame]:
        """تنفيذ: عينات في منشأة/مستلم"""
        # Extract establishment or recipient name
        # This is tricky - look for Arabic names after keywords
        name = None
        
        if 'منشأة' in query or 'منشاة' in query:
            # Extract after منشأة
            match = re.search(r'منش[أا]ة\s+(.+?)(?:\s|$)', query)
            if match:
                name = match.group(1).strip()
        
        elif 'المستلم' in query:
            # Extract after المستلم
            match = re.search(r'المستلم\s+(.+?)(?:\s|$)', query)
            if match:
                name = match.group(1).strip()
        
        if not name:
            return "⚠️ لم أتمكن من تحديد اسم المنشأة أو المستلم.", pd.DataFrame()
        
        # Check if looking for compliant/non-compliant
        is_compliant_filter = None
        if 'مطابقة' in query or 'المطابقة' in query:
            is_compliant_filter = True
        elif 'غير مطابقة' in query or 'الغير مطابقة' in query:
            is_compliant_filter = False
        
        sql = f"""
        SELECT 
            "كود العينة" as sample_code,
            "اسم العينة" as sample_name,
            "اسم المنشاة" as establishment,
            "اسم المستلم" as recipient,
            COUNT(DISTINCT pesticide_name) as pesticide_count,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) as violations
        FROM chemistry_tidy
        WHERE (
            "اسم المنشاة" LIKE '%{name}%' 
            OR "اسم المستلم" LIKE '%{name}%'
        )
        """
        
        if is_compliant_filter is not None:
            if is_compliant_filter:
                sql += " AND is_compliant = 1"
            else:
                sql += " AND is_compliant = 0"
        
        sql += """
        GROUP BY "كود العينة", "اسم العينة", "اسم المنشاة", "اسم المستلم"
        ORDER BY "كود العينة" DESC
        LIMIT 30
        """
        
        df = self._execute_sql(sql)
        
        response = f"🏢 **عينات: {name}**\n\n"
        
        if not df.empty:
            # Get unique samples
            unique_samples = len(df)
            total_violations = int(df['violations'].sum())
            
            response += f"✅ وجدت {unique_samples} عينة فريدة\n"
            if total_violations > 0:
                response += f"• عدد المخالفات: {total_violations}\n\n"
            else:
                response += "\n"
            
            response += df.to_markdown(index=False)
        else:
            response += f"⚠️ لم أجد عينات لـ {name}"
        
        return response, df

    def _execute_neighborhood_ranking(self, query: str) -> Tuple[str, pd.DataFrame]:
        """تنفيذ: ترتيب الأحياء حسب المخالفات"""
        sql = """
        SELECT 
            "الحى" as الحي,
            COUNT(DISTINCT "كود العينة") as عدد_العينات,
            SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) as عدد_المخالفات,
            ROUND(SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) * 100.0 / 
                  COUNT(DISTINCT "كود العينة"), 2) as نسبة_المخالفات
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

    def _execute_sql(self, sql: str) -> pd.DataFrame:
        """تنفيذ SQL"""
        try:
            con = duckdb.connect(self.db_path, read_only=True)
            df = con.execute(sql).df()
            con.close()
            return df
        except Exception as e:
            print(f"❌ SQL Error: {e}")
            print(f"SQL: {sql}")
            return pd.DataFrame()