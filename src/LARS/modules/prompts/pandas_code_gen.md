Generate pandas code to answer this question about the pesticide testing dataset.

**IMPORTANT: READ THE QUESTION CAREFULLY AND ANSWER EXACTLY WHAT IS ASKED!**

🔒 Dataset Schema (Metadata Only - No Actual Data Exposed):

**Column Information:**
$dtypes_markdown

**DataFrame Structure:**
$df_info_str
$sample_stats
$categorical_info
$value_patterns

**Available Columns:** $columns
**Total Records:** $total_records samples
**Shape:** $df_shape

⚠️ PRIVACY NOTE: You are receiving ONLY schema information (column names and types).
DO NOT assume specific values exist. Write generic filtering/aggregation code based on column names only.

User Question: $query
$risk_instruction

$specific_instructions

**AVAILABLE VARIABLES IN SCOPE:**
- df: The main DataFrame (already loaded)
- pd: pandas module
- np: numpy module
- query: The user's question as a string
- pesticide_mapping: Dictionary mapping Arabic pesticide names to English
  Example: pesticide_mapping['البايفنثرن'] = 'Bifenthrin'
  Use this to translate Arabic pesticide names when filtering

**CRITICAL REQUIREMENTS:**
1. ANSWER THE EXACT QUESTION - don't provide generic summaries
2. Store final result in variable 'result'
3. Execute code DIRECTLY - do NOT wrap in a function
4. Do NOT use 'return' statement
5. Handle missing values with .fillna() or dropna()
6. **STRING FILTERING - CRITICAL:**
   - ALWAYS use `na=False` parameter with .str.contains() to handle NaN values
   - Example: df[df['vegetable_english'].str.contains('Cucumber', case=False, na=False)]
   - Never use .str.contains() without na=False parameter
7. **PESTICIDE NAME MATCHING:**
   - If query mentions pesticide name in Arabic (e.g., 'البايفنثرن'), use pesticide_mapping
   - Example: pesticide_name = pesticide_mapping.get('البايفنثرن', 'Bifenthrin')
   - Then filter: df[df['pesticide_standardized'].str.contains(pesticide_name, case=False, na=False)]

**KEY COLUMNS TO USE:**
- 'year' - for yearly analysis
- 'is_compliant' - 1=compliant, 0=violation
- 'pesticide_standardized' - pesticide name
- 'vegetable_english' - vegetable name in English
- 'reading' - measured value
- 'limits' - maximum allowed limit

**EXAMPLE CODE PATTERNS:**

For "compliance trends by year":
```python
result = df.groupby('year').agg(
    total_samples=('is_compliant', 'count'),
    compliant=('is_compliant', 'sum'),
    violations=('is_compliant', lambda x: (x == 0).sum())
).reset_index()
result['compliance_rate'] = (result['compliant'] / result['total_samples'] * 100).round(2)
result = result.sort_values('year')
```

For "pesticides with most violations":
```python
result = df[df['is_compliant'] == 0].groupby('pesticide_standardized').size().reset_index(name='violations')
result = result.sort_values('violations', ascending=False).head(15)
```

For "total number of cucumber samples" (simple count):
```python
cucumber_samples = df[df['vegetable_english'].str.contains('Cucumber', case=False, na=False)]
total_count = len(cucumber_samples)
result = pd.DataFrame({
    'الخضار': ['خيار (Cucumber)'],
    'عدد العينات الكلي': [total_count]
})
```

For "tomato samples with Bifenthrin above/below limit" (Arabic query):
```python
pesticide_name = pesticide_mapping.get('البايفنثرن', 'Bifenthrin')
filtered = df[
    (df['vegetable_english'].str.contains('Tomato', case=False, na=False)) &
    (df['pesticide_standardized'].str.contains(pesticide_name, case=False, na=False))
].copy()
above_limit = (filtered['is_compliant'] == 0).sum()
below_limit = (filtered['is_compliant'] == 1).sum()
result = pd.DataFrame({
    'الخضار': ['الطماطم'],
    'المبيد': [pesticide_name],
    'عدد العينات': [len(filtered)],
    'فوق الحد': [above_limit],
    'تحت الحد': [below_limit]
})
```

For "vegetables in neighborhood with compliance stats" (complex Arabic query):
```python
neighborhood_data = df[df['neighborhood_arabic'].str.contains('الإسكان', case=False, na=False)].copy()
result = neighborhood_data.groupby('vegetable_arabic').agg(
    عدد_العينات=('vegetable_arabic', 'count'),
    فوق_الحد=('is_compliant', lambda x: (x == 0).sum()),
    تحت_الحد=('is_compliant', lambda x: (x == 1).sum())
).reset_index()
result.columns = ['الخضار', 'عدد العينات', 'فوق الحد', 'تحت الحد']
result = result.sort_values('عدد العينات', ascending=False)
```

For "vegetables affected by pesticide with compliance" (Arabic query):
```python
pesticide_name = pesticide_mapping.get('البايفنثرن', 'Bifenthrin')
pesticide_data = df[df['pesticide_standardized'].str.contains(pesticide_name, case=False, na=False)].copy()
result = pesticide_data.groupby('vegetable_arabic').agg(
    عدد_العينات=('vegetable_arabic', 'count'),
    تحت_الحد=('is_compliant', lambda x: (x == 1).sum()),
    فوق_الحد=('is_compliant', lambda x: (x == 0).sum())
).reset_index()
result.columns = ['الخضار', 'عدد العينات', 'تحت الحد', 'فوق الحد']
result = result.sort_values('عدد العينات', ascending=False)
```

Generate ONLY the Python code wrapped in ```python``` markers:
