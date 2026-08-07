import csv
import io
import os
import re
import tempfile
import zipfile
from decimal import Decimal

import qrcode
from django.conf import settings
from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ASSET_SPECS = {
    "facebook_post": (1200, 630, "Facebook post image", "jpg"),
    "instagram_post": (1080, 1080, "Instagram post image", "jpg"),
    "instagram_story": (1080, 1920, "Instagram story", "jpg"),
    "watermarked_images": (None, None, "Watermarked property images", "zip"),
    "brochure": (None, None, "Agency-branded brochure", "pdf"),
    "window_card": (None, None, "Printable window card", "pdf"),
    "qr_code": (None, None, "QR code", "png"),
    "portal_csv": (None, None, "Portal CSV row", "csv"),
    "media_package": (None, None, "Complete property media package", "zip"),
}


def _safe_name(value):
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value or "property").strip("-")[:80]


def _brand_color(agency):
    value = agency.primary_color or "#496B5A"
    try:
        return ImageColor.getrgb(value)
    except ValueError:
        return ImageColor.getrgb("#496B5A")


def _font(size, bold=False):
    names = ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "Arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _primary_media(property_obj):
    media = [item for item in property_obj.media.all() if item.media_type == "image" and item.file]
    return next((item for item in media if item.is_primary), media[0] if media else None)


def _open_media_image(media):
    if not media or not media.file:
        return None
    try:
        media.file.open("rb")
        image = Image.open(media.file)
        image.load()
        return ImageOps.exif_transpose(image).convert("RGB")
    except (OSError, ValueError):
        return None
    finally:
        try:
            media.file.close()
        except Exception:
            pass


def _cover(image, size, brand):
    if image:
        return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    canvas_image = Image.new("RGB", size, brand)
    draw = ImageDraw.Draw(canvas_image)
    for y in range(size[1]):
        ratio = y / max(1, size[1] - 1)
        color = tuple(int(channel * (1 - ratio * 0.35)) for channel in brand)
        draw.line((0, y, size[0], y), fill=color)
    return canvas_image


