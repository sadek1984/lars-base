"""
DEFINITIVE FIX — Based on actual database diagnosis
====================================================
Database stores ENGLISH sample names and ARABIC neighborhood names.
All mappings below are derived from the real DB values.

APPLY THIS FILE:
1. Paste SAMPLE_CORRECTIONS replacement into modules/mappings.py
2. Paste PESTICIDE_CORRECTIONS into modules/mappings.py  
3. Replace _detect_sample_types() in core_query_engine.py
4. Replace _detect_neighborhoods() in core_query_engine.py
5. Replace ALL pesticide IN() filters with the new SQL filter
"""

# ══════════════════════════════════════════════════════════════════════════════
# 1. SAMPLE NAME CORRECTIONS
# Replace SAMPLE_CORRECTIONS in modules/mappings.py with this.
# Keys = what the user might type (Arabic OR English)
# Values = what's actually stored in DB ("اسم العينة" column is ENGLISH)
# ══════════════════════════════════════════════════════════════════════════════

SAMPLE_CORRECTIONS = {
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
    'sesame tahini':  'Sesame Tahini',
}

# ══════════════════════════════════════════════════════════════════════════════
# 2. PESTICIDE NAME SQL FILTER
# Replace the old get_pesticide_variants() IN() pattern everywhere.
# Handles the many typos found in DB: clothiandin/clothianidin/clothindin etc.
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# 3. SAMPLE TYPE CATEGORY MAPPINGS
# Replace نوع العينة category detection — DB now has English values
# ══════════════════════════════════════════════════════════════════════════════

# These are the ACTUAL نوع العينة values in the DB:
# 'Vegetables', 'Spices', 'Fruits', 'Grains', 'Nuts', 'Leafy Greens', 'Dates', 'Ready-to-eat Foods'

SAMPLE_TYPE_CORRECTIONS = {
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
}

# ══════════════════════════════════════════════════════════════════════════════
# 4. NEIGHBORHOOD CORRECTIONS
# Actual DB values confirmed: النهضة، الإسكان، الأخضر، الروضة، النخيل، الريان
# ══════════════════════════════════════════════════════════════════════════════

NEIGHBORHOOD_CORRECTIONS = {
    # Arabic variants
    'الإسكان':    'الإسكان',
    'الاسكان':    'الإسكان',
    'اسكان':      'الإسكان',
    'إسكان':      'الإسكان',
    'النهضة':     'النهضة',
    'النهضه':     'النهضة',
    'نهضة':       'النهضة',
    'الأخضر':     'الأخضر',
    'الاخضر':     'الأخضر',
    'الروضة':     'الروضة',
    'الروضه':     'الروضة',
    'روضة':       'الروضة',
    'النخيل':     'النخيل',
    'نخيل':       'النخيل',
    'الريان':     'الريان',
    'ريان':       'الريان',
    'الفلاح':     'الفلاح',
    'المنتزه':    'المنتزه',
    'الجردة':     'الجردة',
    'الأفق':      'الأفق',
    'الضاحي الغربي': 'الضاحي الغربي',
    'السالمية':   'السالمية',
    'الفايزية':   'الفايزية',
    'الشقة':      'الشقة',
    'الضاحي':     'الضاحي',
    'المنار':     'المنار',
    # English transliterations
    'al-iskan':   'الإسكان',
    'al iskan':   'الإسكان',
    'iskan':      'الإسكان',
    'al-nahda':   'النهضة',
    'al nahda':   'النهضة',
    'nahda':      'النهضة',
    'al-rawda':   'الروضة',
    'rawda':      'الروضة',
    'al-nakhil':  'النخيل',
    'nakhil':     'النخيل',
    'al-rayan':   'الريان',
    'al rayan':   'الريان',
    'rayan':      'الريان',
    'al-akhdar':  'الأخضر',
    'akhdar':     'الأخضر',
    'al-falah':   'الفلاح',
    'falah':      'الفلاح',
    'al-muntazah':'المنتزه',
    'muntazah':   'المنتزه',
}