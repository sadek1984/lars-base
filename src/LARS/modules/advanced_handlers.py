"""
advanced_handlers.py
====================
Advanced analysis handlers for LARS query engine.
These are mixed into CoreQueryEngine via inheritance.

Adds support for:
- Health Risk Index (HRI) calculation
- Quality Index (QI) calculation
- Chemical group analysis
- Category + pesticide queries (e.g. "vegetables with bifenthrin")
- Average concentration above/below limit
- Combined unique non-compliant + repetition count
- Pesticide frequency in a specific sample (targeted version of list)
"""

from __future__ import annotations
import logging
from typing import List, Optional, Tuple
import pandas as pd

from modules.mappings import CATEGORY_AR


class AdvancedHandlersMixin:
    """
    Mixin class — attach to CoreQueryEngine.
    All methods call self._get_connection() which CoreQueryEngine provides.
    """

    # ──────────────────────────────────────────────────────────────────────────
    # Health Risk Index  (HRI = concentration × daily_consumption / ADI / BW)
    # ──────────────────────────────────────────────────────────────────────────
    # TODO(category-5): Add `group_key` parameter to `_handle_health_risk_index`.
    # NOTE: This trigger fix alone does NOT add chemical-group filtering to
    # _handle_health_risk_index — C026 asks specifically for the organochlorine
    # group's HRI in cucumber, and the handler currently computes HRI for ALL
    # detected pesticides regardless of group. This fix makes the query answer
    # SOMETHING (better than a hard fail) but the answer will be broader than asked.
    def _handle_health_risk_index(
        self, samples: List[str]
    ) -> Tuple[str, pd.DataFrame]:
        """
        Calculate Health Risk Index for detected pesticides in given samples.
        HRI = (mean_concentration × daily_consumption_kg) / (ADI × body_weight_kg)
        HRI > 1 → potential health risk
        """
        try:
            from modules.pesticide_groups import get_adi, get_consumption, BODY_WEIGHT_KG
        except ImportError:
            from pesticide_groups import get_adi, get_consumption, BODY_WEIGHT_KG

        con = self._get_connection()

        sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        sample_filter = f"({' OR '.join(sample_conditions)})"

        sql = f"""
        SELECT
            "اسم العينة"       AS sample_name,
            pesticide_name,
            COUNT(*)           AS detections,
            ROUND(AVG(concentration), 5)  AS mean_conc,
            ROUND(MAX(concentration), 5)  AS max_conc,
            ROUND(MAX(limit_value), 5)    AS mrl
        FROM chemistry_tidy
        WHERE is_detected = 1
          AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
          AND {sample_filter}
        GROUP BY "اسم العينة", pesticide_name
        ORDER BY mean_conc DESC
        """
        df = con.execute(sql).df()
        con.close()

        if df.empty:
            return f"⚠️ لم أجد مبيدات مكتشفة في {' + '.join(samples)}", df

        # Calculate HRI per row
        rows = []
        for _, row in df.iterrows():
            consumption_g = get_consumption(str(row["sample_name"]))
            consumption_kg = consumption_g / 1000.0
            adi = get_adi(str(row["pesticide_name"]))
            mean_c = float(row["mean_conc"]) if row["mean_conc"] else 0.0
            max_c  = float(row["max_conc"])  if row["max_conc"]  else 0.0

            if adi and adi > 0:
                hri_mean = round((mean_c * consumption_kg) / (adi * BODY_WEIGHT_KG), 4)
                hri_max  = round((max_c  * consumption_kg) / (adi * BODY_WEIGHT_KG), 4)
                risk_level = "🔴 مرتفع" if hri_max > 1 else ("🟡 متوسط" if hri_max > 0.1 else "🟢 منخفض")
            else:
                hri_mean = "N/A"
                hri_max  = "N/A"
                risk_level = "⚪ غير محدد"

            rows.append({
                "نوع العينة":    row["sample_name"],
                "المبيد":        row["pesticide_name"],
                "متوسط التركيز": row["mean_conc"],
                "أعلى تركيز":    row["max_conc"],
                "ADI":           adi if adi else "N/A",
                "HRI (متوسط)":  hri_mean,
                "HRI (أعلى)":   hri_max,
                "مستوى الخطر":  risk_level,
            })

        result_df = pd.DataFrame(rows)

        sample_display = " + ".join(samples)
        risky = result_df[result_df["مستوى الخطر"] == "🔴 مرتفع"]
        moderate = result_df[result_df["مستوى الخطر"] == "🟡 متوسط"]

        response = f"⚕️ **مؤشر الخطر الصحي (HRI) لعينات {sample_display}:**\n\n"
        response += f"📐 **المعادلة:** HRI = (تركيز × استهلاك يومي) ÷ (ADI × وزن الجسم 60كجم)\n"
        response += f"✅ HRI < 0.1 = منخفض | ⚠️ HRI 0.1–1 = متوسط | 🔴 HRI > 1 = مرتفع\n\n"
        response += f"🔴 مبيدات ذات خطر مرتفع: **{len(risky)}**\n"
        response += f"🟡 مبيدات ذات خطر متوسط: **{len(moderate)}**\n\n"
        response += result_df.to_markdown(index=False)

        if risky.empty is False:
            response += f"\n\n⚠️ **تحذير:** المبيدات التالية تتجاوز HRI > 1 وتستحق مراجعة فورية:\n"
            for _, r in risky.iterrows():
                response += f"• {r['المبيد']} (HRI أعلى = {r['HRI (أعلى)']})\n"

        return response, result_df

    # ──────────────────────────────────────────────────────────────────────────
    # Quality Index  (QI = Σ concentration_i / MRL_i)
    # ──────────────────────────────────────────────────────────────────────────
    def _handle_quality_index(
        self, samples: List[str]
    ) -> Tuple[str, pd.DataFrame]:
        """
        Quality Index per sample code.
        QI = sum(concentration_i / MRL_i) for all detected pesticides.
        Higher QI = worse quality.
        """
        con = self._get_connection()

        sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        sample_filter = f"({' OR '.join(sample_conditions)})"

        sql = f"""
        WITH qi_calc AS (
            SELECT
                "كود العينة"           AS sample_code,
                "اسم العينة"           AS sample_name,
                SUM(
                    CASE
                        WHEN limit_value > 0
                        THEN concentration / limit_value
                        ELSE 0
                    END
                )                        AS quality_index,
                COUNT(*)                 AS pesticide_count,
                SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations
            FROM chemistry_tidy
            WHERE is_detected = 1
              AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
              AND {sample_filter}
            GROUP BY "كود العينة", "اسم العينة"
        )
        SELECT
            sample_code         AS كود_العينة,
            sample_name         AS نوع_العينة,
            ROUND(quality_index, 3) AS مؤشر_الجودة,
            pesticide_count     AS عدد_المبيدات,
            violations          AS مخالفات,
            CASE
                WHEN quality_index < 1 THEN '🟢 جيد'
                WHEN quality_index < 3 THEN '🟡 مقبول'
                ELSE '🔴 ضعيف'
            END                 AS تقييم_الجودة
        FROM qi_calc
        ORDER BY quality_index DESC
        LIMIT 100
        """
        df = con.execute(sql).df()
        con.close()

        sample_display = " + ".join(samples)

        if df.empty:
            return f"⚠️ لم أجد بيانات كافية لحساب مؤشر الجودة لـ {sample_display}", df

        poor = (df["تقييم_الجودة"] == "🔴 ضعيف").sum()
        acceptable = (df["تقييم_الجودة"] == "🟡 مقبول").sum()
        good = (df["تقييم_الجودة"] == "🟢 جيد").sum()
        avg_qi = df["مؤشر_الجودة"].mean().round(3)

        response = f"📊 **مؤشر الجودة (QI) لعينات {sample_display}:**\n\n"
        response += f"📐 **المعادلة:** QI = Σ(تركيز المبيد ÷ حد MRL)\n"
        response += f"✅ QI < 1 = جيد | ⚠️ QI 1–3 = مقبول | 🔴 QI > 3 = ضعيف\n\n"
        response += f"📈 متوسط مؤشر الجودة: **{avg_qi}**\n"
        response += f"🟢 جيد: **{good}** عينة\n"
        response += f"🟡 مقبول: **{acceptable}** عينة\n"
        response += f"🔴 ضعيف: **{poor}** عينة\n\n"
        response += df.head(50).to_markdown(index=False)

        return response, df

    # ──────────────────────────────────────────────────────────────────────────
    # Chemical Group Summary
    # ──────────────────────────────────────────────────────────────────────────
    def _handle_chemical_groups(
        self, samples: List[str], min_pesticides: int = 0
    ) -> Tuple[str, pd.DataFrame]:
        """
        Summarize pesticides by chemical group for given samples.
        Optionally filter to samples that contain >= min_pesticides.
        """
        try:
            from modules.pesticide_groups import classify_pesticide
        except ImportError:
            from pesticide_groups import classify_pesticide

        con = self._get_connection()

        sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples] if samples else ["1=1"]
        sample_filter = f"({' OR '.join(sample_conditions)})"

        # If min_pesticides > 0, filter to sample codes that have enough pesticides
        having_clause = f"HAVING COUNT(*) >= {min_pesticides}" if min_pesticides > 0 else ""

        if min_pesticides > 0:
            sql = f"""
            WITH eligible_samples AS (
                SELECT "كود العينة"
                FROM chemistry_tidy
                WHERE is_detected = 1
                  AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
                  AND {sample_filter}
                GROUP BY "كود العينة"
                {having_clause}
            )
            SELECT
                pesticide_name,
                "اسم العينة" AS sample_name,
                COUNT(*) AS detections,
                SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations
            FROM chemistry_tidy
            WHERE is_detected = 1
              AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
              AND {sample_filter}
              AND "كود العينة" IN (SELECT "كود العينة" FROM eligible_samples)
            GROUP BY pesticide_name, "اسم العينة"
            ORDER BY detections DESC
            """
        else:
            sql = f"""
            SELECT
                pesticide_name,
                "اسم العينة" AS sample_name,
                COUNT(*) AS detections,
                SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations
            FROM chemistry_tidy
            WHERE is_detected = 1
              AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
              AND {sample_filter}
            GROUP BY pesticide_name, "اسم العينة"
            ORDER BY detections DESC
            """

        df = con.execute(sql).df()
        con.close()

        if df.empty:
            return f"⚠️ لم أجد بيانات مبيدات لـ {' + '.join(samples) if samples else 'جميع العينات'}", df

        # Classify each pesticide
        df["chemical_group"] = df["pesticide_name"].apply(classify_pesticide)

        # Group summary
        group_summary = (
            df.groupby("chemical_group")
            .agg(
                unique_pesticides=("pesticide_name", "nunique"),
                total_detections=("detections", "sum"),
                total_violations=("violations", "sum"),
            )
            .reset_index()
            .sort_values("total_detections", ascending=False)
        )
        group_summary.columns = [
            "المجموعة الكيميائية", "عدد المبيدات", "إجمالي الاكتشافات", "إجمالي المخالفات"
        ]

        # Per-pesticide detail
        df_display = df.rename(columns={
            "pesticide_name": "المبيد",
            "sample_name": "نوع العينة",
            "detections": "الاكتشافات",
            "violations": "المخالفات",
            "chemical_group": "المجموعة الكيميائية",
        })

        sample_display = " + ".join(samples) if samples else "جميع العينات"
        filter_desc = f" (عينات تحتوي على ≥ {min_pesticides} مبيدات)" if min_pesticides > 0 else ""

        response = f"🧬 **تصنيف المبيدات الكيميائي لـ {sample_display}{filter_desc}:**\n\n"
        response += f"### 📊 ملخص المجموعات الكيميائية\n\n"
        response += group_summary.to_markdown(index=False)
        response += f"\n\n### 🔬 تفاصيل المبيدات\n\n"
        response += df_display.head(40).to_markdown(index=False)

        return response, df_display

    # ──────────────────────────────────────────────────────────────────────────
    # Category + Pesticide (e.g. "vegetables associated with bifenthrin")
    # ──────────────────────────────────────────────────────────────────────────
    def _handle_category_pesticide(
        self, pesticide: str, category_key: Optional[str], samples: List[str]
    ) -> Tuple[str, pd.DataFrame]:
        """
        Find all sample types in a category that contain a specific pesticide.
        """
        try:
            from modules.mappings import get_pesticide_variants
        except ImportError:
            get_pesticide_variants = lambda p: [p]

        con = self._get_connection()

        # Build sample filter from category or explicit samples
        # CATEGORY_AR imported from modules.mappings — single source of truth

        if samples:
            conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        elif category_key and category_key in CATEGORY_AR:
            conditions = [f"\"اسم العينة\" LIKE '%{ar}%'" for ar in CATEGORY_AR[category_key]]
        else:
            conditions = ["1=1"]

        sample_filter = f"({' OR '.join(conditions)})"

        pesticide_variants = get_pesticide_variants(pesticide)
        pest_filter = ", ".join([f"'{v}'" for v in pesticide_variants])

        sql = f"""
        SELECT
            "اسم العينة"     AS نوع_العينة,
            pesticide_name   AS المبيد,
            COUNT(*)         AS التكرار,
            ROUND(AVG(concentration), 5) AS متوسط_التركيز,
            ROUND(MAX(concentration), 5) AS أعلى_تركيز,
            ROUND(MAX(limit_value), 5)   AS MRL,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS المخالفات
        FROM chemistry_tidy
        WHERE is_detected = 1
          AND pesticide_name IN ({pest_filter})
          AND {sample_filter}
        GROUP BY "اسم العينة", pesticide_name
        ORDER BY التكرار DESC
        """

        df = con.execute(sql).df()
        con.close()

        category_label = {
            "vegetable": "الخضار", "fruit": "الفواكه", "spice": "التوابل",
            "nut": "المكسرات", "grain": "الحبوب", "leafy": "الورقيات"
        }.get(category_key or "", " + ".join(samples) if samples else "جميع العينات")

        if df.empty:
            return f"⚠️ لم أجد {pesticide} في {category_label}", df

        total = int(df["التكرار"].sum())
        violations = int(df["المخالفات"].sum())
        types_count = df["نوع_العينة"].nunique()

        response = f"🔍 **توزيع مبيد {pesticide} في {category_label}:**\n\n"
        response += f"✅ وُجد في **{types_count}** نوع عينة | إجمالي الاكتشافات: **{total}** | المخالفات: **{violations}**\n\n"
        response += df.to_markdown(index=False)

        return response, df

    # ──────────────────────────────────────────────────────────────────────────
    # Municipality pesticides (A053)
    # ──────────────────────────────────────────────────────────────────────────
    def _handle_municipality_pesticides(self, municipality: str) -> Tuple[str, pd.DataFrame]:
        """Pesticides detected within a given municipality. Covers A053."""
        con = self._get_connection()
        sql = f"""
        SELECT
            pesticide_name AS pesticide,
            COUNT(*) AS detections,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations
        FROM chemistry_tidy
        WHERE is_detected = 1
          AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
          AND "اسم البلدية" LIKE '%{municipality}%'
        GROUP BY pesticide_name
        ORDER BY detections DESC
        LIMIT 50
        """
        df = con.execute(sql).df()
        con.close()
        if df.empty:
            return f"⚠️ لم أجد بيانات لبلدية {municipality}", df
        response = f"🏛️ **المبيدات في بلدية {municipality}:**\n\n"
        response += df.to_markdown(index=False)
        return response, df

    def _handle_municipality_comparison(self, mun_a: str, mun_b: str) -> Tuple[str, pd.DataFrame]:
        """Compare violation rate between two municipalities. Covers A054, D012."""
        con = self._get_connection()
        sql = f"""
        SELECT
            "اسم البلدية" AS municipality,
            COUNT(DISTINCT "كود العينة") AS total_samples,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations,
            ROUND(100.0 * SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) /
                  NULLIF(COUNT(DISTINCT "كود العينة"), 0), 1) AS violation_rate_pct
        FROM chemistry_tidy
        WHERE "اسم البلدية" IN ('{mun_a}', '{mun_b}')
        GROUP BY "اسم البلدية"
        """
        df = con.execute(sql).df()
        con.close()
        if df.empty:
            return f"⚠️ لم أجد بيانات للمقارنة بين {mun_a} و{mun_b}", df
        response = f"📊 **مقارنة {mun_a} و{mun_b}:**\n\n"
        response += df.to_markdown(index=False)
        return response, df

    def _handle_municipality_breakdown(self, municipality: str) -> Tuple[str, pd.DataFrame]:
        """Sample counts per product type within a municipality. Covers A055."""
        con = self._get_connection()
        sql = f"""
        SELECT
            "اسم العينة" AS sample_type,
            COUNT(DISTINCT "كود العينة") AS sample_count
        FROM chemistry_tidy
        WHERE "اسم البلدية" LIKE '%{municipality}%'
        GROUP BY "اسم العينة"
        ORDER BY sample_count DESC
        """
        df = con.execute(sql).df()
        con.close()
        if df.empty:
            return f"⚠️ لم أجد بيانات لبلدية {municipality}", df
        response = f"📊 **توزيع العينات حسب النوع — بلدية {municipality}:**\n\n"
        response += df.to_markdown(index=False)
        return response, df

    def _handle_missing_field_pct(self, field: str) -> Tuple[str, pd.DataFrame]:
        """% of records missing a given field (الحى or اسم البلدية). Covers D035-D037."""
        col_map = {"neighborhood": '"الحى"', "municipality": '"اسم البلدية"'}
        col = col_map.get(field)
        if not col:
            return "⚠️ حقل غير معروف", pd.DataFrame()
        con = self._get_connection()
        sql = f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN {col} IS NULL OR {col} = '' THEN 1 ELSE 0 END) AS missing,
            ROUND(100.0 * SUM(CASE WHEN {col} IS NULL OR {col} = '' THEN 1 ELSE 0 END) / COUNT(*), 1) AS missing_pct
        FROM chemistry_tidy
        """
        df = con.execute(sql).df()
        con.close()
        row = df.iloc[0]
        label = "الحى" if field == "neighborhood" else "البلدية"
        response = (
            f"📊 **نسبة السجلات الناقصة في حقل {label}:**\n\n"
            f"إجمالي السجلات: **{int(row['total'])}**\n"
            f"سجلات ناقصة: **{int(row['missing'])}** ({row['missing_pct']}%)"
        )
        return response, df


    def _handle_exceedance_multiplier(
        self, samples: List[str], multiplier: float,
        category_key: Optional[str] = None,
    ) -> Tuple[str, pd.DataFrame]:
        """Samples where concentration exceeded `multiplier`x the MRL. B018, B019."""
        from modules.mappings import CATEGORY_AR
        if samples:
            conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        elif category_key and category_key in CATEGORY_AR:
            conditions = [f"\"اسم العينة\" LIKE '%{ar}%'" for ar in CATEGORY_AR[category_key]]
        else:
            conditions = ["1=1"]
        sample_filter = f"({' OR '.join(conditions)})"
        con = self._get_connection()
        sql = f"""
        SELECT "كود العينة" AS sample_code, "اسم العينة" AS sample_name,
               pesticide_name AS pesticide, concentration, limit_value AS mrl,
               ROUND(exceedance_ratio, 2) AS ratio
        FROM chemistry_tidy
        WHERE is_detected = 1 AND limit_value > 0 AND exceedance_ratio >= {multiplier}
          AND {sample_filter}
        ORDER BY exceedance_ratio DESC LIMIT 100
        """
        df = con.execute(sql).df()
        con.close()
        label = " + ".join(samples) if samples else (category_key or "جميع العينات")
        if df.empty:
            return f"⚠️ لم أجد عينات تجاوزت {multiplier}× الحد المسموح في {label}", df
        response = f"📊 **عينات تجاوزت {multiplier}× الحد المسموح — {label}:**\n\n✅ العدد: **{len(df)}**\n\n"
        response += df.to_markdown(index=False)
        return response, df

    def _handle_limit_proximity_band(
        self, samples: List[str], low_pct: float, high_pct: float,
    ) -> Tuple[str, pd.DataFrame]:
        """Samples between low_pct% and high_pct% of MRL. B020, B021."""
        sample_filter = ""
        if samples:
            conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
            sample_filter = f"AND ({' OR '.join(conditions)})"
        con = self._get_connection()
        sql = f"""
        SELECT "كود العينة" AS sample_code, "اسم العينة" AS sample_name,
               pesticide_name AS pesticide, concentration, limit_value AS mrl,
               ROUND(exceedance_ratio * 100, 1) AS pct_of_mrl
        FROM chemistry_tidy
        WHERE is_detected = 1 AND limit_value > 0
          AND exceedance_ratio * 100 >= {low_pct} AND exceedance_ratio * 100 < {high_pct}
          {sample_filter}
        ORDER BY pct_of_mrl DESC LIMIT 100
        """
        df = con.execute(sql).df()
        con.close()
        label = " + ".join(samples) if samples else "جميع العينات"
        if df.empty:
            return f"⚠️ لم أجد عينات بين {low_pct}% و{high_pct}% من الحد في {label}", df
        response = f"📊 **عينات بين {low_pct}% و{high_pct}% من الحد المسموح — {label}:**\n\n"
        response += df.to_markdown(index=False)
        return response, df

    def _handle_global_violation_rate(self, group_by: str) -> Tuple[str, pd.DataFrame]:
        """Global violation % by pesticide or product, no filter. B028, B029."""
        col = "pesticide_name" if group_by == "pesticide" else '"اسم العينة"'
        label_col = "pesticide" if group_by == "pesticide" else "sample_type"
        con = self._get_connection()
        sql = f"""
        SELECT {col} AS {label_col}, COUNT(*) AS total_detections,
               SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations,
               ROUND(100.0 * SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS violation_pct
        FROM chemistry_tidy
        WHERE is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        GROUP BY {col} HAVING COUNT(*) >= 5 ORDER BY violation_pct DESC LIMIT 50
        """
        df = con.execute(sql).df()
        con.close()
        if df.empty:
            return "⚠️ لم أجد بيانات كافية", df
        title = "لكل مبيد" if group_by == "pesticide" else "لكل منتج"
        response = f"📊 **نسبة المخالفة {title} (عام):**\n\n*(العناصر ذات أقل من 5 اكتشافات مستبعدة)*\n\n"
        response += df.to_markdown(index=False)
        return response, df

    def _handle_zero_violations(self, entity_type: str) -> Tuple[str, pd.DataFrame]:
        """Entities with detections but ZERO violations. B031, D032, D033."""
        col_map = {"pesticide": ("pesticide_name", "pesticide"),
                   "product": ('"اسم العينة"', "sample_type"),
                   "neighborhood": ('"الحى"', "neighborhood")}
        col, label = col_map[entity_type]
        con = self._get_connection()
        sql = f"""
        SELECT {col} AS {label}, COUNT(*) AS total_detections
        FROM chemistry_tidy
        WHERE is_detected = 1 AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
        GROUP BY {col} HAVING SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) = 0
        ORDER BY total_detections DESC LIMIT 100
        """
        df = con.execute(sql).df()
        con.close()
        titles = {"pesticide": "المبيدات", "product": "المنتجات", "neighborhood": "الأحياء"}
        if df.empty:
            return f"⚠️ لم أجد {titles[entity_type]} بدون أي مخالفة", df
        response = f"🟢 **{titles[entity_type]} بدون أي مخالفة مسجّلة:**\n\n✅ العدد: **{len(df)}**\n\n"
        response += df.to_markdown(index=False)
        return response, df

    def _handle_top_n_by_metric(self, entity: str, metric: str, n: int = 5) -> Tuple[str, pd.DataFrame]:
        """Top N products/facilities by violation count or rate. D007, D008, D014."""
        col_map = {"product": '"اسم العينة"', "facility": '"اسم المنشاة"'}
        col = col_map.get(entity)
        if not col:
            return "⚠️ نوع غير معروف", pd.DataFrame()
        order_col = "violations" if metric == "count" else "violation_rate_pct"
        con = self._get_connection()
        sql = f"""
        SELECT {col} AS entity_name, COUNT(DISTINCT "كود العينة") AS total_samples,
               SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations,
               ROUND(100.0 * SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) /
                     NULLIF(COUNT(DISTINCT "كود العينة"), 0), 1) AS violation_rate_pct
        FROM chemistry_tidy
        WHERE {col} IS NOT NULL
        GROUP BY {col} HAVING COUNT(DISTINCT "كود العينة") >= 5
        ORDER BY {order_col} DESC LIMIT {n}
        """
        df = con.execute(sql).df()
        con.close()
        if df.empty:
            return "⚠️ لم أجد بيانات كافية", df
        response = f"📊 **أعلى {n} {'حسب نسبة المخالفة' if metric == 'rate' else 'حسب عدد المخالفات'}:**\n\n"
        response += df.to_markdown(index=False)
        return response, df

    def _handle_category_comparison(
        self, cat_a: str, cat_b: str, metric: str = "count"
    ) -> Tuple[str, pd.DataFrame]:
        """
        Compare two categories (e.g. spices vs vegetables) on a chosen
        metric: 'count' (sample counts), 'violations' (violation counts),
        or 'avg_pesticides' (avg pesticide count per sample).
        Covers A045, B023, C014.
        """
        from modules.mappings import CATEGORY_AR
        cats = {"a": cat_a, "b": cat_b}
        rows = []
        con = self._get_connection()
        for label, cat_key in cats.items():
            ar_names = CATEGORY_AR.get(cat_key, [])
            if not ar_names:
                continue
            conditions = [f"\"اسم العينة\" LIKE '%{ar}%'" for ar in ar_names]
            sample_filter = f"({' OR '.join(conditions)})"

            if metric == "violations":
                sql = f"""
                SELECT COUNT(DISTINCT "كود العينة") AS total,
                       SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS violations
                FROM chemistry_tidy WHERE {sample_filter}
                """
            elif metric == "avg_pesticides":
                sql = f"""
                WITH counts AS (
                    SELECT "كود العينة", COUNT(CASE WHEN is_detected=1 THEN 1 END) AS n
                    FROM chemistry_tidy WHERE {sample_filter}
                    GROUP BY "كود العينة"
                )
                SELECT COUNT(*) AS total, ROUND(AVG(n), 2) AS avg_pesticides FROM counts
                """
            else:  # count
                sql = f"""
                SELECT COUNT(DISTINCT "كود العينة") AS total FROM chemistry_tidy
                WHERE {sample_filter}
                """
            row = con.execute(sql).fetchone()
            rows.append({"category": cat_key, "data": row})
        con.close()

        if len(rows) < 2:
            return "⚠️ تعذّرت المقارنة — تأكد من صحة اسم الفئتين", pd.DataFrame()

        df = pd.DataFrame(rows)
        response = f"📊 **مقارنة {cat_a} مقابل {cat_b} ({metric}):**\n\n"
        for r in rows:
            response += f"• {r['category']}: {r['data']}\n"
        return response, df
    def _handle_missing_mrl_stats(self, want: str) -> Tuple[str, pd.DataFrame]:
        """
        Non-compliant samples / residues with no recorded MRL limit_value.
        want: 'noncompliant_no_mrl' (B032) | 'unevaluable_count' (B033) |
        'unevaluable_pct' (D035).
        """
        con = self._get_connection()
        if want == "noncompliant_no_mrl":
            sql = """
            SELECT "كود العينة" AS sample_code, "اسم العينة" AS sample_name,
                   pesticide_name AS pesticide, concentration
            FROM chemistry_tidy
            WHERE sample_result = 'Non-Compliant'
              AND (limit_value IS NULL OR limit_value = 0)
            LIMIT 100
            """
            df = con.execute(sql).df()
            con.close()
            if df.empty:
                return "⚠️ لم أجد عينات غير مطابقة بدون حد مسجل", df
            response = f"📊 **عينات غير مطابقة بدون حد MRL مسجل:**\n\n✅ العدد: **{len(df)}**\n\n"
            response += df.to_markdown(index=False)
            return response, df

        sql = """
        SELECT
            COUNT(*) AS total_residues,
            SUM(CASE WHEN limit_value IS NULL OR limit_value = 0 THEN 1 ELSE 0 END) AS unevaluable,
            ROUND(100.0 * SUM(CASE WHEN limit_value IS NULL OR limit_value = 0 THEN 1 ELSE 0 END)
                  / COUNT(*), 1) AS unevaluable_pct
        FROM chemistry_tidy
        WHERE is_detected = 1
        """
        df = con.execute(sql).df()
        con.close()
        row = df.iloc[0]
        if want == "unevaluable_count":
            response = f"📊 **المتبقيات التي تعذّر تقييمها لعدم وجود حد:**\n\nالعدد: **{int(row['unevaluable'])}**"
        else:
            response = (
                f"📊 **نسبة العينات التي تعذّر تقييمها:**\n\n"
                f"إجمالي: **{int(row['total_residues'])}** | "
                f"غير قابلة للتقييم: **{int(row['unevaluable'])}** ({row['unevaluable_pct']}%)"
            )
        return response, df
    # ──────────────────────────────────────────────────────────────────────────
    # Average concentration above / below limit
    # ──────────────────────────────────────────────────────────────────────────
    def _handle_avg_concentration_limit(
        self, pesticide: str, samples: List[str], is_above: bool
    ) -> Tuple[str, pd.DataFrame]:
        """Average concentration of pesticide in samples that are above/below limit."""
        try:
            from modules.mappings import get_pesticide_variants
        except ImportError:
            get_pesticide_variants = lambda p: [p]

        con = self._get_connection()

        sample_filter = ""
        if samples:
            conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
            sample_filter = f"AND ({' OR '.join(conditions)})"

        limit_filter = f"AND is_above_limit = {1 if is_above else 0}"
        pest_filter = ", ".join([f"'{v}'" for v in get_pesticide_variants(pesticide)])

        sql = f"""
        SELECT
            "اسم العينة"     AS نوع_العينة,
            COUNT(*)         AS عدد_السجلات,
            ROUND(AVG(concentration), 5) AS متوسط_التركيز,
            ROUND(MIN(concentration), 5) AS أقل_تركيز,
            ROUND(MAX(concentration), 5) AS أعلى_تركيز,
            ROUND(MAX(limit_value), 5)   AS MRL
        FROM chemistry_tidy
        WHERE is_detected = 1
          AND pesticide_name IN ({pest_filter})
          {sample_filter}
          {limit_filter}
        GROUP BY "اسم العينة"
        ORDER BY متوسط_التركيز DESC
        """

        df = con.execute(sql).df()
        con.close()

        limit_label = "فوق الحد" if is_above else "تحت الحد"
        sample_display = " + ".join(samples) if samples else "جميع العينات"

        if df.empty:
            return f"⚠️ لم أجد سجلات لمبيد {pesticide} {limit_label} في {sample_display}", df

        overall_avg = df["متوسط_التركيز"].mean().round(5)
        response = f"📊 **متوسط تركيز {pesticide} في العينات {limit_label} — {sample_display}:**\n\n"
        response += f"📈 المتوسط الكلي: **{overall_avg} mg/kg**\n\n"
        response += df.to_markdown(index=False)

        return response, df

    # ──────────────────────────────────────────────────────────────────────────
    # Unique non-compliant samples + pesticide repetitions (combined)
    # ──────────────────────────────────────────────────────────────────────────
    def _handle_unique_noncompliant_with_pesticides(
        self, samples: List[str]
    ) -> Tuple[str, pd.DataFrame]:
        """
        Count unique non-compliant sample codes AND show pesticide repetition counts.
        "How many unique non-compliant samples in cardamom + pesticide repetitions?"
        """
        con = self._get_connection()

        sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        sample_filter = f"({' OR '.join(sample_conditions)})"

        # Part 1: unique non-compliant sample codes
        unique_sql = f"""
        SELECT
            COUNT(DISTINCT "كود العينة") AS unique_non_compliant_samples,
            COUNT(*)                     AS total_records
        FROM chemistry_tidy
        WHERE {sample_filter}
          AND sample_result LIKE '%non-compliant%'
        """

        unique_df = con.execute(unique_sql).df()
        unique_count = int(unique_df.iloc[0]["unique_non_compliant_samples"]) if not unique_df.empty else 0

        # Part 2: pesticide repetitions in non-compliant samples
        pest_sql = f"""
        SELECT
            pesticide_name            AS المبيد,
            COUNT(*)                  AS عدد_التكرار,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS فوق_الحد,
            ROUND(AVG(concentration), 5) AS متوسط_التركيز,
            ROUND(MAX(limit_value), 5)   AS MRL
        FROM chemistry_tidy
        WHERE {sample_filter}
          AND is_detected = 1
          AND pesticide_name NOT IN ('NO DETECTION', 'NO DATA')
          AND sample_result LIKE '%non-compliant%'
        GROUP BY pesticide_name
        ORDER BY عدد_التكرار DESC
        """

        pest_df = con.execute(pest_sql).df()
        con.close()

        sample_display = " + ".join(samples)
        response = f"📊 **العينات غير المطابقة الفريدة لـ {sample_display}:**\n\n"
        response += f"🔢 **عدد العينات غير المطابقة الفريدة: {unique_count}**\n\n"

        if not pest_df.empty:
            response += f"### 🧪 تكرار المبيدات في العينات غير المطابقة\n\n"
            response += pest_df.to_markdown(index=False)
        else:
            response += "⚠️ لم أجد تفاصيل مبيدات"

        return response, pest_df

    # ──────────────────────────────────────────────────────────────────────────
    # Pesticide frequency in a specific sample (targeted)
    # ──────────────────────────────────────────────────────────────────────────
    def _handle_pesticide_frequency_in_sample(
        self, pesticide: str, samples: List[str]
    ) -> Tuple[str, pd.DataFrame]:
        """
        How many times does pesticide X appear in sample Y?
        "Frequency of imidacloprid in tomatoes"
        """
        try:
            from modules.mappings import get_pesticide_variants
        except ImportError:
            get_pesticide_variants = lambda p: [p]

        con = self._get_connection()

        sample_conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        sample_filter = f"({' OR '.join(sample_conditions)})"
        pest_filter = ", ".join([f"'{v}'" for v in get_pesticide_variants(pesticide)])

        sql = f"""
        SELECT
            "اسم العينة"     AS نوع_العينة,
            pesticide_name   AS المبيد,
            COUNT(*)         AS التكرار,
            COUNT(DISTINCT "كود العينة") AS عينات_فريدة,
            SUM(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS فوق_الحد,
            ROUND(AVG(concentration), 5) AS متوسط_التركيز,
            ROUND(MIN(concentration), 5) AS أقل_تركيز,
            ROUND(MAX(concentration), 5) AS أعلى_تركيز,
            ROUND(MAX(limit_value), 5)   AS MRL
        FROM chemistry_tidy
        WHERE is_detected = 1
          AND pesticide_name IN ({pest_filter})
          AND {sample_filter}
        GROUP BY "اسم العينة", pesticide_name
        """

        df = con.execute(sql).df()
        con.close()

        sample_display = " + ".join(samples)

        if df.empty:
            return f"⚠️ لم أجد {pesticide} في {sample_display}", df

        total_freq = int(df["التكرار"].sum())
        total_violations = int(df["فوق_الحد"].sum())

        response = f"📊 **تكرار مبيد {pesticide} في {sample_display}:**\n\n"
        response += f"🔢 **إجمالي التكرار: {total_freq}**\n"
        response += f"🔴 فوق الحد: **{total_violations}**\n"
        response += f"🟢 ضمن الحد: **{total_freq - total_violations}**\n\n"
        response += df.to_markdown(index=False)

        return response, df

    # ──────────────────────────────────────────────────────────────────────────
    # Category limit summary (spices above AND below limits)
    # ──────────────────────────────────────────────────────────────────────────
    def _handle_category_limit_summary(
        self, category_key: Optional[str], samples: List[str], test_type: Optional[str] = None
    ) -> Tuple[str, pd.DataFrame]:
        """
        Show all sample types in a category with their above/below limit counts.
        "spices above and below permissible limits"
        """
        con = self._get_connection()

        # CATEGORY_AR imported from modules.mappings — single source of truth

        if samples:
            conditions = [f"\"اسم العينة\" LIKE '%{s}%'" for s in samples]
        elif category_key and category_key in CATEGORY_AR:
            conditions = [f"\"اسم العينة\" LIKE '%{ar}%'" for ar in CATEGORY_AR[category_key]]
        else:
            conditions = ["1=1"]

        sample_filter = f"({' OR '.join(conditions)})"

        # Optional test type filter
        test_filter = ""
        if test_type == "pesticide":
            test_filter = "AND \"نوع الاختبار\" LIKE '%مبيد%'"
        elif test_type == "mycotoxin":
            test_filter = "AND \"نوع الاختبار\" LIKE '%فطري%'"

        sql = f"""
        WITH sample_status AS (
            SELECT
                "كود العينة"  AS sample_code,
                "اسم العينة"  AS sample_name,
                "نوع الاختبار" AS test_type,
                MAX(CASE WHEN is_above_limit = 1 THEN 1 ELSE 0 END) AS has_violation,
                COUNT(CASE WHEN is_detected = 1 THEN 1 END) AS pesticide_count
            FROM chemistry_tidy
            WHERE {sample_filter}
            {test_filter}
            GROUP BY "كود العينة", "اسم العينة", "نوع الاختبار"
        )
        SELECT
            sample_name         AS نوع_العينة,
            test_type           AS نوع_الاختبار,
            COUNT(*)            AS إجمالي_العينات,
            SUM(has_violation)  AS فوق_الحد,
            SUM(CASE WHEN has_violation = 0 THEN 1 ELSE 0 END) AS تحت_الحد,
            ROUND(100.0 * SUM(has_violation) / COUNT(*), 1) AS نسبة_المخالفات
        FROM sample_status
        GROUP BY sample_name, test_type
        ORDER BY نوع_العينة, test_type
        """

        df = con.execute(sql).df()
        con.close()

        category_label = {
            "vegetable": "الخضار", "fruit": "الفواكه", "spice": "التوابل",
            "nut": "المكسرات", "grain": "الحبوب", "leafy": "الورقيات"
        }.get(category_key or "", " + ".join(samples) if samples else "جميع العينات")

        if df.empty:
            return f"⚠️ لم أجد بيانات لـ {category_label}", df

        total_samples = int(df["إجمالي_العينات"].sum())
        total_above = int(df["فوق_الحد"].sum())
        total_below = int(df["تحت_الحد"].sum())

        response = f"📊 **ملخص {category_label} — فوق وتحت الحد المسموح:**\n\n"
        response += f"✅ إجمالي العينات: **{total_samples}**\n"
        response += f"🔴 فوق الحد: **{total_above}**\n"
        response += f"🟢 تحت الحد: **{total_below}**\n\n"
        response += df.to_markdown(index=False)

        return response, df