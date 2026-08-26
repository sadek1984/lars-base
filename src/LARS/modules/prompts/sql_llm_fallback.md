Generate a DuckDB SQL query to answer the following question about a pesticide testing database.

🔒 Schema (metadata only — no actual data exposed):
$schema

RULES:
1. Always quote Arabic column names in double quotes: `"كود العينة"`
2. Use COUNT(DISTINCT "كود العينة") to count unique samples
3. Use ILIKE for case-insensitive text matching
4. DuckDB syntax only — no MySQL/Postgres extensions
5. Limit results to 100 rows unless the question asks for all
6. "اسم العينة" stores ENGLISH names: Tomato, Cucumber, Pepper, Cardamom, Pistachios, …
7. "الحى" stores Arabic neighborhood names

Detected entities:
- Samples       : $detected_samples
- Neighborhoods : $detected_neighborhoods
- Pesticide     : $detected_pesticide

Arabic ↔ English quick map:
طماطم→Tomato  خيار→Cucumber  فلفل→Pepper  باذنجان→Eggplant  كوسة→Zucchini
كمون→Cumin  هيل→Cardamom  فستق→Pistachios  زعتر→Thyme
فوق الحد / تجاوز     → is_above_limit = 1
تحت الحد / ضمن الحد  → is_above_limit = 0
غير مطابق / راسب     → sample_result LIKE '%Non-Compliant%'
مطابق / ناجح          → sample_result LIKE '%Compliant%' AND sample_result NOT LIKE '%Non%'
البايفنثرن→Bifenthrin  الكلوربيريفوس→Chlorpyrifos  الإيميداكلوبريد→Imidacloprid
الأباميكتين→Abamectin  الثيامثوكسام→Thiamethoxam  الفيبرونيل→Fipronil

Question: $query

Generate ONLY the SQL wrapped in ```sql``` markers:
