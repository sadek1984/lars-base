"""
apply_patches.py
Run this script from your LARS project root to automatically 
apply all translation patches to ai_assistant.py

Usage:
    python apply_patches.py path/to/ai_assistant.py
"""
import sys
import re
import shutil
from pathlib import Path

def apply_all_patches(filepath: str):
    path = Path(filepath)
    if not path.exists():
        print(f"❌ File not found: {filepath}")
        sys.exit(1)

    # Backup original
    backup = path.with_suffix('.py.backup')
    shutil.copy2(path, backup)
    print(f"✅ Backup created: {backup}")

    content = path.read_text(encoding='utf-8')
    original_content = content  # Keep for comparison
    changes_made = 0

    # ─────────────────────────────────────────────────────────────
    # PATCH 1: Add translation import
    # ─────────────────────────────────────────────────────────────
    OLD_IMPORT = "from modules.mappings import PESTICIDE_AR_TO_EN, translate_pesticide"
    NEW_IMPORT = """from modules.mappings import PESTICIDE_AR_TO_EN, translate_pesticide
# Bilingual translation utilities (Arabic ↔ English)
from modules.translation_utils import detect_language, translate_dataframe, get_language_system_prompt"""

    if OLD_IMPORT in content and "translation_utils" not in content:
        content = content.replace(OLD_IMPORT, NEW_IMPORT)
        changes_made += 1
        print("✅ PATCH 1: Translation import added")
    else:
        print("⏭️  PATCH 1: Already applied or import not found")

    # ─────────────────────────────────────────────────────────────
    # PATCH 2: Language detection at start of process_data_query_sql
    # ─────────────────────────────────────────────────────────────
    OLD_PRIORITY1 = "    # ================================================================\n    # PRIORITY 1: Try CoreQueryEngine (Pattern + Intent Router)\n    # Handles 95% of queries with pre-built handlers\n    # ================================================================"
    NEW_PRIORITY1 = """    # === LANGUAGE DETECTION (runs once, used for all results in this function) ===
    query_lang = detect_language(query)
    lang_sql_instruction = get_language_system_prompt(query_lang)

    # ================================================================
    # PRIORITY 1: Try CoreQueryEngine (Pattern + Intent Router)
    # Handles 95% of queries with pre-built handlers
    # ================================================================"""

    if OLD_PRIORITY1 in content and "query_lang = detect_language" not in content:
        content = content.replace(OLD_PRIORITY1, NEW_PRIORITY1)
        changes_made += 1
        print("✅ PATCH 2: Language detection added to process_data_query_sql()")
    else:
        print("⏭️  PATCH 2: Already applied or anchor not found")

    # ─────────────────────────────────────────────────────────────
    # PATCH 3: Translate CoreQueryEngine DataFrame result
    # ─────────────────────────────────────────────────────────────
    OLD_DF = "            # Display the DataFrame\n            st.dataframe(result_df, use_container_width=True)"
    NEW_DF = """            # Display the DataFrame (auto-translated for English queries)
            result_df_display = translate_dataframe(result_df, query_lang)
            st.dataframe(result_df_display, use_container_width=True)"""

    if OLD_DF in content:
        content = content.replace(OLD_DF, NEW_DF)
        changes_made += 1
        print("✅ PATCH 3: CoreQueryEngine result translation added")
    else:
        print("⏭️  PATCH 3: Anchor not found (may already be patched)")

    # ─────────────────────────────────────────────────────────────
    # PATCH 4: Replace static rule 15 with dynamic language instruction
    # ─────────────────────────────────────────────────────────────
    OLD_RULE = """15. LANGUAGE CONSTRAINT: If the user query is in English, you MUST translate
 all data results (including category names like 'عنب' or 'فاصوليا') 
 into English in your final response. Do not provide the answer in Arabic 
 if the question is English."""
    NEW_RULE = "15. {lang_sql_instruction}"

    if OLD_RULE in content:
        content = content.replace(OLD_RULE, NEW_RULE)
        changes_made += 1
        print("✅ PATCH 4: Dynamic language rule injected into SQL prompt")
    else:
        print("⏭️  PATCH 4: Rule not found (may already be patched)")

    # ─────────────────────────────────────────────────────────────
    # PATCH 5: Translate all st.dataframe calls in SQL patterns
    # Pattern: st.dataframe(df, use_container_width=True, hide_index=True)
    # and: st.dataframe(result, use_container_width=True, hide_index=True)
    # ─────────────────────────────────────────────────────────────
    # We use regex to find all st.dataframe() calls in the sql function
    # and wrap their first argument with translate_dataframe()
    
    # Replace in Pattern -2 through Pattern 4 (before the big AI prompt section)
    # We only want to replace inside process_data_query_sql, not process_data_query
    # Strategy: replace patterns that have the hide_index=True (these are in sql function)
    
    old_df_hide = 'st.dataframe(df, use_container_width=True, hide_index=True)'
    new_df_hide = 'st.dataframe(translate_dataframe(df, query_lang), use_container_width=True, hide_index=True)'
    
    count_before = content.count(old_df_hide)
    if count_before > 0:
        content = content.replace(old_df_hide, new_df_hide)
        changes_made += 1
        print(f"✅ PATCH 5a: Translated {count_before} st.dataframe(df, ...) calls")

    old_result_hide = 'st.dataframe(result, use_container_width=True, hide_index=True)'
    new_result_hide = 'st.dataframe(translate_dataframe(result, query_lang), use_container_width=True, hide_index=True)'
    
    count_before = content.count(old_result_hide)
    if count_before > 0:
        content = content.replace(old_result_hide, new_result_hide)
        changes_made += 1
        print(f"✅ PATCH 5b: Translated {count_before} st.dataframe(result, ...) calls")

    # Also handle the detailed_result and distribution_result, pesticide_stats displays
    for var_name in ['detailed_result', 'distribution_result', 'pesticide_stats', 
                     'summary_result', 'classification_result', 'samples_by_failing',
                     'failing_stats', 'result_df']:
        old_call = f'st.dataframe({var_name}, use_container_width=True, hide_index=True)'
        new_call = f'st.dataframe(translate_dataframe({var_name}, query_lang), use_container_width=True, hide_index=True)'
        if old_call in content:
            content = content.replace(old_call, new_call)
            changes_made += 1
            print(f"✅ PATCH 5c: Translated st.dataframe({var_name}, ...)")

    # ─────────────────────────────────────────────────────────────
    # PATCH 6: Add language detection in process_data_query (pandas)
    # ─────────────────────────────────────────────────────────────
    OLD_PANDAS_SPINNER = '    with st.spinner("🔄 Generating analysis code..."):'
    NEW_PANDAS_SPINNER = '''    # Language detection for pandas query engine
    query_lang = detect_language(query)

    with st.spinner("🔄 Generating analysis code..."):'''

    # Only apply in process_data_query (not process_data_query_sql)
    # Find the pandas function specifically
    pandas_func_marker = 'def process_data_query(query: str, df: pd.DataFrame, model, include_risk: bool = False):'
    if pandas_func_marker in content:
        # Find the position of the pandas function
        pandas_start = content.find(pandas_func_marker)
        # Find the spinner within that function
        spinner_in_pandas = content.find(OLD_PANDAS_SPINNER, pandas_start)
        if spinner_in_pandas != -1 and "query_lang = detect_language" not in content[pandas_start:pandas_start+200]:
            content = content[:spinner_in_pandas] + NEW_PANDAS_SPINNER + content[spinner_in_pandas + len(OLD_PANDAS_SPINNER):]
            changes_made += 1
            print("✅ PATCH 6: Language detection added to process_data_query() (pandas)")
        else:
            print("⏭️  PATCH 6: Already applied")
    else:
        print("⏭️  PATCH 6: pandas function marker not found")

    # ─────────────────────────────────────────────────────────────
    # PATCH 7: Translate pandas result before display
    # ─────────────────────────────────────────────────────────────
    OLD_PANDAS_RESULT = '            elif isinstance(result, pd.DataFrame):\n                # Smart metrics display based on result type\n                result_cols = set(result.columns)'
    NEW_PANDAS_RESULT = '''            elif isinstance(result, pd.DataFrame):
                # Auto-translate for English queries
                result = translate_dataframe(result, query_lang)
                # Smart metrics display based on result type
                result_cols = set(result.columns)'''

    if OLD_PANDAS_RESULT in content:
        content = content.replace(OLD_PANDAS_RESULT, NEW_PANDAS_RESULT)
        changes_made += 1
        print("✅ PATCH 7: Pandas result translation added")
    else:
        print("⏭️  PATCH 7: Anchor not found")

    # ─────────────────────────────────────────────────────────────
    # PATCH 8: Translate the final SQL result display
    # (the st.dataframe(result) at the very end of the SQL function)
    # ─────────────────────────────────────────────────────────────
    OLD_FINAL_SQL = '                st.dataframe(result, use_container_width=True)\n                \n                # Download button\n                csv = result.to_csv(index=False)'
    NEW_FINAL_SQL = '''                # Translate for English queries before final display
                result_display = translate_dataframe(result, query_lang)
                st.dataframe(result_display, use_container_width=True)
                
                # Download button
                csv = result.to_csv(index=False)'''

    if OLD_FINAL_SQL in content:
        content = content.replace(OLD_FINAL_SQL, NEW_FINAL_SQL)
        changes_made += 1
        print("✅ PATCH 8: Final SQL result display translation added")
    else:
        print("⏭️  PATCH 8: Anchor not found")

    # ─────────────────────────────────────────────────────────────
    # Write updated file
    # ─────────────────────────────────────────────────────────────
    if changes_made > 0:
        path.write_text(content, encoding='utf-8')
        print(f"\n✅ SUCCESS: Applied {changes_made} patches to {filepath}")
        print(f"   Original backed up to: {backup}")
    else:
        print("\n⚠️  No changes were made. File may already be patched or anchors not found.")
        print("   Check the backup file and apply manually using PATCH_INSTRUCTIONS.txt")

    return changes_made

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python apply_patches.py path/to/modules/ai_assistant.py")
        print("\nExample:")
        print("  python apply_patches.py src/LARS/modules/ai_assistant.py")
        sys.exit(1)
    
    filepath = sys.argv[1]
    changes = apply_all_patches(filepath)
    print(f"\nTotal changes applied: {changes}")