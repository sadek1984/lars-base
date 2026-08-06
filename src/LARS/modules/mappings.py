"""
LARS Centralized Mappings Module.

Single source of truth for all Arabic/English pesticide, sample,
and STT correction dictionaries used across the application.

Why this module exists:
    Before this refactor, identical dictionaries were duplicated in
    voice_lars.py, voice_bot_unified.py, unified_query_processor.py,
    ai_assistant.py, and core_query_engine.py. Any update required
    editing 4-5 files — a major DRY violation and bug magnet.

Usage:
    from modules.mappings import (
        PESTICIDE_AR_TO_EN,
        SAMPLE_CORRECTIONS,
        STT_CORRECTIONS,
        correct_stt_text,
    )
"""

from __future__ import annotations

from difflib import get_close_matches
from typing import Dict, List, Optional
import re
import unicodedata

# ============================================================================
# ARABIC TEXT NORMALIZATION (for dictionary matching only)
# ============================================================================
# Mirrors modules.poisoning.router_gate.norm_q() so pesticide/sample/
# neighborhood matching behaves consistently with the poisoning domain gate.
# This does NOT replace normalize_arabic_query() above (which handles
# numerals) — it runs in addition, specifically to make dictionary lookups
# spelling-variant tolerant.

_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def normalize_arabic_text(s: str) -> str:
    """
    Normalize Arabic text for dictionary key matching.

    Steps: NFKC normalize -> strip diacritics/tatweel -> unify hamza
    carriers (أ/إ/آ -> ا, ؤ -> و, ئ -> ي) -> unify ى -> ي, ة -> ه.

    Use this on BOTH the dictionary keys (once, at load time, via the
    _NORM dicts below) and the incoming query text (at detection time)
    so they compare on equal footing. Comparing a normalized query
    against un-normalized keys (or vice versa) will silently fail.
    """
    if not s:
        return s
    s = unicodedata.normalize("NFKC", s)
    s = _DIACRITICS_RE.sub("", s).replace("\u0640", "")
    s = (
        s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
         .replace("ى", "ي").replace("ة", "ه")
         .replace("ؤ", "و").replace("ئ", "ي")
    )
    return s

# ============================================================================
# PESTICIDE MAPPINGS: Arabic → English
# ============================================================================
# Canonical mapping. Every Arabic spelling variant maps to ONE English name.
# Merged from voice_lars.py, ai_assistant.py, core_query_engine.py,
# and unified_query_processor.py — deduplicated & alphabetised.

PESTICIDE_AR_TO_EN: Dict[str, str] = {
    # Abamectin
    "ابامكتين": "abamectin",
    "الابامكتين": "abamectin",
    # Acetamiprid
    "اسيتامبريد": "acetamiprid",
    "الاسيتامبريد": "acetamiprid",
    "اسيتاميبريد": "acetamiprid",
    "الاسيتاميبريد": "acetamiprid",
    # Azoxystrobin
    "ازوكسيستروبين": "azoxystrobin",
    "الازوكسيستروبين": "azoxystrobin",
    # Bifenthrin
    "بايفنثرن": "bifenthrin",
    "بايفنثرين": "bifenthrin",
    "البايفنثرن": "bifenthrin",
    # Buprofezin
    "بوبروفيزين": "buprofezin",
    "بابروفيزن": "buprofezin",
    "البابروفيزن": "buprofezin",
    "البوبروفيزين": "buprofezin",
    "بروفيزين": "buprofezin",
    # Carbendazim
    "كاربندازيم": "carbendazim",
    "الكاربندازيم": "carbendazim",
    "الكاربندزيم": "carbendazim",
    # Chlorantraniliprole
    "كلورانترانيليبرول": "chlorantraniliprole",
    # Chlorpyrifos
    "كلوربيريفوس": "chlorpyrifos",
    "الكلوربيريفوس": "chlorpyrifos",
    # Cypermethrin
    "سايبرمثرن": "cypermethrin",
    "سايبرمثرين": "cypermethrin",
    "السايبرمثرن": "cypermethrin",
    "السايبرمثرين": "cypermethrin",
    "السيبرمثرين": "cypermethrin",
    # Deltamethrin
    "دلتامثرن": "deltamethrin",
    "دلتامثرين": "deltamethrin",
    "الدلتامثرن": "deltamethrin",
    "الدلتامثرين": "deltamethrin",
    "الدلتاميثرين": "deltamethrin",
    # Dimethoate
    "الديمثويت": "dimethoate",
    # Emamectin
    "الإيماميكتين": "emamectin",
    # Fipronil
    "فبرونيل": "fipronil",
    "فيبرونيل": "fipronil",
    "الفبرونيل": "fipronil",
    "الفيبرونيل": "fipronil",
    # Imidacloprid
    "ايميداكلوبريد": "imidacloprid",
    "اميداكلوبريد": "imidacloprid",
    "الايميداكلوبريد": "imidacloprid",
    "الأيميداكلوبريد": "imidacloprid",
    "إيميداكلوبريد": "imidacloprid",
    "ايميداكلوبرايد": "imidacloprid",
    # Lambda-cyhalothrin
    "اللامبدا": "lambda-cyhalothrin",
    # Malathion
    "ملاثيون": "malathion",
    "الملاثيون": "malathion",
    # Metalaxyl
    "ميتالاكسيل": "metalaxyl",
    "الميتالاكسيل": "metalaxyl",
    # Methomyl
    "الميثوميل": "methomyl",
    # Profenofos
    "بروفينوفوس": "profenofos",
    "البروفينوفوس": "profenofos",
    # Spinosad
    "سبينوساد": "spinosad",
    "السبينوساد": "spinosad",
    # Thiamethoxam
    "ثياميثوكسام": "thiamethoxam",
    "الثياميثوكسام": "thiamethoxam",
    "الثيامثوكسام": "thiamethoxam",
    # Ethion (from core_query_engine)
    "ايثيون": "ethion",
    "الايثيون": "ethion",
    "الايثون": "ethion",
    # Lambda-cyhalothrin (expanded)
    "لامدا سيهالوثرين": "lambda-cyhalothrin",
    "لامدا": "lambda-cyhalothrin",
    "اللامبدا": "lambda-cyhalothrin",
    # Dimethoate (expanded)
    "ديميثويت": "dimethoate",
    "الديميثويت": "dimethoate",
    "الديمثويت": "dimethoate",
    # Methomyl
    "ميثوميل": "methomyl",
    "الميثوميل": "methomyl",
    # Propiconazole
    "بروكونازول": "propiconazole",
    "البروكونازول": "propiconazole",
    # Tebuconazole
    "تيبوكونازول": "tebuconazole",
    "التيبوكونازول": "tebuconazole",
    # Emamectin
    "الإيماميكتين": "emamectin",
    # Boscalid (A013)
    "بوسكاليد": "boscalid",
    "البوسكاليد": "boscalid",
    # Difenoconazole (A016)
    "ديفينوكونازول": "difenoconazole",
    "الديفينوكونازول": "difenoconazole",
    # Carbofuran (A017, A050)
    "كاربوفيوران": "carbofuran",
    "الكاربوفيوران": "carbofuran",
    # Cyhalothrin — standalone form, in addition to the existing
    # "لامدا سيهالوثرين" / "لامدا" entries (A018)
    "سيهالوثرين": "lambda-cyhalothrin",
    "السيهالوثرين": "lambda-cyhalothrin",
    # Emamectin — additional spelling variant missing the extra ي (A019)
    "إيمامكتين": "emamectin",
    "الإيمامكتين": "emamectin",
    "ايمامكتين": "emamectin",
}

