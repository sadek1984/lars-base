#!/usr/bin/env python3
"""
🔍 LARS Database Inspector
Quick tool to view DuckDB database contents

Usage:
    python check_db.py              # Show last 5 rows
    python check_db.py --count      # Show total count
    python check_db.py --all        # Show all summary stats
"""

import duckdb
from pathlib import Path
import argparse

def main():
    parser = argparse.ArgumentParser(description="LARS Database Inspector")
    parser.add_argument('--count', action='store_true', help="Show total record count")
    parser.add_argument('--all', action='store_true', help="Show all summary statistics")
    parser.add_argument('--rows', type=int, default=5, help="Number of rows to display")
    args = parser.parse_args()
    
    db_path = Path(__file__).parent.parent / 'data' / 'lars_data_demo.duckdb'
    
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return
    
    con = duckdb.connect(str(db_path), read_only=True)
    
    print("=" * 60)
    print("🗄️ LARS DuckDB Database Inspector")
    print("=" * 60)
    print(f"📁 Database: {db_path}")
    
    # Total count
    total = con.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    print(f"📊 Total Records: {total:,}")
    
    if args.all:
        # Show more stats
        print("\n📈 Summary Statistics:")
        
        # By year
        print("\n  By Year:")
        years = con.execute("""
            SELECT CAST(year AS INTEGER) as year, COUNT(*) as count 
            FROM samples 
            GROUP BY year 
            ORDER BY year
        """).fetchall()
        for year, count in years:
            print(f"    {year}: {count} samples")
        
        # Compliance rate
        compliance = con.execute("""
            SELECT 
                ROUND(AVG(is_compliant) * 100, 2) as rate
            FROM samples
        """).fetchone()[0]
        print(f"\n  ✅ Compliance Rate: {compliance}%")
        
        # Top vegetables
        print("\n  Top 5 Vegetables:")
        vegs = con.execute("""
            SELECT vegetable_arabic, COUNT(*) as count 
            FROM samples 
            GROUP BY vegetable_arabic 
            ORDER BY count DESC 
            LIMIT 5
        """).fetchall()
        for veg, count in vegs:
            print(f"    {veg}: {count}")
    
    if not args.count:
        # Show last N rows
        print(f"\n📋 Last {args.rows} Rows:")
        print("-" * 60)
        
        result = con.execute(f"""
            SELECT 
                vegetable_arabic as الخضار,
                pesticide_standardized as المبيد,
                reading as القراءة,
                limits as الحد,
                result as النتيجة,
                CAST(document_date AS DATE) as التاريخ
            FROM samples
            ORDER BY ROWID DESC
            LIMIT {args.rows}
        """).df()
        
        print(result.to_string(index=True))
    
    con.close()
    print("\n" + "=" * 60)
    print("✅ Database check complete!")

if __name__ == "__main__":
    main()
