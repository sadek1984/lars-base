"""
LLM providers that fill a QuerySpec. The LLM sees the question, the catalog
vocabulary (names only) and the spec docs — never data rows — and returns
JSON only; it never writes SQL.

Providers sit behind SpecProvider so another model (e.g. ALLaM) can be added
without touching the rest of the layer.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import List

from modules.semantic.catalog import Catalog
from modules.semantic.query_spec import QuerySpec

DEFAULT_PROJECT = "gen-lang-client-0519489172"
DEFAULT_LOCATION = "us-central1"
TIMEOUT_S = 8.0


class SpecProvider(ABC):
    name: str = "provider"

    @abstractmethod
    def fill(self, question: str, system_prompt: str) -> str:
        """Return the raw JSON text of a QuerySpec for `question`."""


class GeminiVertexProvider(SpecProvider):
    """Gemini 2.5 Flash on Vertex AI via Application Default Credentials
    (no API keys). Temperature 0, fixed seed, no thinking, JSON constrained
    to the QuerySpec schema."""

    def __init__(self, model: str = "gemini-2.5-flash", timeout_s: float = TIMEOUT_S):
        from google import genai
        from google.genai import types
        self.name = model
        self._types = types
        self._client = genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", DEFAULT_PROJECT),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION),
            http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
        )

    def fill(self, question: str, system_prompt: str) -> str:
        t = self._types
        config = t.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0,
            seed=0,
            response_mime_type="application/json",
            response_schema=QuerySpec,        # Gemini's native schema: fills nested
                                              # period fields reliably (JSON-schema mode dropped them)
            thinking_config=t.ThinkingConfig(thinking_budget=0),
        )
        return self._client.models.generate_content(model=self.name, contents=question, config=config).text


# ── Prompt ───────────────────────────────────────────────────────────────────

# Deliberately different from the evaluation questions (failure set, its
# paraphrases and the bank's refused questions) so the evaluation is not
# graded on examples the model was shown.
EXAMPLES = [
    ("كم عدد العينات غير المطابقة في الحبوب؟",
     {"metric": "noncompliant_count", "filters": {"category": ["الحبوب"]}}),
    ("وش المبيدات اللي طلعت في الورقيات؟",
     {"metric": "pesticide_list", "filters": {"category": ["الورقيات"]}}),
    ("ما هي أكثر 4 مبيدات ظهوراً في العينات غير المطابقة خلال آخر 3 أسابيع؟",
     {"metric": "top_pesticides", "scope": "non_compliant", "top_n": 4,
      "period": {"type": "relative", "n": 3, "unit": "week"}}),
    ("كم عدد المخالفات في الطماطم في بلدية الرس؟",
     {"metric": "noncompliant_count", "filters": {"product": ["الطماطم"], "municipality": ["بلدية الرس"]}}),
    ("قارن نسبة الرسوب بين الحبوب والورقيات",
     {"metric": "noncompliance_rate", "filters": {"category": ["الحبوب", "الورقيات"]}, "group_by": "category"}),
    ("كيف تغيرت نسبة العينات اللي تجاوزت الحد من شهر لشهر؟",
     {"metric": "above_limit_rate", "group_by": "month"}),
    ("أقل 3 بلديات في عدد العينات",
     {"metric": "sample_count", "group_by": "municipality", "top_n": 3, "sort": "asc"}),
    ("كم عينة تجاوزت الحد الأقصى الأوروبي في الخيار من فبراير إلى أبريل؟",
     {"metric": "above_limit_sample_count", "filters": {"product": ["الخيار"]},
      "period": {"type": "range", "from_month": 2, "to_month": 4}}),
    ("كم عينة فلفل تجاوزت 3 أضعاف الحد المسموح؟",
     {"metric": "above_limit_sample_count", "filters": {"product": ["فلفل"]}, "mrl_multiple": 3}),
    ("كم عينة انفحصت في أبريل؟",
     {"metric": "sample_count", "period": {"type": "absolute_month", "month": 4}}),
    ("عطني تقرير عن آخر أسبوعين",
     {"metric": "noncompliance_rate", "period": {"type": "relative", "n": 2, "unit": "week"}}),
    ("ما المبيدات التي لم تظهر أبداً في الحبوب؟",
     {"metric": "never_detected_list", "filters": {"category": ["الحبوب"]}}),
    ("كم عينة كمون ظهر فيها الكاربندازيم؟",
     {"metric": "sample_count", "filters": {"product": ["كمون"], "pesticide": ["carbendazim"]}}),
    ("نصيب كل بلدية من العينات غير المطابقة",
     {"metric": "noncompliant_count", "group_by": "municipality"}),
    ("ما هو أعلى تركيز للإيميداكلوبريد؟",
     {"metric": "sample_count", "unsupported": True, "reason": "أسئلة التركيز (أعلى/متوسط تركيز) غير مدعومة في هذا المسار"}),
    ("كم سعر كيلو الطماطم؟",
     {"metric": "sample_count", "unsupported": True, "reason": "السؤال خارج بيانات فحوصات المختبر"}),
]


def build_system_prompt(catalog: Catalog) -> str:
    cats = "، ".join(f"{t} → {'|'.join(v)}" for t, v in sorted(catalog.category_terms.items()))
    stored = "، ".join(f"{c} ({n})" for c, n in sorted(catalog.categories.items()))
    examples = "\n".join(f"س: {q}\nJSON: {json.dumps(s, ensure_ascii=False)}" for q, s in EXAMPLES)
    return f"""أنت تحوّل أسئلة عن بيانات مختبر متبقيات المبيدات إلى JSON يطابق مخطط QuerySpec.