# Reverse lookup: English → list of Arabic names (auto-generated)
PESTICIDE_EN_TO_AR: Dict[str, List[str]] = {}
for _ar, _en in PESTICIDE_AR_TO_EN.items():
    PESTICIDE_EN_TO_AR.setdefault(_en, []).append(_ar)


# ============================================================================
# PESTICIDE VARIANTS: Canonical English → List of Database Typos/Variants
# ============================================================================
# Used to ensure queries find all records, even those with typos in the DB.

PESTICIDE_VARIANTS: Dict[str, List[str]] = {
    # Buprofezin (Confirmed typos)
    "buprofezin": ["buprofezin", "buprofuzin", "buprofuzibn"],
    
    # Detected potential typos
    "chlorantraniliprole": ["chlorantraniliprole", "chlorantraniliprle", "chlorantraniliproel"],
    "chlorpyrifos": ["chlorpyrifos", "chlorpyriphos"],
    "clothianidin": ["clothianidin", "clothiandin", "clothindin"],
    "cyantraniliprole": ["cyantraniliprole", "cyanantraniliprole"],
    "cypermethrin": ["cypermethrin", "cyprtmethrin"],
    "deltamethrin": ["deltamethrin", "deltamithrin"],
    "etofenprox": ["etofenprox", "etofenoprox"],
    "fenhexamid": ["fenhexamid", "fenhexamide"],
    "fenpyroximate": ["fenpyroximate", "fenpyroxymate"],
    "fluopyram": ["fluopyram", "fluoptram"],
    "imidacloprid": ["imidacloprid", "imidaclopride", "imidaclprid"],
    "mandipropamid": ["mandipropamid", "mandiprobamid"],
    "metalaxyl": ["metalaxyl", "metalazyl"],
    "methoxyfenozide": ["methoxyfenozide", "methoxyfenozid"],
    "myclobutanil": ["myclobutanil", "myclobutanyl"],
    "piperonyl butoxide": ["piperonyl butoxide", "pipronil butoxid", "pipronil-butoxid"],
    "abamectin": ["abamectin", "abmectin"],
    "acetamiprid": ["acetamiprid", "acetamiprod"],
    "azoxystrobin": ["azoxystrobin", "azoxystrobn"],
}

def get_pesticide_variants(canonical_name: str) -> List[str]:
    """Get all database variants for a pesticide name.
    
    Args:
        canonical_name: The correct English name (e.g. 'buprofezin').
        
    Returns:
        List of strings including the canonical name and any known typos.
        e.g. ['buprofezin', 'buprofuzin', 'buprofuzibn']
    """
    name = canonical_name.lower().strip()
    if name in PESTICIDE_VARIANTS:
        return PESTICIDE_VARIANTS[name]
    return [name] 


