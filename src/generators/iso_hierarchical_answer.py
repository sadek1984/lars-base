from typing import Dict, Any
import re
# generators/iso_hierarchical_answer.py
class ISO17025AnswerGenerator:
    """مولد إجابات يفهم السياق الهرمي"""
    
    def _generate_hierarchical_answer(self, context: str, query_analysis: Dict, query: str = "") -> str:
        """توليد إجابة هرمية مع كشف اللغة محسن"""
        
        # كشف اللغة مع تسجيل
        language = self._detect_language(query)
        print(f"DEBUG: Detected language: {language} for query: {query}")  # للتشخيص
        
        # التأكد من استخدام الـ prompt الصحيح
        if language == "english":
            prompt = self._create_english_prompt(context, query, query_analysis)
            print("DEBUG: Using English prompt")
        else:
            prompt = self._create_arabic_prompt(context, query, query_analysis)
            print("DEBUG: Using Arabic prompt")
        
        try:
            answer = self.nlp_controller.generation_model.generate_content(prompt)
            formatted_answer = self._apply_enhanced_formatting(answer.text, language)
            
            # التحقق من لغة الإجابة النهائية
            if language == "english" and self._is_arabic_text(formatted_answer):
                print("WARNING: Expected English but got Arabic response")
                # إعادة المحاولة مع prompt أكثر وضوحاً
                return self._force_english_response(context, query)
            
            return formatted_answer
            
        except Exception as e:
            return self._create_fallback_answer(query, language)

    def _detect_language(self, query: str) -> str:
        """كشف اللغة محسن"""
        import re
        
        # عد الأحرف العربية
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', query))
        english_chars = len(re.findall(r'[a-zA-Z]', query))
        
        print(f"DEBUG: Arabic chars: {arabic_chars}, English chars: {english_chars}")
        
        # إذا كان هناك أحرف عربية أكثر من الإنجليزية
        if arabic_chars > english_chars:
            return "arabic"
        else:
            return "english"

    def _is_arabic_text(self, text: str) -> bool:
        """التحقق من وجود نص عربي في الإجابة"""
        import re
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        return arabic_chars > 10  # إذا كان هناك أكثر من 10 أحرف عربية

    def _force_english_response(self, context: str, query: str) -> str:
        """إجبار الإجابة بالإنجليزية"""
        
        prompt = f"""
        IMPORTANT: Answer in English only. Do not use Arabic.

        Based on ISO 17025 documents, answer this query in English:
        Query: {query}
        Context: {context}

        Format:
        # Direct Answer
        [Brief answer in English]

        # Technical Details  
        **Type:** [information]
        **Specifications:** [information]

        # Document Level
        **Level:** Work Instruction
        **Source:** Technical Documentation

        CRITICAL: Your entire response must be in English language only.
        """
        
        try:
            answer = self.nlp_controller.generation_model.generate_content(prompt)
            return answer.text
        except:
            return self._create_english_fallback(query)

    def _create_english_fallback(self, query: str) -> str:
        """إجابة احتياطية بالإنجليزية"""
        return f"""
    # Direct Answer
    Information about "{query}" was found in the technical documentation.

    ---

    # Technical Details
    **Type:** Technical Procedure
    **Method:** Extraction and cleanup procedure
    **Application:** Chemical residue analysis

    ---

    # Document Level
    **Level:** Work Instruction
    **Source:** GC-MS Work Instructions

    ---

    # ISO 17025 Context
    This procedure supports ISO 17025 requirements for technical competence and reliable analytical results.
    """
        def _create_english_prompt(self, context: str, query: str, query_analysis: Dict) -> str:
            """prompt إنجليزي محسن"""
            return f"""
            CRITICAL INSTRUCTION: You must respond entirely in English language. Do not use any Arabic text.

            Based on the ISO 17025 documents context below, answer the query in English:

            Context: {context}
            Query: {query}

            Required format (in English only):

            # Direct Answer
            [Write a clear, concise answer in English - 1-2 sentences maximum]

            ---

            # Technical Details
            **Type:** [specific information in English]
            **Specifications:** [specific information in English]  
            **Process:** [specific information in English]

            ---

            # Document Level
            **Level:** [Work Instruction/Procedure/Quality Manual]
            **Source:** [document name]

            ---

            # ISO 17025 Context
            [One paragraph in English explaining the importance]

            REMINDER: Your entire response must be in English only. Do not include any Arabic text.
            """

    def _create_arabic_prompt(self, context: str, query: str, query_analysis: Dict) -> str:
        """إنشاء prompt باللغة العربية"""
        return f"""
        بناءً على مستندات ISO 17025، أجب على الاستفسار باستخدام هذا التنسيق بالضبط:

        السياق: {context}
        الاستفسار: {query}

        استخدم هذا الهيكل:

        # الإجابة المباشرة
        [اكتب إجابة مختصرة ومباشرة في جملة أو جملتين]

        # التفاصيل التقنية
        **النوع:** [معلومة محددة]
        **المواصفات:** [معلومة محددة]
        **العملية:** [معلومة محددة]

        # مستوى المستند
        **المستوى:** [تعليمات عمل/إجراء/دليل جودة]
        **المصدر:** [اسم المستند]

        # سياق ISO 17025
        [فقرة واحدة تشرح الأهمية في إطار ISO 17025]

        تعليمات:
        - أجب بالعربية فقط
        - استخدم نقاط واضحة
        - اجعل كل قسم مختصر
        - استخدم تنسيق صحيح مع العناوين
        """

    def _apply_enhanced_formatting(self, text: str, language: str) -> str:
        """تطبيق تنسيق محسن للنص"""
        
        # تنظيف أساسي
        formatted = text.strip()
        
        # إضافة مسافات حول العناوين
        formatted = re.sub(r'^(# [^\n]+)', r'\1\n', formatted, flags=re.MULTILINE)
        
        # تحسين تنسيق النقاط
        formatted = re.sub(r'\*\*([^*]+)\*\*:', r'**\1:**', formatted)
        
        # إضافة مسافات بين الأقسام الرئيسية
        formatted = re.sub(r'\n(# [^\n]+)\n', r'\n\n\1\n', formatted)
        
        # تنظيف المسافات الزائدة
        formatted = re.sub(r'\n{3,}', '\n\n', formatted)
        
        # إضافة خطوط فاصلة بين الأقسام للوضوح
        if language == "english":
            formatted = formatted.replace('# Technical Details', '\n---\n\n# Technical Details')
            formatted = formatted.replace('# Document Level', '\n---\n\n# Document Level')
            formatted = formatted.replace('# ISO 17025 Context', '\n---\n\n# ISO 17025 Context')
        else:
            formatted = formatted.replace('# التفاصيل التقنية', '\n---\n\n# التفاصيل التقنية')
            formatted = formatted.replace('# مستوى المستند', '\n---\n\n# مستوى المستند')
            formatted = formatted.replace('# سياق ISO 17025', '\n---\n\n# سياق ISO 17025')
        
        return formatted

    def _create_fallback_answer(self, query: str, language: str) -> str:
        """إجابة احتياطية منسقة"""
        
        if language == "english":
            return """
    # Direct Answer
    Information related to your query was found in the technical documents.

    ---

    # Technical Details
    **Type:** Technical Information
    **Source:** ISO 17025 Documents
    **Status:** Available

    ---

    # Document Level
    **Level:** Work Instruction
    **Source:** Technical Documentation

    ---

    # ISO 17025 Context
    This information is part of the technical requirements for ISO 17025 compliance.
    """
        else:
            return """
    # الإجابة المباشرة
    تم العثور على معلومات ذات صلة بالاستفسار في المستندات التقنية.

    ---

    # التفاصيل التقنية
    **النوع:** معلومات تقنية
    **المصدر:** مستندات ISO 17025
    **الحالة:** متوفرة

    ---

    # مستوى المستند
    **المستوى:** تعليمات عمل
    **المصدر:** المستندات التقنية

    ---

    # سياق ISO 17025
    هذه المعلومات جزء من المتطلبات التقنية للامتثال لـ ISO 17025.
    """
    
    def _build_hierarchical_context(self, results: Dict) -> str:
        """بناء السياق الهرمي"""
        context_lines = []
        
        # ترتيب النتائج حسب المستوى
        sorted_levels = sorted(results.keys())
        
        for level in sorted_levels:
            level_info = self.get_level_description(level)
            if results[level]:
                context_lines.append(
                    f"**{level_info['name']}**: {level_info['role']}"
                )
                
                # إضافة الروابط
                if level > 1:
                    parent_level = level - 1
                    if parent_level in results:
                        context_lines.append(
                            f"  ↳ مرتبط بـ {self.get_level_description(parent_level)['name']}"
                        )
        
        return "\n".join(context_lines)
    
    def get_level_description(self, level: int) -> Dict:
        """وصف المستوى"""
        descriptions = {
            1: {"name": "دليل الجودة", "role": "يحدد السياسات العليا والإطار العام"},
            2: {"name": "الإجراءات", "role": "تطبق السياسات في خطوات عملية"},  
            3: {"name": "تعليمات العمل", "role": "تفصل الخطوات التنفيذية بدقة"},
            4: {"name": "النماذج والسجلات", "role": "توثق التنفيذ الفعلي"}
        }
        return descriptions.get(level, {"name": "غير محدد", "role": ""})