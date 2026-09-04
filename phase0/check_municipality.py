import duckdb
con = duckdb.connect('/Users/a12/lars-base/src/LARS/data/lars_data_demo.duckdb', read_only=True)

total = con.execute('SELECT COUNT(*) FROM chemistry_tidy').fetchone()[0]
matching = con.execute('''
    SELECT COUNT(*) FROM chemistry_tidy
    WHERE TRIM("اسم البلدية") = TRIM("اسم المنشاة")
''').fetchone()[0]
print(f'إجمالي الصفوف: {total}')
print(f'صفوف متطابقة: {matching} ({100*matching/total:.1f}%)')
print()

sample = con.execute('''
    SELECT DISTINCT "اسم المنشاة", "اسم البلدية"
    FROM chemistry_tidy
    WHERE TRIM("اسم البلدية") = TRIM("اسم المنشاة")
    LIMIT 15
''').df()
print(sample)