def get_pesticide_sql_filter(pesticide: str) -> str:
    """
    Case-insensitive, typo-tolerant SQL filter for pesticide_name.
    
    USAGE in SQL: WHERE ({get_pesticide_sql_filter(pesticide)})
    
    DB has many typos: clothiandin/clothianidin, bifenazate, cyprtmethrin etc.
    This uses LOWER + LIKE prefix to catch all variants.
    """
    p = pesticide.strip()
    if p.startswith('ال') and len(p) > 4:
        p = p[2:]
    p_lower = p.lower()

    conditions = set()
    # Exact match
    conditions.add(f"LOWER(pesticide_name) = '{p_lower}'")
    # Substring match — catches metabolites and compound names
    conditions.add(f"LOWER(pesticide_name) LIKE '%{p_lower}%'")
    # Prefix match (7 chars) — catches suffix typos
    if len(p_lower) >= 6:
        conditions.add(f"LOWER(pesticide_name) LIKE '{p_lower[:7]}%'")

    # Known variant groups based on ACTUAL DB typos discovered
    VARIANT_GROUPS = {
        'imidacloprid':   ['imidacloprid', 'imidaclopride', 'imidaclprid'],
        'clothianidin':   ['clothianidin', 'clothiandin', 'clothindin'],
        'acetamiprid':    ['acetamiprid', 'acetamipeid', 'aceatamiprid', 'acetamprid'],
        'azoxystrobin':   ['azoxystrobin', 'azoxystobin', 'azolxystrobin'],
        'chlorpyrifos':   ['chlorpyrifos', 'chlorpyriphos'],
        'deltamethrin':   ['deltamethrin', 'deltamithrin'],
        'cypermethrin':   ['cypermethrin', 'cyprtmethrin'],
        'abamectin':      ['abamectin', 'abemictin', 'abimactin'],
        'thiamethoxam':   ['thiamethoxam', 'thiamithoxam', 'thioamethoxam'],
        'buprofezin':     ['buprofezin', 'buprofuzin', 'buprofuzibn'],
        'pyriproxyfen':   ['pyriproxyfen'],
        'fipronil':       ['fipronil', 'pipronil butoxid', 'pipronil-butoxid', 'pipronyl butoxide'],
        'bifenthrin':     ['bifenthrin'],
        'chlorantraniliprole': ['chlorantraniliprole', 'chlorantraniliprle', 'chlorantraniliproel',
                               'cyanantraniliprole', 'cyantraniliprole'],
        'difenoconazole': ['difenoconazole'],
        'profenofos':     ['profenofos', 'profenfos'],
        'pirimiphos':     ['pirimiphos', 'pirimiphos methyl', 'pirimiphos-methyl', 'pirmiphos'],
        'fenpyroximate':  ['fenpyroximate', 'fenpyroxymate'],
        'thiophanate':    ['thiophanate', 'thiophonate', 'thiopendazole',
                          'thiophonate methyl', 'thiophonate-methyl',
                          'thiophonat methyl', 'thiaophonat-methyl'],
        'methoxyfenozide':['methoxyfenozide', 'methoxyfenozid', 'mrthoxyfenoxide'],
        'trifloxystrobin':['trifloxystrobin', 'trifloxystobin', 'trifloxistrobin'],
        'metalaxyl':      ['metalaxyl', 'metalazyl'],
        'spirotetramate': ['spirotetramate', 'spirotetramat'],
        'myclobutanil':   ['myclobutanil', 'myclobutanyl'],
        'aflatoxin':      ['afla', 'afla b1', 'afla b2', 'aflaB1', 'aflaB2', 'aflaG1', 'alfaB1',
                          'afla B1', 'afla B2'],
        'mandipropamid':  ['mandipropamid', 'mandiprobamid'],
        'pyrimethanil':   ['pyrimethanil', 'pyrimethanyl', 'pyrmethanil'],
        'pyridaben':      ['pyridaben', 'pyridabin'],
        'dinotefuran':    ['dinotefuran'],
        'cyhalothrin':    ['cyhalothrin'],
        'ethion':         ['ethion'],
        'carbofuran':     ['carbofuran'],
        'carbendazim':    ['carbendazim'],
        'tebuconazole':   ['tebuconazole'],
        'propiconazole':  ['propiconazole'],
        'indoxacarb':     ['indoxacarb'],
        'hexythiazox':    ['hexythiazox'],
        'etoxazole':      ['etoxazole'],
        'spinosad':       ['spinosad A', 'spinosad D', 'spinosad d'],
        'bifenazate':     ['bifenazate'],
        'fenhexamid':     ['fenhexamid', 'fenhexamide'],
        'fluopyram':      ['fluopyram'],
        'fludioxonil':    ['fludioxonil'],
        'flutriafol':     ['flutriafol'],
        'dimethomorph':   ['dimethomorph'],
        'spiromesifen':   ['spiromesfin'],
        'sulfoxaflor':    ['sulfoxaflor'],
        'penconazole':    ['penconazole'],
        'thiabendazole':  ['thiabendazole'],
        'tricyclazole':   ['tricyclazole'],
        'malathion':      ['malathion'],
        'carbaryl':       ['carbaryl'],
        'boscalid':       ['boscalid'],
    }

    for key, variants in VARIANT_GROUPS.items():
        if (key in p_lower or p_lower in key or
                (len(p_lower) >= 5 and len(key) >= 5 and p_lower[:5] == key[:5])):
            for v in variants:
                conditions.add(f"LOWER(pesticide_name) LIKE '%{v.lower()}%'")
            break

    return ' OR '.join(conditions)


# ============================================================================
# KNOWN ARABIC PESTICIDE NAMES (for fuzzy STT matching)
# ============================================================================

KNOWN_PESTICIDES_AR: List[str] = sorted(set(PESTICIDE_AR_TO_EN.keys()))


# ============================================================================
# SAMPLE / COMMODITY CORRECTIONS: variant → canonical Arabic
# ============================================================================
# Merged from voice_lars.py and unified_query_processor.py.

