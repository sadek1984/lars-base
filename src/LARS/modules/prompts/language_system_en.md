LANGUAGE CONSTRAINT - CRITICAL AND NON-NEGOTIABLE:
The user's question is in ENGLISH. You MUST ensure ALL output is in English.
- In your SQL query, use CASE statements or aliases to translate Arabic values if possible
- All column aliases (AS ...) must be English words
- **CRITICAL NOTE**: The `chemistry_tidy` table NOW CONTAINS ENGLISH values for `اسم العينة` (Sample Name). E.g., it contains 'Tomato' instead of 'طماطم'. IF querying for sample names, search for the English literal ('Tomato', 'Cucumber', 'Zucchini', etc.) OR use a case-insensitive `LOWER("اسم العينة") LIKE '%tomato%'` approach.
- After you generate the SQL, the system will also auto-translate remaining Arabic values
- Do NOT use Arabic characters anywhere in column aliases or string literals in the SQL EXCEPT if specifically matching an Arabic district name (e.g., district remains Arabic).
- Example: Instead of AS عدد_العينات, write AS sample_count
- Example: Instead of AS المبيد, write AS pesticide_name
- Example: Instead of AS الحالة, write AS status
