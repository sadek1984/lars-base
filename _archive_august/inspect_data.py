
import pandas as pd
import os

try:
    file_path = 'src/LARS/processed_data_with_neighborhood.xlsx'
    df = pd.read_excel(file_path)
    
    print("Columns:", df.columns.tolist())
    
    # Check for likely neighborhood columns
    possible_cols = ['الحي', 'الحى', 'neighborhood', 'Neighborhood']
    found_col = None
    for col in possible_cols:
        if col in df.columns:
            found_col = col
            break
            
    if found_col:
        print(f"Found neighborhood column: '{found_col}'")
        unique_vals = df[found_col].unique().tolist()
        print("Unique values:")
        for v in unique_vals:
            print(f"- {v!r}")  # Use repr to show hidden chars/encoding
    else:
        print("No neighborhood column found.")

except Exception as e:
    print(f"Error: {e}")