SAMPLE_CORRECTIONS: Dict[str, str] = {
    # ── Arabic queries → English DB values ──────────────────────────────────
    'طماطم':          'Tomato',
    'طماطم شيري':     'Cherry Tomato',
    'خيار':           'Cucumber',
    'كوسة':           'Zucchini',
    'كوسا':           'Zucchini',
    'باذنجان':        'Eggplant',
    'فلفل حار احمر':  'Red Hot Pepper',
    'فلفل حار اخضر':  'Green Hot Pepper',
    'فلفل حار':       'Red Hot Pepper',
    'حار احمر':       'Red Hot Pepper',
    'حار اخضر':       'Green Hot Pepper',
    'حار أحمر':       'Red Hot Pepper',
    'حار أخضر':       'Green Hot Pepper',
    'فلفل بارد احمر': 'Red Sweet Pepper',
    'فلفل بارد اخضر': 'Green Sweet Pepper',
    'فلفل بارد أخضر': 'Green Sweet Pepper',
    'فلفل بارد اصفر': 'Yellow Sweet Pepper',
    'فلفل بارد ملون': 'Colored Sweet Pepper',
    'فلفل بارد':      'Sweet Pepper',
    'فلفل':           'Red Hot Pepper',
    'بارد أخضر':      'Green Sweet Pepper',
    'بارد اخضر':      'Green Sweet Pepper',
    'بارد احمر':      'Red Sweet Pepper',
    'بامية':          'Okra',
    'فاصوليا':        'Beans',
    'بطاطس':          'Potato',
    'جزر':            'Carrot',
    'بصل اخضر':       'Green Onion',
    'بصل':            'Onion',
    'ثوم':            'Garlic',
    'بروكلي':         'Broccoli',
    'زهرة':           'Cauliflower',
    'زهره':           'Cauliflower',
    'سبانخ':          'Spinach',
    'جرجير':          'Rocket/Arugula',
    'بقدونس':         'Parsley',
    'كزبرة':          'Coriander',
    'شبت':            'Dill',
    'نعناع':          'Mint',
    'ملوخية':         'Molokhia (Jute Leaves)',
    'مورينقا':        'Moringa',
    'عنب':            'Grapes',
    'عنب اسود':       'Black Grapes',
    'فراولة':         'Strawberry',
    'فروالة':         'Strawberry',
    'تفاح':           'Apple',
    'تفاح اخضر':      'Green Apple',
    'برتقال':         'Orange',
    'رمان':           'Pomegranate',
    'كمثرى':          'Pear',
    'ليمون':          'Lemon',
    'ليمون اسود':     'Black Lemon (Dried Lime)',
    'توت ازرق':       'Blueberries',
    'توت احمر':       'Red Berries',
    'تمر':            'Dates',
    'تمر سكري':       'Sukkari Dates',
    'تمر جالكسي':     'Galaxy Dates',
    'تمر سكري جلكسي': 'Galaxy Sukkari Dates',
    'تمر سكري مفتل':  'Maftal Sukkari Dates',
    'تمر اخلاص':      'Akhlas Dates',
    'هيل':            'Cardamom',
    'هيل هندي':       'Indian Cardamom',
    'كمون':           'Cumin',
    'كمون بلدي':      'Local Cumin',
    'كمون سوداني':    'Sudanese Cumin',
    'كمون سوري':      'Syrian Cumin',
    'كمون هندي':      'Indian Cumin',
    'زعتر':           'Thyme',
    'يانسون':         'Anise',
    'يانسون نجمة':    'Star Anise',
    'ينسون هندي':     'Indian Anise',
    'شمر':            'Fennel',
    'قرنفل':          'Cloves',
    'فلفل اسود':      'Black Pepper',
    'فلفل مجروش':     'Crushed Pepper',
    'بهارات':         'Spices',
    'بهارات حارة':    'Hot Spices',
    'بهارات  حارة':   'Hot Spices',
    'بهارات مشكلة':   'Mixed Spices',
    'بهارات دجاج':    'Chicken Spices',
    'بهارات الديك':   'Chicken Spices',
    'بهارات انس':     'Anise Spices',
    'بهارات ببريكا':  'Paprika Spices',
    'بهارات فارس':    'Fares Spices',
    'بهارات فيجاي':   'Vijay Spices',
    'بابريكا فلفل حار': 'Paprika Hot Pepper',
    'فلفل حار توابل': 'Hot Pepper Spices',
    'محلب':           'Mahleb',
    'مسحوق كاري':     'Curry Powder',
    'فستق':           'Pistachios',
    'فستق امريكي':    'American Pistachios',
    'لوز':            'Almonds',
    'لوز بالليمون':   'Lemon Almonds',
    'كاجو':           'Cashew',
    'بندق':           'Hazelnut',
    'بيكان':          'Pecan',
    'جوز عين الجمل':  'Walnut',
    'فول سوداني':     'Peanuts',
    'فول سودانى':     'Peanuts',
    'زبدة فول سوداني': 'Peanut Butter',
    'زبدة ةفول سوداني': 'Peanut Butter',
    'مكسرات':         'Mixed Nuts',
    'مكسرات ماليزية': 'Malaysian Nuts',
    'مكسرات مكسيكيه': 'Mexican Nuts',
    'بذور المشمش':    'Apricot Seeds',
    'سمسم':           'Sesame',
    'طحينة':          'Tahini',
    'طحينة سمسم':     'Sesame Tahini',
    'قمح':            'Wheat',
    'قمح ابيض':       'White Wheat',
    'قمح بر':         'Whole Wheat',
    'قمح حب':         'Wheat Grain',
    'قمح معية':       'Maeya Wheat',
    'قمح معية حب':    'Maeya Wheat Grain',
    'قمح معية دقيق':  'Maeya Wheat Flour',
    'دقيق':           'Flour',
    'دقيق ابيض':      'White Flour',
    'دقيق بر':        'Whole Wheat Flour',
    'دقيق قمح':       'Wheat Flour',
    'دقيق معية':      'Maeya Flour',
    'رز':             'Rice',
    'ارز اروما':      'Aroma Rice',
    'ذرة':            'Corn',
    'حبوب ذرة':       'Corn Kernels',
    'عدس':            'Lentils',
    'شوفان':          'Oats',
    'معكرونة':        'Pasta',
    'مكرونة':         'Pasta',
    'مكرونة الجود':   'Al-Joud Pasta',
    'كورن فليكس':     'Corn Flakes',
    'قهوة':           'Coffee',
    'كتشب':           'Ketchup',
    'بودرة تمر':      'Date Powder',
    'فشار تايلندي':   'Thai Popcorn',
    # ── English queries → English DB values (pass-through) ──────────────────
    'tomato':         'Tomato',
    'tomatoes':       'Tomato',
    'cherry tomato':  'Cherry Tomato',
    'cucumber':       'Cucumber',
    'cucumbers':      'Cucumber',
    'zucchini':       'Zucchini',
    'courgette':      'Zucchini',
    'eggplant':       'Eggplant',
    'aubergine':      'Eggplant',
    'okra':           'Okra',
    'beans':          'Beans',
    'potato':         'Potato',
    'potatoes':       'Potato',
    'carrot':         'Carrot',
    'green onion':    'Green Onion',
    'onion':          'Onion',
    'garlic':         'Garlic',
    'broccoli':       'Broccoli',
    'cauliflower':    'Cauliflower',
    'spinach':        'Spinach',
    'arugula':        'Rocket/Arugula',
    'rocket':         'Rocket/Arugula',
    'parsley':        'Parsley',
    'coriander':      'Coriander',
    'cilantro':       'Coriander',
    'dill':           'Dill',
    'mint':           'Mint',
    'molokhia':       'Molokhia (Jute Leaves)',
    'moringa':        'Moringa',
    'grapes':         'Grapes',
    'grape':          'Grapes',
    'black grapes':   'Black Grapes',
    'strawberry':     'Strawberry',
    'strawberries':   'Strawberry',
    'apple':          'Apple',
    'green apple':    'Green Apple',
    'orange':         'Orange',
    'pomegranate':    'Pomegranate',
    'pear':           'Pear',
    'lemon':          'Lemon',
    'dried lime':     'Black Lemon (Dried Lime)',
    'blueberries':    'Blueberries',
    'blueberry':      'Blueberries',
    'red berries':    'Red Berries',
    'dates':          'Dates',
    'date':           'Dates',
    'cardamom':       'Cardamom',
    'indian cardamom':'Indian Cardamom',
    'cumin':          'Cumin',
    'local cumin':    'Local Cumin',
    'sudanese cumin': 'Sudanese Cumin',
    'syrian cumin':   'Syrian Cumin',
    'indian cumin':   'Indian Cumin',
    'thyme':          'Thyme',
    'anise':          'Anise',
    'star anise':     'Star Anise',
    'indian anise':   'Indian Anise',
    'fennel':         'Fennel',
    'cloves':         'Cloves',
    'clove':          'Cloves',
    'black pepper':   'Black Pepper',
    'crushed pepper': 'Crushed Pepper',
    'spices':         'Spices',
    'hot spices':     'Hot Spices',
    'mixed spices':   'Mixed Spices',
    'pistachios':     'Pistachios',
    'pistachio':      'Pistachios',
    'american pistachios': 'American Pistachios',
    'almonds':        'Almonds',
    'almond':         'Almonds',
    'lemon almonds':  'Lemon Almonds',
    'cashew':         'Cashew',
    'cashews':        'Cashew',
    'hazelnut':       'Hazelnut',
    'pecan':          'Pecan',
    'walnut':         'Walnut',
    'walnuts':        'Walnut',
    'peanuts':        'Peanuts',
    'peanut':         'Peanuts',
    'peanut butter':  'Peanut Butter',
    'mixed nuts':     'Mixed Nuts',
    'sesame':         'Sesame',
    'tahini':         'Tahini',
    'sesame tahini':  'Sesame Tahini',
    'wheat':          'Wheat',
    'white wheat':    'White Wheat',
    'whole wheat':    'Whole Wheat',
    'rice':           'Rice',
    'corn':           'Corn',
    'lentils':        'Lentils',
    'oats':           'Oats',
    'pasta':          'Pasta',
    'corn flakes':    'Corn Flakes',
    'coffee':         'Coffee',
    'ketchup':        'Ketchup',
    # Pepper variants
    'red hot pepper':       'Red Hot Pepper',
    'green hot pepper':     'Green Hot Pepper',
    'sweet pepper':         'Sweet Pepper',
    'red sweet pepper':     'Red Sweet Pepper',
    'green sweet pepper':   'Green Sweet Pepper',
    'yellow sweet pepper':  'Yellow Sweet Pepper',
    'colored sweet pepper': 'Colored Sweet Pepper',
    'hot pepper':           'Red Hot Pepper',
    'pepper':               'Sweet Pepper',
    'peppers':              'Sweet Pepper',
}

