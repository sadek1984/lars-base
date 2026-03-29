"""
pattern_extractor.py
====================
استخراج كل أنماط Regex من النظام النصي القديم
"""
import re


class PatternExtractor:
    """استخراج كل الأنماط من handle_natural_language_query"""
    
    @staticmethod
    def extract_all_patterns() -> dict:
        """استخراج كل الأنماط بشكل منظم"""
        return {
            # Pattern 0: Count of samples above/below limit
            'pattern_0': {
                'regex': [
                    r'(?:count|how many|عدد|كم|ماهي|ما هي|what is|give me).*?(?:more than limit|exceeding|above limit|over limit|reading more|exceed|فوق|تجاوز|مخالف|راسب|below limit|under limit|within limit|تحت|ناجح|سليم|مطابق)'
                ],
                'sample_types': ['طماطم', 'خيار', 'كوسة', 'فاصوليا', 'فلفل', 'باذنجان'],
                'keywords': ['count', 'how many', 'عدد', 'كم', 'فوق', 'تحت', 'limit']
            },

            # Pattern 0.5: Neighborhood-based queries
            'pattern_0_5': {
                'regex': [
                    r'ماهي المبيدات في حي.*',
                    r'pesticides in.*neighborhood',
                    r'المبيدات.*حي.*'
                ],
                'neighborhoods': ['الإسكان', 'النهضة', 'الريان', 'الأخضر'],
                'keywords': ['حي', 'neighborhood', 'المبيدات', 'pesticides']
            },

            # Pattern 0.6: Samples containing specific pesticide
            'pattern_0_6': {
                'regex': [
                    r'ما هي عينات.*التي تحتوي علي مبيد.*',
                    r'samples containing.*pesticide',
                    r'عينات.*مبيد.*'
                ],
                'keywords': ['عينات', 'تحتوي', 'مبيد', 'samples', 'containing', 'pesticide']
            },

            # Pattern 1: Find samples with exactly N pesticides
            'pattern_1': {
                'regex': [
                    r'(?:عدد\s*)?(\d+)\s*(?:مبيدات?|مبيد|pesticides?)',
                    r'(?:مبيدات?|مبيد|pesticides?)\s*(?:عدد\s*)?(\d+)',
                    r'عينات.*تحتوي.*على.*\d+.*مبيد'
                ],
                'keywords': ['مبيد', 'pesticide', 'عدد', 'count']
            },


            # Pattern 2: Extract specific pesticide readings
            'pattern_2': {
                'regex': [
                    r'ابحث عن.*مبيد.*في.*',
                    r'find.*pesticide.*in.*',
                    r'مبيد.*في.*'
                ],
                'pesticides': ['بيفنثرين', 'كلوربيريفوس', 'إيميداكلوبريد', 'فيبرونيل'],
                'keywords': ['ابحث', 'find', 'مبيد', 'pesticide']
            },


            # Pattern 3: List all pesticides for a sample type
            'pattern_3': {
                'regex': [
                    r'المبيدات الموجوده.*في.*عينة.*',
                    r'المبيدات في عينة.*',
                    r'تكرار المبيدات.*',
                    r'المبيدات المكتشفة.*',
                    r'ماهي المبيدات.*في.*',
                    r'المبيدات.*التي.*ظهرت.*في.*'
                ],
                'keywords': ['المبيدات', 'عينة', 'sample', 'pesticides', 'ظهرت']
            },

            # Pattern 4: Pesticides in multiple neighborhoods
            'pattern_4': {
                'regex': [
                    r'المبيدات.*في حي.*و.*حي.*',
                    r'pesticides.*neighborhood.*and.*',
                    r'المبيدات.*حي.*كل علي حده'
                ],
                'keywords': ['المبيدات', 'حي', 'neighborhood', 'كل على حده']
            }
        }
