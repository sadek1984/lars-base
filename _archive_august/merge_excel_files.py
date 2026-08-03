import pandas as pd
from pathlib import Path
import re
import sys
from datetime import datetime
from typing import Optional

# Add the 'src' directory to the Python path
sys.path.append('src')

try:
    from src.utils.data_cleaning import load_and_prepare_excel
except ImportError:
    print("Error: Could not import 'load_and_prepare_excel'.")
    print("Please ensure this script is run from the root directory of your 'my-mini-rag' project.")
    sys.exit(1)

# --- CONFIGURATION ---
DATA_DIRECTORY = Path("./src/data")
YEARS = ["2022", "2023", "2024", "2025"]
MONTHS = ["Jan", "Feb", "March", "April", "May", "June",
          "July", "Aug", "Sep", "Oct", "Nov", "Dec"]

# --- UPDATED ROBUST FUNCTION TO EXTRACT THE CORRECT GREGORIAN DATE ---

def extract_gregorian_date_from_excel(file_path: str) -> Optional[str]:
    """
    Scans the top 20 rows of an Excel file to find the Gregorian date associated with
    "التاريخ الميلاد" or "AD date", ensuring we get the correct date and not the Hijri date.
    """
    try:
        df_raw = pd.read_excel(file_path, header=None, nrows=20, engine='openpyxl')
        
        # Enhanced date pattern to capture various formats
        date_pattern = re.compile(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b')
        
        # Multiple possible markers for Gregorian date
        gregorian_markers = [
            "التاريخ الميلاد",    # As shown in your image
            "التاريخ الميلادي",   # Alternative spelling
            "AD date",           # English marker
            "التاريخ الميلادى"    # Another alternative
        ]

        for _, row in df_raw.iterrows():
            row_list = row.tolist()
            
            # Convert row to a single string for easier parsing
            row_text = ' '.join([str(cell) for cell in row_list if pd.notna(cell)])
            
            # Look for Gregorian date markers
            for marker in gregorian_markers:
                if marker in row_text:
                    print(f"      -> Found marker '{marker}' in row")
                    
                    # Method 1: Extract date that comes AFTER the Gregorian marker
                    marker_pos = row_text.find(marker)
                    if marker_pos != -1:
                        # Get text after the marker
                        text_after_marker = row_text[marker_pos + len(marker):]
                        
                        # Find the first date in the text after the marker
                        match = date_pattern.search(text_after_marker)
                        if match:
                            extracted_date = match.group(0)
                            print(f"      -> Extracted date after '{marker}': {extracted_date}")
                            return extracted_date
                    
                    # Method 2: If the above didn't work, look for "AD date" specifically
                    if "AD date" in row_text:
                        # Find date near "AD date"
                        ad_pos = row_text.find("AD date")
                        # Look in a window around "AD date"
                        window_start = max(0, ad_pos - 50)
                        window_end = min(len(row_text), ad_pos + 50)
                        window_text = row_text[window_start:window_end]
                        
                        dates_in_window = date_pattern.findall(window_text)
                        if dates_in_window:
                            # Take the date closest to "AD date"
                            extracted_date = dates_in_window[-1]  # Usually the last one
                            print(f"      -> Extracted AD date: {extracted_date}")
                            return extracted_date
            
            # Method 3: If we found both Hijri and Gregorian markers, extract the right date
            if "التاريخ الهجري" in row_text and any(marker in row_text for marker in gregorian_markers):
                print(f"      -> Found both Hijri and Gregorian dates in same row")
                
                # Split by common separators and analyze each part
                parts = re.split(r'(التاريخ الهجري|التاريخ الميلاد|التاريخ الميلادي|Hijri date|AD date)', row_text)
                
                for i, part in enumerate(parts):
                    if any(marker in part for marker in gregorian_markers) or "AD date" in part:
                        # Look for date in this part and the next part
                        search_text = part
                        if i + 1 < len(parts):
                            search_text += " " + parts[i + 1]
                        
                        match = date_pattern.search(search_text)
                        if match:
                            extracted_date = match.group(0)
                            # Validate it's not a Hijri date (Hijri years are typically 14xx)
                            if not extracted_date.endswith(('/14', '/1400', '/1401', '/1402', '/1403', '/1404', '/1405', '/1406', '/1407', '/1408', '/1409')):
                                print(f"      -> Extracted Gregorian date: {extracted_date}")
                                return extracted_date
            
            # Method 4: Check individual cells for datetime objects (Excel parsed dates)
            for i, cell in enumerate(row_list):
                if isinstance(cell, datetime):
                    # Check if this datetime is near a Gregorian marker
                    context_cells = row_list[max(0, i-2):i+3]  # Check surrounding cells
                    context_text = ' '.join([str(c) for c in context_cells if pd.notna(c)])
                    
                    if any(marker in context_text for marker in gregorian_markers) or "AD" in context_text:
                        formatted_date = cell.strftime('%Y-%m-%d')
                        print(f"      -> Found datetime object for Gregorian date: {formatted_date}")
                        return formatted_date

    except Exception as e:
        print(f"      -> Warning: Could not scan for date in {Path(file_path).name}: {e}")
    
    return None

def validate_gregorian_date(date_str: str) -> bool:
    """
    Validate that the extracted date is likely a Gregorian date and not Hijri.
    Hijri dates in this context would typically be 1440s, while Gregorian would be 2020s.
    """
    try:
        # Parse the date
        parsed_date = pd.to_datetime(date_str, dayfirst=True, errors='coerce')
        if pd.isna(parsed_date):
            return False
        
        year = parsed_date.year
        
        # Check if year is in reasonable Gregorian range for pesticide testing data
        if 2020 <= year <= 2030:
            return True
        elif 1440 <= year <= 1450:  # Likely Hijri year
            print(f"      -> Warning: Date {date_str} appears to be Hijri (year {year}), skipping")
            return False
        else:
            print(f"      -> Warning: Date {date_str} has unusual year {year}")
            return False
            
    except Exception:
        return False

def extract_and_validate_date(file_path: str) -> Optional[str]:
    """
    Extract and validate the Gregorian date from Excel file.
    """
    extracted_date = extract_gregorian_date_from_excel(file_path)
    
    if extracted_date and validate_gregorian_date(extracted_date):
        return extracted_date
    else:
        print(f"      -> No valid Gregorian date found in {Path(file_path).name}")
        return None

# --- ENHANCED SCRIPT LOGIC ---

def normalize_column_name(col_name: str) -> str:
    if not isinstance(col_name, str):
        col_name = str(col_name)
    normalized = re.sub(r'\s+', ' ', col_name).strip().lower()
    return normalized

def merge_yearly_data():
    if not DATA_DIRECTORY.is_dir():
        print(f"Error: Data directory not found at '{DATA_DIRECTORY}'")
        return

    print("Starting the Excel file merging process...")
    print("Enhanced to extract Gregorian dates (التاريخ الميلاد) for time series analysis")
    print("=" * 80)
    
    all_dataframes = []
    total_files_processed = 0
    files_with_dates = 0
    files_without_dates = 0

    for year in YEARS:
        year_path = DATA_DIRECTORY / year
        if not year_path.is_dir():
            continue
        
        print(f"\n--- Processing Year: '{year}' ---")
        
        for month in MONTHS:
            month_path = year_path / month
            if not month_path.is_dir():
                continue

            print(f"  - Processing month: '{month_path.name}'")
            
            for file_path in month_path.glob("*.xlsx"):
                print(f"    Processing file: {file_path.name}...")
                
                # Extract and validate Gregorian date
                extracted_date = extract_and_validate_date(str(file_path))
                
                if extracted_date:
                    print(f"      -> ✅ Found Gregorian date: {extracted_date}")
                    files_with_dates += 1
                else:
                    print("      -> ❌ No valid Gregorian date found")
                    files_without_dates += 1

                # Load and process the data
                df = load_and_prepare_excel(str(file_path))
                
                if df is not None and not df.empty:
                    # Add date information
                    if extracted_date:
                        try:
                            # Convert to standard format for time series analysis
                            parsed_date = pd.to_datetime(extracted_date, dayfirst=True, errors='coerce')
                            if pd.notna(parsed_date):
                                df['document_date'] = parsed_date.strftime('%Y-%m-%d')
                                df['year'] = parsed_date.year
                                df['month'] = parsed_date.month
                                df['quarter'] = f"Q{((parsed_date.month-1)//3) + 1}"
                                df['week_of_year'] = parsed_date.isocalendar()[1]
                            else:
                                df['document_date'] = extracted_date
                                print(f"      -> Warning: Could not parse date {extracted_date}")
                        except Exception as e:
                            df['document_date'] = extracted_date
                            print(f"      -> Warning: Error processing date {extracted_date}: {e}")
                    else:
                        df['document_date'] = None
                        df['year'] = None
                        df['month'] = None
                        df['quarter'] = None
                        df['week_of_year'] = None
                    
                    # Add file metadata
                    df['source_file'] = file_path.name
                    df['source_year_folder'] = year
                    df['source_month_folder'] = month
                    
                    # Normalize column names
                    df.columns = [normalize_column_name(col) for col in df.columns]
                    
                    all_dataframes.append(df)
                    total_files_processed += 1
                else:
                    print(f"      -> Skipped {file_path.name} (no valid data table found).")

    if not all_dataframes:
        print("\nProcess finished, but no data was found to merge.")
        return

    print(f"\n" + "=" * 80)
    print(f"PROCESSING SUMMARY:")
    print(f"• Total files processed: {total_files_processed}")
    print(f"• Files with valid dates: {files_with_dates}")
    print(f"• Files without dates: {files_without_dates}")
    print(f"• Date extraction success rate: {(files_with_dates/total_files_processed)*100:.1f}%")
    
    print(f"\nMerging data from {total_files_processed} files...")
    
    try:
        merged_df = pd.concat(all_dataframes, ignore_index=True)
    except Exception as e:
        print(f"An error occurred during the final merge: {e}")
        return

    # Generate summary statistics for time series readiness
    print(f"\n" + "=" * 80)
    print("TIME SERIES ANALYSIS READINESS:")
    
    if 'document_date' in merged_df.columns:
        dated_samples = merged_df[merged_df['document_date'].notna()]
        print(f"• Total samples: {len(merged_df)}")
        print(f"• Samples with dates: {len(dated_samples)}")
        print(f"• Date coverage: {(len(dated_samples)/len(merged_df))*100:.1f}%")
        
        if len(dated_samples) > 0:
            print(f"• Date range: {dated_samples['document_date'].min()} to {dated_samples['document_date'].max()}")
            
            # Monthly distribution
            if 'year' in merged_df.columns and 'month' in merged_df.columns:
                monthly_counts = dated_samples.groupby(['year', 'month']).size()
                print(f"• Monthly data points available: {len(monthly_counts)}")
                print(f"• Average samples per month: {monthly_counts.mean():.1f}")

    # Save the merged dataset
    today_str = datetime.now().strftime("%Y-%m-%d")
    output_filename = f"merged_pesticide_data_with_dates_{today_str}.xlsx"

    print(f"\nSaving merged data to '{output_filename}'...")
    merged_df.to_excel(output_filename, index=False)
    
    print("\n" + "🎉" * 20 + " SUCCESS! " + "🎉" * 20)
    print(f"Master file created: {Path(output_filename).resolve()}")
    print(f"Ready for time series analysis with {files_with_dates} dated samples!")
    
    # Optional: Create a separate file with only dated samples for time series
    if 'document_date' in merged_df.columns:
        dated_only = merged_df[merged_df['document_date'].notna()].copy()
        if len(dated_only) > 0:
            dated_filename = f"dated_pesticide_data_{today_str}.xlsx"
            dated_only.to_excel(dated_filename, index=False)
            print(f"Dated samples only: {dated_filename}")


if __name__ == "__main__":
    merge_yearly_data()