# Arabic → English sample mapping (auto-generated from SAMPLE_CORRECTIONS Arabic keys)
SAMPLE_AR_TO_EN: Dict[str, str] = {
    k: v for k, v in SAMPLE_CORRECTIONS.items()
    if any('\u0600' <= c <= '\u06ff' for c in k)
}

# ============================================================================
# SAMPLE TYPE / CATEGORY CORRECTIONS: variant → canonical DB value
# ============================================================================
# Maps user-typed category names to the exact "نوع العينة" values in the DB.
# Actual DB values: Vegetables, Fruits, Spices, Nuts, Grains, Leafy Greens,
#                   Dates, Ready-to-eat Foods

SAMPLE_TYPE_CORRECTIONS: Dict[str, str] = {
    # Arabic → English DB value
    'خضراوات':         'Vegetables',
    'خضار':            'Vegetables',
    'خضروات':          'Vegetables',
    'فواكهة':          'Fruits',
    'فواكه':           'Fruits',
    'فاكهة':           'Fruits',
    'توابل':           'Spices',
    'مكسرات':          'Nuts',
    'حبوب':            'Grains',
    'ورقيات':          'Leafy Greens',
    'تمر':             'Dates',
    'تمور':            'Dates',
    'أغذية جاهزة':    'Ready-to-eat Foods',
    # English pass-through
    'vegetables':      'Vegetables',
    'fruits':          'Fruits',
    'spices':          'Spices',
    'nuts':            'Nuts',
    'grains':          'Grains',
    'leafy greens':    'Leafy Greens',
    'dates':           'Dates',
    'ready-to-eat':    'Ready-to-eat Foods',
}

