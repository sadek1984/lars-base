import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'src', 'LARS')))

from modules.core_query_engine import CoreQueryEngine

def main():
    engine = CoreQueryEngine(enable_llm_fallback=False)
    
    test_queries = [
        "Search for fipronil in beans",
        "What pesticides are in cucumber?",
        "How many non-compliant cherry tomato samples?",
        "How many tomato samples are above limit?",
        "Pesticides in al iskan",
        "Neighborhood ranking by violations",
        "How many samples of sweet pepper with 2 pesticides?",
    ]
    
    for q in test_queries:
        print(f"\n{'='*60}\nQuery: {q}")
        text, df = engine.process(q)
        # Check for Arabic text in the response
        has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
        arabic_flag = " ⚠️ ARABIC DETECTED" if has_arabic else " ✅ English only"
        print(f"[{arabic_flag}]")
        print(f"\nResponse:\n{text[:400]}\n")

if __name__ == "__main__":
    main()
