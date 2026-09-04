"""
🔄 LARS Database Migration Script
==================================
Converts Excel files to DuckDB database (one-time migration)

Usage:
    python migrate_db.py

This script:
1. Reads the existing Excel file
2. Creates a DuckDB database file (lars_data_demo.duckdb)
3. Creates a 'samples' table with all the data
4. Verifies the migration was successful

Author: LARS Development Team
Date: 2025-12-12
"""

import duckdb
import pandas as pd
from pathlib import Path
import sys

def migrate_excel_to_duckdb(force=False):
    """Convert Excel file to DuckDB database"""
    
    # Configuration (files are in ../data/ folder)
    excel_file = Path(__file__).parent.parent / 'data' / '6_months.xlsx'
    db_file = Path(__file__).parent.parent / 'data' / 'lars_data_demo.duckdb'
    
    print("=" * 60)
    print("🔄 LARS Database Migration: Excel → DuckDB")
    print("=" * 60)
    
    # Check if Excel file exists
    if not excel_file.exists():
        print(f"❌ Error: Excel file not found at {excel_file}")
        sys.exit(1)
    
    print(f"\n📂 Source: {excel_file}")
    print(f"📦 Target: {db_file}")
    
    # Check if database already exists
    if db_file.exists():
        if not force:
            response = input("\n⚠️ Database already exists. Overwrite? (y/n): ")
            if response.lower() != 'y':
                print("❌ Migration cancelled.")
                sys.exit(0)
        db_file.unlink()  # Delete existing file
    
    try:
        # Step 1: Read Excel file
        print("\n📖 Step 1: Reading Excel file...")
        df = pd.read_excel(excel_file)
        print(f"   ✅ Loaded {len(df):,} rows, {len(df.columns)} columns")
        
        # Step 2: Create DuckDB connection (creates file automatically)
        print("\n🗄️ Step 2: Creating DuckDB database...")
        con = duckdb.connect(str(db_file))
        
        # Step 3: Create table and insert data
        print("\n📥 Step 3: Importing data into 'samples' table...")
        con.execute("CREATE TABLE samples AS SELECT * FROM df")
        
        # Step 4: Create indexes for faster queries
        print("\n⚡ Step 4: Creating indexes for better performance...")
        
        # Index on commonly queried columns
        index_columns = [
            'year',
            'vegetable_english',
            'pesticide_standardized',
            'neighborhood_arabic',
            'is_compliant'
        ]
        
        for col in index_columns:
            if col in df.columns:
                try:
                    con.execute(f"CREATE INDEX idx_{col} ON samples({col})")
                    print(f"   ✅ Index created: idx_{col}")
                except Exception as e:
                    print(f"   ⚠️ Could not create index on {col}: {e}")
        
        # Step 5: Verify migration
        print("\n✅ Step 5: Verifying migration...")
        result = con.execute("SELECT COUNT(*) as count FROM samples").fetchone()
        db_count = result[0]
        
        if db_count == len(df):
            print(f"   ✅ Verification passed: {db_count:,} rows in database")
        else:
            print(f"   ⚠️ Warning: Row count mismatch (Excel: {len(df)}, DB: {db_count})")
        
        # Show table schema
        print("\n📋 Table Schema:")
        schema = con.execute("DESCRIBE samples").fetchall()
        for col_name, col_type, *_ in schema:
            print(f"   - {col_name}: {col_type}")
        
        # Close connection
        con.close()
        
        print("\n" + "=" * 60)
        print("🎉 Migration completed successfully!")
        print("=" * 60)
        print(f"\n📦 Database file: {db_file}")
        print(f"📊 Total records: {db_count:,}")
        print(f"💾 File size: {db_file.stat().st_size / 1024:.2f} KB")
        print("\n💡 Next steps:")
        print("   1. Update app.py to use DuckDB")
        print("   2. Test queries with: SELECT * FROM samples LIMIT 10")
        print("   3. Start your Streamlit app")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def migrate_chemistry_sheet():
    """
    Migrate the Chemistry sheet (الكيمياء) from bur_dataset.xlsx to DuckDB
    This adds a 'chemistry' table to the existing database
    """
    
    # Configuration (files are in ../data/ folder)
    excel_file = Path(__file__).parent.parent / 'data' / 'chemistry_translated.xlsx'
    db_file = Path(__file__).parent.parent / 'data' / 'lars_data_demo.duckdb'
    sheet_name = "Chemistry"  # Chemistry sheet in translated dataset
    
    print("=" * 60)
    print("🧪 LARS Chemistry Sheet Migration")
    print("=" * 60)
    
    # Check if Excel file exists
    if not excel_file.exists():
        print(f"❌ Error: Excel file not found at {excel_file}")
        sys.exit(1)
    
    print(f"\n📂 Source: {excel_file}")
    print(f"📄 Sheet: {sheet_name}")
    print(f"📦 Target: {db_file}")
    
    try:
        # Step 1: Read Chemistry sheet from Excel
        print(f"\n📖 Step 1: Reading '{sheet_name}' sheet...")
        df_chemistry = pd.read_excel(excel_file, sheet_name=sheet_name)
        print(f"   ✅ Loaded {len(df_chemistry):,} rows, {len(df_chemistry.columns)} columns")
        
        # Map English columns to original Arabic columns for downstream compatibility
        column_mapping = {
            'sample_code': 'كود العينة',
            'date': 'التاريخ',
            'sample_name': 'اسم العينة',
            'sample_type': 'نوع العينة',
            'sample_classification': 'تصنيف العينة',
            'test_type': 'نوع الاختبار',
            'district': 'الحى',
            'facility_name': 'اسم المنشاة',
            'municipality': 'اسم البلدية',
            'license_number': 'رقم الرخصة',
            'sample_condition': 'حالة العينة',
            'receiver_name': 'اسم المستلم',
            'result': 'ch_tracking.نتيجة العينة\nResult',
        }
        
        # Map contaminant columns
        contaminants = [col for col in df_chemistry.columns if str(col).startswith('contaminant_')]
        for col in contaminants:
            idx = col.split('_')[1]
            column_mapping[col] = f'ملوث {idx}'
            
        df_chemistry = df_chemistry.rename(columns=column_mapping)
        
        # Show columns
        print(f"\n📋 Columns after mapping:")
        for col in df_chemistry.columns:
            print(f"   - {col}")
        
        # Step 2: Connect to existing DuckDB (or create new)
        print("\n🗄️ Step 2: Connecting to DuckDB database...")
        con = duckdb.connect(str(db_file))
        
        # Drop existing chemistry table if exists
        con.execute("DROP TABLE IF EXISTS chemistry")
        
        # Step 3: Create table and insert data
        print("\n📥 Step 3: Creating 'chemistry' table...")
        con.execute("CREATE TABLE chemistry AS SELECT * FROM df_chemistry")
        
        # Step 4: Verify migration
        print("\n✅ Step 4: Verifying migration...")
        result = con.execute("SELECT COUNT(*) as count FROM chemistry").fetchone()
        db_count = result[0]
        
        if db_count == len(df_chemistry):
            print(f"   ✅ Verification passed: {db_count:,} rows in 'chemistry' table")
        else:
            print(f"   ⚠️ Warning: Row count mismatch (Excel: {len(df_chemistry)}, DB: {db_count})")
        
        # Show table schema
        print("\n📋 Chemistry Table Schema:")
        schema = con.execute("DESCRIBE chemistry").fetchall()
        for col_name, col_type, *_ in schema:
            print(f"   - {col_name}: {col_type}")
        
        # Close connection
        con.close()
        
        print("\n" + "=" * 60)
        print("🎉 Chemistry sheet migration completed!")
        print("=" * 60)
        print(f"\n📊 Total records: {db_count:,}")
        print("💡 Query with: SELECT * FROM chemistry LIMIT 10")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def migrate_chemistry_tidy():
    """
    Transform chemistry data into tidy format and save to chemistry_tidy table.
    Each row will represent one pesticide detection per sample.
    IMPORTANT: Includes ALL samples, even those without pesticide detections.
    """
    
    db_file = Path(__file__).parent.parent / 'data' / 'lars_data_demo.duckdb'
    
    print("=" * 60)
    print("🧪 LARS Chemistry Tidy Format Migration")
    print("=" * 60)
    
    if not db_file.exists():
        print(f"❌ Error: Database not found at {db_file}")
        print("   Please run migration first: python migrate_db.py")
        sys.exit(1)
    
    try:
        # Connect to DuckDB
        print("\n🗄️ Step 1: Connecting to DuckDB...")
        con = duckdb.connect(str(db_file))
        
        # Check if chemistry table exists
        try:
            con.execute("SELECT COUNT(*) FROM chemistry").fetchone()
        except:
            print("❌ Chemistry table not found. Run: python migrate_db.py --chemistry")
            return False
        
        # Step 2: Read chemistry data
        print("\n📖 Step 2: Reading chemistry data...")
        df = con.execute("SELECT * FROM chemistry").df()
        print(f"   ✅ Loaded {len(df):,} rows (ALL samples)")
        
        # Step 3: Transform to tidy format
        print("\n🔄 Step 3: Transforming to tidy format...")
        
        # Find pesticide columns dynamically (they contain 'ملوث' in their names)
        pesticide_columns = [col for col in df.columns if 'ملوث' in col]
        print(f"   Found {len(pesticide_columns)} pesticide columns")
        
        import re
        transformed_data = []
        samples_with_detections = set()  # Track which samples have pesticide data
        
        for idx, row in df.iterrows():
            sample_code = row.get('كود العينة', None)
            if pd.isna(sample_code):
                continue
            
            sample_has_data = False  # Track if this sample has any pesticide data
                
            for pesticide_col in pesticide_columns:
                cell_value = row[pesticide_col]
                if pd.notna(cell_value) and str(cell_value).strip() != '':
                    cell_str = str(cell_value).strip()
                    
                    # Extract contaminant number (e.g., "ملوث 1" -> "1")
                    contaminant_match = re.search(r'ملوث\s*(\d+)', pesticide_col)
                    contaminant_num = contaminant_match.group(1) if contaminant_match else '0'
                    
                    # Try to parse the pesticide info using multiple methods
                    pesticide_name = None
                    concentration = None
                    limit_value = None
                    
                    # Method 1: Standard comma-separated format "chlorpyrifos,0.7,0.01"
                    parts = cell_str.split(',')
                    if len(parts) >= 3:
                        pesticide_name = parts[0].strip()
                        try:
                            # Remove parentheses from concentration and limit values
                            conc_str = parts[1].strip().replace('(', '').replace(')', '')
                            limit_str = parts[2].strip().replace('(', '').replace(')', '')
                            concentration = float(conc_str)
                            limit_value = float(limit_str)
                        except (ValueError, TypeError):
                            pass
                    
                    # Method 2: Handle missing comma after name (e.g., "bifenazate0.017,0.01")
                    if concentration is None:
                        # Use regex to extract: name followed by number, comma, number
                        match = re.match(r'^([a-zA-Z\-]+)\s*(\d+\.?\d*)\s*,\s*(\d+\.?\d*)$', cell_str)
                        if match:
                            pesticide_name = match.group(1)
                            try:
                                concentration = float(match.group(2))
                                limit_value = float(match.group(3))
                            except ValueError:
                                pass
                    
                    # Method 3: Handle concatenated numbers (e.g., "bifenazate,0.0440.01")
                    if concentration is None and len(parts) == 2:
                        pesticide_name = parts[0].strip()
                        # Try to split concatenated numbers like "0.0440.01" -> "0.044" and "0.01"
                        num_str = parts[1].strip().replace('(', '').replace(')', '')
                        # Find pattern like X.XXX0.01 (limit is often 0.01)
                        concat_match = re.match(r'^(\d+\.\d+)(0\.\d+)$', num_str)
                        if concat_match:
                            try:
                                concentration = float(concat_match.group(1))
                                limit_value = float(concat_match.group(2))
                            except ValueError:
                                pass
                    
                    # Method 4: Handle malformed concentration like "0.0.25" 
                    if concentration is None and len(parts) >= 3:
                        pesticide_name = parts[0].strip()
                        conc_str = parts[1].strip().replace('(', '').replace(')', '')
                        limit_str = parts[2].strip().replace('(', '').replace(')', '')
                        # Try to extract first valid number from malformed string
                        conc_nums = re.findall(r'\d+\.?\d*', conc_str)
                        limit_nums = re.findall(r'\d+\.?\d*', limit_str)
                        if conc_nums and limit_nums:
                            try:
                                concentration = float(conc_nums[0])
                                limit_value = float(limit_nums[0])
                            except ValueError:
                                pass
                    
                    # If we successfully parsed the data, add the record
                    if pesticide_name and concentration is not None and limit_value is not None:
                        # Get sample result (compliant/non-compliant) from ORIGINAL data
                        sample_result_col = 'ch_tracking.نتيجة العينة\nResult'
                        sample_result = row.get(sample_result_col, None)
                        if pd.isna(sample_result):
                            sample_result = None
                        
                        # Determine is_compliant from original sample_result (lab's judgment)
                        # NOT from concentration vs limit calculation
                        if sample_result:
                            sample_result_lower = str(sample_result).lower()
                            is_compliant = 1 if 'compliant' in sample_result_lower and 'non' not in sample_result_lower else 0
                        else:
                            # Fallback to calculated if no sample_result
                            is_compliant = 1 if concentration <= limit_value else 0
                        
                        transformed_data.append({
                            'كود العينة': sample_code,
                            'التاريخ': row.get('التاريخ', None),
                            'اسم العينة': row.get('اسم العينة', ''),
                            'نوع العينة': row.get('نوع العينة', ''),
                            'تصنيف العينة': row.get('تصنيف العينة', ''),
                            'نوع الاختبار': row.get('نوع الاختبار', ''),
                            'الحى': row.get('الحى', ''),
                            'اسم المنشاة': row.get('اسم المنشاة', ''),
                            'اسم البلدية': row.get('اسم البلدية', ''),
                            'رقم الرخصة': row.get('رقم الرخصة', ''),
                            'حالة العينة': row.get('حالة العينة', ''),
                            'اسم المستلم': row.get('اسم المستلم', ''),
                            'pesticide_name': pesticide_name,
                            'concentration': concentration,
                            'limit_value': limit_value,
                            'exceedance_ratio': concentration / limit_value if limit_value > 0 else 0,
                            'is_above_limit': 1 if concentration > limit_value else 0,  # Calculated from data
                            'is_compliant': is_compliant,  # From lab judgment
                            'contaminant_number': contaminant_num,
                            'is_detected': 1,
                            'sample_result': sample_result
                        })
                        sample_has_data = True
                        samples_with_detections.add(sample_code)
                    else:
                        # Handle "NO CBD" or other non-parseable values
                        if 'NO' in cell_str.upper():
                            sample_result_col = 'ch_tracking.نتيجة العينة\nResult'
                            sample_result = row.get(sample_result_col, None)
                            if pd.isna(sample_result):
                                sample_result = None
                            
                            # Determine is_compliant from original sample_result
                            if sample_result:
                                sample_result_lower = str(sample_result).lower()
                                is_compliant = 1 if 'compliant' in sample_result_lower and 'non' not in sample_result_lower else 0
                            else:
                                is_compliant = 1  # No detection = compliant
                            
                            transformed_data.append({
                                'كود العينة': sample_code,
                                'التاريخ': row.get('التاريخ', None),
                                'اسم العينة': row.get('اسم العينة', ''),
                                'نوع العينة': row.get('نوع العينة', ''),
                                'تصنيف العينة': row.get('تصنيف العينة', ''),
                                'نوع الاختبار': row.get('نوع الاختبار', ''),
                                'الحى': row.get('الحى', ''),
                                'اسم المنشاة': row.get('اسم المنشاة', ''),
                                'اسم البلدية': row.get('اسم البلدية', ''),
                                'رقم الرخصة': row.get('رقم الرخصة', ''),
                                'حالة العينة': row.get('حالة العينة', ''),
                                'اسم المستلم': row.get('اسم المستلم', ''),
                                'pesticide_name': 'NO DETECTION',
                                'concentration': 0,
                                'limit_value': 0,
                                'exceedance_ratio': 0,
                                'is_above_limit': 0,  # No detection = not above limit
                                'is_compliant': is_compliant,
                                'contaminant_number': contaminant_num,
                                'is_detected': 0,
                                'sample_result': sample_result
                            })
                            sample_has_data = True
        
        # IMPORTANT: Add samples that have NO pesticide data at all
        print("   Adding samples without any pesticide data...")
        samples_without_data = 0
        for idx, row in df.iterrows():
            sample_code = row.get('كود العينة', None)
            if pd.isna(sample_code):
                continue
            
            if sample_code not in samples_with_detections:
                # Get sample result for this sample
                sample_result_col = 'ch_tracking.نتيجة العينة\nResult'
                sample_result = row.get(sample_result_col, None)
                if pd.isna(sample_result):
                    sample_result = None
                
                # Determine is_compliant from original sample_result
                if sample_result:
                    sample_result_lower = str(sample_result).lower()
                    is_compliant = 1 if 'compliant' in sample_result_lower and 'non' not in sample_result_lower else 0
                else:
                    is_compliant = 1  # No data = assume compliant
                
                # Add a single row for this sample with no detection
                transformed_data.append({
                    'كود العينة': sample_code,
                    'التاريخ': row.get('التاريخ', None),
                    'اسم العينة': row.get('اسم العينة', ''),
                    'نوع العينة': row.get('نوع العينة', ''),
                    'تصنيف العينة': row.get('تصنيف العينة', ''),
                    'نوع الاختبار': row.get('نوع الاختبار', ''),
                    'الحى': row.get('الحى', ''),
                    'اسم المنشاة': row.get('اسم المنشاة', ''),
                    'اسم البلدية': row.get('اسم البلدية', ''),
                    'رقم الرخصة': row.get('رقم الرخصة', ''),
                    'حالة العينة': row.get('حالة العينة', ''),
                    'اسم المستلم': row.get('اسم المستلم', ''),
                    'pesticide_name': 'NO DATA',
                    'concentration': 0,
                    'limit_value': 0,
                    'exceedance_ratio': 0,
                    'is_above_limit': 0,  # No data = not above limit
                    'is_compliant': is_compliant,
                    'contaminant_number': '0',
                    'is_detected': 0,
                    'sample_result': sample_result
                })
                samples_without_data += 1
        
        print(f"   ✅ Added {samples_without_data} samples that had no pesticide data")
        
        df_tidy = pd.DataFrame(transformed_data)
        print(f"   ✅ Transformed to {len(df_tidy):,} records total")
        
        # Step 4: Save to DuckDB
        print("\n📥 Step 4: Creating 'chemistry_tidy' table...")
        con.execute("DROP TABLE IF EXISTS chemistry_tidy")
        con.execute("CREATE TABLE chemistry_tidy AS SELECT * FROM df_tidy")
        
        # Step 5: Create indexes
        print("\n⚡ Step 5: Creating indexes...")
        try:
            con.execute("CREATE INDEX idx_tidy_sample ON chemistry_tidy(\"كود العينة\")")
            con.execute("CREATE INDEX idx_tidy_pesticide ON chemistry_tidy(pesticide_name)")
            con.execute("CREATE INDEX idx_tidy_compliant ON chemistry_tidy(is_compliant)")
            print("   ✅ Indexes created")
        except Exception as e:
            print(f"   ⚠️ Could not create some indexes: {e}")
        
        # Step 6: Verify
        print("\n✅ Step 6: Verifying migration...")
        result = con.execute("SELECT COUNT(*) FROM chemistry_tidy").fetchone()
        print(f"   ✅ Total records: {result[0]:,}")
        
        unique_samples = con.execute("SELECT COUNT(DISTINCT \"كود العينة\") FROM chemistry_tidy").fetchone()
        print(f"   📊 Unique samples: {unique_samples[0]:,}")
        
        pesticide_count = con.execute("SELECT COUNT(DISTINCT pesticide_name) FROM chemistry_tidy WHERE is_detected = 1").fetchone()
        print(f"   🧪 Unique pesticides: {pesticide_count[0]:,}")
        
        # Show schema
        print("\n📋 chemistry_tidy Table Schema:")
        schema = con.execute("DESCRIBE chemistry_tidy").fetchall()
        for col_name, col_type, *_ in schema:
            print(f"   - {col_name}: {col_type}")
        
        con.close()
        
        print("\n" + "=" * 60)
        print("🎉 Chemistry Tidy migration completed!")
        print("=" * 60)
        print("\n💡 Query examples:")
        print('   SELECT * FROM chemistry_tidy WHERE pesticide_name = \'chlorpyrifos\'')
        print("   SELECT \"كود العينة\", COUNT(*) FROM chemistry_tidy WHERE is_detected = 1 GROUP BY \"كود العينة\" HAVING COUNT(*) = 2")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database():
    """Test the database with sample queries"""
    
    db_file = Path(__file__).parent.parent / 'data' / 'lars_data_demo.duckdb'
    
    if not db_file.exists():
        print("❌ Database not found. Run migration first.")
        return
    
    print("\n🧪 Testing Database Queries...")
    print("-" * 40)
    
    con = duckdb.connect(str(db_file), read_only=True)
    
    # Test queries for samples table
    tests = [
        ("Total samples records", "SELECT COUNT(*) FROM samples"),
        ("Unique vegetables", "SELECT COUNT(DISTINCT vegetable_english) FROM samples"),
        ("Unique pesticides", "SELECT COUNT(DISTINCT pesticide_standardized) FROM samples"),
        ("Compliance rate", "SELECT ROUND(AVG(is_compliant) * 100, 2) as rate FROM samples"),
        ("Records by year", "SELECT year, COUNT(*) as count FROM samples GROUP BY year ORDER BY year"),
    ]
    
    for name, query in tests:
        try:
            result = con.execute(query).fetchall()
            print(f"✅ {name}: {result}")
        except Exception as e:
            print(f"❌ {name}: {e}")
    
    # Test chemistry table if exists
    print("\n🧪 Testing Chemistry Table...")
    print("-" * 40)
    try:
        result = con.execute("SELECT COUNT(*) FROM chemistry").fetchone()
        print(f"✅ Total chemistry records: {result[0]}")
        
        # Show sample result columns
        result = con.execute("SELECT \"نوع العينة\", \"نوع الاختبار\", COUNT(*) as count FROM chemistry GROUP BY \"نوع العينة\", \"نوع الاختبار\" LIMIT 5").fetchall()
        print(f"✅ Sample types and tests: {result}")
    except Exception as e:
        print(f"⚠️ Chemistry table not found or error: {e}")
    
    con.close()
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="LARS Database Migration Tool")
    parser.add_argument('--test', action='store_true', help="Test existing database")
    parser.add_argument('--chemistry', action='store_true', help="Migrate Chemistry sheet (الكيمياء) from bur_dataset.xlsx")
    parser.add_argument('--tidy', action='store_true', help="Transform chemistry data to tidy format (one row per pesticide)")
    parser.add_argument('--all', action='store_true', help="Migrate all data sources (samples + chemistry + tidy)")
    parser.add_argument('-y', '--force', action='store_true', help="Force overwrite of existing database without confirmation")
    args = parser.parse_args()
    
    if args.test:
        test_database()
    elif args.chemistry:
        migrate_chemistry_sheet()
    elif args.tidy:
        migrate_chemistry_tidy()
    elif args.all:
        migrate_excel_to_duckdb(force=args.force)
        migrate_chemistry_sheet()
        migrate_chemistry_tidy()
    else:
        migrate_excel_to_duckdb(force=args.force)