# English → Arabic sample (reverse)
SAMPLE_EN_TO_AR: Dict[str, str] = {
    # Add these English → Arabic name mappings
    'tomato':       'طماطم',
    'tomatoes':     'طماطم',
    'cucumber':     'خيار',
    'cucumbers':    'خيار',
    'zucchini':     'كوسة',
    'pepper':       'فلفل',
    'peppers':      'فلفل',
    'eggplant':     'باذنجان',
    'okra':         'بامية',
    'beans':        'فاصوليا',
    'potato':       'بطاطس',
    'parsley':      'بقدونس',
    'spinach':      'سبانخ',
    'cardamom':     'هيل',
    'cumin':        'كمون',
    'thyme':        'زعتر',
    'grapes':       'عنب',
    'strawberry':   'فراولة',
    'apple':        'تفاح',
    'orange':       'برتقال',
    'pomegranate':  'رمان',
    'dates':        'تمر',
    'pistachio':    'فستق',
    'pistachios':   'فستق',
    'almonds':      'لوز',
    'cashew':       'كاجو',
    'peanut':       'فول سوداني',
    'peanuts':      'فول سوداني',
    'wheat':        'قمح',
    'rice':         'رز',
    'corn':         'ذرة',
    'lentils':      'عدس',
    'sesame':       'سمسم',
    'tahini':       'طحينة',
    'fennel':       'شمر',
    'anise':        'يانسون',
    'cloves':       'قرنفل',
    'molokhia':     'ملوخية',
    'moringa':      'مورينقا',
    'mint':         'نعناع',
    'broccoli':     'بروكلي',
    'cauliflower':  'زهرة',
    'onion':        'بصل',
    'garlic':       'ثوم',
    'carrot':       'جزر',
    'cherry tomato': 'طماطم شيري',
    'walnut':       'جوز عين الجمل',
    'hazelnut':     'بندق',
    # ── Vegetables ──
    "tomato": "طماطم", "tomatoes": "طماطم",
    "cucumber": "خيار", "cucumbers": "خيار",
    "zucchini": "كوسة", "squash": "كوسة",
    "pepper": "فلفل", "peppers": "فلفل",
    "eggplant": "باذنجان", "aubergine": "باذنجان",
    "beans": "فاصوليا", "bean": "فاصوليا",
    "okra": "بامية", "potato": "بطاطس",
    "carrot": "جزر", "onion": "بصل",
    # ── Leafy greens ──
    "lettuce": "خس", "parsley": "بقدونس", "spinach": "سبانخ",
    "arugula": "جرجير", "rocket": "جرجير",
    "coriander": "كزبرة", "cilantro": "كزبرة",
    "dill": "شبت", "molokhia": "ملوخية", "mint": "نعناع",
    "cauliflower": "زهرة", "broccoli": "بروكلي", "cabbage": "ملفوف",
    # ── Fruits ──
    "strawberry": "فراولة", "grape": "عنب", "apple": "تفاح",
    "orange": "برتقال", "pomegranate": "رمان", "pear": "كمثرى",
    "lemon": "ليمون", "lime": "ليمون", "berry": "توت",
    "date": "تمر", "dates": "تمر",
    # ── Grains ──
    "wheat": "قمح", "rice": "رز", "corn": "ذرة",
    "lentil": "عدس", "flour": "دقيق", "oat": "شوفان", "oats": "شوفان",
    # ── Spices ──
    "cardamom": "هيل", "cumin": "كمون", "thyme": "زعتر",
    "spices": "توابل", "spice": "توابل",
    "clove": "قرنفل", "anise": "يانسون", "fennel": "شمر",
    # ── Nuts ──
    "pistachio": "فستق", "pistachios": "فستق",
    "nuts": "مكسرات", "almond": "لوز",
    "cashew": "كاجو", "hazelnut": "بندق",
    "pecan": "بيكان", "peanut": "فول سوداني", "peanuts": "فول سوداني",
    "sesame": "سمسم",
}

# Commodity → Arabic (for risk_windows.py reverse lookup)
COMMODITY_TO_ARABIC: Dict[str, str] = {
    "Tomato": "طماطم", "Cucumber": "خيار", "Pepper": "فلفل",
    "Eggplant": "باذنجان", "Zucchini": "كوسة", "Beans": "فاصوليا",
    "Okra": "بامية", "Lettuce": "خس", "Parsley": "بقدونس",
    "Coriander": "كزبرة", "Mint": "نعناع", "Leafy Greens": "ورقيات",
    "Cabbage": "ملفوف", "Root Vegetables": "جزر",
    "Total Vegetables": "", "Total Fruits": "",
}


# ============================================================================
# STT (Speech-to-Text) CORRECTIONS
# ============================================================================
# Whisper frequently splits Arabic pesticide names. This dict maps
# the most common mis-transcriptions to the correct canonical form.

STT_CORRECTIONS: Dict[str, str] = {
    # Buprofezin variants
    "البير فزن": "البوبروفيزين",
    "بير فيزين": "البوبروفيزين",
    "بوبروفزين": "البوبروفيزين",
    # Imidacloprid
    "اميدا كلوبريد": "الايميداكلوبريد",
    "ايميدا كلوبريد": "الايميداكلوبريد",
    "اميداكلو بريد": "الايميداكلوبريد",
    # Fipronil
    "الفيب رونيل": "الفبرونيل",
    "في برونيل": "الفبرونيل",
    "فايبرونيل": "الفبرونيل",
    # Chlorpyrifos
    "كلور بيريفوس": "الكلوربيريفوس",
    "كلوربيري فوس": "الكلوربيريفوس",
    # Abamectin
    "ابا مكتين": "الابامكتين",
    "ابامك تين": "الابامكتين",
    # Deltamethrin
    "دلتا مثرين": "الدلتامثرن",
    # Cypermethrin
    "سايبر مثرين": "السايبرمثرن",
    # Thiamethoxam
    "ثيا ميثوكسام": "الثياميثوكسام",
    # Carbendazim
    "كاربن دازيم": "الكاربندازيم",
    # Malathion
    "ملا ثيون": "الملاثيون",
    # Profenofos
    "بروفينو فوس": "البروفينوفوس",
    # Azoxystrobin
    "ازوكسي ستروبين": "الازوكسيستروبين",
    # Sample name corrections (STT-specific)
    "الفصولية": "الفاصوليا",
    "فصوليا": "الفاصوليا",
    "فصولية": "الفاصوليا",
    "طماطه": "طماطم",
    "الطماطة": "الطماطم",
}

# Neighbourhood normalization (from core_query_engine.py)
NEIGHBORHOOD_CORRECTIONS: Dict[str, str] = {
    # ── Arabic keys ──
    "الاسكان": "الإسكان", "الإسكان": "الإسكان", "اسكان": "الإسكان", "إسكان": "الإسكان",
    "الصفراء": "الصفراء", "صفراء": "الصفراء",
    "الموطأ": "الموطأ", "موطأ": "الموطأ",
    "الريان": "الريان", "ريان": "الريان",
    "النخيل": "النخيل", "نخيل": "النخيل",
    "الخليج": "الخليج", "خليج": "الخليج",
    "الفيصلية": "الفيصلية", "فيصلية": "الفيصلية",
    "النهضة": "النهضة", "نهضة": "النهضة", "النهضه": "النهضة",
    "السلام": "السلام", "سلام": "السلام",
    "الشفاء": "الشفاء", "شفاء": "الشفاء",
    "المنتزه": "المنتزه", "منتزه": "المنتزه",
    "العليا": "العليا", "عليا": "العليا",
    "الورود": "الورود", "ورود": "الورود",
    "المروج": "المروج", "مروج": "المروج",
    "البساتين": "البساتين", "بساتين": "البساتين",
    "الهلال": "الهلال", "هلال": "الهلال",
    "الأخضر": "الأخضر", "الاخضر": "الأخضر", "اخضر": "الأخضر",
    "الروضة": "الروضة", "روضة": "الروضة", "الروضه": "الروضة",
    "الفلاح": "الفلاح", "فلاح": "الفلاح",
    "المنار": "المنار", "منار": "المنار",
    "الجردة": "الجردة", "جردة": "الجردة",
    # ── English transliterations (longer first so they match before subsets) ──
    "al-iskan":    "الإسكان",
    "al iskan":    "الإسكان",
    "iskan":       "الإسكان",
    "al-nahda":    "النهضة",
    "al nahda":    "النهضة",
    "nahda":       "النهضة",
    "al-rawda":    "الروضة",
    "al rawda":    "الروضة",
    "rawda":       "الروضة",
    "al-nakhil":   "النخيل",
    "al nakhil":   "النخيل",
    "nakhil":      "النخيل",
    "al-rayan":    "الريان",
    "al rayan":    "الريان",
    "rayan":       "الريان",
    "al-akhdar":   "الأخضر",
    "al akhdar":   "الأخضر",
    "akhdar":      "الأخضر",
    "al-falah":    "الفلاح",
    "al falah":    "الفلاح",
    "falah":       "الفلاح",
    "al-muntazah": "المنتزه",
    "al muntazah": "المنتزه",
    "muntazah":    "المنتزه",
    "al-salam":    "السلام",
    "al salam":    "السلام",
    "salam":       "السلام",
    "al-manar":    "المنار",
    "al manar":    "المنار",
    "manar":       "المنار",
    "al-waroud":   "الورود",
    "al waroud":   "الورود",
    "waroud":      "الورود",
    "al-muruj":    "المروج",
    "al muruj":    "المروج",
    "muruj":       "المروج",
    "al-hilal":    "الهلال",
    "al hilal":    "الهلال",
    "hilal":       "الهلال",
    "al-faisaliah":"الفيصلية",
    "al faisaliah":"الفيصلية",
    "al-khalij":   "الخليج",
    "al khalij":   "الخليج",
    "khalij":      "الخليج",
}


# ============================================================================
# ARABIC NUMERAL CONVERSION
# ============================================================================

ARABIC_NUMERALS: Dict[str, str] = {
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
}

