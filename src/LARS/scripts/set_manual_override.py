#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
set_manual_override.py — رفع/إلغاء أولوية منشأة يدويًا (لشكوى عاجلة مثلًا)
=============================================================================
بديل خفيف لصفحة admin كاملة. يكتب في جدول risk_overrides المنفصل —
مش داخل risk_scores نفسه — عشان الرفع يفضل موجود حتى بعد أي إعادة بناء
لـ build_risk_scores.py (اللي بيعمل CREATE OR REPLACE على risk_scores).

كل الواجهات (Streamlit / core_query_engine / الصوت) بتقرا من risk_overrides
أوتوماتيك عن طريق inspection_priority.get_top() — مفيش أي تعديل تاني مطلوب.

الاستخدام:
    # ابحث الأول عن الـ entity_id الصحيح
    python set_manual_override.py --search "مخازن العالمية"

    # ارفع منشأة +30 نقطة لمدة 14 يوم (شكوى عاجلة)
    python set_manual_override.py --set --entity-id 3909364390 --level establishment \
        --boost 30 --note "شكوى تسمم مشتبه - بلاغ 2026-08-12" --days 14

    # اعرض كل الرفوعات النشطة حاليًا
    python set_manual_override.py --list

    # ألغِ رفع منشأة قبل انتهاء مدته
    python set_manual_override.py --clear --entity-id 3909364390 --level establishment
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

_HERE = Path(__file__).resolve().parent
DEFAULT_DB = str(_HERE.parent / "data" / "lars_data_demo.duckdb")


def _ensure_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS risk_overrides (
            level VARCHAR,
            entity_id VARCHAR,
            boost DOUBLE,
            note VARCHAR,
            expires_at TIMESTAMP,
            set_by VARCHAR,
            set_at TIMESTAMP
        )
    """)


def cmd_search(con, term, level):
    where = "level = ?" if level else "1=1"
    params = [level] if level else []
    df = con.execute(
        f"SELECT level, entity_id, entity_name, risk_score, confidence "
        f"FROM risk_scores WHERE {where} AND entity_name ILIKE ? "
        f"ORDER BY risk_score DESC LIMIT 15",
        params + [f"%{term}%"]
    ).df()
    if df.empty:
        print("مفيش نتائج.")
        return
    print(df.to_string(index=False))


def cmd_set(con, level, entity_id, boost, note, days, set_by):
    row = con.execute(
        "SELECT entity_name, risk_score FROM risk_scores WHERE level=? AND entity_id=?",
        [level, entity_id]
    ).fetchone()
    if not row:
        sys.exit(f"❌ مفيش كيان بـ entity_id={entity_id} في مستوى {level}. "
                  f"استخدم --search الأول للتأكد من الرقم الصحيح.")
    name, current_score = row

    expires_at = (datetime.now() + timedelta(days=days)) if days else None
    con.execute(
        "DELETE FROM risk_overrides WHERE level=? AND entity_id=?",  # يمنع تراكم صفوف قديمة لنفس الكيان
        [level, entity_id]
    )
    con.execute(
        "INSERT INTO risk_overrides VALUES (?,?,?,?,?,?,now())",
        [level, entity_id, boost, note, expires_at, set_by]
    )
    print(f"✅ اترفع «{name}» (درجة أصلية {current_score:.0f}) بمقدار {boost:+.0f} نقطة")
    if expires_at:
        print(f"   ينتهي في: {expires_at.strftime('%Y-%m-%d %H:%M')}")
    else:
        print("   بدون تاريخ انتهاء — لازم تتلغى يدويًا بـ --clear")


def cmd_clear(con, level, entity_id):
    n = con.execute(
        "DELETE FROM risk_overrides WHERE level=? AND entity_id=? RETURNING entity_id",
        [level, entity_id]
    ).fetchall()
    if n:
        print(f"✅ اتلغى الرفع اليدوي عن {len(n)} صف")
    else:
        print("ℹ️ مفيش رفع نشط أصلًا لهذا الكيان.")


def cmd_list(con):
    df = con.execute("""
        SELECT o.level, o.entity_id, r.entity_name, r.risk_score AS current_score,
               o.boost, o.note, o.expires_at, o.set_by, o.set_at
        FROM risk_overrides o
        LEFT JOIN risk_scores r ON r.level = o.level AND r.entity_id = o.entity_id
        WHERE o.expires_at IS NULL OR o.expires_at > now()
        ORDER BY o.set_at DESC
    """).df()
    if df.empty:
        print("مفيش رفوعات نشطة حاليًا.")
        return
    print(df.to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--search", metavar="TERM", help="ابحث عن كيان بالاسم")
    ap.add_argument("--set", action="store_true", help="ارفع كيان")
    ap.add_argument("--clear", action="store_true", help="ألغِ رفع كيان")
    ap.add_argument("--list", action="store_true", help="اعرض كل الرفوعات النشطة")
    ap.add_argument("--level", default="establishment",
                    choices=["establishment", "neighborhood", "municipality"])
    ap.add_argument("--entity-id")
    ap.add_argument("--boost", type=float, help="مقدار الرفع (موجب) — النتيجة تُقصّ عند 100")
    ap.add_argument("--note", default="", help="سبب الرفع — إلزامي للشفافية")
    ap.add_argument("--days", type=int, default=None, help="مدة الصلاحية بالأيام (افتراضي: بلا انتهاء)")
    ap.add_argument("--by", default="supervisor", help="اسم من قام بالرفع")
    args = ap.parse_args()

    if not any([args.search, args.set, args.clear, args.list]):
        ap.print_help()
        return

    con = duckdb.connect(args.db, read_only=False)
    _ensure_table(con)

    if args.search:
        cmd_search(con, args.search, args.level if args.level else None)
    elif args.set:
        if not args.entity_id or args.boost is None:
            sys.exit("❌ --set محتاج --entity-id و --boost")
        if not args.note:
            print("⚠️ محبّذ تكتب --note يوضح سبب الرفع — للشفافية أمام أي حد يراجع القرار لاحقًا")
        cmd_set(con, args.level, args.entity_id, args.boost, args.note, args.days, args.by)
    elif args.clear:
        if not args.entity_id:
            sys.exit("❌ --clear محتاج --entity-id")
        cmd_clear(con, args.level, args.entity_id)
    elif args.list:
        cmd_list(con)

    con.close()


if __name__ == "__main__":
    main()
