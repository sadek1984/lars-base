import pandas as pd
import re

df = pd.read_excel('/Users/a12/Buraidah_lars/src/LARS/data/bur_dataset.xlsx', sheet_name='الكيمياء')
pesticide_cols = [col for col in df.columns if 'ملوث' in col]

def count_pesticides(row):
    count = 0
    for col in pesticide_cols:
        val = str(row[col]).strip()
        if val and val.upper() != 'NAN' and 'NO' not in val.upper():
            count += 1
    return count

df['p_count'] = df.apply(count_pesticides, axis=1)
print("Samples with 10 pesticides in raw excel:", len(df[df['p_count'] == 10]))
print("Codes:", df[df['p_count'] == 10]['كود العينة'].tolist())
