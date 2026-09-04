"""
🔄 LARS Chemistry Data Transformation Script (v2)
===================================================
Transforms packed chemistry data into tidy format for SQL analysis

Fixes:
- Handles "NO CBD" type entries (no contaminant detected)
- Keeps ALL original columns
- Properly handles multiple contaminants per sample

Author: LARS Development Team
Date: 2025-12-14
"""

import duckdb
import pandas as pd
import numpy as np
from pathlib import Path
import re


def transform_chemistry_to_tidy():
    """
    Transform packed chemistry data to tidy format
    Keeps all original columns and properly splits contaminant data
    """
    
    db_path = Path(__file__).parent.parent / 'data' / 'lars_data_demo.duckdb'
    
    print("=" * 60)
    print("🔄 LARS Chemistry Data Transformation (v2)")
    print("=" * 60)
    
    # Check if database exists
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return False
    
    try:
        # Connect to DuckDB
        con = duckdb.connect(str(db_path))
        
        # Step 1: Read the chemistry table
        print("\n📖 Step 1: Reading chemistry table...")
        df = con.execute("SELECT * FROM chemistry").df()
        print(f"   ✅ Loaded {len(df):,} rows, {len(df.columns)} columns")
        
        # Step 2: Identify ALL columns
        print("\n📋 Step 2: Analyzing all columns...")
        all_columns = list(df.columns)
        
        # Identify contaminant columns (ملوث 1-10)
        contaminant_cols = [col for col in all_columns if 'ملوث' in col]
        print(f"   Found {len(contaminant_cols)} contaminant columns")
        
        # All other columns are ID/metadata columns
        id_columns = [col for col in all_columns if col not in contaminant_cols]
        print(f"   Found {len(id_columns)} metadata columns to keep")
        
        # Step 3: Melt the dataframe (wide to long)
        print("\n🔄 Step 3: Melting data (Wide → Long)...")
        df_long = df.melt(
            id_vars=id_columns,
            value_vars=contaminant_cols,
            var_name='contaminant_column',
            value_name='packed_data'
        )
        print(f"   Rows after melt: {len(df_long):,}")
        
        # Step 4: Clean - remove rows with no contaminant data
        print("\n🧹 Step 4: Cleaning empty rows...")
        original_len = len(df_long)
        df_long = df_long.dropna(subset=['packed_data'])
        df_long = df_long[df_long['packed_data'].str.strip() != '']
        print(f"   Removed {original_len - len(df_long):,} empty rows")
        print(f"   Remaining: {len(df_long):,} rows with contaminant data")
        
        # Step 5: Extract contaminant number from column name
        def get_contaminant_number(col_name):
            match = re.search(r'ملوث (\d+)', col_name)
            return int(match.group(1)) if match else 0
        
        df_long['contaminant_number'] = df_long['contaminant_column'].apply(get_contaminant_number)
        
        # Step 6: Parse packed data
        print("\n✂️ Step 5: Parsing packed data...")
        
        def parse_contaminant(packed_string):
            """
            Parse contaminant string into (name, concentration, limit)
            
            Formats:
            - "chlorpyrifos,0.7,0.01" -> (chlorpyrifos, 0.7, 0.01)
            - "NO CBD" -> (NO CBD, None, None) - no contaminant detected
            - "afla b1,0.875,0.004" -> (afla b1, 0.875, 0.004)
            """
            if pd.isna(packed_string) or not packed_string:
                return None, None, None
            
            packed_string = str(packed_string).strip()
            
            # Check if it's a "no contaminant" type entry
            if ',' not in packed_string:
                # Single value like "NO CBD" - means no contaminant detected
                return packed_string, None, None
            
            try:
                # Split by comma
                parts = [p.strip() for p in packed_string.split(',')]
                
                if len(parts) >= 3:
                    # Full format: Name, Conc, Limit
                    name = parts[0]
                    try:
                        conc = float(parts[1])
                    except (ValueError, TypeError):
                        conc = None
                    try:
                        limit_val = float(parts[2])
                    except (ValueError, TypeError):
                        limit_val = None
                    return name, conc, limit_val
                    
                elif len(parts) == 2:
                    # Partial format: Name, Value
                    name = parts[0]
                    try:
                        conc = float(parts[1])
                    except (ValueError, TypeError):
                        conc = None
                    return name, conc, None
                    
                else:
                    return packed_string, None, None
                    
            except Exception as e:
                print(f"   Warning: Could not parse '{packed_string}': {e}")
                return packed_string, None, None
        
        # Apply parsing
        parsed_data = df_long['packed_data'].apply(parse_contaminant)
        df_long['pesticide_name'] = parsed_data.apply(lambda x: x[0])
        df_long['concentration'] = parsed_data.apply(lambda x: x[1])
        df_long['limit_value'] = parsed_data.apply(lambda x: x[2])
        
        # Step 7: Show parsing statistics
        print("\n📊 Step 6: Parsing Statistics:")
        total_entries = len(df_long)
        with_conc = df_long['concentration'].notna().sum()
        without_conc = total_entries - with_conc
        print(f"   Total contaminant entries: {total_entries:,}")
        print(f"   With concentration data: {with_conc:,}")
        print(f"   Without concentration (e.g., 'NO CBD'): {without_conc:,}")
        
        # Step 8: Calculate derived fields
        print("\n📈 Step 7: Calculating derived fields...")
        
        # Exceedance ratio
        df_long['exceedance_ratio'] = np.where(
            (df_long['limit_value'].notna()) & (df_long['limit_value'] > 0),
            df_long['concentration'] / df_long['limit_value'],
            None
        )
        
        # Is compliant (1 = yes, 0 = no)
        df_long['is_compliant'] = np.where(
            df_long['exceedance_ratio'].notna(),
            (df_long['exceedance_ratio'] <= 1).astype(int),
            None
        )
        
        # Is detected (has actual concentration value)
        df_long['is_detected'] = df_long['concentration'].notna().astype(int)
        
        # Step 9: Remove the packed_data column (no longer needed)
        df_long = df_long.drop(columns=['packed_data'])
        
        # Step 10: Reorder columns for better readability
        print("\n🔧 Step 8: Organizing columns...")
        
        # Priority columns first, then the rest
        priority_cols = [
            'كود العينة',
            'التاريخ', 
            'اسم العينة',
            'نوع العينة',
            'نوع الاختبار',
            'الحى',
            'اسم البلدية',
            'pesticide_name',
            'concentration',
            'limit_value',
            'exceedance_ratio',
            'is_compliant',
            'is_detected',
            'contaminant_number'
        ]
        
        # Get columns that exist
        existing_priority = [c for c in priority_cols if c in df_long.columns]
        other_cols = [c for c in df_long.columns if c not in existing_priority]
        final_column_order = existing_priority + other_cols
        
        df_final = df_long[final_column_order]
        
        print(f"   Final dataset: {len(df_final):,} rows, {len(df_final.columns)} columns")
        
        # Step 11: Save to DuckDB
        print("\n💾 Step 9: Saving to DuckDB as 'chemistry_tidy' table...")
        
        con.execute("DROP TABLE IF EXISTS chemistry_tidy")
        con.execute("CREATE TABLE chemistry_tidy AS SELECT * FROM df_final")
        
        # Verify
        count = con.execute("SELECT COUNT(*) FROM chemistry_tidy").fetchone()[0]
        print(f"   ✅ Created 'chemistry_tidy' table with {count:,} rows")
        
        # Step 12: Show sample of properly parsed data
        print("\n📋 Sample of transformed data (with concentration):")
        sample = con.execute("""
            SELECT 
                "اسم العينة" as sample,
                pesticide_name,
                concentration,
                limit_value,
                ROUND(exceedance_ratio, 2) as ratio,
                is_compliant
            FROM chemistry_tidy 
            WHERE concentration IS NOT NULL
            LIMIT 10
        """).df()
        print(sample.to_string())
        
        # Step 13: Show sample of "NO CBD" type entries
        print("\n📋 Sample of 'No Contaminant Detected' entries:")
        sample2 = con.execute("""
            SELECT 
                "اسم العينة" as sample,
                pesticide_name,
                is_detected
            FROM chemistry_tidy 
            WHERE concentration IS NULL
            LIMIT 5
        """).df()
        print(sample2.to_string())
        
        # Step 14: Final Statistics
        print("\n📊 Final Statistics:")
        stats = con.execute("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT "كود العينة") as unique_samples,
                COUNT(DISTINCT pesticide_name) as unique_pesticides,
                SUM(is_detected) as detected_entries,
                SUM(CASE WHEN is_compliant = 1 THEN 1 ELSE 0 END) as compliant,
                SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) as violations
            FROM chemistry_tidy
        """).fetchone()
        
        print(f"   Total Records: {stats[0]:,}")
        print(f"   Unique Samples: {stats[1]:,}")
        print(f"   Unique Pesticides: {stats[2]:,}")
        print(f"   Detected Entries (with concentration): {stats[3]:,}")
        print(f"   Compliant: {stats[4]:,}")
        print(f"   Violations: {stats[5]:,}")
        
        if stats[3] > 0:
            compliance_rate = (stats[4] / (stats[4] + stats[5])) * 100
            print(f"   Compliance Rate: {compliance_rate:.2f}%")
        
        # List all columns in final table
        print("\n📋 All columns in chemistry_tidy table:")
        cols = con.execute("DESCRIBE chemistry_tidy").fetchall()
        for i, (col_name, col_type, *_) in enumerate(cols):
            print(f"   {i+1}. {col_name} ({col_type})")
        
        con.close()
        
        print("\n" + "=" * 60)
        print("🎉 Transformation completed successfully!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Transformation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_queries():
    """Test the transformed table with sample queries"""
    
    db_path = Path(__file__).parent.parent / 'data' / 'lars_data_demo.duckdb'
    
    print("\n🧪 Testing Chemistry_Tidy Queries...")
    print("-" * 40)
    
    con = duckdb.connect(str(db_path), read_only=True)
    
    # Test 1: Samples with multiple pesticides
    print("\n1. Samples with multiple pesticides detected:")
    result = con.execute("""
        SELECT 
            "اسم العينة" as sample,
            COUNT(*) as pesticide_count,
            GROUP_CONCAT(pesticide_name, ' + ') as pesticides
        FROM chemistry_tidy
        WHERE is_detected = 1
        GROUP BY "كود العينة", "اسم العينة"
        HAVING COUNT(*) > 1
        ORDER BY pesticide_count DESC
        LIMIT 10
    """).df()
    print(result.to_string())
    
    # Test 2: Top violations
    print("\n2. Top 10 Violations (highest exceedance ratio):")
    result = con.execute("""
        SELECT 
            "اسم العينة" as sample,
            pesticide_name,
            concentration,
            limit_value,
            ROUND(exceedance_ratio, 2) as ratio
        FROM chemistry_tidy
        WHERE is_compliant = 0
        ORDER BY exceedance_ratio DESC
        LIMIT 10
    """).df()
    print(result.to_string())
    
    # Test 3: Pesticide frequency
    print("\n3. Most Common Pesticides (with actual detections):")
    result = con.execute("""
        SELECT 
            pesticide_name,
            COUNT(*) as count,
            SUM(CASE WHEN is_compliant = 0 THEN 1 ELSE 0 END) as violations
        FROM chemistry_tidy
        WHERE is_detected = 1
        GROUP BY pesticide_name
        ORDER BY count DESC
        LIMIT 10
    """).df()
    print(result.to_string())
    
    con.close()
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="LARS Chemistry Data Transformation v2")
    parser.add_argument('--test', action='store_true', help="Test the transformed table")
    args = parser.parse_args()
    
    if args.test:
        test_queries()
    else:
        success = transform_chemistry_to_tidy()
        if success:
            test_queries()
