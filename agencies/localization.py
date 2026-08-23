from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from bikram_sambat import date as bs_date
from django.utils import timezone

from .phone import is_valid_nepal_phone, normalize_nepal_phone


NEPAL_TIMEZONE = ZoneInfo("Asia/Kathmandu")
NEPALI_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")
LATIN_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

BS_MONTHS_EN = [
    "Baishakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
]
BS_MONTHS_NE = [
    "वैशाख", "जेठ", "असार", "साउन", "भदौ", "असोज",
    "कात्तिक", "मंसिर", "पुस", "माघ", "फागुन", "चैत",
]
AD_MONTHS_NE = [
    "जनवरी", "फेब्रुअरी", "मार्च", "अप्रिल", "मे", "जुन",
    "जुलाई", "अगस्ट", "सेप्टेम्बर", "अक्टोबर", "नोभेम्बर", "डिसेम्बर",
]

DEFAULT_MESSAGE_TEMPLATES = {
    "lead_follow_up": {
        "en": {
            "subject": "Follow-up due: {lead_name}",
            "body": "Please follow up with {lead_name} by {follow_up_date}. Property: {property_title}.",
        },
        "ne": {
            "subject": "फलो-अप बाँकी: {lead_name}",
            "body": "कृपया {lead_name} सँग {follow_up_date} भित्र सम्पर्क गर्नुहोस्। सम्पत्ति: {property_title}।",
        },
    },
    "site_visit_confirmation": {
        "en": {
            "subject": "Site visit confirmed - {property_title}",
            "body": "Your site visit for {property_title} is scheduled for {visit_date}. Contact: {agent_phone}.",
        },
        "ne": {
            "subject": "साइट भिजिट पुष्टि - {property_title}",
            "body": "{property_title} को साइट भिजिट {visit_date} का लागि तय भएको छ। सम्पर्क: {agent_phone}।",
        },
    },
    "site_visit_reminder": {
        "en": {
            "subject": "Reminder: site visit for {property_title}",
            "body": "This is a reminder that your site visit is scheduled for {visit_date}. Contact: {agent_phone}.",
        },
        "ne": {
            "subject": "सम्झना: {property_title} को साइट भिजिट",
            "body": "तपाईंको साइट भिजिट {visit_date} का लागि तय भएको सम्झना गराइन्छ। सम्पर्क: {agent_phone}।",
        },
    },
    "listing_confirmation_due": {
        "en": {
            "subject": "Listing confirmation due",
            "body": "Please reconfirm the availability of {property_title} before {expiry_date}.",
        },
        "ne": {
            "subject": "लिस्टिङ पुष्टि गर्न बाँकी",
            "body": "कृपया {property_title} को उपलब्धता {expiry_date} अघि पुनः पुष्टि गर्नुहोस्।",
        },
    },
    "listing_expired": {
        "en": {
            "subject": "Listing expired",
            "body": "{property_title} has expired and is no longer publicly visible.",
        },
        "ne": {
            "subject": "लिस्टिङको म्याद सकियो",
            "body": "{property_title} को म्याद सकिएको छ र अब सार्वजनिक रूपमा देखिँदैन।",
        },
    },
    "property_share": {
        "en": {
            "subject": "Property details",
            "body": "{property_title} - {price} at {address}. Details: {property_url}",
        },
        "ne": {
            "subject": "सम्पत्तिको विवरण",
            "body": "{property_title} - {address} मा {price}। थप जानकारी: {property_url}",
        },
    },
}


class SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def to_nepali_digits(value):
    return str(value).translate(NEPALI_DIGITS)


def to_latin_digits(value):
    return str(value).translate(LATIN_DIGITS)


def resolved_message_templates(overrides=None):
    templates = deepcopy(DEFAULT_MESSAGE_TEMPLATES)
    for key, localized in (overrides or {}).items():
        if key not in templates or not isinstance(localized, dict):
            continue
        for language in ("en", "ne"):
            values = localized.get(language)
            if isinstance(values, dict):
                templates[key][language].update(
                    {name: str(value) for name, value in values.items() if name in {"subject", "body"}}
                )
    return templates


def render_message(agency, template_key, language=None, **context):
    language = language or getattr(agency, "default_language", "en")
    templates = resolved_message_templates(getattr(agency, "message_templates", {}))
    selected = templates.get(template_key, {}).get(language) or templates.get(template_key, {}).get("en", {})
    values = SafeFormatDict({key: value if value not in (None, "") else "-" for key, value in context.items()})
    return {
        "subject": selected.get("subject", "").format_map(values),
        "body": selected.get("body", "").format_map(values),
    }


