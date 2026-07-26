"""
LARS :: LLM fallback layer for the poisoning register
=====================================================
Bolts onto poisoning_ingest.py. Three jobs, in descending order of how much
the deterministic layer still guards them:

  1. resolve_term()      — unmapped categorical values. LLM output is clamped
                           to the existing enum, cached to a DuckDB alias
                           table, and flagged for human review. Called at most
                           ONCE per novel spelling, ever.
  2. classify_reason()   — free-text سبب عدم الإدانة into reason categories.
                           Genuinely open-ended; LLM is the right tool.
  3. draft_rationale()   — Arabic narrative for the committee, generated FROM
                           the deterministic fields. The LLM writes prose; it
                           never decides anything.

Nothing here can change an attribution flag, an incubation figure, or an
agent class. Those stay in poisoning_ingest.py.

Wire-up:
    from llm_fallback import LLMResolver
    resolver = LLMResolver(con, llm_call=my_gemini_call)   # or None to disable
    df = load_poisoning_frame(path, resolver=resolver)
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

log = logging.getLogger("lars.poisoning.llm")

# ---------------------------------------------------------------------------
# Enums the LLM is allowed to return. Anything else is rejected outright.
# ---------------------------------------------------------------------------

VOCABULARIES = {
    "decision": {
        "CONVICTED": "اللجنة أدانت المنشأة",
        "NOT_CONVICTED": "اللجنة لم تدن المنشأة",
        "UNDER_REVIEW": "القرار لم يصدر بعد / قيد الدراسة",
        "REFERRED": "أحيلت لجهة أخرى دون قرار",
    },
    "kinship": {
        "SINGLE_FAMILY": "كل المصابين من أسرة واحدة",
        "MULTIPLE_FAMILIES": "المصابون من أسر مختلفة غير مترابطة",
        "MIXED": "مجموعة تضم أسرة واحدة وأفراداً منفصلين",
        "UNKNOWN": "صلة القرابة غير مذكورة أو غير واضحة",
    },
}

REASON_CATEGORIES = {
    "INCUBATION_MISMATCH": "فترة الحضانة لا تتوافق مع الوجبة المشتبه بها",
    "SINGLE_HOUSEHOLD": "الإصابات محصورة في أسرة واحدة",
    "NO_LAB_CONFIRMATION": "لا توجد نتائج مخبرية مؤكدة",
    "SAMPLES_CONFORMING": "العينات المسحوبة مطابقة للمواصفات",
    "OTHER_FOOD_SOURCE": "وجود مصدر غذائي آخر محتمل",
    "INSUFFICIENT_EVIDENCE": "أدلة غير كافية بشكل عام",
    "COMPLAINT_WITHDRAWN": "تنازل المبلّغ أو سحب الشكوى",
    "OTHER": "سبب آخر لا ينطبق على التصنيفات أعلاه",
}

ALIAS_DDL = """
CREATE TABLE IF NOT EXISTS term_aliases (
    vocabulary     VARCHAR,
    raw_term       VARCHAR,
    resolved_code  VARCHAR,
    confidence     DOUBLE,
    source         VARCHAR,      -- 'llm' | 'human'
    needs_review   BOOLEAN,
    first_seen     TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (vocabulary, raw_term)
);
"""


class LLMResolver:
    """
    llm_call: Callable[[str], str] -- takes a prompt, returns raw text.
              Plug in your existing Gemini client. Use temperature=0.
              Pass None to run fully deterministic (fallbacks return UNKNOWN).
    """

    def __init__(self, con, llm_call: Optional[Callable[[str], str]] = None,
                 min_confidence: float = 0.75):
        self.con = con
        self.llm_call = llm_call
        self.min_confidence = min_confidence
        con.execute(ALIAS_DDL)

    # -- cache -------------------------------------------------------------

    def _cached(self, vocabulary: str, term: str) -> Optional[str]:
        row = self.con.execute(
            "SELECT resolved_code FROM term_aliases "
            "WHERE vocabulary = ? AND raw_term = ?", [vocabulary, term]
        ).fetchone()
        return row[0] if row else None

    def _cache(self, vocabulary: str, term: str, code: str,
               conf: float, needs_review: bool):
        self.con.execute(
            "INSERT OR REPLACE INTO term_aliases "
            "(vocabulary, raw_term, resolved_code, confidence, source, needs_review) "
            "VALUES (?, ?, ?, ?, 'llm', ?)",
            [vocabulary, term, code, conf, needs_review],
        )

    # -- 1. constrained vocabulary resolution ------------------------------

    def resolve_term(self, vocabulary: str, term: Optional[str]) -> str:
        """Deterministic map already missed. Returns an enum code, never free text."""
        if not term:
            return "UNKNOWN"

        hit = self._cached(vocabulary, term)
        if hit:
            return hit
        if self.llm_call is None:
            return "UNKNOWN"

        options = VOCABULARIES[vocabulary]
        prompt = (
            "أنت مصنّف بيانات في سجل حالات تسمم غذائي بلدي.\n"
            f"صنّف العبارة التالية إلى واحد من الرموز المحددة فقط:\n\nالعبارة: «{term}»\n\n"
            "الرموز المسموح بها:\n"
            + "\n".join(f"- {k}: {v}" for k, v in options.items())
            + "\n\nأعد JSON فقط بدون أي نص آخر وبدون علامات markdown:\n"
              '{"code": "<أحد الرموز أعلاه حرفياً>", "confidence": <0.0-1.0>, '
              '"note": "<سبب مختصر>"}\n'
              "إذا لم تكن العبارة منطبقة بوضوح على أي رمز، استخدم UNKNOWN بثقة منخفضة."
        )

        try:
            raw = self.llm_call(prompt)
            data = json.loads(raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
            code = str(data.get("code", "")).strip().upper()
            conf = float(data.get("confidence", 0.0))
        except Exception as exc:
            log.warning("LLM resolve failed for %r (%s): %s", term, vocabulary, exc)
            return "UNKNOWN"

        # the clamp: anything outside the enum is discarded, not trusted
        if code not in options:
            log.warning("LLM returned off-enum code %r for %r — rejected", code, term)
            return "UNKNOWN"

        needs_review = conf < self.min_confidence
        self._cache(vocabulary, term, code, conf, needs_review)
        log.info("LLM mapped %r -> %s (conf=%.2f, review=%s)",
                 term, code, conf, needs_review)
        return code

    # -- 2. free-text reason classification --------------------------------

    def classify_reason(self, text: Optional[str]) -> tuple[str, Optional[str]]:
        """سبب عدم الإدانة free text -> (category_code, one-line Arabic summary)."""
        if not text or not text.strip():
            return ("MISSING", None)
        if self.llm_call is None:
            return ("UNCLASSIFIED", None)

        prompt = (
            "صنّف سبب عدم الإدانة التالي المذكور في محضر لجنة تسمم غذائي.\n\n"
            f"النص: «{text}»\n\nالتصنيفات:\n"
            + "\n".join(f"- {k}: {v}" for k, v in REASON_CATEGORIES.items())
            + "\n\nأعد JSON فقط:\n"
              '{"category": "<رمز>", "summary": "<تلخيص في جملة واحدة>"}'
        )
        try:
            raw = self.llm_call(prompt)
            data = json.loads(raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
            cat = str(data.get("category", "")).strip().upper()
            if cat not in REASON_CATEGORIES:
                cat = "OTHER"
            return (cat, data.get("summary"))
        except Exception as exc:
            log.warning("LLM reason classification failed: %s", exc)
            return ("UNCLASSIFIED", None)

    # -- 3. narrative drafting (prose only, zero decision authority) --------

    def draft_rationale(self, record: dict) -> Optional[str]:
        """
        Arabic paragraph for the committee form, built strictly from fields the
        deterministic layer already computed. The verdict is an INPUT here.
        """
        if self.llm_call is None:
            return None

        prompt = (
            "اكتب فقرة عربية رسمية واحدة (3-4 أسطر) لمحضر لجنة التسمم الغذائي، "
            "تلخّص المعطيات أدناه وتشرح الأساس الفني للتوصية.\n"
            "التزم بالمعطيات حرفياً. لا تضف أرقاماً أو استنتاجات غير مذكورة. "
            "لا تذكر تشخيصاً ميكروبيولوجياً كحقيقة مؤكدة — استخدم صيغة الاحتمال.\n\n"
            f"- التاريخ: {record.get('incident_date')}\n"
            f"- البلدية: {record.get('municipality')}\n"
            f"- فترة الحضانة: {record.get('incubation_hours')} ساعة\n"
            f"- عدد المصابين: {record.get('cases_count')}\n"
            f"- صلة القرابة: {record.get('kinship_ar')}\n"
            f"- التصنيف الاسترشادي للمسبب: {record.get('agent_class_ar')}\n"
            f"- نتيجة قاعدة الإسناد: {record.get('attribution_reason_ar')}\n"
            f"- قرار اللجنة المسجّل: {record.get('decision_ar')}\n\n"
            "أعد نص الفقرة فقط."
        )
        try:
            return self.llm_call(prompt).strip()
        except Exception as exc:
            log.warning("LLM rationale drafting failed: %s", exc)
            return None

    # -- review queue -------------------------------------------------------

    def pending_review(self):
        return self.con.execute(
            "SELECT vocabulary, raw_term, resolved_code, confidence, first_seen "
            "FROM term_aliases WHERE needs_review ORDER BY first_seen"
        ).df()

    def approve(self, vocabulary: str, raw_term: str, code: Optional[str] = None):
        """Human sign-off. After this the term is deterministic forever."""
        if code:
            self.con.execute(
                "UPDATE term_aliases SET resolved_code = ? "
                "WHERE vocabulary = ? AND raw_term = ?", [code, vocabulary, raw_term])
        self.con.execute(
            "UPDATE term_aliases SET needs_review = FALSE, source = 'human' "
            "WHERE vocabulary = ? AND raw_term = ?", [vocabulary, raw_term])


# ---------------------------------------------------------------------------
# Patch for poisoning_ingest._lookup — deterministic first, LLM only on miss
# ---------------------------------------------------------------------------

def lookup_with_fallback(mapping: dict, key, vocabulary: str,
                         resolver: Optional[LLMResolver], normalize_ar):
    """Drop-in replacement for _lookup() in poisoning_ingest.py."""
    if key is None:
        return ("UNKNOWN", None, None)
    hit = mapping.get(normalize_ar(key))
    if hit:
        return hit
    if resolver is None:
        return ("UNKNOWN", str(key), str(key))
    code = resolver.resolve_term(vocabulary, str(key).strip())
    label = VOCABULARIES.get(vocabulary, {}).get(code, str(key))
    return (code, label, code.replace("_", " ").title())