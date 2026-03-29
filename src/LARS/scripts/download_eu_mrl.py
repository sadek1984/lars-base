#!/usr/bin/env python3
"""
EU MRL Data Downloader and Parser

Downloads MRL (Maximum Residue Level) data from the EU Pesticides Database
and creates a local lookup table for fast queries.

The EU provides 8 XML files split alphabetically by pesticide name.
This script downloads, parses, and stores them in a SQLite/DuckDB database.

Usage:
    python download_eu_mrl.py          # Download and update MRL data
    python download_eu_mrl.py --check  # Check if update needed

Author: LARS Team
"""

import os
import sys
import json
import sqlite3
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import argparse

# EU MRL XML Download URLs
EU_MRL_XML_URLS = {
    "1-B": "https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/backend/api/mrl/download/link?filename=Publication1.xml",
    "C": "https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/backend/api/mrl/download/link?filename=Publication2.xml",
    "D-E": "https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/backend/api/mrl/download/link?filename=Publication3.xml",
    "F": "https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/backend/api/mrl/download/link?filename=Publication4.xml",
    "G-L": "https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/backend/api/mrl/download/link?filename=Publication5.xml",
    "M-O": "https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/backend/api/mrl/download/link?filename=Publication6.xml",
    "P-Q": "https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/backend/api/mrl/download/link?filename=Publication7.xml",
    "R-Z": "https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/backend/api/mrl/download/link?filename=Publication8.xml",
}

# Script directory
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "eu_mrl_data"
DB_PATH = DATA_DIR / "eu_mrl.db"
METADATA_PATH = DATA_DIR / "metadata.json"


def ensure_data_dir():
    """Create data directory if it doesn't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def download_xml_file(url: str, range_name: str) -> Optional[str]:
    """Download a single XML file from EU database."""
    print(f"  Downloading {range_name}...", end=" ", flush=True)
    try:
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        
        file_path = DATA_DIR / f"mrl_{range_name.replace('-', '_')}.xml"
        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        size_kb = len(response.content) / 1024
        print(f"✅ ({size_kb:.1f} KB)")
        return str(file_path)
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def download_all_xml_files() -> List[str]:
    """Download all EU MRL XML files."""
    print("\n📥 Downloading EU MRL XML files...")
    
    downloaded_files = []
    for range_name, url in EU_MRL_XML_URLS.items():
        file_path = download_xml_file(url, range_name)
        if file_path:
            downloaded_files.append(file_path)
    
    print(f"\n✅ Downloaded {len(downloaded_files)}/{len(EU_MRL_XML_URLS)} files")
    return downloaded_files


def parse_xml_file(file_path: str) -> List[Dict]:
    """Parse a single EU MRL XML file and extract MRL data."""
    records = []
    
    try:
        # Parse the XML file
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # EU MRL XML structure:
        # <Pesticides>
        #   <Substances>
        #     <Name>Pesticide Name</Name>
        #     <Pest_res_id>...</Pest_res_id>
        #     <Product>
        #       <Product_name>...</Product_name>
        #       <Product_code>...</Product_code>
        #       <MRL>0.01*</MRL>
        #     </Product>
        #     ... more products ...
        #   </Substances>
        #   ... more substances ...
        # </Pesticides>
        
        current_pesticide = None
        
        for elem in root.iter():
            tag = elem.tag
            
            # Found a new substance/pesticide
            if tag == 'Name' and elem.text:
                current_pesticide = elem.text.strip()
            
            # Found a product with MRL
            elif tag == 'Product' and current_pesticide:
                product_name = None
                product_code = None
                mrl_value = None
                is_loq = False
                
                for child in elem:
                    if child.tag == 'Product_name' and child.text:
                        product_name = child.text.strip()
                    elif child.tag == 'Product_code' and child.text:
                        product_code = child.text.strip()
                    elif child.tag == 'MRL' and child.text:
                        mrl_text = child.text.strip()
                        # Check if it's at LOQ (marked with *)
                        is_loq = '*' in mrl_text
                        try:
                            mrl_value = float(mrl_text.replace('*', ''))
                        except ValueError:
                            mrl_value = mrl_text
                
                if product_name and mrl_value is not None:
                    records.append({
                        'pesticide': current_pesticide,
                        'product': product_name,
                        'product_code': product_code,
                        'mrl': mrl_value,
                        'is_loq': is_loq
                    })
    
    except Exception as e:
        print(f"  ⚠️ Error parsing {file_path}: {e}")
    
    return records



def create_database():
    """Create SQLite database for MRL data."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Create MRL table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eu_mrl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pesticide TEXT NOT NULL,
            pesticide_lower TEXT NOT NULL,
            product TEXT NOT NULL,
            product_lower TEXT NOT NULL,
            mrl_value REAL,
            mrl_text TEXT,
            is_loq BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create indexes for fast lookup
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pesticide ON eu_mrl(pesticide_lower)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_product ON eu_mrl(product_lower)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pest_prod ON eu_mrl(pesticide_lower, product_lower)')
    
    conn.commit()
    return conn


