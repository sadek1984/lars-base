# LARS Debugging Playbook

A living record of debugging sessions and the reusable strategy behind them.
Add a new entry under **Session Log** each time you track down a real bug —
future-you (or anyone else on the project) should be able to reconstruct the
reasoning, not just see the diff.

---

## General Debugging Strategy (apply this first, every time)

1. **Get ground truth before touching code.**
   Don't guess at prompts/patterns from the symptom. Get the actual generated
   SQL, the actual columns returned, the actual response text. In LARS this
   means adding a debug expander around `generated_sql` / `result_df` in
   `ai_assistant.py` before doing anything else.

2. **Match output shape to a specific function — don't assume from the name.**
   Column names and exact response strings (e.g. `"Comprehensive Analysis"`)
   are unique fingerprints. `grep` for them directly:
   ```bash
   grep -n "your_column_name\|Your Response String" src/LARS/modules/core_query_engine.py
   ```
   This is far more reliable than guessing which function "sounds right" —
   especially in this codebase, which has near-duplicate function names
   (`_handle_comprehensive_neighborhood` vs the now-removed
   `_handle_comprehensive_neighborhood_samples`).

3. **Trace routing, not just the handler.**
   `process()` in `core_query_engine.py` is a linear 3-tier cascade:
   - Tier 1: Semantic pattern recognition (embedding-based, confidence ≥ 0.75)
   - Tier 2: Intent-based routing (`IntentRouter` + `_dispatch_by_intent`)
   - Tier 3: Keyword pattern cascade (`_dispatch_keyword_patterns`)

   A wrong-looking output often means the *wrong handler* fired, not that the
   right handler is broken. Read `process()` top to bottom and check which
   tier's condition actually matched your query.

4. **Isolate variables.**
   Change one thing at a time and retest: Arabic vs English phrasing, with vs
   without a specific keyword, one entity vs multiple. This tells you whether
   a bug is language-specific, phrase-specific, or structural.

5. **Prefer narrow, additive fixes over rewrites.**
   A small early "Tier 0" override or a targeted SQL/GROUP BY fix is safer
   than restructuring routing logic — it can't silently break the many other
   query patterns you haven't retested.

6. **Verify any find-and-replace edit against a mock before running it on the
   real file**, especially with Arabic text and f-string `\n` escapes — those
   are easy to get subtly wrong (see Session Log #1 for a concrete failure
   mode). Test with an `assert count == 1` guard so a bad match aborts safely
   instead of silently editing the wrong spot.

7. **After any edit, check for dead code you're now duplicating or bypassing.**
   Search whole-repo (not just one directory) before deleting anything:
   ```bash
   grep -rn "function_name" . --include="*.py" | grep -v "defining_file.py"
   grep -rn "from.*module import\|import module" . --include="*.py"
   ```
   Watch out for aliased imports and singleton factories called from outside
   the file you're looking at.

---

## Quick Reference: Getting the Generated SQL / Debug Output

If the "View SQL" UI button isn't available, add a debug block right after
SQL/response generation in `ai_assistant.py`:

```python
with st.expander("🔍 Debug: Generated SQL", expanded=True):
    st.code(generated_sql, language="sql")
    if result_df is not None:
        st.write(f"Rows returned: {len(result_df)}")
        st.write(f"Columns: {list(result_df.columns)}")
```

Remember: `generated_sql` is `None` whenever the query was handled by Tier 1
(pattern matching) rather than Tier 2 (LLM SQL fallback) — that alone tells
you to go look in `core_query_engine.py`, not the LLM prompt.

---

## Quick Reference: Finding Dead Functions

