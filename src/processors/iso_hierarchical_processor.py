# processors/iso_hierarchical_processor.py
from typing import Dict, List, Any
from pathlib import Path
import re

class ISO17025HierarchicalProcessor:
    """معالج ذكي يفهم التسلسل الهرمي لـ ISO 17025"""
    
    def __init__(self):
        self.hierarchy_map = {
            "1_quality_manual": {
                "level": 1,
                "type": "Quality Manual",
                "prefix": "QM",
                "role": "السياسات العليا والتوجهات الاستراتيجية",
                "children": ["procedures", "work_instructions", "forms"]
            },
            "2_procedures": {
                "level": 2, 
                "type": "Procedure",
                "prefix": "PROC",
                "role": "العمليات الرئيسية والخطوات العامة",
                "parent": "quality_manual",
                "children": ["work_instructions", "forms"]
            },
            "3_work_instructions": {
                "level": 3,
                "type": "Work Instruction", 
                "prefix": "WI",
                "role": "الخطوات التفصيلية لتنفيذ المهام",
                "parent": "procedures"
            },
            "4_forms_and_records": {
                "level": 4,
                "type": "Form/Record",
                "prefix": ["FORM", "REC"],
                "role": "أدلة التنفيذ والسجلات",
                "parent": "procedures"
            }
        }
    
    def _discover_cross_references(self, documents: List[Dict]) -> List[Dict]:
        """نسخة مبسطة لاكتشاف العلاقات"""
        # إرجاع قائمة فارغة للآن - يمكن تطويرها لاحقاً
        return []
    
    def _get_level_by_prefix(self, prefix: str) -> int:
        """تحديد المستوى الهرمي بناءً على البادئة"""
        level_map = {
            "QM": 1,
            "PROC": 2, 
            "WI": 3,
            "FORM": 4,
            "REC": 4
        }
        return level_map.get(prefix, 2)
    
    def _extract_compliance_requirements(self, text: str) -> List[str]:
        """استخراج متطلبات الامتثال - نسخة مبسطة"""
        # البحث عن بنود ISO 17025
        import re
        iso_clauses = re.findall(r'ISO\s+17025\s+(\d+\.\d+(?:\.\d+)?)', text, re.IGNORECASE)
        requirements = re.findall(r'(?:shall|must|يجب)\s+([^.]{10,50})', text, re.IGNORECASE)
        
        return list(set(iso_clauses + requirements))[:10]

    def process_iso_folder_structure(self, base_path: str) -> Dict[str, Any]:
        """معالجة كامل المجلد بفهم هرمي"""
        base_path = Path(base_path)
        
        hierarchy_data = {
            "documents": [],
            "relationships": [],
            "hierarchy_map": {},
            "cross_references": []
        }
        
        for folder_name, folder_info in self.hierarchy_map.items():
            folder_path = base_path / folder_name
            if folder_path.exists():
                level_docs = self._process_hierarchy_level(
                    folder_path, folder_info
                )
                hierarchy_data["documents"].extend(level_docs)
        
        # اكتشاف العلاقات المتبادلة
        hierarchy_data["relationships"] = self._discover_cross_references(
            hierarchy_data["documents"]
        )
        
        return hierarchy_data
    
    def _process_hierarchy_level(self, folder_path: Path, level_info: Dict) -> List[Dict]:
        """معالجة مستوى واحد من التسلسل الهرمي"""
        documents = []
        
        for file_path in folder_path.glob("*"):
            if file_path.suffix in ['.pdf', '.docx', '.xlsx']:
                doc_data = self._extract_document_intelligence(
                    file_path, level_info
                )
                documents.append(doc_data)
        
        return documents
    
    def _extract_document_intelligence(self, file_path: Path, level_info: Dict) -> Dict:
        """استخراج ذكي للمحتوى مع فهم الدور الهرمي"""
        from processors.iso_document_processor import parse_document_metadata
        
        # المعالجة الأساسية
        parsed_data = parse_document_metadata(str(file_path), level_info["type"])
        
        # الذكاء الهرمي
        doc_intelligence = {
            **parsed_data,
            "hierarchy_level": level_info["level"],
            "hierarchy_role": level_info["role"],
            "document_relationships": self._find_document_relationships(
                parsed_data["text"], level_info
            ),
            "control_points": self._extract_control_points(
                parsed_data["text"], level_info["type"]
            ),
            "compliance_requirements": self._extract_compliance_requirements(
                parsed_data["text"]
            )
        }
        
        return doc_intelligence
    
    def _find_document_relationships(self, text: str, level_info: Dict) -> Dict:
        """اكتشاف العلاقات مع الوثائق الأخرى"""
        relationships = {
            "references_to_parent": [],
            "references_to_children": [],
            "cross_references": []
        }
        
        # البحث عن مراجع للمستندات الأخرى
        doc_patterns = {
            "QM": r"QM-\d+",
            "PROC": r"PROC-\d+", 
            "WI": r"WI-\d+-\d+",
            "FORM": r"FORM-\d+",
            "REC": r"REC-\d+"
        }
        
        for doc_type, pattern in doc_patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                target_level = self._get_level_by_prefix(doc_type)
                current_level = level_info["level"]
                
                if target_level < current_level:
                    relationships["references_to_parent"].extend(matches)
                elif target_level > current_level:
                    relationships["references_to_children"].extend(matches)
                else:
                    relationships["cross_references"].extend(matches)
        
        return relationships
    
    def _extract_control_points(self, text: str, doc_type: str) -> List[str]:
        """استخراج نقاط التحكم والمراجعة"""
        control_patterns = {
            "Quality Manual": [
                r"سياسة\s+(\w+)",
                r"policy\s+for\s+(\w+)",
                r"إدارة\s+(\w+)"
            ],
            "Procedure": [
                r"خطوة\s+(\d+)",
                r"step\s+(\d+)",
                r"يجب\s+(\w+)",
                r"must\s+(\w+)"
            ],
            "Work Instruction": [
                r"تعليمة\s+(\w+)",
                r"instruction\s+(\w+)",
                r"احرص\s+على\s+(\w+)"
            ]
        }
        
        control_points = []
        if doc_type in control_patterns:
            for pattern in control_patterns[doc_type]:
                matches = re.findall(pattern, text, re.IGNORECASE)
                control_points.extend(matches)
        
        return control_points[:10]  # أول 10 نقاط