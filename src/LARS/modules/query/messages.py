"""
User-facing fallback messages shared across the query engine and modules.

phase0/run_question_bank.py matches POLITE_ERROR_MESSAGE's opening phrase
("حدث خطأ أثناء معالجة سؤالك") to count these replies as failures, so keep
that phrase if the wording changes.
"""

POLITE_ERROR_MESSAGE = (
    "⚠️ حدث خطأ أثناء معالجة سؤالك، ولم أتمكن من إعداد إجابة موثوقة. "
    "تم تسجيل المشكلة للمراجعة — جرّب إعادة صياغة السؤال أو اسأل عن جانب آخر."
)

MULTI_MONTH_MESSAGE = "⚠️ الفترات التي تشمل أكثر من شهر غير مدعومة حالياً."

CANNOT_COMPUTE_RATE_MESSAGE = (
    "⚠️ تعذّر حساب النسبة بشكل موثوق لهذا السؤال (نتجت قيمة خارج نطاق 0–100%). "
    "تم تسجيل المشكلة للمراجعة، ولن أعرض رقماً غير صحيح."
)


# The technical metric (a result above limit_value, the EU MRL) is a reference
# comparison only; the lab's official verdict is sample_result. Tables that
# show the technical metric use these display labels instead of
# "violations / المخالفات / Above limit". Display only: the DataFrame's own
# column names do not change.
EU_MRL_RATE_LABEL = "نسبة تجاوز الحد الأقصى الأوروبي (EU MRL)"
EU_MRL_COUNT_LABEL = "تجاوزت الحد الأقصى الأوروبي"

EU_MRL_COLUMN_LABELS = {
    "violations": EU_MRL_COUNT_LABEL,
    "violating_samples": f"عينات {EU_MRL_COUNT_LABEL}",
    "violation_rate_pct": f"{EU_MRL_RATE_LABEL} %",
    "violation_pct": f"{EU_MRL_RATE_LABEL} %",
    "المخالفات": EU_MRL_COUNT_LABEL,
    "فوق_الحد": EU_MRL_COUNT_LABEL,
    "تحت_الحد": "ضمن الحد الأقصى الأوروبي",
    "نسبة_المخالفات": f"{EU_MRL_RATE_LABEL} %",
}


def eu_mrl_markdown(df) -> str:
    """df.to_markdown with the technical-metric columns relabelled for display."""
    return df.rename(columns=EU_MRL_COLUMN_LABELS).to_markdown(index=False)
