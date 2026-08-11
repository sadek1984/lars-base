#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_license_to_tidy.py — يرجّع عمود `رقم الرخصة` إلى chemistry_tidy
===================================================================
العمود اتشال في الـ ETL الأصلي. ده ترحيل *إضافي* — بيضيف عمود في آخر
الجدول ومش بيلمس أي عمود قايم، فالبنشمارك المفروض ما يتأثرش.

بيعالج تلات مشاكل جودة اكتشفناها في ملف المصدر:
  1. قيم غير رقمية ('إعادة', 'رقم 10')          → NULL
  2. رخص متتابعة من سحب خلية في إكسل            → تتجمّع على أقل رقم
  3. أكواد عينات مكررة بأكتر من رخصة             → تتحل بالربط على (كود + اسم المنشأة)

الاستخدام:
    python add_license_to_tidy.py --excel <path.xlsx> --dry-run
    python add_license_to_tidy.py --excel <path.xlsx>
    python add_license_to_tidy.py --excel <path.xlsx> --rollback
"""

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
DEFAULT_DB = str(_HERE.parent / "data" / "lars_data.duckdb")
TABLE = "chemistry_tidy"
LIC_COL = "رقم الرخصة"
CODE_COL = "كود العينة"
EST_COL = "اسم المنشاة"

# رخصتان تعتبران "متتابعتين" لو الفرق بينهما <= ده (أثر السحب في إكسل)
SEQ_GAP = 3

_AR_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ـ": ""})


def norm_ar(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = str(s).translate(_AR_NORM).strip()
    return re.sub(r"\s+", " ", s) or None


# ---------------------------------------------------------------- extraction

def load_source(excel_path: str = "/Users/a12/lars-base/src/LARS/data/Merged_Pesticide_Receiving_Tracking.xlsx") -> pd.DataFrame:
    """يقرأ ملف الدمج — الهيدر الحقيقي في الصف الثاني (index 1)."""
    df = pd.read_excel(excel_path, sheet_name=0, header=1)
    missing = [c for c in (CODE_COL, LIC_COL, EST_COL) if c not in df.columns]
    if missing:
        sys.exit(f"❌ أعمدة ناقصة في ملف المصدر: {missing}\nالموجود: {list(df.columns)}")
    df = df[pd.to_numeric(df[CODE_COL], errors="coerce").notna()].copy()
    df["code"] = pd.to_numeric(df[CODE_COL]).astype(int)
    df["est_norm"] = df[EST_COL].map(norm_ar)

    lic = df[LIC_COL].astype(str).str.strip()
    bad = ~lic.str.fullmatch(r"\d+", na=False)
    if bad.sum():
        vals = sorted(set(lic[bad & df[LIC_COL].notna()]))[:5]
        print(f"ℹ️  {int(bad.sum()):,} قيمة رخصة غير رقمية → NULL. أمثلة: {vals}")
    df["lic"] = lic.where(~bad, None)
    return df


def collapse_sequential(df: pd.DataFrame) -> pd.DataFrame:
    """
    داخل المنشأة الواحدة، الرخص المتتابعة رقميًا (فرق <= SEQ_GAP) بتتجمّع
    على أقل رقم — دي أرقام متولّدة من سحب خلية، مش رخص فروع حقيقية.
    الفروع الحقيقية أرقامها بعيدة عن بعض جدًا (شوف أسواق سبت).
    """
    mapping = {}
    for est, grp in df[df["lic"].notna()].groupby("est_norm"):
        lics = sorted(set(grp["lic"]))
        if len(lics) < 2:
            continue
        by_len = {}
        for l in lics:
            by_len.setdefault(len(l), []).append(l)
        for _, same in by_len.items():
            if len(same) < 2:
                continue
            vals = sorted(int(x) for x in same)
            run = [vals[0]]
            for v in vals[1:]:
                if v - run[-1] <= SEQ_GAP:
                    run.append(v)
                else:
                    if len(run) > 1:
                        for x in run:
                            mapping[str(x)] = str(run[0])
                    run = [v]
            if len(run) > 1:
                for x in run:
                    mapping[str(x)] = str(run[0])
    if mapping:
        n_est = df[df["lic"].isin(mapping)]["est_norm"].nunique()
        print(f"ℹ️  تجميع {len(mapping)} رخصة متتابعة إلى "
              f"{len(set(mapping.values()))} رخصة، في {n_est} منشأة")
    df["lic"] = df["lic"].map(lambda x: mapping.get(x, x) if x else x)
    return df


def build_maps(df: pd.DataFrame):
    """
    خريطتان:
      - دقيقة: (كود، اسم منشأة مطبّع) → رخصة   [بتحل تصادم الأكواد]
      - احتياطية: كود → رخصة                    [للأكواد غير الملتبسة فقط]
    """
    d = df[df["lic"].notna()]

    pair = (d.groupby(["code", "est_norm"])["lic"]
              .agg(lambda s: s.mode().iloc[0]).reset_index()
              .rename(columns={"lic": "lic_pair"}))

    per_code = d.groupby("code")["lic"].nunique()
    ambiguous = set(per_code[per_code > 1].index)
    if ambiguous:
        print(f"ℹ️  {len(ambiguous)} كود عينة بأكتر من رخصة — هيتحلوا بالاسم، "
              f"واللي يفضل ملتبس هيبقى NULL")
    code_map = (d[~d["code"].isin(ambiguous)]
                .groupby("code")["lic"].first().reset_index()
                .rename(columns={"lic": "lic_code"}))
    return pair, code_map


# ---------------------------------------------------------------- migration

def _register(con, name, df):
    reg = df.copy()
    for c in reg.columns:                       # توافق pandas 3.x
        if reg[c].dtype.kind in "OU" or str(reg[c].dtype) == "str":
            reg[c] = reg[c].astype(object)
    con.register(name, reg)


def migrate(db_path, pair, code_map, dry_run=False):
    con = duckdb.connect(db_path, read_only=dry_run)
    cols = [r[0] for r in con.execute(f"DESCRIBE {TABLE}").fetchall()]
    if LIC_COL in cols:
        print(f"⚠️  العمود «{LIC_COL}» موجود بالفعل في {TABLE} — مفيش حاجة تتعمل")
        con.close()
        return

    _register(con, "pair_map", pair)
    _register(con, "code_map", code_map)

    lic_q = '"' + LIC_COL + '"'
    code_q = '"' + CODE_COL + '"'
    est_q = '"' + EST_COL + '"'
    # نفس تطبيع norm_ar بالظبط، بس داخل SQL
    est_expr = (f"regexp_replace(trim(translate(CAST(t.{est_q} AS VARCHAR), "
                f"'أإآىـ', 'اااي')), '\\s+', ' ', 'g')")

    join_sql = (
        f"SELECT t.*, COALESCE(p.lic_pair, c.lic_code) AS {lic_q} "
        f"FROM {TABLE} t "
        f"LEFT JOIN pair_map p ON t.{code_q} = p.code AND {est_expr} = p.est_norm "
        f"LEFT JOIN code_map c ON t.{code_q} = c.code"
    )

    prev = con.execute(
        f"SELECT COUNT(*) AS n_all, "
        f"SUM(CASE WHEN {lic_q} IS NULL THEN 1 ELSE 0 END) AS n_null, "
        f"COUNT(DISTINCT {lic_q}) AS n_uniq FROM ({join_sql})").df().iloc[0]
    n, nn, uq = int(prev["n_all"]), int(prev["n_null"]), int(prev["n_uniq"])
    print(f"\n📊 نتيجة الربط: {n:,} صف | مربوط {n - nn:,} ({(n - nn) / n * 100:.1f}%) "
          f"| بدون رخصة {nn:,} | رخص فريدة {uq:,}")

    if dry_run:
        print("\n(dry-run — مفيش كتابة)")
        con.close()
        return

    con.execute(f"CREATE OR REPLACE TABLE {TABLE} AS {join_sql}")
    new_cols = [r[0] for r in con.execute(f"DESCRIBE {TABLE}").fetchall()]
    con.close()
    if new_cols[:-1] != cols or new_cols[-1] != LIC_COL:
        sys.exit("❌ ترتيب الأعمدة اتغير — رجّع النسخة الاحتياطية وراجع")
    print(f"✅ اتضاف «{LIC_COL}» في آخر {TABLE} ({len(new_cols)} عمود)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", required=True, help="ملف Merged_Pesticide_Receiving_Tracking.xlsx")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rollback", action="store_true", help="رجّع آخر نسخة احتياطية")
    args = ap.parse_args()

    db = Path(args.db)
    if args.rollback:
        baks = sorted(db.parent.glob(db.name + ".bak_*"))
        if not baks:
            sys.exit("❌ مفيش نسخ احتياطية")
        shutil.copy2(baks[-1], db)
        print(f"✅ اترجّعت النسخة {baks[-1].name}")
        return

    if not db.exists():
        sys.exit(f"❌ قاعدة البيانات مش موجودة: {db}")

    src = load_source(args.excel)
    src = collapse_sequential(src)
    pair, code_map = build_maps(src)

    if not args.dry_run:
        bak = db.parent / (db.name + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        shutil.copy2(db, bak)
        print(f"💾 نسخة احتياطية: {bak.name}")

    migrate(str(db), pair, code_map, dry_run=args.dry_run)

    if not args.dry_run:
        print("\nالخطوات الجاية:")
        print("  1) python scripts/run_question_bank.py     # تأكد إن 211/220 ثابتة")
        print("  2) python scripts/build_risk_scores.py --inspect")
        print("  3) python scripts/build_risk_scores.py")


if __name__ == "__main__":
    main()