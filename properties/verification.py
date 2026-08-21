from django.db import transaction

from .models import (
    PropertyHistory,
    PropertyVerification,
    PropertyVerificationDocument,
)


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


@transaction.atomic
def reconcile_verification(verification, *, actor=None, reason="Document checklist changed"):
    """Downgrade milestones that are no longer supported by the checklist."""
    verification = PropertyVerification.objects.select_for_update().get(pk=verification.pk)
    documents = {
        item.document_type: item.status
        for item in verification.documents.all()
    }
    statuses = list(documents.values())
    lalpurja_received = documents.get("lalpurja") not in {None, "missing"}
    all_resolved = bool(statuses) and all(
        status in {"approved", "rejected", "not_applicable"}
        for status in statuses
    )
    all_approved = bool(statuses) and all(
        status in {"approved", "not_applicable"}
        for status in statuses
    )

    valid = {
        "owner_identity_verified": verification.owner_identity_verified,
        "ownership_document_received": (
            verification.owner_identity_verified and lalpurja_received
        ),
        "physically_inspected": (
            verification.owner_identity_verified
            and lalpurja_received
            and verification.physically_inspected
        ),
        "documents_reviewed": (
            verification.owner_identity_verified
            and lalpurja_received
            and verification.physically_inspected
            and all_resolved
        ),
        "fully_verified": (
            verification.owner_identity_verified
            and lalpurja_received
            and verification.physically_inspected
            and all_resolved
            and all_approved
        ),
    }
    changes = {}
    update_fields = []
    for field, _ in PropertyVerification.MILESTONES:
        current = getattr(verification, field)
        target = current and valid[field]
        if current == target:
            continue
        changes[field] = {"from": current, "to": target}
        setattr(verification, field, target)
        setattr(verification, f"{field}_at", None if not target else getattr(verification, f"{field}_at"))
        update_fields.extend([field, f"{field}_at"])

    if update_fields:
        verification.updated_by = actor
        update_fields.extend(["updated_by", "updated_at"])
        verification.save(update_fields=update_fields)
        PropertyHistory.objects.create(
            agency=verification.agency,
            property=verification.property,
            actor=actor,
            event_type="verification_changed",
            summary="Verification level recalculated",
            changes=changes,
            note=reason,
        )
    return verification
