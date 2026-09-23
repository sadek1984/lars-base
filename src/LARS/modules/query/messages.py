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

CANNOT_COMPUTE_RATE_MESSAGE = (
    "⚠️ تعذّر حساب النسبة بشكل موثوق لهذا السؤال (نتجت قيمة خارج نطاق 0–100%). "
    "تم تسجيل المشكلة للمراجعة، ولن أعرض رقماً غير صحيح."
)
