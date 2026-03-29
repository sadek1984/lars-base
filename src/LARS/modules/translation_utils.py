"""
translation_utils.py
====================
Bilingual translation utilities for LARS AI Assistant.
Place this file in: modules/translation_utils.py

Handles Arabic ↔ English translation for:
- Sample/food names (عنب → Grapes)
- Status values (مطابق → Compliant)
- Column headers (عدد_العينات → sample_count)
- DataFrame values and headers
- AI prompt language instructions
- Response text (translate_response_text)
"""

import pandas as pd


# ============================================================
# TRANSLATION DICTIONARIES
# ============================================================

ARABIC_TO_ENGLISH_SAMPLES = {
    # Vegetables
    "طماطم": "Tomatoes",
    "طماطم شيري": "Cherry Tomatoes",
    "خيار": "Cucumber",
    "باذنجان": "Eggplant",
    "فلفل": "Pepper",
    "حار احمر": "Red Pepper",
    "حار اخضر": "Green Pepper",
    "حار": "Hot Pepper",
    "كوسة": "Zucchini",
    "كوسا": "Zucchini",
    "جزر": "Carrot",
    "خس": "Lettuce",
    "بقدونس": "Parsley",
    "سبانخ": "Spinach",
    "بطاطس": "Potato",
    "فاصوليا": "Beans",
    "فاصووليا": "Beans",
    "بامية": "Okra",
    "بروكلي": "Broccoli",
    "بصل": "Onion",
    "جرجير": "Arugula",
    "زهرة": "Cauliflower",
    "شبت": "Dill",
    "كزبرة": "Coriander",
    "ملوخية": "Molokhia",
    "نعناع": "Mint",
    "ملفوف": "Cabbage",
    "كرنب": "Cabbage",
    "رجلة": "Purslane",
    "سلق": "Swiss Chard",
    # Fruits
    "فراولة": "Strawberry",
    "عنب": "Grapes",
    "تفاح": "Apple",
    "برتقال": "Orange",
    "رمان": "Pomegranate",
    "كمثرى": "Pear",
    "ليمون": "Lemon",
    "توت": "Berries",
    "تمر": "Dates",
    "مانجو": "Mango",
    "موز": "Banana",
    "بطيخ": "Watermelon",
    "شمام": "Melon",
    "خوخ": "Peach",
    "مشمش": "Apricot",
    "يوسف افندي": "Mandarin",
    "كيوي": "Kiwi",
    "أناناس": "Pineapple",
    "انجاص": "Pear",
    # Grains
    "قمح": "Wheat",
    "رز": "Rice",
    "ذرة": "Corn",
    "عدس": "Lentils",
    "دقيق": "Flour",
    "طحين": "Flour",
    "شوفان": "Oats",
    # Spices
    "كمون": "Cumin",
    "زعتر": "Thyme",
    "بهارات": "Spices",
    "توابل": "Spices",
    "قرنفل": "Clove",
    "هيل": "Cardamom",
    "يانسون": "Anise",
    "شمر": "Fennel",
    "كركم": "Turmeric",
    "قرفة": "Cinnamon",
    "فلفل اسود": "Black Pepper",
    "محلب": "Mahlab",
    "زعفران": "Saffron",
    "حبة البركة": "Black Seed",
    "حبه البركه": "Black Seed",
    # Nuts
    "لوز": "Almonds",
    "فستق": "Pistachios",
    "كاجو": "Cashews",
    "بندق": "Hazelnuts",
    "بيكان": "Pecans",
    "فول سوداني": "Peanuts",
    "سمسم": "Sesame",
    "جوز": "Walnuts",
    "فلفل بارد": "Sweet Pepper",
    "فلفل حار احمر": "Hot Red Pepper",
    "فلفل حار اخضر": "Hot Green Pepper",
    "فلفل بارد اصفر": "Yellow Sweet Pepper",
    "فلفل بارد اخضر": "Green Sweet Pepper",
    "حار أخضر": "Green Hot Pepper",
    "حار اخضر": "Green Hot Pepper",
    "حار احمر": "Red Hot Pepper",
}

ARABIC_TO_ENGLISH_STATUS = {
    "مطابق": "Compliant",
    "غير مطابق": "Non-Compliant",
    "مقبول": "Acceptable",
    "مرفوض": "Rejected",
    "فوق الحد": "Above Limit",
    "تحت الحد": "Below Limit",
    "مكتشف": "Detected",
    "غير مكتشف": "Not Detected",
    "ناجح": "Pass",
    "راسب": "Fail",
    "مطابقة": "Compliant",
    "غير مطابقة": "Non-Compliant",
}

ARABIC_TO_ENGLISH_TYPES = {
    "خضراوات": "Vegetables",
    "خضروات": "Vegetables",
    "فواكه": "Fruits",
    "فاكهة": "Fruits",
    "توابل": "Spices",
    "مكسرات": "Nuts",
    "حبوب": "Grains",
    "ورقيات": "Leafy Vegetables",
    "بقوليات": "Legumes",
    "خدمية": "Service",
    "تجارية": "Commercial",
}

