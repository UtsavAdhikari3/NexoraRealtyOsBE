from decimal import Decimal, ROUND_HALF_UP

SQFT_PER_UNIT = {
    "sqft": Decimal("1"), "sqm": Decimal("10.7639104167"),
    "ropani": Decimal("5476"), "aana": Decimal("342.25"),
    "paisa": Decimal("85.5625"), "daam": Decimal("21.390625"),
    "bigha": Decimal("72900"), "kattha": Decimal("3645"), "dhur": Decimal("182.25"),
}

def convert_area(value, from_unit, to_unit="sqft"):
    if value in (None, ""): return None
    if from_unit not in SQFT_PER_UNIT or to_unit not in SQFT_PER_UNIT:
        raise ValueError("Unsupported area unit.")
    return Decimal(str(value)) * SQFT_PER_UNIT[from_unit] / SQFT_PER_UNIT[to_unit]

def rounded(value, places="0.0001"):
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)

def conversion_payload(value, unit):
    if value in (None, "") or not unit: return None
    return {key: str(rounded(convert_area(value, unit, key))) for key in SQFT_PER_UNIT}

def price_per_area(price, area_value, area_unit, target_unit):
    if not price or not area_value or not area_unit: return None
    target_area = convert_area(area_value, area_unit, target_unit)
    if target_area <= 0: return None
    return str((Decimal(str(price)) / target_area).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