ARABIC_NUM_WORDS: Dict[str, str] = {
    "واحد": "1", "اثنين": "2", "ثلاثة": "3", "اربعة": "4",
    "خمسة": "5", "ستة": "6", "سبعة": "7", "ثمانية": "8",
    "تسعة": "9", "عشرة": "10",
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def correct_stt_text(text: str, *, use_fuzzy: bool = True) -> str:
    """Apply STT corrections and optional fuzzy matching.

    Args:
        text: Raw transcribed text from Whisper.
        use_fuzzy: If True, attempt fuzzy matching against known
            pesticide names for words not caught by direct replacement.

    Returns:
        Corrected text string.

    Why fuzzy matching:
        Whisper frequently produces novel mis-transcriptions that are
        close (but not identical) to known pesticide names. A 0.6
        cutoff catches most of these while avoiding false positives.
    """
    corrected = text
    for wrong, right in STT_CORRECTIONS.items():
        corrected = corrected.replace(wrong, right)

    if use_fuzzy:
        words = corrected.split()
        for i, word in enumerate(words):
            if len(word) > 3 and word not in KNOWN_PESTICIDES_AR:
                matches = get_close_matches(
                    word, KNOWN_PESTICIDES_AR, n=1, cutoff=0.6
                )
                if matches:
                    words[i] = matches[0]
        corrected = " ".join(words)

    return corrected


def normalize_arabic_query(query: str) -> str:
    """Normalize Arabic numerals and number words in a query.

    Args:
        query: User query that may contain Arabic numerals (٠-٩)
            or number words (واحد, اثنين, …).

    Returns:
        Query with all numerals converted to Western digits.
    """
    for ar, en in ARABIC_NUMERALS.items():
        query = query.replace(ar, en)
    for word, num in ARABIC_NUM_WORDS.items():
        query = query.replace(word, num)
    return query


def translate_pesticide(name: str) -> Optional[str]:
    """Translate an Arabic pesticide name to English.

    Tries exact match first, then with/without the 'ال' prefix.

    Args:
        name: Arabic pesticide name.

    Returns:
        English name or None if no match found.
    """
    key = name.strip()
    if key in PESTICIDE_AR_TO_EN:
        return PESTICIDE_AR_TO_EN[key]
    # Try adding ال
    with_al = "ال" + key
    if with_al in PESTICIDE_AR_TO_EN:
        return PESTICIDE_AR_TO_EN[with_al]
    # Try removing ال
    if key.startswith("ال") and key[2:] in PESTICIDE_AR_TO_EN:
        return PESTICIDE_AR_TO_EN[key[2:]]
    return None


def normalize_sample_name(name: str) -> str:
    """Normalize an Arabic sample/commodity name to its canonical form.

    Args:
        name: Raw sample name (e.g. 'الفصولية', 'طماطه').

    Returns:
        Canonical Arabic name (e.g. 'فاصوليا', 'طماطم').
    """
    return SAMPLE_CORRECTIONS.get(name.strip(), name.strip())


def normalize_neighborhood(name: str) -> str:
    """Normalize neighbourhood name to canonical form.

    Args:
        name: Raw neighbourhood name.

    Returns:
        Canonical neighbourhood name.
    """
    return NEIGHBORHOOD_CORRECTIONS.get(name.strip(), name.strip())


# ============================================================
# FOOD CATEGORY MEMBERSHIP
# Single source of truth for category → sample name lists.
# Used by advanced_handlers.py and core_query_engine.py.
# ============================================================

# English category key → list of canonical Arabic sample names stored in DB.
# This is the union of the two previously divergent inline dicts in
# advanced_handlers._handle_category_pesticide and _handle_category_limit_summary.
CATEGORY_AR: Dict[str, List[str]] = {
    "vegetable": ["طماطم", "خيار", "كوسة", "فلفل", "باذنجان", "فاصوليا", "بامية", "بطاطس", "جزر", "بصل"],
    "fruit":     ["فراولة", "عنب", "تفاح", "برتقال", "رمان", "كمثرى", "ليمون", "توت", "تمر"],
    "spice":     ["هيل", "كمون", "زعتر", "توابل", "بهارات", "قرنفل", "يانسون", "شمر", "كزبرة", "فلفل اسود"],
    "nut":       ["فستق", "مكسرات", "لوز", "كاجو", "بندق", "بيكان", "سمسم", "فول سوداني"],
    "grain":     ["قمح", "رز", "ذرة", "عدس", "دقيق", "شوفان"],
    "leafy":     ["خس", "بقدونس", "سبانخ", "جرجير", "نعناع", "ملوخية", "شبت", "كزبرة"],
}

# English query keyword → "نوع العينة" DB value used in _detect_sample_types().
# Add plural forms alongside singular so queries like "vegetables" match.
CATEGORY_EN: Dict[str, str] = {
    "vegetable":  "Vegetables",
    "vegetables": "Vegetables",
    "fruit":      "Fruits",
    "fruits":     "Fruits",
    "spice":      "Spices",
    "spices":     "Spices",
    "nut":        "Nuts",
    "nuts":       "Nuts",
    "grain":      "Grains",
    "grains":     "Grains",
    "leafy":      "Leafy Greens",
    "dates":      "Dates",
}

# ============================================================================
# NORMALIZED LOOKUP DICTS (built once at import time)
# ============================================================================
# Keys are normalize_arabic_text()'d versions of the originals. Callers
# doing Arabic dictionary matching should normalize the query text with
# normalize_arabic_text() and check against these, NOT the raw dicts —
# otherwise hamza/ta-marbuta/alif-maqsura spelling variants won't match.
#
# NOTE: if two differently-spelled original keys normalize to the SAME
# string, the later one in dict iteration order wins (standard dict
# overwrite behavior). This is acceptable here since all known variants
# of a given pesticide/sample already map to the same canonical value.

def _build_norm_dict_with_al_variants(source: Dict[str, str]) -> Dict[str, str]:
    """
    Build a normalized lookup dict where EVERY entry exists both with and
    without a leading 'ال' (definite article), regardless of which form
    was originally typed into the source dict.

    Why: many entries in PESTICIDE_AR_TO_EN / SAMPLE_CORRECTIONS /
    NEIGHBORHOOD_CORRECTIONS only have one of the two forms hand-entered
    (e.g. "ايميداكلوبرايد" but not "الايميداكلوبرايد"). Auditing every
    entry manually is error-prone; generating both forms here means a
    future new entry only needs to be added once, in whichever form is
    convenient, and both will resolve.

    Note: if a bare form and its 'ال'-prefixed form normalize to two
    DIFFERENT canonical values in the source dict (shouldn't happen for
    pesticide/sample names, but just in case), the bare form's mapping
    wins for the bare key and the prefixed form's mapping wins for the
    prefixed key — i.e. explicit entries are never overwritten by a
    generated variant of a different entry.
    """
    normalized = {normalize_arabic_text(k): v for k, v in source.items()}
    generated: Dict[str, str] = {}
    for norm_key, val in normalized.items():
        if norm_key.startswith("ال") and len(norm_key) > 2:
            bare = norm_key[2:]
            generated.setdefault(bare, val)
        else:
            prefixed = "ال" + norm_key
            generated.setdefault(prefixed, val)
    # Explicit entries take priority over generated ones
    generated.update(normalized)
    return generated


PESTICIDE_AR_TO_EN_NORM: Dict[str, str] = _build_norm_dict_with_al_variants(PESTICIDE_AR_TO_EN)
SAMPLE_CORRECTIONS_NORM: Dict[str, str] = _build_norm_dict_with_al_variants(SAMPLE_CORRECTIONS)
NEIGHBORHOOD_CORRECTIONS_NORM: Dict[str, str] = _build_norm_dict_with_al_variants(NEIGHBORHOOD_CORRECTIONS)

# ============================================================================
# SPACE-INSENSITIVE PESTICIDE MATCHING
# ============================================================================

PESTICIDE_AR_TO_EN_NORM_NOSPACE: Dict[str, str] = {
    k.replace(" ", ""): v for k, v in PESTICIDE_AR_TO_EN_NORM.items()
}