لا تجب عن السؤال، ولا تكتب SQL، ولا تخترع قيماً. أعد JSON فقط.

المقاييس (metric):
- sample_count: عدد العينات.
- noncompliant_count / noncompliance_rate: العينات غير المطابقة حسب النتيجة الرسمية للمختبر.
  كلمات: غير مطابقة، مخالفة، مخالفات، راسبة، رسبت، الرسوب، ما طابقت. "نسبة" ← noncompliance_rate.
- above_limit_sample_count / above_limit_rate: عينات تجاوزت الحد الأقصى الأوروبي (EU MRL) — فقط عند ذكر
  "الحد" صراحة (تجاوز الحد، فوق الحد الأقصى، أعلى من الحد المسموح، MRL). "ضعف الحد"/"3 أضعاف" ← mrl_multiple.
  "التركيز فوق الحد / تجاوز فيها التركيز ضعف الحد" سؤال عن تجاوز الحد (مدعوم)، وليس سؤال تركيز.
- top_pesticides: المبيدات الأكثر (أو الأقل) ظهوراً/تكراراً/انتشاراً/رصداً؛ top_n من السؤال (افتراضياً 5).
- pesticide_list: ما هي المبيدات الموجودة/التي ظهرت. السؤال عن المنتجات لا المبيدات ("في أي <تصنيف>"،
  "أي نوع/صنف"، "<التصنيف> اللي فيها مبيدات") ← pesticide_list مع group_by=product.
- never_detected_list: المبيدات التي لم تظهر أبداً في نطاق معيّن.
- سؤال عام عن "الوضع" أو "تقرير" ← noncompliance_rate.
- فترة فقط دون مقياس (مثل "من فبراير إلى أبريل") ← sample_count لتلك الفترة.
scope = non_compliant فقط عندما يُسأل عن المبيدات أو العدد داخل العينات غير المطابقة.

الفلاتر (filters) — انسخ الكلمة كما وردت في السؤال:
- category: كلمات التصنيف: {cats}
  (القيم المخزنة وعدد العينات: {stored})
- product: اسم منتج محدد (طماطم، كمون، فستق ...). لا تضع كلمة تصنيف في product.
- municipality: البلديات: {"، ".join(catalog.municipalities)}
- neighborhood: الأحياء: {"، ".join(catalog.neighborhoods)}
- pesticide: الاسم الإنجليزي الموحّد من هذه القائمة إن عرفته، وإلا كما ورد:
  {", ".join(catalog.analytes.canonical_names)}

الفترة (period) — البيانات من {catalog.min_date} إلى {catalog.max_date}:
- "آخر شهر/آخر شهرين/آخر 3 أشهر/آخر أسبوع" ← relative {{n, unit}}.
- اسم شهر واحد ← absolute_month {{month}} (بدون year إلا إذا ذُكرت السنة).
- "من شهر إلى شهر" ← range {{from_month, to_month}} (أرقام الأشهر، بدون year إلا إذا ذُكرت السنة).
  لا تضع range بدون from_month و to_month.
- بدون فترة ← لا تضع period.

group_by: "شهر بشهر/كل شهر" ← month؛ "كل بلدية/حسب البلدية" ← municipality؛ "أعلى N أحياء" ← neighborhood مع top_n؛
مقارنة تصنيفات أو "مقارنة بالعام/الإجمالي" ← category. sort=asc فقط لـ "الأقل".

قواعد مهمة:
- لا تُسقط أبداً أي تصنيف أو منتج أو بلدية أو مبيد أو فترة مذكورة في السؤال.
- مقارنة تصنيف واحد بالمعدل/النسبة العامة أو الإجمالي ← group_by=category ولا تضع ذلك التصنيف في filters.
- "نسبة/حصة X من إجمالي المخالفات (أو العينات غير المطابقة)" ← noncompliant_count مع group_by على بُعد X
  (الإجابة تعرض حصة كل مجموعة من الإجمالي)، وليس noncompliance_rate.
- الفترة: absolute_month يجب أن يحتوي month؛ range يجب أن يحتوي from_month و to_month.

unsupported=true مع reason عربي قصير إذا كان السؤال: خارج بيانات المختبر، أو عن التركيزات أو المتوسطات أو الانحراف،
أو عن قراءات/نتائج فردية (مثل "أعلى 10 قراءات")، أو عن عدد المبيدات في كل عينة (عينات بمبيد واحد أو مبيدين)،
أو عن مبيدات "لم تسبب مخالفة"،
أو عن منشأة/محل/شركة بعينها، أو عن عينة محددة برقمها، أو يحتاج مقياساً غير موجود أعلاه.

أمثلة:
{examples}"""


def parse_spec(raw: str) -> QuerySpec:
    return QuerySpec.model_validate_json(raw)


def example_specs() -> List[QuerySpec]:
    return [QuerySpec.model_validate(s) for _, s in EXAMPLES]
