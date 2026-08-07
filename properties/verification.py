from django.db import transaction

from .models import PropertyVerification, PropertyVerificationDocument


@transaction.atomic
def get_or_create_verification(property_obj):
    verification, _ = PropertyVerification.objects.get_or_create(
        property=property_obj,
        defaults={"agency": property_obj.agency},
    )
    existing = set(verification.documents.values_list("document_type", flat=True))
    PropertyVerificationDocument.objects.bulk_create([
        PropertyVerificationDocument(
            verification=verification,
            agency=property_obj.agency,
            document_type=document_type,
        )
        for document_type, _ in PropertyVerificationDocument.DOCUMENT_TYPES
        if document_type not in existing
    ])
    return verification