def _as_nepal_datetime(value):
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            value = timezone.make_aware(value, NEPAL_TIMEZONE)
        return value.astimezone(NEPAL_TIMEZONE)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=NEPAL_TIMEZONE)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, NEPAL_TIMEZONE)
        return parsed.astimezone(NEPAL_TIMEZONE)
    raise ValueError("Enter a valid ISO date or datetime.")


def convert_date(value, target="bs"):
    if target == "bs":
        local_value = _as_nepal_datetime(value)
        converted = bs_date.fromgregorian(local_value.date())
        return {"year": converted.year, "month": converted.month, "day": converted.day}
    if target == "ad":
        if isinstance(value, str):
            parts = [int(part) for part in to_latin_digits(value).split("-")[:3]]
        elif isinstance(value, (tuple, list)):
            parts = [int(part) for part in value[:3]]
        else:
            parts = [value.year, value.month, value.day]
        converted = bs_date(*parts).togregorian()
        return {"year": converted.year, "month": converted.month, "day": converted.day}
    raise ValueError("Date system must be ad or bs.")


def format_localized_date(
    value, *, date_system="ad", language="en", nepali_digits=False, include_time=False
):
    local_value = _as_nepal_datetime(value)
    if date_system == "bs":
        converted = bs_date.fromgregorian(local_value.date())
        month = (BS_MONTHS_NE if language == "ne" else BS_MONTHS_EN)[converted.month - 1]
        if language == "ne":
            result = f"{converted.year} {month} {converted.day} गते"
        else:
            result = f"{converted.day} {month} {converted.year} BS"
    elif language == "ne":
        result = f"{local_value.year} {AD_MONTHS_NE[local_value.month - 1]} {local_value.day}"
    else:
        result = local_value.strftime("%d %b %Y")
    if include_time:
        result += local_value.strftime(" %I:%M %p")
    return to_nepali_digits(result) if nepali_digits else result


def format_nepal_number(value, *, nepali_digits=False, maximum_decimals=2):
    try:
        number = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return str(value or "")
    rendered = f"{number:,.{maximum_decimals}f}".rstrip("0").rstrip(".")
    return to_nepali_digits(rendered) if nepali_digits else rendered


def format_nepal_currency(value, *, language="en", nepali_digits=False, suffix=""):
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        amount = Decimal("0")
    if amount >= Decimal("10000000"):
        number, unit_en, unit_ne = amount / Decimal("10000000"), "Crore", "करोड"
    elif amount >= Decimal("100000"):
        number, unit_en, unit_ne = amount / Decimal("100000"), "Lakh", "लाख"
    else:
        rendered = format_nepal_number(amount, nepali_digits=nepali_digits, maximum_decimals=0)
        return f"रु. {rendered}{suffix}" if language == "ne" else f"NPR {rendered}{suffix}"
    rendered = format_nepal_number(number, nepali_digits=nepali_digits)
    return f"रु. {rendered} {unit_ne}{suffix}" if language == "ne" else f"NPR {rendered} {unit_en}{suffix}"


def format_nepal_phone(value, *, international=True, nepali_digits=False):
    valid = is_valid_nepal_phone(value)
    normalized = normalize_nepal_phone(value)
    digits = normalized.lstrip("+")
    if digits.startswith("977"):
        digits = digits[3:]
    if len(digits) == 10 and digits.startswith(("97", "98")):
        rendered = f"{digits[:3]} {digits[3:6]} {digits[6:]}"
    elif len(digits) == 10 and digits.startswith("01"):
        rendered = f"{digits[:2]}-{digits[2:6]} {digits[6:]}"
    else:
        rendered = normalized
    if international and valid and rendered and not rendered.startswith("+"):
        rendered = f"+977 {rendered}"
    return to_nepali_digits(rendered) if nepali_digits else rendered


def format_nepal_address(obj, *, language="en", nepali_digits=False):
    values = {
        "tole": getattr(obj, "tole", ""),
        "ward": getattr(obj, "ward_number", ""),
        "municipality": getattr(obj, "municipality", "") or getattr(obj, "city", ""),
        "district": getattr(obj, "district", ""),
        "province": getattr(obj, "province", ""),
    }
    ward = ""
    if values["ward"]:
        ward = f"वडा नं. {values['ward']}" if language == "ne" else f"Ward {values['ward']}"
    parts = [values["tole"], ward, values["municipality"], values["district"], values["province"]]
    rendered = ", ".join(str(part).strip() for part in parts if str(part).strip())
    if rendered:
        rendered += ", नेपाल" if language == "ne" else ", Nepal"
    return to_nepali_digits(rendered) if nepali_digits else rendered
