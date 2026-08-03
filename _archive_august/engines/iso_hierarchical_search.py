from typing import Dict, List, Any, Optional

# engines/iso_hierarchical_search.py
# engines/iso_hierarchical_search.py
from typing import Dict, List, Any
import re

class ISO17025HierarchicalSearch:
    """محرك بحث يفهم التسلسل الهرمي"""
    
    def __init__(self, nlp_controller):
        self.nlp_controller = nlp_controller
        self.hierarchy_weights = {
            3: 1.0,    # Work Instructions - أعلى وزن للأسئلة التقنية
            2: 0.9,    # Procedures
            1: 0.7,    # Quality Manual - أقل للأسئلة التقنية
            4: 0.5    # Forms/Records
            }
    
    async def hierarchical_search(self, query: str, project_id: str) -> Dict:
        """بحث هرمي ذكي"""
        
        # 1. تحليل نوع الاستفسار
        query_analysis = self._analyze_query_intent(query)
        
        # 2. تحديد المستويات ذات الصلة
        relevant_levels = self._determine_relevant_levels(query_analysis)
        
        # 3. البحث في كل مستوى مع الأوزان
        level_results = {}
        for level in relevant_levels:
            results = await self._search_in_level(
                query, project_id, level, query_analysis
            )
            level_results[level] = results
        
        # 4. دمج النتائج هرمياً - تمرير query
        final_answer = self._merge_hierarchical_results(
            level_results, query_analysis, query  # إضافة query هنا
        )
        
        return final_answer
        
    def _analyze_query_intent(self, query: str) -> Dict:
        """تحليل نية الاستفسار"""
        intent_patterns = {
            "policy_inquiry": [
                "سياسة", "policy", "إدارة", "management", "استراتيجية"
            ],
            "procedure_inquiry": [
                "إجراء", "procedure", "خطوات", "steps", "عملية", "process"
            ],
            "instruction_inquiry": [
                "كيف", "how", "تعليمات", "instruction", "طريقة", "method"
            ],
            "compliance_inquiry": [
                "متطلبات", "requirements", "امتثال", "compliance", "معيار"
            ],
            "evidence_inquiry": [
                "نموذج", "form", "سجل", "record", "إثبات", "evidence"
            ]
        }
        
        query_lower = query.lower()
        detected_intents = []
        
        for intent, keywords in intent_patterns.items():
            if any(keyword in query_lower for keyword in keywords):
                detected_intents.append(intent)
        
        return {
            "intents": detected_intents,
            "primary_intent": detected_intents[0] if detected_intents else "general",
            "complexity": "complex" if len(detected_intents) > 1 else "simple"
        }
    
    def _determine_relevant_levels(self, query_analysis: Dict) -> List[int]:
        """تحديد المستويات ذات الصلة بناءً على نوع الاستفسار"""
        intent_to_levels = {
            "policy_inquiry": [1, 2],        # Quality Manual + Procedures
            "procedure_inquiry": [2, 3],     # Procedures + Work Instructions  
            "instruction_inquiry": [3, 4],   # Work Instructions + Forms
            "compliance_inquiry": [1, 2, 3], # جميع المستويات التشغيلية
            "evidence_inquiry": [4, 3],      # Forms + Work Instructions
            "general": [1, 2, 3, 4]          # جميع المستويات
        }
        
        primary_intent = query_analysis["primary_intent"]
        return intent_to_levels.get(primary_intent, [1, 2, 3, 4])
    
    async def _search_in_level(self, query: str, project_id: str, level: int, query_analysis: Dict) -> List[Dict]:
        """البحث في مستوى هرمي محدد"""
        try:
            collection_name = f"local_project_{project_id}"
            collection = self.nlp_controller.chroma_client.get_collection(
                name=collection_name,
                embedding_function=self.nlp_controller.embed_fn
            )
            
            # فلتر حسب المستوى الهرمي
            where_filter = {"hierarchy_level": level}
            
            # البحث مع الفلتر
            results = collection.query(
                query_texts=[query],
                n_results=5,
                where=where_filter
            )
            
            # تنسيق النتائج
            formatted_results = []
            if results["documents"] and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    formatted_results.append({
                        "document": doc,
                        "metadata": results["metadatas"][0][i],
                        "level": level,
                        "weight": self.hierarchy_weights.get(level, 0.5)
                    })
            
            return formatted_results
            
        except Exception as e:
            # إذا لم توجد مستندات في هذا المستوى، إرجاع قائمة فارغة
            return []
    
    def _merge_hierarchical_results(self, level_results: Dict, query_analysis: Dict, query: str = "") -> Dict:
        """دمج النتائج هرمياً - مع إضافة معامل query"""
        
        # جمع جميع النتائج مع أوزانها
        all_results = []
        for level, results in level_results.items():
            for result in results:
                all_results.append({
                    **result,
                    "final_score": result["weight"] * self._calculate_relevance_score(result, query_analysis)
                })
        
        # ترتيب حسب النتيجة النهائية
        all_results.sort(key=lambda x: x["final_score"], reverse=True)
        
        # اختيار أفضل النتائج
        top_results = all_results[:5]
        
        if not top_results:
            return {
                "hierarchical_answer": "لم يتم العثور على معلومات ذات صلة في المستندات الهرمية",
                "sources": [],
                "hierarchy_breakdown": {},
                "status": "no_results"
            }
        
        # بناء السياق الهرمي
        context = self._build_hierarchical_context(top_results)
        
        # توليد إجابة هرمية - إضافة معامل query
        hierarchical_answer = self._generate_hierarchical_answer(context, query_analysis, query)
        
        # إحصائيات هرمية
        hierarchy_breakdown = self._create_hierarchy_breakdown(top_results)
        
        return {
            "hierarchical_answer": hierarchical_answer,
            "sources": list(set([r["metadata"].get("source_file", "Unknown") for r in top_results])),
            "hierarchy_breakdown": hierarchy_breakdown,
            "primary_level": top_results[0]["level"] if top_results else None,
            "status": "hierarchical_success"
        }
    
    def _calculate_relevance_score(self, result: Dict, query_analysis: Dict) -> float:
        """حساب نتيجة الصلة"""
        base_score = 1.0
        
        # زيادة النتيجة حسب نوع الاستفسار
        primary_intent = query_analysis["primary_intent"]
        doc_level = result["level"]
        
        # منطق تحديد الصلة
        if primary_intent == "instruction_inquiry" and doc_level == 3:
            base_score += 0.5  # Work Instructions للاستفسارات التعليمية
        elif primary_intent == "policy_inquiry" and doc_level == 1:
            base_score += 0.5  # Quality Manual للسياسات
        elif primary_intent == "procedure_inquiry" and doc_level == 2:
            base_score += 0.5  # Procedures للعمليات
        
        return base_score
    
    def _build_hierarchical_context(self, results: List[Dict]) -> str:
        """بناء السياق الهرمي"""
        context_parts = []
        
        # تجميع حسب المستوى
        by_level = {}
        for result in results:
            level = result["level"]
            if level not in by_level:
                by_level[level] = []
            by_level[level].append(result["document"])
        
        # بناء السياق مرتب هرمياً
        for level in sorted(by_level.keys()):
            level_name = self._get_level_name(level)
            context_parts.append(f"=== {level_name} ===")
            context_parts.extend(by_level[level])
            context_parts.append("")
        
        return "\n".join(context_parts)
    
    def _generate_hierarchical_answer(self, context: str, query_analysis: Dict, query: str) -> str:
        """توليد إجابة هرمية منظمة وسهلة القراءة"""
        
        primary_intent = query_analysis["primary_intent"]
        
        prompt = f"""
        أجب على الاستفسار بناءً على السياق التالي، واستخدم التنسيق المحدد بالضبط:

        السياق: {context}
        الاستفسار: {query}

        استخدم هذا التنسيق وهذا التنسيق فقط:

        ## الإجابة المباشرة
        [اكتب إجابة مختصرة ومباشرة للسؤال في 2-3 أسطر فقط]

        ## المواصفات التقنية
        • **النوع:** [معلومة محددة]
        • **الأبعاد:** [معلومة محددة]
        • **الإعدادات:** [معلومة محددة]

        ## المستوى الهرمي
        **النوع:** [Work Instruction/Procedure/Quality Manual]
        **المصدر:** [اسم المستند]

        ## السياق في ISO 17025
        [فقرة واحدة مختصرة تشرح الأهمية]

        تعليمات مهمة:
        - استخدم نقاط واضحة
        - اجعل كل قسم مختصر
        - لا تكرر المعلومات
        - استخدم الترقيم والتنسيق بوضوح
        """
        
        try:
            answer = self.nlp_controller.generation_model.generate_content(prompt)
            return self._format_hierarchical_output(answer.text)
        except Exception as e:
            return self._create_fallback_answer(context, query)

    def _format_hierarchical_output(self, raw_answer: str) -> str:
        """تنسيق نهائي للنص لضمان الوضوح"""
        
        # تنظيف أساسي
        formatted = raw_answer.strip()
        
        # إضافة فواصل بين الأقسام
        formatted = re.sub(r'(## [^#\n]+)', r'\n\1\n', formatted)
        
        # تحسين النقاط
        formatted = re.sub(r'•\s*\*\*([^*]+)\*\*:\s*', r'• **\1:** ', formatted)
        
        # إضافة فواصل بين النقاط
        formatted = re.sub(r'(• [^\n]+)', r'\1\n', formatted)
        
        # تنظيف المسافات الزائدة
        formatted = re.sub(r'\n{3,}', '\n\n', formatted)
        
        return formatted.strip()

    def _create_fallback_answer(self, context: str, query: str) -> str:
        """إجابة احتياطية منسقة في حالة فشل التوليد"""
        
        # استخراج معلومات أساسية من السياق
        key_info = self._extract_key_information(context, query)
        
        return f"""## الإجابة المباشرة
    تم العثور على معلومات ذات صلة بالاستفسار في المستندات التقنية.

    ## المعلومات المستخرجة
    {key_info}

    ## المستوى الهرمي
    **النوع:** Work Instruction
    **المصدر:** مستندات ISO 17025

    ## السياق في ISO 17025
    هذه المعلومات جزء من التعليمات التقنية المطلوبة لضمان الامتثال للمعايير."""

    def _extract_key_information(self, context: str, query: str) -> str:
        """استخراج معلومات مفتاحية من السياق"""
        
        # البحث عن كلمات مفتاحية في الاستعلام
        query_words = query.lower().split()
        
        # استخراج جمل ذات صلة
        sentences = context.split('.')
        relevant_sentences = []
        
        for sentence in sentences[:10]:  # أول 10 جمل فقط
            sentence_lower = sentence.lower()
            if any(word in sentence_lower for word in query_words):
                if len(sentence.strip()) > 20:  # تجنب الجمل القصيرة جداً
                    relevant_sentences.append(sentence.strip())
        
        # تنسيق كنقاط
        if relevant_sentences:
            formatted_info = "\n".join([f"• {sent}." for sent in relevant_sentences[:3]])
            return formatted_info
        
        return "• معلومات تقنية ذات صلة متوفرة في المستندات."
    def _create_hierarchy_breakdown(self, results: List[Dict]) -> Dict:
        """إنشاء تفصيل هرمي للنتائج"""
        breakdown = {}
        
        for result in results:
            level = result["level"]
            level_name = self._get_level_name(level)
            
            if level_name not in breakdown:
                breakdown[level_name] = {
                    "count": 0,
                    "sources": [],
                    "weight": self.hierarchy_weights.get(level, 0.5)
                }
            
            breakdown[level_name]["count"] += 1
            source = result["metadata"].get("source_file", "Unknown")
            if source not in breakdown[level_name]["sources"]:
                breakdown[level_name]["sources"].append(source)
        
        return breakdown
    
    def _get_level_name(self, level: int) -> str:
        """الحصول على اسم المستوى"""
        level_names = {
            1: "Quality Manual",
            2: "Procedures", 
            3: "Work Instructions",
            4: "Forms/Records"
        }
        return level_names.get(level, f"Level {level}")