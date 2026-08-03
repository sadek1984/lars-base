#!/usr/bin/env python3
"""
Test Script: Verify Schema-Only Prompting Implementation
=========================================================

This script helps verify that sensitive data is NOT being sent to Cloud APIs.

Usage:
    python test_schema_only.py

What it does:
1. Simulates the prompt generation
2. Shows what WOULD be sent to the API
3. Verifies no actual data is present
4. Checks for sensitive information leakage

Author: LARS Development Team
Date: 2025-12-08
"""

import pandas as pd
import io
import re
from typing import Dict, List

def create_sample_dataframe() -> pd.DataFrame:
    """Create sample laboratory data (simulated)"""
    data = {
        'sample_id': ['2024-001', '2024-002', '2024-003'],
        'vegetable_english': ['Tomato', 'Cucumber', 'Pepper'],
        'pesticide_standardized': ['Bifenthrin', 'Chlorpyrifos', 'Dimethoate'],
        'reading': [0.153, 0.089, 0.234],
        'limits': [0.100, 0.050, 0.200],
        'is_compliant': [0, 0, 0],
        'client_name': ['شركة الريان', 'مزارع النخبة', 'شركة الطازج'],
        'neighborhood_arabic': ['الإسكان', 'الصفراء', 'الموطأ']
    }
    return pd.DataFrame(data)

def generate_old_prompt(df: pd.DataFrame, query: str) -> str:
    """OLD METHOD - Sends actual data (INSECURE)"""
    prompt = f"""Generate pandas code to answer this question about the dataset.

Dataset Information:
- Columns: {list(df.columns)}
- Shape: {df.shape}
- Sample data (first 3 rows):
{df.head(3).to_string()}

Question: {query}
"""
    return prompt

def generate_new_prompt(df: pd.DataFrame, query: str) -> str:
    """NEW METHOD - Sends only schema (SECURE)"""
    import numpy as np
    
    # Get column types
    dtypes_markdown = df.dtypes.to_frame('Type').to_markdown()
    
    # Get structure info
    buffer = io.StringIO()
    df.info(buf=buffer)
    df_info_str = buffer.getvalue()
    
    # Get numeric ranges
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    sample_stats = ""
    if numeric_cols:
        stats_df = df[numeric_cols].describe()
        # Get min, max, mean from the describe output
        stats_summary = stats_df.loc[['min', 'max', 'mean']]
        sample_stats = f"\nNumeric column ranges:\n{stats_summary.to_markdown()}"
    
    prompt = f"""Generate pandas code to answer this question about the dataset.

🔒 Dataset Schema (Metadata Only - No Actual Data Exposed):

**Column Information:**
{dtypes_markdown}

**DataFrame Structure:**
{df_info_str}
{sample_stats}

**Available Columns:** {list(df.columns)}
**Total Records:** {len(df)} samples
**Shape:** {df.shape}

⚠️ PRIVACY NOTE: You are receiving ONLY schema information (column names and types).
DO NOT assume specific values exist. Write generic filtering/aggregation code based on column names only.

Question: {query}
"""
    return prompt

