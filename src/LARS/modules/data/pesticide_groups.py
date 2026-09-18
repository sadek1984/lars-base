"""
pesticide_groups.py
===================
Chemical group classifications and ADI values for pesticides.
Used by:
- chemical group analysis handler
- health risk index calculations
- quality index calculations
"""

# ── Chemical Group Classification ──────────────────────────────────────────────
# Maps pesticide name patterns → chemical group
# Keys are lowercase substrings to match against pesticide_name
PESTICIDE_CHEMICAL_GROUPS = {
    # Organophosphates
    "chlorpyrifos":   "Organophosphate",
    "dimethoate":     "Organophosphate",
    "malathion":      "Organophosphate",
    "methidathion":   "Organophosphate",
    "profenofos":     "Organophosphate",
    "triazophos":     "Organophosphate",
    "ethion":         "Organophosphate",
    "phosmet":        "Organophosphate",
    "acephate":       "Organophosphate",
    "methomyl":       "Organophosphate",
    "omethoate":      "Organophosphate",
    "parathion":      "Organophosphate",
    "pirimiphos":     "Organophosphate",
    "quinalphos":     "Organophosphate",

    # Pyrethroids
    "bifenthrin":     "Pyrethroid",
    "cypermethrin":   "Pyrethroid",
    "deltamethrin":   "Pyrethroid",
    "lambda-cyhalothrin": "Pyrethroid",
    "lambda cyhalothrin": "Pyrethroid",
    "cyhalothrin":    "Pyrethroid",
    "permethrin":     "Pyrethroid",
    "fenvalerate":    "Pyrethroid",
    "fenpropathrin":  "Pyrethroid",
    "esfenvalerate":  "Pyrethroid",
    "alpha-cypermethrin": "Pyrethroid",
    "beta-cypermethrin":  "Pyrethroid",
    "zeta-cypermethrin":  "Pyrethroid",
    "etofenprox":     "Pyrethroid",
    "flucythrinate":  "Pyrethroid",
    "tefluthrin":     "Pyrethroid",
    "flumethrin":     "Pyrethroid",
    "tau-fluvalinate": "Pyrethroid",

    # Neonicotinoids
    "imidacloprid":   "Neonicotinoid",
    "thiamethoxam":   "Neonicotinoid",
    "clothianidin":   "Neonicotinoid",
    "acetamiprid":    "Neonicotinoid",
    "thiacloprid":    "Neonicotinoid",
    "nitenpyram":     "Neonicotinoid",
    "dinotefuran":    "Neonicotinoid",

    # Organochlorines
    "endosulfan":     "Organochlorine",
    "dde":            "Organochlorine",
    "ddt":            "Organochlorine",
    "lindane":        "Organochlorine",
    "heptachlor":     "Organochlorine",
    "aldrin":         "Organochlorine",
    "dieldrin":       "Organochlorine",
    "hexachlorobenzene": "Organochlorine",

    # Triazoles (Fungicides)
    "tebuconazole":   "Triazole Fungicide",
    "propiconazole":  "Triazole Fungicide",
    "epoxiconazole":  "Triazole Fungicide",
    "difenoconazole": "Triazole Fungicide",
    "triadimefon":    "Triazole Fungicide",
    "myclobutanil":   "Triazole Fungicide",
    "hexaconazole":   "Triazole Fungicide",
    "cyproconazole":  "Triazole Fungicide",
    "metconazole":    "Triazole Fungicide",
    "flutriafol":     "Triazole Fungicide",
    "penconazole":    "Triazole Fungicide",
    "prothioconazole":"Triazole Fungicide",

    # Benzimidazoles (Fungicides)
    "carbendazim":    "Benzimidazole Fungicide",
    "thiabendazole":  "Benzimidazole Fungicide",
    "thiophanate":    "Benzimidazole Fungicide",

    # Carbamates
    "carbofuran":     "Carbamate",
    "pirimicarb":     "Carbamate",
    "aldicarb":       "Carbamate",
    "oxamyl":         "Carbamate",
    "carbaryl":       "Carbamate",
    "fenoxycarb":     "Carbamate",

    # IGRs (Insect Growth Regulators)
    "pyriproxyfen":   "Insect Growth Regulator",
    "buprofezin":     "Insect Growth Regulator",
    "buprofezin":     "Insect Growth Regulator",
    "cyromazine":     "Insect Growth Regulator",
    "diflubenzuron":  "Insect Growth Regulator",
    "lufenuron":      "Insect Growth Regulator",
    "novaluron":      "Insect Growth Regulator",
    "hexaflumuron":   "Insect Growth Regulator",
    "methoxyfenozide":"Insect Growth Regulator",
    "tebufenozide":   "Insect Growth Regulator",
    "chromafenozide": "Insect Growth Regulator",

    # Phenylpyrazoles
    "fipronil":       "Phenylpyrazole",

    # Avermectins
    "abamectin":      "Avermectin",
    "emamectin":      "Avermectin",
    "spinosad":       "Spinosyn",
    "spinetoram":     "Spinosyn",

    # Diamides
    "chlorantraniliprole": "Diamide",
    "cyantraniliprole":    "Diamide",
    "flubendiamide":       "Diamide",

    # Strobilurins (Fungicides)
    "azoxystrobin":   "Strobilurin Fungicide",
    "trifloxystrobin":"Strobilurin Fungicide",
    "kresoxim":       "Strobilurin Fungicide",
    "picoxystrobin":  "Strobilurin Fungicide",
    "pyraclostrobin": "Strobilurin Fungicide",
    "fluoxastrobin":  "Strobilurin Fungicide",

    # Dithiocarbamates (Fungicides)
    "mancozeb":       "Dithiocarbamate Fungicide",
    "maneb":          "Dithiocarbamate Fungicide",
    "thiram":         "Dithiocarbamate Fungicide",
    "iprodione":      "Dicarboximide Fungicide",

    # SDHI Fungicides
    "fluxapyroxad":   "SDHI Fungicide",
    "boscalid":       "SDHI Fungicide",
    "penthiopyrad":   "SDHI Fungicide",
    "flutolanil":     "SDHI Fungicide",

    # Organotins
    "fenbutatin":     "Organotin Acaricide",
    "cyhexatin":      "Organotin Acaricide",

    # Acaricides
    "hexythiazox":    "Acaricide",
    "clofentezine":   "Acaricide",
    "dicofol":        "Acaricide",
    "spirodiclofen":  "Acaricide",
    "spiromesifen":   "Acaricide",

    # Mycotoxins (not pesticides but in same DB)
    "aflatoxin":      "Mycotoxin",
    "ochratoxin":     "Mycotoxin",
    "deoxynivalenol": "Mycotoxin",
    "zearalenone":    "Mycotoxin",
    "fumonisins":     "Mycotoxin",
    "patulin":        "Mycotoxin",
    "t-2 toxin":      "Mycotoxin",
}

