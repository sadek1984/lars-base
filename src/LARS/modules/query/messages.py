"""
User-facing fallback messages shared across the query engine and modules.

phase0/run_question_bank.py matches POLITE_ERROR_MESSAGE's opening phrase
("حدث خطأ أثناء معالجة سؤالك") to count these replies as failures, so keep
that phrase if the wording changes.
"""

from typing import Optional


class Refusal(str):
    """A refusal text that carries why the engine refused (`kind`).

    Every refusal is built as a Refusal, so process() reads the kind from the
    returned text itself: no code path can emit a refusal without it being
    classified, and a message that is built but not returned classifies
    nothing. Compares and prints exactly like the plain text; `+` (e.g. the
    period label appended at the end) keeps the kind.

    Kinds: out_of_scope, not_understood, category, multi_month,
    unresolved_period, period_not_applied, unresolved_product,
    unresolved_municipality.
    """
    kind: str

    def __new__(cls, kind: str, text: str):
        obj = super().__new__(cls, text)
        obj.kind = kind
        return obj

    def __add__(self, other):
        return Refusal(self.kind, str.__add__(self, other))

    def __reduce__(self):
        return Refusal, (self.kind, str(self))


def refusal_kind(text) -> Optional[str]:
    """The refusal kind of an answer text, or None for a real answer."""
    return text.kind if isinstance(text, Refusal) else None


POLITE_ERROR_MESSAGE = (
    "⚠️ حدث خطأ أثناء معالجة سؤالك، ولم أتمكن من إعداد إجابة موثوقة. "
    "تم تسجيل المشكلة للمراجعة — جرّب إعادة صياغة السؤال أو اسأل عن جانب آخر."
)

CATEGORY_UNSUPPORTED_MESSAGE = Refusal("category", (
    "⚠️ الأسئلة على مستوى التصنيف (مثل المكسرات أو الخضروات) غير مدعومة حالياً. "
    "يمكنك السؤال عن منتج محدد مثل الفستق أو الطماطم."
))

MULTI_MONTH_MESSAGE = Refusal("multi_month", "⚠️ الفترات التي تشمل أكثر من شهر غير مدعومة حالياً.")

UNRESOLVED_PERIOD_MESSAGE = Refusal("unresolved_period", (
    "⚠️ لم أتمكن من فهم الفترة الزمنية المذكورة في السؤال، ولن أجيب على كامل "
    "البيانات بدلاً منها. جرّب صيغة مثل «آخر ٣ أشهر» أو «الشهر الماضي» أو اسم الشهر."
))

# A period was understood, but the handler that would answer cannot filter by
# it (not on CoreQueryEngine._PERIOD_VERIFIED): never answer over all dates.
PERIOD_NOT_APPLIED_MESSAGE = Refusal("period_not_applied", (
    "⚠️ هذا النوع من الأسئلة لا يدعم حالياً التصفية بفترة زمنية، "
    "ولن أجيب على كامل البيانات بدلاً من الفترة المطلوبة."
))

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
