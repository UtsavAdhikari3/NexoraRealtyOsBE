from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from django.core.files.base import ContentFile
from django.db.models import Q
from PIL import Image, ImageOps

from .models import PropertyMedia


RENDITION_FIELDS = ("file", "thumbnail", "card_image", "large_image")


def _referenced_elsewhere(name, exclude_pk=None):
    if not name:
        return False
    query = Q()
    for field in RENDITION_FIELDS:
        query |= Q(**{field: name})
    queryset = PropertyMedia.objects.filter(query)
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.exists()


def delete_unreferenced_files(files, exclude_pk=None):
    seen = set()
    for field_file in files:
        name = getattr(field_file, "name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        if _referenced_elsewhere(name, exclude_pk=exclude_pk):
            continue
        try:
            field_file.storage.delete(name)
        except OSError:
            # Storage cleanup is best-effort and may be retried operationally.
            pass


def media_files(instance):
    files = []
    for field in RENDITION_FIELDS:
        field_file = getattr(instance, field, None)
        if field_file and field_file.name:
            files.append(SimpleNamespace(name=field_file.name, storage=field_file.storage))
    return files


def file_references(*field_files):
    return [
        SimpleNamespace(name=field_file.name, storage=field_file.storage)
        for field_file in field_files
        if field_file and field_file.name
    ]


def _webp_content(image, max_width, quality):
    output = image.copy()
    if output.width > max_width:
        height = max(1, round(output.height * max_width / output.width))
        output = output.resize((max_width, height), Image.Resampling.LANCZOS)
    if output.mode not in {"RGB", "RGBA"}:
        output = output.convert("RGBA" if "transparency" in output.info else "RGB")
    if output.mode == "RGBA":
        background = Image.new("RGB", output.size, "white")
        background.paste(output, mask=output.getchannel("A"))
        output = background
    buffer = BytesIO()
    output.save(buffer, format="WEBP", quality=quality, method=6)
    return ContentFile(buffer.getvalue()), output.size


def generate_property_media_renditions(instance):
    old_renditions = file_references(instance.card_image, instance.large_image)
    if instance.media_type != "image" or not instance.file:
        instance.card_image = None
        instance.large_image = None
        instance.original_width = instance.original_height = None
        instance.card_width = instance.card_height = None
        instance.large_width = instance.large_height = None
        instance.save(update_fields=[
            "card_image", "large_image", "original_width", "original_height",
            "card_width", "card_height", "large_width", "large_height",
        ])
        delete_unreferenced_files(old_renditions, exclude_pk=instance.pk)
        return instance

    instance.file.open("rb")
    try:
        with Image.open(instance.file) as uploaded:
            image = ImageOps.exif_transpose(uploaded)
            image.load()
            instance.original_width, instance.original_height = image.size
            card_content, card_size = _webp_content(image, 720, 82)
            large_content, large_size = _webp_content(image, 1800, 88)
    finally:
        instance.file.close()

    stem = Path(instance.file.name).stem[:80] or "property-image"
    token = uuid4().hex[:10]
    instance.card_image.save(f"{stem}-{instance.pk}-{token}-card.webp", card_content, save=False)
    instance.large_image.save(f"{stem}-{instance.pk}-{token}-large.webp", large_content, save=False)
    instance.card_width, instance.card_height = card_size
    instance.large_width, instance.large_height = large_size
    instance.save(update_fields=[
        "card_image", "large_image", "original_width", "original_height",
        "card_width", "card_height", "large_width", "large_height",
    ])
    delete_unreferenced_files(old_renditions, exclude_pk=instance.pk)
    return instance