def classify_pesticide(name: str) -> str:
    """
    Return the chemical group for a pesticide name.
    Uses substring matching (case-insensitive).
    """
    name_lower = name.lower()
    for key, group in PESTICIDE_CHEMICAL_GROUPS.items():
        if key in name_lower:
            return group
    return "Other"


# ── ADI values (mg/kg body weight/day) ─────────────────────────────────────────
# Source: JMPR / EFSA / FAO/WHO
# Used for Health Risk Index (HRI) calculation
ADI_VALUES = {
    # Organophosphates
    "chlorpyrifos":    0.001,
    "dimethoate":      0.002,
    "malathion":       0.300,
    "methidathion":    0.001,
    "profenofos":      0.030,
    "triazophos":      0.001,
    "ethion":          0.002,
    "phosmet":         0.010,
    "acephate":        0.030,

    # Pyrethroids
    "bifenthrin":      0.010,
    "cypermethrin":    0.020,
    "deltamethrin":    0.010,
    "lambda-cyhalothrin": 0.005,
    "cyhalothrin":     0.005,
    "permethrin":      0.050,
    "fenvalerate":     0.020,

    # Neonicotinoids
    "imidacloprid":    0.060,
    "thiamethoxam":    0.026,
    "clothianidin":    0.097,
    "acetamiprid":     0.025,
    "thiacloprid":     0.010,

    # Organochlorines
    "endosulfan":      0.006,

    # Triazoles
    "tebuconazole":    0.030,
    "propiconazole":   0.040,
    "difenoconazole":  0.010,
    "myclobutanil":    0.025,

    # Benzimidazoles
    "carbendazim":     0.020,
    "thiabendazole":   0.100,

    # IGRs
    "pyriproxyfen":    0.100,
    "buprofezin":      0.009,

    # Phenylpyrazoles
    "fipronil":        0.0002,

    # Avermectins
    "abamectin":       0.001,
    "emamectin":       0.0005,
    "spinosad":        0.024,

    # Diamides
    "chlorantraniliprole": 1.500,
    "flubendiamide":       0.020,

    # Fungicides
    "azoxystrobin":    0.200,
    "carbendazim":     0.020,
    "iprodione":       0.060,

    # Carbamates
    "carbofuran":      0.001,
    "pirimicarb":      0.035,

    # Acaricides
    "hexythiazox":     0.030,
    "dicofol":         0.002,
}

