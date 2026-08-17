# -*- coding: utf-8 -*-
"""
reset_inspections_log.py — تفضية جدول inspections_log بالكامل
================================================================
شغّله لما تكون خلّصت اختبار وعايز ترجع للوضع الأول (زي ما لو محدش
ضغط "تم التفتيش" خالص). بيمسح كل الصفوف، مش بيمسح الجدول نفسه —
عشان أي كود شغال (زي الصفحة) يفضل شغال عادي من غير أخطاء.

الاستخدام:
    python reset_inspections_log.py            # يمسح كل حاجة
    python reset_inspections_log.py --dry-run   # يعرضلك هيمسح كام صف بس من غير ما يمسح فعليًا
"""

import argparse
import os
import duckdb

DB_PATH = os.environ.get(
    "LARS_DUCKDB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "lars_data.duckdb"),
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="يعرض عدد الصفوف بس من غير ما يمسح")
    args = ap.parse_args()

    con = duckdb.connect(DB_PATH, read_only=args.dry_run)
    try:
        count = con.execute(
            "SELECT COUNT(*) FROM inspections_log"
        ).fetchone()[0]
    except Exception:
        print("جدول inspections_log مش موجود أصلًا — مفيش حاجة تتمسح.")
        con.close()
        return

    print(f"عدد الزيارات المسجّلة حاليًا: {count}")

    if args.dry_run:
        print("(--dry-run: مفيش حاجة اتمسحت)")
    elif count > 0:
        con.execute("DELETE FROM inspections_log")
        print(f"تم مسح {count} صف. الصفحة هترجع تشتغل زي أول مرة.")
    else:
        print("الجدول فاضي أصلًا.")

    con.close()


if __name__ == "__main__":
    main()