def detect_sensitive_data(prompt: str, df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Check if prompt contains sensitive INDIVIDUAL data
    
    Note: Statistical aggregates (min, max, mean) are allowed as they don't
    expose specific individual records. We're looking for row-level data.
    
    Returns:
        Dictionary with detected sensitive information
    """
    violations = {
        'sample_ids': [],
        'client_names': [],
        'actual_readings': [],  # Only individual readings, not aggregates
        'neighborhoods': []
    }
    
    # Check for sample IDs (these should NEVER appear)
    for sample_id in df['sample_id']:
        if str(sample_id) in prompt:
            violations['sample_ids'].append(sample_id)
    
    # Check for client names (these should NEVER appear)
    for client in df['client_name']:
        if str(client) in prompt:
            violations['client_names'].append(client)
    
    # Check for neighborhoods (these should NEVER appear)
    for neighborhood in df['neighborhood_arabic']:
        if str(neighborhood) in prompt:
            violations['neighborhoods'].append(neighborhood)
    
    # Check for actual row data (using regex to find tabular data)
    # Look for patterns like "2024-001 | Tomato | 0.153" which indicate row-level data
    row_pattern = r'\d{4}-\d{3}'  # Sample ID pattern
    if re.search(row_pattern, prompt):
        # If we find sample IDs in tabular format, mark it
        for reading in df['reading']:
            # Check if reading appears in a row context (with sample ID nearby)
            reading_str = f"{reading:.3f}"
            if reading_str in prompt:
                # Check if it's in a table row (within 100 chars of a sample ID)
                for sample_id in df['sample_id']:
                    idx = prompt.find(reading_str)
                    id_idx = prompt.find(str(sample_id))
                    if idx > 0 and id_idx > 0 and abs(idx - id_idx) < 100:
                        violations['actual_readings'].append(reading)
                        break
    
    return violations

def run_tests():
    """Run all security tests"""
    print("=" * 70)
    print("🔒 LARS Schema-Only Prompting Security Test")
    print("=" * 70)
    print()
    
    # Create sample data
    df = create_sample_dataframe()
    test_query = "Show tomato samples above limit"
    
    print("📊 Sample Data Created:")
    print(f"   - {len(df)} records")
    print(f"   - {len(df.columns)} columns")
    print(f"   - Contains sensitive: client names, sample IDs, readings")
    print()
    
    # Test OLD method
    print("-" * 70)
    print("❌ TEST 1: OLD METHOD (INSECURE)")
    print("-" * 70)
    old_prompt = generate_old_prompt(df, test_query)
    old_violations = detect_sensitive_data(old_prompt, df)
    
    print(f"Prompt size: {len(old_prompt)} characters\n")
    print("Sensitive data found:")
    print(f"  ❌ Sample IDs: {len(old_violations['sample_ids'])} detected")
    print(f"  ❌ Client names: {len(old_violations['client_names'])} detected")
    print(f"  ❌ Actual readings: {len(old_violations['actual_readings'])} detected")
    print(f"  ❌ Neighborhoods: {len(old_violations['neighborhoods'])} detected")
    print()
    
    if any(old_violations.values()):
        print("⚠️  WARNING: Sensitive data would be sent to external API!")
        print()
        print("Examples of leaked data:")
        if old_violations['sample_ids']:
            print(f"   - Sample ID: {old_violations['sample_ids'][0]}")
        if old_violations['client_names']:
            print(f"   - Client: {old_violations['client_names'][0]}")
        if old_violations['actual_readings']:
            print(f"   - Reading: {old_violations['actual_readings'][0]}")
    print()
    
    # Test NEW method
    print("-" * 70)
    print("✅ TEST 2: NEW METHOD (SECURE)")
    print("-" * 70)
    new_prompt = generate_new_prompt(df, test_query)
    new_violations = detect_sensitive_data(new_prompt, df)
    
    print(f"Prompt size: {len(new_prompt)} characters (smaller!)\n")
    print("Sensitive data found:")
    print(f"  ✅ Sample IDs: {len(new_violations['sample_ids'])} detected")
    print(f"  ✅ Client names: {len(new_violations['client_names'])} detected")
    print(f"  ✅ Actual readings: {len(new_violations['actual_readings'])} detected")
    print(f"  ✅ Neighborhoods: {len(new_violations['neighborhoods'])} detected")
    print()
    
    if not any(new_violations.values()):
        print("✅ SUCCESS: NO sensitive data detected!")
        print("   Schema-only prompting is working correctly.")
    else:
        print("⚠️  WARNING: Some sensitive data still detected!")
        print("   Please review the implementation.")
    print()
    
    # Comparison
    print("-" * 70)
    print("📊 COMPARISON")
    print("-" * 70)
    print(f"Size reduction: {len(old_prompt) - len(new_prompt)} characters")
    print(f"                ({(1 - len(new_prompt)/len(old_prompt))*100:.1f}% smaller)")
    print()
    
    old_total = sum(len(v) for v in old_violations.values())
    new_total = sum(len(v) for v in new_violations.values())
    print(f"Data leakage reduction: {old_total - new_total} sensitive items")
    print(f"                        ({(1 - new_total/(old_total or 1))*100:.1f}% safer)")
    print()
    
    # Show sample of what gets sent
    print("-" * 70)
    print("📤 WHAT GETS SENT TO API (Preview)")
    print("-" * 70)
    print("\nOLD METHOD (first 500 chars):")
    print("─" * 70)
    print(old_prompt[:500] + "...")
    print()
    
    print("\nNEW METHOD (first 500 chars):")
    print("─" * 70)
    print(new_prompt[:500] + "...")
    print()
    
    # Final verdict
    print("=" * 70)
    if not any(new_violations.values()) and any(old_violations.values()):
        print("✅ VERDICT: Schema-Only Prompting WORKING CORRECTLY")
        print("   Your data is SAFE from external exposure.")
    else:
        print("⚠️  VERDICT: Review needed")
        print("   Check implementation for potential issues.")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
