import pandas as pd
import re
from typing import List

def parse_llm_response_to_df(llm_text: str) -> pd.DataFrame | None:
    """
    Parses a markdown-style table from the LLM's text response into a pandas DataFrame.

    This function is designed to be robust against common formatting quirks from LLMs.

    Args:
        llm_text: The raw string response from the language model.

    Returns:
        A pandas DataFrame containing the structured data, or None if parsing fails.
    """
    lines = llm_text.strip().split('\n')
    
    header = []
    data_rows = []
    header_found = False

    for line in lines:
        # Clean up the line by removing extra whitespace
        line = line.strip()
        if not line or line.startswith('---') or '---' in line:
            # This is a separator line or empty, skip it. If we found the header, the next lines are data.
            if header:
                header_found = True
            continue

        # Split the line by the pipe character '|'
        parts = [part.strip() for part in line.split('|')]
        
        # Filter out empty parts that result from leading/trailing pipes
        parts = [part for part in parts if part]

        if not header and parts:
            # Assume the first non-empty, non-separator line is the header
            header = parts
        elif header_found and len(parts) > 0:
            # Only add rows that seem to contain data
            # Ensure the row has a similar number of columns as the header for consistency
            if len(parts) >= len(header) -1: # Allow for some flexibility
                 data_rows.append(parts)

    if not header or not data_rows:
        return None

    # Pad rows that might be shorter than the header
    for row in data_rows:
        while len(row) < len(header):
            row.append(None)
            
    # Truncate rows that are longer than the header
    data_rows = [row[:len(header)] for row in data_rows]

    try:
        df = pd.DataFrame(data_rows, columns=header)
        return df
    except Exception:
        # If DataFrame creation fails (e.g., due to mismatched lengths after all), return None
        return None
