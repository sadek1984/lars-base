#!/usr/bin/env python3
"""
Applies the three poisoning integration edits to core_query_engine.py.
Idempotent. Writes a .bak_poisoning backup first.
"""
import ast
import re
import shutil
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "modules/core_query_engine.py"
GUARD_FNS = ("_handle_llm_query", "process_with_gemini_fallback")
SCHEMA_IMPORT = "from modules.poisoning import POISONING_SCHEMA_CARD\n"

GUARD = (
    "# --- poisoning domain guard: never answer a تسمم question from chemistry_tidy\n"
    "from modules.poisoning import is_poisoning_domain\n"
    "if is_poisoning_domain(query):\n"
    "    return self._handle_poisoning(\"POISONING_HEADLINE\", query, None)\n"
    "# --- end poisoning guard\n"
)

src = open(PATH, encoding="utf-8").read()
shutil.copy(PATH, PATH + ".bak_poisoning")
lines = src.splitlines(keepends=True)
report = []

# ---- edit 1: remove the bogus schema_card lines ---------------------------
before = len(lines)
kept = []
for i, l in enumerate(lines):
    if "self.schema_card" in l:
        continue                                  # the bogus attribute line
    if re.match(r"\s*from modules\.poisoning import POISONING_SCHEMA_CARD\s*$", l):
        # only drop this import if it belongs to the bogus block, i.e. the next
        # non-blank line is the self.schema_card assignment
        nxt = next((x for x in lines[i + 1:] if x.strip()), "")
        if "self.schema_card" in nxt:
            continue
    kept.append(l)
lines = kept
report.append(f"edit 1: removed {before - len(lines)} bogus schema_card line(s)")
src = "".join(lines)

# ---- edit 2: append the card where the SQL prompt gets its schema ---------
old = "schema=self._get_schema_info(),"
new = 'schema=self._get_schema_info() + "\\n" + POISONING_SCHEMA_CARD,'
SCHEMA_FN = "_build_llm_sql_prompt"
if new in src:
    report.append("edit 2: already applied")
elif old in src:
    src = src.replace(old, new, 1)
    report.append("edit 2: schema card appended to _build_llm_sql_prompt")
    SCHEMA_FN = "_build_llm_sql_prompt"
else:
    SCHEMA_FN = None
    report.append("edit 2: !! anchor 'schema=self._get_schema_info(),' NOT FOUND")

# ---- edit 3: insert the guard as first statement of both LLM methods ------
tree = ast.parse(src)
targets = []
inserts = []          # (lineno, col, fn_name, text)
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == SCHEMA_FN:
        body = node.body
        first = body[1] if (len(body) > 1 and isinstance(body[0], ast.Expr)
                            and isinstance(getattr(body[0], "value", None), ast.Constant)
                            and isinstance(body[0].value.value, str)) else body[0]
        inserts.append((first.lineno, first.col_offset, node.name, SCHEMA_IMPORT))
    if isinstance(node, ast.FunctionDef) and node.name in GUARD_FNS:
        body = node.body
        first = body[1] if (len(body) > 1 and isinstance(body[0], ast.Expr)
                            and isinstance(getattr(body[0], "value", None), ast.Constant)
                            and isinstance(body[0].value.value, str)) else body[0]
        targets.append((first.lineno, first.col_offset, node.name, GUARD))

lines = src.splitlines(keepends=True)
for lineno, col, name, text in sorted(targets + inserts, reverse=True):
    marker = "is_poisoning_domain" if text is GUARD else "import POISONING_SCHEMA_CARD"
    window = "".join(lines[max(0, lineno - 8):lineno + 2])
    if marker in window:
        report.append(f"edit 3: {name} already patched")
        continue
    indent = " " * col
    block = "".join(indent + l for l in text.splitlines(keepends=True))
    lines.insert(lineno - 1, block)
    report.append(f"edit 3: patched {name} at line {lineno}")

src = "".join(lines)
ast.parse(src)                       # refuse to write broken syntax
open(PATH, "w", encoding="utf-8").write(src)

print("\n".join("  " + r for r in report))
print(f"\n  backup: {PATH}.bak_poisoning")