ARABIC_TO_ENGLISH_COLUMNS = {
    # Sample info columns
    "اسم_العينة": "sample_name",
    "نوع_العينة": "sample_type",
    "نوع العينة": "sample_type",
    "تصنيف_العينة": "sample_classification",
    # Count columns
    "عدد_العينات": "sample_count",
    "عدد العينات": "sample_count",
    "إجمالي_العينات": "total_samples",
    "العدد_الكلي": "total_count",
    # Pesticide columns
    "المبيد": "pesticide",
    "اسم_المبيد": "pesticide_name",
    "عدد_التكرار": "frequency",
    "أنواع_المبيدات": "pesticide_types",
    # Concentration/limit columns
    "التركيز": "concentration",
    "الحد_المسموح": "limit_value",
    "الحد": "limit",
    "اعلى_تركيز": "max_concentration",
    "متوسط_التركيز": "avg_concentration",
    "نسبة_التجاوز": "exceedance_ratio",
    # Limit status columns
    "فوق_الحد": "above_limit",
    "تحت_الحد": "below_limit",
    "عينات_فوق_الحد": "samples_above_limit",
    "عينات_تحت_الحد": "samples_below_limit",
    "خالية_من_المبيدات": "pesticide_free",
    # Result columns
    "نتيجة_العينة": "sample_result",
    "الحالة": "status",
    "حالة_العينة": "sample_status",
    # Violation columns
    "نسبة_المخالفات": "violation_rate",
    "عدد_المخالفات": "violation_count",
    "عدد_التجاوزات": "exceedance_count",
    # Detection columns
    "عدد_الكشف": "detection_count",
    "الحي": "neighborhood",
    "الحى": "neighborhood",
    # Comprehensive analysis columns
    "نوع_العينة": "sample_type",
    "عدد_المبيدات": "pesticide_count",
    "عدد_المبيدات_الراسبة": "failing_pesticide_count",
    "عدد_العينات_المتأثرة": "affected_sample_count",
    "متوسط_التركيز": "avg_concentration",
    # Violations threshold handler
    "نوع العينة": "sample_type",
    "إجمالي السجلات": "total_records",
    "عدد المخالفات": "violation_count",
    "نسبة المخالفات (%)": "violation_rate_%",
    # Count-limit handler columns
    "نوع_العينة": "sample_type",
    "عدد_العينات": "sample_count",
    "عينات_فوق_الحد": "above_limit",
    "عينات_تحت_الحد": "below_limit",
}


# ============================================================
# CORE FUNCTIONS
# ============================================================

def detect_language(query: str) -> str:
    """
    Detect if query is in Arabic or English.
    Returns 'arabic' or 'english'.
    """
    if not query:
        return "english"
    arabic_chars = sum(1 for c in query if '\u0600' <= c <= '\u06FF')
    return "arabic" if arabic_chars > len(query) * 0.2 else "english"

def translate_cell_value(value, lang: str):
    """
    Translate a single cell value from Arabic to English.
    Handles exact matches AND compound Arabic names.
    """
    if lang != "english" or not isinstance(value, str):
        return value

    val = str(value).strip()

    # Step 1: Exact match first (fastest)
    for dictionary in [ARABIC_TO_ENGLISH_SAMPLES, ARABIC_TO_ENGLISH_STATUS, ARABIC_TO_ENGLISH_TYPES]:
        if val in dictionary:
            return dictionary[val]

    # Step 2: Compound word translation
    # Handles names like: فلفل بارد، فلفل حار احمر، فلفل بارد اصفر
    COMPOUND_PARTS = {
        "فلفل": "Pepper",
        "حار": "Hot",
        "بارد": "Sweet",       # فلفل بارد = Sweet Pepper (Bell Pepper)
        "احمر": "Red",
        "اخضر": "Green",
        "اصفر": "Yellow",
        "ابيض": "White",
        "اسود": "Black",
        "اسمر": "Brown",
        "صغير": "Small",
        "كبير": "Large",
        "طازج": "Fresh",
        "مجفف": "Dried",
        "بري": "Wild",
        "بلدي": "Local",
        "هندي": "Indian",
        "صيني": "Chinese",
        "طماطم": "Tomato",
        "خيار": "Cucumber",
        "باذنجان": "Eggplant",
        "بصل": "Onion",
        "ثوم": "Garlic",
        "جزر": "Carrot",
        "بطاطس": "Potato",
        "كوسة": "Zucchini",
        "كوسا": "Zucchini",
        "توابل": "Spices",
        "بهارات": "Spices",
        "أخضر": "Green",
        "أحمر": "Red",
        "أصفر": "Yellow",
    }

    # Split compound Arabic name into parts and translate each
    parts = val.split()
    if len(parts) > 1:
        translated_parts = []
        all_translated = True
        for part in parts:
            if part in COMPOUND_PARTS:
                translated_parts.append(COMPOUND_PARTS[part])
            elif part in ARABIC_TO_ENGLISH_SAMPLES:
                translated_parts.append(ARABIC_TO_ENGLISH_SAMPLES[part])
            else:
                all_translated = False
                translated_parts.append(part)  # Keep untranslated part

        # Return compound translation (even if partial)
        result = " ".join(translated_parts)
        if result != val:  # Only return if something changed
            return result

    # Step 3: Partial/substring match for single untranslated words
    # Catches Arabic words with slight spelling variations
    val_normalized = val.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
    for dictionary in [ARABIC_TO_ENGLISH_SAMPLES, ARABIC_TO_ENGLISH_STATUS]:
        for ar_key, en_val in dictionary.items():
            ar_normalized = ar_key.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
            if val_normalized == ar_normalized:
                return en_val

    return value  # Return original if nothing matched


