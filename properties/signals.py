from django.db.models.signals import post_delete
from django.dispatch import receiver

from .media_renditions import delete_unreferenced_files, media_files
from .models import PropertyMedia


@receiver(post_delete, sender=PropertyMedia)
def cleanup_property_media_files(sender, instance, **kwargs):
    delete_unreferenced_files(media_files(instance))