def insert_records(conn: sqlite3.Connection, records: List[Dict]):
    """Insert MRL records into database."""
    cursor = conn.cursor()
    
    for record in records:
        pesticide = record.get('pesticide', '')
        product = record.get('product', '')
        mrl = record.get('mrl')
        is_loq = record.get('is_loq', False)
        
        mrl_value = float(mrl) if isinstance(mrl, (int, float)) else None
        mrl_text = str(mrl) if mrl else None
        
        cursor.execute('''
            INSERT INTO eu_mrl (pesticide, pesticide_lower, product, product_lower, mrl_value, mrl_text, is_loq)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (pesticide, pesticide.lower(), product, product.lower(), mrl_value, mrl_text, is_loq))
    
    conn.commit()


def update_metadata():
    """Save download metadata."""
    metadata = {
        'last_updated': datetime.now().isoformat(),
        'source': 'EU Pesticides Database',
        'source_url': 'https://ec.europa.eu/food/plant/pesticides/eu-pesticides-database/start/screen/mrls/download',
        'files_count': len(EU_MRL_XML_URLS)
    }
    
    with open(METADATA_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    return metadata


def get_last_update() -> Optional[datetime]:
    """Get the last update timestamp."""
    try:
        with open(METADATA_PATH, 'r') as f:
            metadata = json.load(f)
            return datetime.fromisoformat(metadata['last_updated'])
    except:
        return None


def lookup_mrl(pesticide: str, product: Optional[str] = None) -> List[Dict]:
    """
    Look up MRL for a pesticide (and optionally product).
    
    Parameters:
        pesticide: Pesticide name (case-insensitive)
        product: Optional product/commodity name (case-insensitive)
    
    Returns:
        List of matching MRL records
    """
    if not DB_PATH.exists():
        return []
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if product:
        cursor.execute('''
            SELECT pesticide, product, mrl_value, mrl_text, is_loq
            FROM eu_mrl
            WHERE pesticide_lower LIKE ? AND product_lower LIKE ?
            LIMIT 100
        ''', (f'%{pesticide.lower()}%', f'%{product.lower()}%'))
    else:
        cursor.execute('''
            SELECT pesticide, product, mrl_value, mrl_text, is_loq
            FROM eu_mrl
            WHERE pesticide_lower LIKE ?
            LIMIT 100
        ''', (f'%{pesticide.lower()}%',))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(description='Download and manage EU MRL data')
    parser.add_argument('--check', action='store_true', help='Check last update time')
    parser.add_argument('--lookup', type=str, help='Look up MRL for a pesticide')
    parser.add_argument('--product', type=str, help='Filter by product (use with --lookup)')
    args = parser.parse_args()
    
    if args.check:
        last_update = get_last_update()
        if last_update:
            print(f"📅 Last updated: {last_update.strftime('%Y-%m-%d %H:%M:%S')}")
            days_ago = (datetime.now() - last_update).days
            print(f"   ({days_ago} days ago)")
        else:
            print("❌ No data found. Run without --check to download.")
        return
    
    if args.lookup:
        results = lookup_mrl(args.lookup, args.product)
        if results:
            print(f"\n🔍 Found {len(results)} MRL entries for '{args.lookup}':")
            for r in results[:20]:
                mrl = r['mrl_value'] if r['mrl_value'] else r['mrl_text']
                loq = " (LOQ)" if r['is_loq'] else ""
                print(f"  • {r['product']}: {mrl} mg/kg{loq}")
            if len(results) > 20:
                print(f"  ... and {len(results) - 20} more")
        else:
            print(f"❌ No MRL data found for '{args.lookup}'")
        return
    
    # Full download and update
    print("🇪🇺 EU MRL Data Downloader")
    print("=" * 50)
    
    ensure_data_dir()
    
    # Download XML files
    xml_files = download_all_xml_files()
    
    if not xml_files:
        print("❌ No files downloaded. Exiting.")
        return 1
    
    # Parse and insert into database
    print("\n📊 Parsing XML files...")
    
    # Remove old database
    if DB_PATH.exists():
        DB_PATH.unlink()
    
    conn = create_database()
    total_records = 0
    
    for xml_file in xml_files:
        print(f"  Parsing {Path(xml_file).name}...", end=" ", flush=True)
        records = parse_xml_file(xml_file)
        if records:
            insert_records(conn, records)
            total_records += len(records)
            print(f"✅ {len(records)} records")
        else:
            print("⚠️ No records extracted")
    
    conn.close()
    
    # Update metadata
    metadata = update_metadata()
    
    print("\n" + "=" * 50)
    print(f"✅ Done! Database created at: {DB_PATH}")
    print(f"   Total records: {total_records}")
    print(f"   Last updated: {metadata['last_updated']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
