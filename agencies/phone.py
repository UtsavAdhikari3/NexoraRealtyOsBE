import re


NEPAL_PHONE_ERROR = (
    "Enter a 10-digit Nepal phone number starting with 97, 98, or 01."
)
NEPAL_PHONE_RE = re.compile(r"^(?:97|98|01)\d{8}$")
_NEPALI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def nepal_phone_national_digits(value):
    """Return national digits from national or +977-prefixed user input."""
    raw = str(value or "").strip().translate(_NEPALI_DIGITS)
    digits = re.sub(r"\D", "", raw)

    if digits.startswith("00977") and len(digits) == 15:
        return digits[5:]
    if digits.startswith("977") and len(digits) == 13:
        return digits[3:]
    return digits


def is_valid_nepal_phone(value):
    return bool(NEPAL_PHONE_RE.fullmatch(nepal_phone_national_digits(value)))


def normalize_nepal_phone(value):
    """Normalize valid Nepal numbers to the application's +977 storage form."""
    national = nepal_phone_national_digits(value)
    if NEPAL_PHONE_RE.fullmatch(national):
        return f"+977{national}"
    return str(value or "").strip()