def translate_dataframe(df: pd.DataFrame, lang: str) -> pd.DataFrame:
    """
    Translate a DataFrame's Arabic values and column names to English.

    - Only applies when lang == 'english'
    - Translates string cell values using translation dictionaries
    - Renames Arabic column headers to English equivalents
    - Returns original df unchanged for Arabic queries

    Usage:
        result_display = translate_dataframe(result, query_lang)
        st.dataframe(result_display, use_container_width=True)
    """
    if lang != "english" or df is None or df.empty:
        return df

    df_out = df.copy()

    # Step 1: Translate string column VALUES
    for col in df_out.columns:
        if df_out[col].dtype == object:
            df_out[col] = df_out[col].apply(
                lambda x: translate_cell_value(x, lang) if pd.notna(x) else x
            )

    # Step 2: Translate COLUMN NAMES (Arabic → English)
    df_out.rename(columns=ARABIC_TO_ENGLISH_COLUMNS, inplace=True)

    return df_out


def get_language_system_prompt(lang: str) -> str:
    """
    Return the language instruction string to inject into AI SQL/Pandas prompts.
    This replaces the static rule #15 in your existing prompt.

    Usage:
        lang_instruction = get_language_system_prompt(query_lang)
        prompt = prompt.replace("{lang_instruction}", lang_instruction)
    """
    if lang == "english":
        return """LANGUAGE CONSTRAINT - CRITICAL AND NON-NEGOTIABLE:
The user's question is in ENGLISH. You MUST ensure ALL output is in English.
- In your SQL query, use CASE statements or aliases to translate Arabic values if possible
- All column aliases (AS ...) must be English words
- **CRITICAL NOTE**: The `chemistry_tidy` table NOW CONTAINS ENGLISH values for `اسم العينة` (Sample Name). E.g., it contains 'Tomato' instead of 'طماطم'. IF querying for sample names, search for the English literal ('Tomato', 'Cucumber', 'Zucchini', etc.) OR use a case-insensitive `LOWER("اسم العينة") LIKE '%tomato%'` approach.
- After you generate the SQL, the system will also auto-translate remaining Arabic values
- Do NOT use Arabic characters anywhere in column aliases or string literals in the SQL EXCEPT if specifically matching an Arabic district name (e.g., district remains Arabic).
- Example: Instead of AS عدد_العينات, write AS sample_count
- Example: Instead of AS المبيد, write AS pesticide_name
- Example: Instead of AS الحالة, write AS status"""
    else:
        return """قاعدة اللغة: المستخدم يتحدث بالعربية. أجب باللغة العربية فقط.
- **ملاحظة هامة جداً**: قاعدة البيانات `chemistry_tidy` تحتوي الآن على أسماء العينات باللغة الإنجليزية في عمود `اسم العينة`. \
عند كتابة كود SQL، يجب أن تترجم اسم العينة إلى الإنجليزي في الـ WHERE clause. مثلاً، إذا سأل المستخدم عن 'طماطم'، اكتب `"اسم العينة" LIKE '%Tomato%'`، 'الخيار' هو 'Cucumber', 'الكوسة' هي 'Zucchini' وهكذا. \
- استخدم الأسماء العربية للبيانات في ردودك النهائية للمستخدم.
- أسماء أعمدة SQL يمكن أن تكون عربية أو إنجليزية"""


def translate_success_message(msg: str, lang: str) -> str:
    """Translate common Streamlit success/info messages."""
    if lang != "english":
        return msg

    translations = {
        "✅ تم العثور على": "✅ Found",
        "⚠️ لم يتم العثور على": "⚠️ No results found for",
        "✅ إجمالي العينات الفريدة:": "✅ Total unique samples:",
        "عينة": "sample(s)",
        "عينة فوق الحد": "sample(s) above limit",
        "عينة تحت الحد": "sample(s) below limit",
    }

    result = msg
    for ar, en in translations.items():
        result = result.replace(ar, en)
    return result


def translate_response_text(text: str, lang: str) -> str:
    """
    Pass-through for response text. Handlers now output English directly.
    """
    return text