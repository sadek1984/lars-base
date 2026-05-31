"""
PATCH for src/LARS/modules/core_query_engine.py
================================================
Your DB stores Arabic names ('طماطم', 'خيار', ...).
The engine was generating LIKE '%Tomato%' → 0 results.

Apply this patch by replacing two methods in core_query_engine.py:
  1. _build_sample_filter()
  2. _detect_sample_types()   ← small tweak only

The rest of core_query_engine.py stays unchanged.
"""

# ══════════════════════════════════════════════════════════════
# PASTE THIS into core_query_engine.py
# REPLACE the existing _build_sample_filter method
# ══════════════════════════════════════════════════════════════

PATCH_build_sample_filter = '''
    def _build_sample_filter(self, samples: list) -> str:
        """
        Build SQL WHERE clause for "اسم العينة".

        YOUR DATABASE stores ARABIC names ('طماطم', 'خيار', ...).
        _detect_sample_types() returns English canonical values ('Tomato').
        This method converts them back to Arabic substrings for the LIKE.

        Falls back to English substring search too, so the filter works
        even if the DB is later migrated to English names.
        """
        if not samples:
            return "1=1"

        # Build reverse map: English canonical → list of Arabic query keys
        # e.g. 'Tomato' → ['طماطم', 'طماطم شيري']  (only the base match matters)
        from modules.mappings import SAMPLE_CORRECTIONS

        en_to_ar: dict = {}
        for ar_key, en_val in SAMPLE_CORRECTIONS.items():
            en_to_ar.setdefault(en_val, []).append(ar_key)

        conditions = []
        for s in samples:
            # ── A: Arabic LIKE (what your DB actually has) ──────────────
            arabic_variants = en_to_ar.get(s, [])
            # Use TRIM() on the column side to handle accidental spaces
            for ar in arabic_variants:
                conditions.append(
                    f"TRIM(\"اسم العينة\") LIKE \'%{ar}%\'"
                )

            # ── B: English LIKE fallback (future-proof) ─────────────────
            conditions.append(f"\"اسم العينة\" LIKE \'%{s}%\'")

            # ── C: Category column (نوع العينة) ─────────────────────────
            conditions.append(f"\"نوع العينة\" LIKE \'%{s}%\'")

        return f"({' OR '.join(conditions)})"
'''

# ══════════════════════════════════════════════════════════════
# ALSO ADD to api_service.py — _SESSION_DEFAULTS
# Prevents the engine defaulting to Pandas every fresh session
# ══════════════════════════════════════════════════════════════

PATCH_session_defaults = '''
# In api_service.py, find _SESSION_DEFAULTS and ADD "query_engine":

_SESSION_DEFAULTS: Dict[str, Any] = {
    "chat_messages": [
        {
            "role": "assistant",
            "content": (
                "👋 Hello! I\'m your **pesticide analysis AI assistant** — "
                "ready to help you explore, assess, and analyze pesticide "
                "data with ease.\\n\\n"
                "💬 **Type your question below and I\'ll analyze the data "
                "for you** 🚀"
            ),
        }
    ],
    "selected_year": DEFAULT_YEAR,
    "indexed_years": set(),
    "project_id": "default_project",
    "intro_shown": False,
    "current_page": "🏠 Dashboard Overview",
    "data_loaded": False,
    "query_engine": "sql",          # ← ADD THIS — default to SQL, not Pandas
}
'''

# ══════════════════════════════════════════════════════════════
# AUTOMATED PATCHER  (optional — run instead of manual edit)
# ══════════════════════════════════════════════════════════════

import re
from pathlib import Path

def patch_build_sample_filter(engine_path: Path) -> bool:
    """Replace _build_sample_filter in core_query_engine.py."""
    src = engine_path.read_text(encoding="utf-8")

    # Find method start and end by indentation
    pattern = re.compile(
        r'(\n    def _build_sample_filter\(self.*?)'   # method signature
        r'(?=\n    def |\nclass |\Z)',                  # until next method/class/EOF
        re.DOTALL
    )
    match = pattern.search(src)
    if not match:
        print("❌ Could not locate _build_sample_filter — patch manually.")
        return False

    new_method = PATCH_build_sample_filter  # indented with 4 spaces already
    new_src = src[: match.start()] + "\n" + new_method + "\n" + src[match.end() :]

    # Write backup
    backup = engine_path.with_suffix(".py.bak")
    backup.write_text(src, encoding="utf-8")
    print(f"  Backup written → {backup}")

    engine_path.write_text(new_src, encoding="utf-8")
    print(f"✅ _build_sample_filter patched in {engine_path}")
    return True


def patch_session_defaults(api_path: Path) -> bool:
    """Add 'query_engine': 'sql' to _SESSION_DEFAULTS."""
    src = api_path.read_text(encoding="utf-8")

    if '"query_engine"' in src or "'query_engine'" in src:
        print("  query_engine already in _SESSION_DEFAULTS — skipping.")
        return True

    # Insert before the closing brace of _SESSION_DEFAULTS
    old = '    "data_loaded": False,\n}'
    new = '    "data_loaded": False,\n    "query_engine": "sql",\n}'
    if old not in src:
        # try without closing brace (dict may span differently)
        old = '    "data_loaded": False,\n'
        new = '    "data_loaded": False,\n    "query_engine": "sql",\n'

    if old not in src:
        print("❌ Could not locate insertion point — add manually (see PATCH_session_defaults above).")
        return False

    backup = api_path.with_suffix(".py.bak")
    backup.write_text(src, encoding="utf-8")
    print(f"  Backup written → {backup}")

    api_path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"✅ query_engine default patched in {api_path}")
    return True


if __name__ == "__main__":
    import sys

    engine_file = Path("src/LARS/modules/core_query_engine.py")
    api_file    = Path("src/LARS/modules/api_service.py")

    print("="*60)
    print("LARS Core Query Engine Patcher")
    print("="*60)

    if not engine_file.exists():
        print(f"❌ Not found: {engine_file}")
        print("   Run from your project root (lars-base/).")
        sys.exit(1)

    ok1 = patch_build_sample_filter(engine_file)
    ok2 = patch_session_defaults(api_file)

    if ok1 and ok2:
        print("\n✅ Both patches applied.")
        print("\nNow run the engine test to verify:")
        print("""
python3 - << 'EOF'
import sys
sys.path.insert(0, "src/LARS")
from modules.core_query_engine import CoreQueryEngine

engine = CoreQueryEngine(
    db_path="src/LARS/data/lars_data.duckdb",
    enable_llm_fallback=False
)
for q in ["how many tomato samples",
          "how many samples above limit",
          "list pesticides in cucumber",
          "كم عدد عينات الطماطم",
          "ما المبيدات في الخيار",
          "how many cashew samples",
          "how many potato samples above limit"]:
    resp, df = engine.process(q)
    rows = len(df) if df is not None else None
    flag = "✅" if rows else "⚠️ "
    print(f"{flag} Q={q!r:45s} rows={rows}")
EOF
""")
    else:
        print("\n⚠️  One or more patches failed — apply manually (see file contents above).")