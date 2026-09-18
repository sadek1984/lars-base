# Lessons (per CLAUDE.md self-improvement loop)

## 2026-09-18 — modules/ refactor

1. **Import-grep is not a usage audit.** Three live Streamlit pages were
   referenced only via string lazy-imports (`"modules.x:func"` in app_new.py's
   PAGES registry). Always grep for the module name in *all* file types, not
   just `from X import` lines.

2. **Module-level anchor fixes don't cover function-level ones.** Moving files
   deeper broke five `Path(__file__).parent.parent` uses *inside functions*
   (ai_assistant, risk_windows, risk_analysis, inspection_priority) that import
   smoke tests structurally cannot catch — they only execute at runtime.
   After any file move: `grep -rn "Path(__file__)"` over the moved files and
   verify each computed path resolves, not just that imports succeed.

3. **Multi-line calls evade single-line greps.** `load_prompt(\n  "name")`
   hid a reference to an archived template (pandas_code_gen.md). Use `grep -A2`
   or AST-level checks when auditing call sites.

4. **A passing harness can mask environment-gated paths.** The ollama fallback
   and inspection DEFAULT_DB bugs were invisible to the 220-question harness
   because those branches don't execute in the harness environment (no ollama;
   explicit db_path). Note which code paths a test suite *cannot* reach before
   claiming full coverage.