```bash
python3 <<'PYEOF'
import ast, os

TARGET_FILE = "src/LARS/modules/core_query_engine.py"
SEARCH_ROOT = "."   # widen to repo root, not just src/LARS

with open(TARGET_FILE, encoding="utf-8") as f:
    tree = ast.parse(f.read(), filename=TARGET_FILE)

defined = {n.name for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
skip = {"__init__", "process", "process_with_gemini_fallback"}
candidates = sorted(n for n in defined if not n.startswith("__") and n not in skip)

files = []
for root, dirs, fs in os.walk(SEARCH_ROOT):
    dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "venv", ".venv")]
    files += [os.path.join(root, f) for f in fs if f.endswith(".py")]

texts = {fp: open(fp, encoding="utf-8").read() for fp in files}

dead = []
for name in candidates:
    total = sum(t.count(f"{name}(") for t in texts.values())
    own_def = texts[TARGET_FILE].count(f"def {name}(")
    if total - own_def == 0:
        dead.append(name)

print("Possibly dead:", dead if dead else "none found")
PYEOF
```

Always cross-check any hit with a repo-wide grep before deleting — string
matching misses dynamic dispatch (`getattr(self, name)()`) and aliased
imports.

---

## Session Log

### Session 1 — 2026-07-24: Neighborhood breakdown collapsing into one merged total

**Symptom:** Query `"ماهي المبيدات الموجوده في حي الريان و الإسكان كل علي حده"`
("...each separately") returned one merged total instead of a per-neighborhood
breakdown.

**Root cause chain:**
1. `generated_sql` was `None` → confirmed it was a Tier 1 pattern-match, not
   LLM SQL — eliminated the LLM prompt as a suspect immediately.
2. The response shape (`sample_type, total_count, above_limit, below_limit,
   pesticide_free`) matched a specific handler's signature exactly —
   `grep -n "total_count\|above_limit\|pesticide_free"` found it.
3. First attempt fixed the wrong function
   (`_handle_comprehensive_neighborhood_samples`) — it *looked* like the right
   one from its name, but wasn't called from anywhere (later confirmed and
   removed as dead code). The real handler was
   `_handle_comprehensive_neighborhood`, confirmed by matching the exact
   response text `"Comprehensive Analysis — {category_name} in {hood_display}"`.
4. Actual bug: the SQL's `neighborhood_filter` OR'd all requested
   neighborhoods into a single `WHERE` clause, and the `GROUP BY` never
   included the neighborhood column at all — structurally impossible to
   separate, regardless of the "separately" keyword.

**Fix:** Added `"الحى" as neighborhood` to the CTE and final `SELECT` /
`GROUP BY`, then changed the response formatter to loop
`for hood, group in df.groupby('neighborhood')` instead of summing across
the whole dataframe.

**Follow-up bug (same session):** A related query asking for **non-compliant
samples only** ("غير مطابقة") was being caught by the same comprehensive
handler — which shows everything, not a filtered list. Fixed by:
- Adding a "Tier 0" override at the very top of `process()` that checks for
  `"غير مطابقة"` / `"مطابقة"` + a detected neighborhood and routes straight to
  `_handle_count_samples_compliance`, bypassing the semantic/intent tiers
  that were misclassifying it.
- Applying the same neighborhood-grouping fix to
  `_handle_count_samples_compliance`, plus filtering the per-neighborhood
  table down to just the requested status instead of showing both.

**Lesson learned — escaping bug:** An early automated find-and-replace
script used single `\n` inside a Python heredoc string. Python's parser
turns `\n` into an actual newline character when constructing the string —
but the target file's f-strings contain the literal two-character sequence
`\` + `n` (an escape *within source code*, not an executed one). Result: the
`old_str` didn't match the file's raw text at all. Fix: use `\\n` in the
heredoc so it produces a literal backslash-n that matches the file's actual
bytes. **Always test find-and-replace scripts against a reconstructed mock
file first** — this is now standard practice (see Strategy step 6).

**Dead code found and removed this session:**
- `_handle_comprehensive_neighborhood_samples` — never called anywhere.
- `get_query_engine()` singleton factory + module-level `_engine` — every
  caller in the repo (`ai_assistant.py`, `voice_bot_enhanced.py`,
  `lars_service.py`, `patch_lars.py`, `test_english_queries.py`) instantiates
  `CoreQueryEngine()` directly instead.

---

### Session 2 — [date]

*(next entry goes here)*