# Saudi Arabia average per capita consumption (g/day) - FAO/WHO 2021 estimates
SAUDI_CONSUMPTION_G_DAY = {
    "default":     100.0,
    "vegetables":  250.0,
    "tomato":      120.0,
    "cucumber":     80.0,
    "pepper":       30.0,
    "eggplant":     30.0,
    "zucchini":     25.0,
    "okra":         20.0,
    "beans":        15.0,
    "potato":      150.0,
    "leafy":       100.0,
    "parsley":      15.0,
    "spinach":      50.0,
    "fruit":       200.0,
    "grapes":       80.0,
    "strawberry":   40.0,
    "apple":        80.0,
    "orange":      100.0,
    "dates":        50.0,
    "spices":        5.0,
    "cardamom":      2.0,
    "cumin":         2.0,
    "nuts":         20.0,
    "grains":      250.0,
    "wheat":       250.0,
    "rice":        120.0,
}

BODY_WEIGHT_KG = 60.0  # Saudi adult average


def get_adi(pesticide_name: str) -> float:
    """Get ADI for a pesticide, searching by substring."""
    name_lower = pesticide_name.lower()
    for key, adi in ADI_VALUES.items():
        if key in name_lower:
            return adi
    return None


def get_consumption(sample_name: str) -> float:
    """Get estimated daily consumption for a sample type."""
    name_lower = sample_name.lower()
    for key, val in SAUDI_CONSUMPTION_G_DAY.items():
        if key in name_lower:
            return val
    # Try Arabic names
    arabic_map = {
        "طماطم": "tomato", "خيار": "cucumber", "فلفل": "pepper",
        "باذنجان": "eggplant", "كوسة": "zucchini", "بامية": "okra",
        "فاصوليا": "beans", "بطاطس": "potato", "بقدونس": "parsley",
        "سبانخ": "spinach", "عنب": "grapes", "فراولة": "strawberry",
        "تفاح": "apple", "برتقال": "orange", "تمر": "dates",
        "هيل": "cardamom", "كمون": "cumin", "قمح": "wheat",
        "رز": "rice", "فستق": "nuts", "لوز": "nuts",
    }
    for ar, en in arabic_map.items():
        if ar in sample_name:
            return SAUDI_CONSUMPTION_G_DAY.get(en, SAUDI_CONSUMPTION_G_DAY["default"])
    return SAUDI_CONSUMPTION_G_DAY["default"]