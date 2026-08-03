
import pandas as pd

file_path = 'src/LARS/processed_data_with_neighborhood.xlsx'
df = pd.read_excel(file_path)

# Mapping dictionary
mapping = {
    'الموطأ': 'Al Mowata',
    'الناصرية': 'An Nasariyah',
    'القاع البارد': 'Al Qaa Al Barid',
    'الوسيطاء': 'Al Wasita',
    'الراشد': 'Al Rashid',
    'السالمية': 'As Salmiyah',
    'البشر': 'Al Bishr',
    'التخصصي': 'At Takhassusi',
    'الفايزية': 'Al Fayziyyah',
    'الهدية': 'Al Hedaya',
    'التغيرة': 'At Taghirah',
    'وهطان': 'Wahtan',
    'اللابدية': 'Al Labidiyah',
    'الأخضر': 'Al Akhdar',
    'النقيب': 'An Naqib',
    'الأفق': 'Al Ufuq',
    'الإسكان': 'Al Iskan',
    'الشماس': 'Ash Shamas',
    'الصفراء': 'As Safra',
    'السلام': 'As Salam',
    'الجامعيين': 'Al Jamioyin',
    'الرفيعة': 'Ar Rafiah',
    'المعارض': 'Al Maared',
    'الأمن': 'Al Amn',
    'السادة': 'As Sadah',
    'مشعل': 'Mishal',
    'الصبيحية': 'As Sabihah',
    'عين الذيب': 'Ain Adh Dhib',
    'النهضة': 'An Nahdah',
    'الخالدية': 'Al Khalidiyah',
    'النازية': 'An Naziyah',
    'البريكة': 'Al Buraykah',
    'غنامة': 'Ghannamah',
    'النصار': 'An Nassar',
    'المنتزه': 'Al Muntazah',
    'العلياء': 'Al Ulya',
    'الفاخرية': 'Al Fakhriyah',
    'النقع الشرقي': 'An Naqa Ash Sharqi',
    'العجيبة': 'Al Ajibah',
    'قرطبة': 'Qurtubah',
    'العوازم': 'Al Awazim',
    'جميعانة': 'Jameana',
    'الزراعي': 'Az Zirai',
    'ابن صبيح': 'Ibn Subayh',
    'الضاحي': 'Ad Dahi'
}

# Create new column
# Use 'الحي' if it exists, otherwise check 'الحى'
source_col = 'الحي' if 'الحي' in df.columns else 'الحى'
df['neighborhood_english'] = df[source_col].map(mapping).fillna(df[source_col])

# Save back to file
df.to_excel(file_path, index=False)
print("✅ Added 'neighborhood_english' column to Excel file.")
print(f"Mapped {len(mapping)} neighborhoods.")
print("First 5 rows with new column:")
print(df[['vegetable_english', source_col, 'neighborhood_english']].head())