def _draw_wrapped(draw, text, xy, font, fill, max_width, max_lines=3, spacing=8):
    words = str(text or "").split()
    lines, line = [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
            if len(lines) == max_lines - 1:
                break
    if line and len(lines) < max_lines:
        lines.append(line)
    y = xy[1]
    for item in lines:
        draw.text((xy[0], y), item, font=font, fill=fill)
        y += draw.textbbox((0, 0), item, font=font)[3] + spacing
    return y


def format_price(property_obj):
    price = Decimal(property_obj.price or 0)
    suffix = " / month" if property_obj.purpose == "rent" else ""
    if price >= Decimal("10000000"):
        value = f"NPR {price / Decimal('10000000'):.2f} Crore"
    elif price >= Decimal("100000"):
        value = f"NPR {price / Decimal('100000'):.2f} Lakh"
    else:
        value = f"NPR {price:,.0f}"
    return value.replace(".00 ", " ") + suffix


def format_area(property_obj):
    if property_obj.land_area_value and property_obj.land_area_unit:
        return f"{property_obj.land_area_value:g} {property_obj.land_area_unit.title()}"
    if property_obj.built_up_area_value and property_obj.built_up_area_unit:
        return f"{property_obj.built_up_area_value:g} {property_obj.built_up_area_unit.title()}"
    return "Area on request"


def property_location(property_obj):
    return ", ".join(filter(None, [
        property_obj.tole, property_obj.municipality or property_obj.city,
        property_obj.district,
    ]))


def canonical_property_url(property_obj):
    base = settings.STOREFRONT_PUBLIC_URL.rstrip("/")
    return f"{base}/agency/{property_obj.agency.slug}/properties/{property_obj.id}"


def tracked_url(link, request=None):
    path = f"/api/public/s/{link.code}/"
    if settings.PUBLIC_API_BASE_URL:
        return f"{settings.PUBLIC_API_BASE_URL.rstrip('/')}/api/public/s/{link.code}/"
    return request.build_absolute_uri(path) if request else path


def qr_png(url, box_size=10):
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def captions(property_obj, url):
    purpose_en = {"sale": "For sale", "rent": "For rent", "lease": "For lease"}.get(property_obj.purpose, "Available")
    purpose_ne = {"sale": "बिक्रीमा", "rent": "भाडामा", "lease": "लिजमा"}.get(property_obj.purpose, "उपलब्ध")
    location = property_location(property_obj)
    details = " | ".join(filter(None, [
        f"{property_obj.bedrooms} bedrooms" if property_obj.bedrooms else "",
        format_area(property_obj),
        f"{property_obj.road_access_value:g} {property_obj.road_access_unit} road" if property_obj.road_access_value else "",
    ]))
    hashtags = "#NepalRealEstate #PropertyInNepal #NexoraRealtyOS"
    english = (
        f"{purpose_en}: {property_obj.title}\n"
        f"Location: {location}\nPrice: {format_price(property_obj)}\n"
        f"{details}\n\n{property_obj.short_description or property_obj.description[:220]}\n\n"
        f"View details and enquire: {url}\n{hashtags}"
    ).strip()
    nepali = (
        f"{purpose_ne}: {property_obj.title}\n"
        f"स्थान: {location}\nमूल्य: {format_price(property_obj)}\n"
        f"विवरण: {details}\n\n{property_obj.short_description or property_obj.description[:220]}\n\n"
        f"थप जानकारी र सम्पर्क: {url}\n#नेपालघरजग्गा #जग्गाबिक्री #घरबिक्री"
    ).strip()
    short_en = f"{property_obj.title} - {format_price(property_obj)} at {location}. Details: {url}"
    short_ne = f"{property_obj.title} - {location} मा {format_price(property_obj)}। थप जानकारी: {url}"
    return {
        "english": {
            "facebook": english,
            "instagram": english,
            "story": f"{purpose_en.upper()}\n{property_obj.title}\n{format_price(property_obj)}\n{url}",
            "whatsapp": short_en,
            "viber": short_en,
        },
        "nepali": {
            "facebook": nepali,
            "instagram": nepali,
            "story": f"{purpose_ne}\n{property_obj.title}\n{format_price(property_obj)}\n{url}",
            "whatsapp": short_ne,
            "viber": short_ne,
        },
    }


def portal_ad(property_obj, url, language="english"):
    agency = property_obj.agency
    contact = property_obj.assigned_agent.phone if property_obj.assigned_agent and property_obj.assigned_agent.phone else agency.phone
    facts = [
        f"Type: {property_obj.get_property_type_display()}",
        f"Purpose: {property_obj.get_purpose_display()}",
        f"Price: {format_price(property_obj)}",
        f"Location: {property_location(property_obj)}",
        f"Area: {format_area(property_obj)}",
        f"Road: {property_obj.road_access_value:g} {property_obj.road_access_unit} {property_obj.get_road_type_display() if property_obj.road_type else ''}" if property_obj.road_access_value else "",
        f"Facing: {property_obj.get_facing_direction_display()}" if property_obj.facing_direction else "",
        f"Contact: {contact}" if contact else "",
        f"Listing: {url}",
    ]
    if language == "nepali":
        return captions(property_obj, url)["nepali"]["facebook"]
    return "\n".join([property_obj.title, property_obj.description or property_obj.short_description, "", *filter(None, facts)])


def social_image(property_obj, asset_type, url):
    width, height, _, _ = ASSET_SPECS[asset_type]
    brand = _brand_color(property_obj.agency)
    hero_ratio = 0.65 if asset_type != "instagram_story" else 0.62
    hero_height = int(height * hero_ratio)
    result = _cover(_open_media_image(_primary_media(property_obj)), (width, hero_height), brand)
    canvas_image = Image.new("RGB", (width, height), "white")
    canvas_image.paste(result, (0, 0))
    overlay = Image.new("RGBA", (width, hero_height), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle((0, int(hero_height * .68), width, hero_height), fill=(0, 0, 0, 135))
    canvas_image.paste(overlay, (0, 0), overlay)
    draw = ImageDraw.Draw(canvas_image)
    margin = int(width * .055)
    draw.text((margin, int(hero_height * .74)), property_obj.agency.name, font=_font(max(22, width // 35), True), fill="white")
    panel_top = hero_height
    draw.rectangle((0, panel_top, width, height), fill=brand)
    title_size = max(34, width // (20 if asset_type == "facebook_post" else 18))
    title_y = panel_top + int((height - panel_top) * .12)
    title_end = _draw_wrapped(draw, property_obj.title, (margin, title_y), _font(title_size, True), "white", int(width * .67), 2, 4)
    draw.text((margin, title_end + 8), f"{format_price(property_obj)}  |  {property_location(property_obj)}", font=_font(max(20, width // 43)), fill=(235, 243, 238))
    qr_size = int(min(width, height) * (.17 if asset_type == "instagram_story" else .19))
    qr_image = Image.open(io.BytesIO(qr_png(url, box_size=8))).convert("RGB").resize((qr_size, qr_size), Image.Resampling.NEAREST)
    canvas_image.paste(qr_image, (width - margin - qr_size, height - margin - qr_size))
    draw.text((width - margin - qr_size, height - margin - qr_size - 26), "SCAN TO VIEW", font=_font(18, True), fill="white")
    output = io.BytesIO()
    canvas_image.save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()


def watermarked_image(image, property_obj):
    image = image.convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(max(18, image.width // 38), True)
    text = f"{property_obj.agency.name}  |  {property_obj.agency.phone or property_obj.agency.license_number}"
    bounds = draw.textbbox((0, 0), text, font=font)
    padding = max(12, image.width // 80)
    x = image.width - (bounds[2] - bounds[0]) - padding * 2
    y = image.height - (bounds[3] - bounds[1]) - padding * 2
    draw.rounded_rectangle((x - padding, y - padding, image.width, image.height), radius=padding, fill=(0, 0, 0, 145))
    draw.text((x, y), text, font=font, fill="white")
    result = Image.alpha_composite(image, overlay).convert("RGB")
    output = io.BytesIO()
    result.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()


def watermarked_zip(property_obj):
    output = tempfile.SpooledTemporaryFile(max_size=20 * 1024 * 1024)
    count = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, media in enumerate(property_obj.media.all(), 1):
            if media.media_type != "image" or not media.file:
                continue
            image = _open_media_image(media)
            if not image:
                continue
            archive.writestr(f"watermarked/{index:02d}-{_safe_name(media.title or property_obj.title)}.jpg", watermarked_image(image, property_obj))
            count += 1
        if not count:
            archive.writestr("README.txt", "No uploaded property images were available for watermarking.")
    output.seek(0)
    return output


def _pdf_wrap(pdf, text, x, y, max_width, font="Helvetica", size=10, leading=14, max_lines=None):
    words = str(text or "").split()
    lines, line = [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if pdf.stringWidth(candidate, font, size) <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
            if max_lines and len(lines) >= max_lines - 1:
                break
    if line and (not max_lines or len(lines) < max_lines):
        lines.append(line)
    pdf.setFont(font, size)
    for line in lines:
        pdf.drawString(x, y, line)
        y -= leading
    return y


def brochure_pdf(property_obj, url):
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    page_width, page_height = A4
    brand_hex = property_obj.agency.primary_color or "#496B5A"
    try:
        brand = HexColor(brand_hex)
    except ValueError:
        brand = HexColor("#496B5A")
    hero = _cover(_open_media_image(_primary_media(property_obj)), (1400, 800), _brand_color(property_obj.agency))
    hero_bytes = io.BytesIO(); hero.save(hero_bytes, "JPEG", quality=90); hero_bytes.seek(0)
    pdf.drawImage(ImageReader(hero_bytes), 0, page_height - 360, width=page_width, height=360, mask="auto")
    pdf.setFillColorRGB(0, 0, 0, alpha=.62)
    pdf.rect(0, page_height - 360, page_width, 105, stroke=0, fill=1)
    pdf.setFillColor(white); pdf.setFont("Helvetica-Bold", 11); pdf.drawString(34, page_height - 282, property_obj.agency.name)
    pdf.setFont("Helvetica-Bold", 25)
    _pdf_wrap(pdf, property_obj.title, 34, page_height - 312, page_width - 68, "Helvetica-Bold", 25, 28, 2)
    pdf.setFillColor(brand); pdf.rect(0, 0, page_width, page_height - 360, stroke=0, fill=1)
    pdf.setFillColor(white); pdf.setFont("Helvetica-Bold", 24); pdf.drawString(34, page_height - 407, format_price(property_obj))
    pdf.setFont("Helvetica", 11); pdf.drawString(34, page_height - 430, property_location(property_obj))
    facts = [
        ("Property", property_obj.get_property_type_display()), ("Purpose", property_obj.get_purpose_display()),
        ("Area", format_area(property_obj)), ("Bedrooms", str(property_obj.bedrooms or "-")),
        ("Bathrooms", str(property_obj.bathrooms or "-")),
        ("Road access", f"{property_obj.road_access_value:g} {property_obj.road_access_unit}" if property_obj.road_access_value else "On request"),
    ]
    y = page_height - 485
    for index, (label, value) in enumerate(facts):
        col = index % 2; row = index // 2
        x = 34 + col * 270; item_y = y - row * 52
        pdf.setFillColorRGB(1, 1, 1, alpha=.72); pdf.setFont("Helvetica", 8); pdf.drawString(x, item_y, label.upper())
        pdf.setFillColor(white); pdf.setFont("Helvetica-Bold", 12); pdf.drawString(x, item_y - 17, value)
    qr_data = qr_png(url); pdf.drawImage(ImageReader(io.BytesIO(qr_data)), page_width - 137, 35, 102, 102)
    pdf.setFillColor(white); pdf.setFont("Helvetica-Bold", 9); pdf.drawString(34, 105, "SCAN FOR LIVE DETAILS AND ENQUIRY")
    pdf.setFont("Helvetica", 9); pdf.drawString(34, 88, property_obj.agency.phone or property_obj.agency.email or property_obj.agency.license_number)
    pdf.drawString(34, 71, url[:78])
    pdf.showPage()
    pdf.setFillColor(brand); pdf.rect(0, page_height - 92, page_width, 92, stroke=0, fill=1)
    pdf.setFillColor(white); pdf.setFont("Helvetica-Bold", 22); pdf.drawString(34, page_height - 55, "Property details")
    pdf.setFont("Helvetica", 10); pdf.drawString(34, page_height - 74, property_obj.agency.name)
    pdf.setFillColor(HexColor("#263238")); y = page_height - 130
    y = _pdf_wrap(pdf, property_obj.description or property_obj.short_description or "Contact the agency for full details.", 34, y, page_width - 68, "Helvetica", 11, 16, 14)
    y -= 22
    detail_rows = [
        ("Address", property_obj.address or property_location(property_obj)),
        ("Land classification", property_obj.get_land_use_classification_display() if property_obj.land_use_classification else "-"),
        ("Road", f"{property_obj.get_road_type_display() if property_obj.road_type else ''} {property_obj.road_access_value or ''} {property_obj.road_access_unit or ''}".strip()),
        ("Facing", property_obj.get_facing_direction_display() if property_obj.facing_direction else "-"),
        ("Utilities", ", ".join(label for label, value in [("Water", property_obj.has_water_supply), ("Electricity", property_obj.has_electricity), ("Drainage", property_obj.has_drainage), ("Sewage", property_obj.has_sewage)] if value) or "Ask agency"),
        ("Listing ID", f"LP-{property_obj.id:03d}"),
    ]
    for label, value in detail_rows:
        pdf.setFillColor(HexColor("#637079")); pdf.setFont("Helvetica-Bold", 9); pdf.drawString(34, y, label.upper())
        pdf.setFillColor(HexColor("#263238")); pdf.setFont("Helvetica", 11); pdf.drawString(180, y, str(value)[:70]); y -= 30
    pdf.setStrokeColor(HexColor("#DDE5E3")); pdf.line(34, 78, page_width - 34, 78)
    pdf.setFont("Helvetica", 8); pdf.setFillColor(HexColor("#637079")); pdf.drawString(34, 55, "Information is subject to owner confirmation and agency verification.")
    pdf.drawRightString(page_width - 34, 55, f"Generated by Nexora RealtyOS | LP-{property_obj.id:03d}")
    pdf.save(); output.seek(0)
    return output.getvalue()


def window_card_pdf(property_obj, url):
    output = io.BytesIO(); pdf = canvas.Canvas(output, pagesize=A4); width, height = A4
    brand_hex = property_obj.agency.primary_color or "#496B5A"
    try: brand = HexColor(brand_hex)
    except ValueError: brand = HexColor("#496B5A")
    hero = _cover(_open_media_image(_primary_media(property_obj)), (1400, 900), _brand_color(property_obj.agency))
    hero_bytes = io.BytesIO(); hero.save(hero_bytes, "JPEG", quality=90); hero_bytes.seek(0)
    pdf.drawImage(ImageReader(hero_bytes), 0, height - 430, width=width, height=350, mask="auto")
    pdf.setFillColor(brand); pdf.rect(0, height - 80, width, 80, stroke=0, fill=1)
    pdf.setFillColor(white); pdf.setFont("Helvetica-Bold", 22); pdf.drawString(28, height - 48, property_obj.agency.name)
    pdf.setFont("Helvetica", 10); pdf.drawRightString(width - 28, height - 48, property_obj.agency.phone or property_obj.agency.license_number)
    pdf.setFillColor(HexColor("#263238")); pdf.setFont("Helvetica-Bold", 27)
    title_y = _pdf_wrap(pdf, property_obj.title, 28, height - 468, width - 56, "Helvetica-Bold", 27, 31, 2)
    pdf.setFillColor(brand); pdf.setFont("Helvetica-Bold", 29); pdf.drawString(28, title_y - 14, format_price(property_obj))
    pdf.setFillColor(HexColor("#637079")); pdf.setFont("Helvetica", 13); pdf.drawString(28, title_y - 40, property_location(property_obj))
    pdf.setFillColor(HexColor("#F1F5F3")); pdf.roundRect(28, 90, width - 56, 105, 10, stroke=0, fill=1)
    facts = [property_obj.get_property_type_display(), format_area(property_obj), f"{property_obj.bedrooms} Beds" if property_obj.bedrooms else "", f"{property_obj.road_access_value:g} {property_obj.road_access_unit} Road" if property_obj.road_access_value else ""]
    pdf.setFillColor(HexColor("#263238")); pdf.setFont("Helvetica-Bold", 12); pdf.drawString(48, 161, "  |  ".join(filter(None, facts)))
    pdf.setFont("Helvetica", 10); pdf.drawString(48, 138, f"Listing LP-{property_obj.id:03d} - Scan the QR code for live availability and enquiry.")
    pdf.drawImage(ImageReader(io.BytesIO(qr_png(url))), width - 126, 100, 82, 82)
    pdf.setFillColor(brand); pdf.rect(0, 0, width, 64, stroke=0, fill=1)
    pdf.setFillColor(white); pdf.setFont("Helvetica-Bold", 12); pdf.drawCentredString(width / 2, 37, "CALL OR MESSAGE THE AGENCY TO ARRANGE A VIEWING")
    pdf.setFont("Helvetica", 9); pdf.drawCentredString(width / 2, 21, url[:90])
    pdf.save(); output.seek(0)
    return output.getvalue()


PORTAL_COLUMNS = [
    "listing_id", "title", "purpose", "property_type", "price_npr", "province",
    "district", "municipality", "ward", "tole", "landmark", "address",
    "land_area", "land_area_unit", "built_up_area", "built_up_area_unit",
    "bedrooms", "bathrooms", "floors", "road_width", "road_unit", "road_type",
    "facing", "latitude", "longitude", "description", "contact_name", "contact_phone",
    "listing_url",
]


def portal_csv(properties, request=None):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=PORTAL_COLUMNS)
    writer.writeheader()
    for item in properties:
        agent = item.assigned_agent
        writer.writerow({
            "listing_id": f"LP-{item.id:03d}", "title": item.title,
            "purpose": item.purpose, "property_type": item.property_type,
            "price_npr": item.price, "province": item.province, "district": item.district,
            "municipality": item.municipality or item.city, "ward": item.ward_number,
            "tole": item.tole, "landmark": item.landmark, "address": item.address,
            "land_area": item.land_area_value or "", "land_area_unit": item.land_area_unit,
            "built_up_area": item.built_up_area_value or "", "built_up_area_unit": item.built_up_area_unit,
            "bedrooms": item.bedrooms, "bathrooms": item.bathrooms, "floors": item.floors,
            "road_width": item.road_access_value or "", "road_unit": item.road_access_unit,
            "road_type": item.road_type, "facing": item.facing_direction or "",
            "latitude": item.latitude or "", "longitude": item.longitude or "",
            "description": item.description or item.short_description,
            "contact_name": agent.full_name if agent else item.agency.name,
            "contact_phone": agent.phone if agent and agent.phone else item.agency.phone or "",
            "listing_url": canonical_property_url(item),
        })
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def media_package(property_obj, url):
    output = tempfile.SpooledTemporaryFile(max_size=30 * 1024 * 1024)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, media in enumerate(property_obj.media.all(), 1):
            if not media.file:
                continue
            extension = os.path.splitext(media.file.name)[1].lower() or ".bin"
            try:
                media.file.open("rb")
                archive.writestr(f"original-media/{index:02d}-{_safe_name(media.title or property_obj.title)}{extension}", media.file.read())
            except OSError:
                pass
            finally:
                try: media.file.close()
                except Exception: pass
            if media.media_type == "image":
                image = _open_media_image(media)
                if image:
                    archive.writestr(f"watermarked/{index:02d}-{_safe_name(media.title or property_obj.title)}.jpg", watermarked_image(image, property_obj))
        archive.writestr("social/facebook-post.jpg", social_image(property_obj, "facebook_post", url))
        archive.writestr("social/instagram-post.jpg", social_image(property_obj, "instagram_post", url))
        archive.writestr("social/instagram-story.jpg", social_image(property_obj, "instagram_story", url))
        archive.writestr("print/property-brochure.pdf", brochure_pdf(property_obj, url))
        archive.writestr("print/window-card.pdf", window_card_pdf(property_obj, url))
        archive.writestr("qr/property-qr.png", qr_png(url))
        text = captions(property_obj, url)
        archive.writestr("copy/english-captions.txt", "\n\n---\n\n".join(text["english"].values()))
        archive.writestr("copy/nepali-captions.txt", "\n\n---\n\n".join(text["nepali"].values()))
        archive.writestr("copy/portal-ad-english.txt", portal_ad(property_obj, url))
        archive.writestr("copy/portal-ad-nepali.txt", portal_ad(property_obj, url, "nepali"))
        archive.writestr("portal/property.csv", portal_csv([property_obj]))
    output.seek(0)
    return output
