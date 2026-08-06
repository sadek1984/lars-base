import sys
sys.path.insert(0, "/Users/a12/lars-base/src/LARS")

from modules.mappings import normalize_arabic_text, PESTICIDE_AR_TO_EN_NORM

q = normalize_arabic_text("الإيميداكلوبرايد")
print("normalized query:", q)
print("found in dict:", PESTICIDE_AR_TO_EN_NORM.get(q))
