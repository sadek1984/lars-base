
import pandas as pd
import re
import logging
from typing import List

# Get a logger instance
logger = logging.getLogger(__name__)

def load_and_prepare_excel(file_path: str) -> pd.DataFrame | None:
    """
    Loads an Excel file by dynamically finding the header row.

    Args:
        file_path: The path to the Excel file.

    Returns:
        A pandas DataFrame with the correct headers, or None if headers can't be found.
    """
    try:
        df_no_header = pd.read_excel(file_path, header=None)
        header_row_index = -1
        
        # Search for the header row within the first 20 rows of the file
        for i, row in df_no_header.head(20).iterrows():
            if any('اسم المبيد' in str(cell) for cell in row.values):
                header_row_index = i
                break
        
        if header_row_index == -1:
            logger.warning(f"Header row containing 'اسم المبيد' not found in file: {file_path}")
            return None
            
        # Reload the file using the correct header row
        df = pd.read_excel(file_path, header=header_row_index)
        df.dropna(how='all', inplace=True)
        return df
        
    except Exception as e:
        logger.error(f"Failed to load and prepare Excel file {file_path}: {e}")
        return None

def find_column(df: pd.DataFrame, keywords: List[str]) -> str | None:
    """
    Finds a column in a DataFrame by searching for a list of keywords.
    This handles variations in column names (e.g., newlines, extra spaces).

    Args:
        df: The pandas DataFrame to search within.
        keywords: A list of keywords to search for.

    Returns:
        The actual column name if found, otherwise None.
    """
    for col in df.columns:
        # Normalize the column name to make matching more reliable
        normalized_col = re.sub(r'\s+', ' ', str(col)).strip()
        for keyword in keywords:
            if keyword in normalized_col:
                return col
    return None

def clean_pesticide_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans the DataFrame by keeping only the rows that have a valid pesticide name.

    Args:
        df: A pandas DataFrame containing the pesticide data.

    Returns:
        A cleaned pandas DataFrame.
    """
    pesticide_column = find_column(df, ['اسم المبيد', 'Pesticide Name'])

    if pesticide_column is None:
        logger.warning(f"Could not find a pesticide name column for cleaning. Columns: {df.columns.tolist()}")
        return pd.DataFrame()

    # Drop rows where the pesticide column is empty/null
    df_cleaned = df.dropna(subset=[pesticide_column])
    df_cleaned = df_cleaned.astype({pesticide_column: str})
    
    # Filter out rows that contain placeholder values like "لا يوجد"
    placeholders = ['', 'لا يوجد', 'Not Found', 'N/A']
    df_cleaned = df_cleaned[~df_cleaned[pesticide_column].str.strip().isin(placeholders)]

    return df_cleaned

def format_rows_as_text(df: pd.DataFrame) -> List[str]:
    """
    Converts each row of a cleaned DataFrame into a descriptive sentence
    for better indexing and query results.

    Args:
        df: A cleaned pandas DataFrame.

    Returns:
        A list of strings, where each string describes a single test result.
    """
    # Find all the necessary columns robustly
    col_map = {
        'code': find_column(df, ['كود العينة', 'sample code']),
        'name': find_column(df, ['اسم العينة', 'Sample Name']),
        'pesticide': find_column(df, ['اسم المبيد', 'Pesticide Name']),
        'reading': find_column(df, ['قراءة الجهاز', 'Reading of device']),
        'limit': find_column(df, ['الحدود', 'Limits']),
        'result': find_column(df, ['النتيجة', 'result'])
    }
    
    if not all([col_map['pesticide'], col_map['name'], col_map['code']]):
        logger.warning("Cannot format rows to text because essential columns (code, name, pesticide) are missing.")
        return []

    formatted_texts = []
    for _, row in df.iterrows():
        parts = []
        # Safely get data from each column, providing a default if it's missing
        code = row.get(col_map['code'], 'N/A') if col_map['code'] else 'N/A'
        name = row.get(col_map['name'], 'N/A') if col_map['name'] else 'N/A'
        pesticide = row.get(col_map['pesticide'], 'N/A') if col_map['pesticide'] else 'N/A'
        
        parts.append(f"Test for sample '{code}' ({name}) found pesticide '{pesticide}'.")

        if col_map['reading'] and pd.notna(row.get(col_map['reading'])):
            parts.append(f"Reading: {row.get(col_map['reading'])}.")
        if col_map['limit'] and pd.notna(row.get(col_map['limit'])):
            parts.append(f"Limit: {row.get(col_map['limit'])}.")
        if col_map['result'] and pd.notna(row.get(col_map['result'])):
            parts.append(f"Result: '{row.get(col_map['result'])}'.")
            
        formatted_texts.append(" ".join(parts))

    return formatted_texts

