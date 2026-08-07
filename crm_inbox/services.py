import hashlib
import hmac
import json
from datetime import datetime, timezone as datetime_timezone

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from leads.models import LeadInteraction
from social_media.models import SocialAccount

from .models import Conversation, SocialContact, SocialMessage, WebhookEvent


def verify_meta_signature(raw_body, signature_header):
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.META_APP_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature_header[7:], expected)


def timestamp_from_milliseconds(value):
    try:
        return datetime.fromtimestamp(
            int(value) / 1000,
            tz=datetime_timezone.utc,
        )
    except (TypeError, ValueError, OSError):
        return timezone.now()


def find_receiving_account(object_type, external_id):
    queryset = SocialAccount.objects.filter(
        provider=SocialAccount.PROVIDER_META,
        status=SocialAccount.STATUS_CONNECTED,
    )
    if object_type == "instagram":
        return queryset.filter(
            platform=SocialAccount.PLATFORM_INSTAGRAM,
            external_id=external_id,
        ).first()
    return queryset.filter(
        platform=SocialAccount.PLATFORM_FACEBOOK,
        page_id=external_id,
    ).first()


def normalize_attachments(message):
    results = []
    for attachment in message.get("attachments", []):
        payload = attachment.get("payload") or {}
        results.append(
            {
                "type": attachment.get("type", "file"),
                "url": payload.get("url", ""),
                "title": attachment.get("title", ""),
            }
        )
    return results


def infer_message_type(message, attachments, is_postback=False):
    if is_postback:
        return SocialMessage.TYPE_POSTBACK
    if message.get("text"):
        return SocialMessage.TYPE_TEXT
    if attachments:
        attachment_type = attachments[0].get("type")
        supported = dict(SocialMessage.TYPE_CHOICES)
        return attachment_type if attachment_type in supported else SocialMessage.TYPE_FILE
    return SocialMessage.TYPE_UNSUPPORTED


@transaction.atomic
def ingest_messaging_event(account, event):
    message = event.get("message")
    postback = event.get("postback")

    if event.get("delivery"):
        mids = event["delivery"].get("mids", [])
        SocialMessage.objects.filter(
            social_account=account,
            provider_message_id__in=mids,
            direction=SocialMessage.DIRECTION_OUTBOUND,
        ).update(delivery_status=SocialMessage.STATUS_DELIVERED)
        return

    if event.get("read"):
        watermark = timestamp_from_milliseconds(event["read"].get("watermark"))
        SocialMessage.objects.filter(
            social_account=account,
            direction=SocialMessage.DIRECTION_OUTBOUND,
            sent_at__lte=watermark,
        ).update(delivery_status=SocialMessage.STATUS_READ)
        return

    if not message and not postback:
        return

    payload = message or postback
    is_echo = bool(message and message.get("is_echo"))
    sender_id = str((event.get("sender") or {}).get("id", ""))
    recipient_id = str((event.get("recipient") or {}).get("id", ""))
    contact_external_id = recipient_id if is_echo else sender_id
    if not contact_external_id:
        return

    contact, _ = SocialContact.objects.get_or_create(
        agency=account.agency,
        social_account=account,
        platform=account.platform,
        external_user_id=contact_external_id,
        defaults={"display_name": contact_external_id},
    )
    conversation, _ = Conversation.objects.get_or_create(
        agency=account.agency,
        social_account=account,
        contact=contact,
        platform=account.platform,
        external_conversation_id=contact_external_id,
        defaults={"linked_lead": contact.linked_lead},
    )

    attachments = normalize_attachments(message or {})
    text = payload.get("text") or payload.get("title") or payload.get("payload") or ""
    provider_message_id = payload.get("mid")
    if not provider_message_id:
        provider_message_id = hashlib.sha256(
            json.dumps(event, sort_keys=True).encode("utf-8")
        ).hexdigest()

    direction = (
        SocialMessage.DIRECTION_OUTBOUND
        if is_echo
        else SocialMessage.DIRECTION_INBOUND
    )
    sent_at = timestamp_from_milliseconds(event.get("timestamp"))
    social_message, created = SocialMessage.objects.get_or_create(
        social_account=account,
        provider_message_id=provider_message_id,
        defaults={
            "conversation": conversation,
            "direction": direction,
            "message_type": infer_message_type(
                message or {},
                attachments,
                is_postback=bool(postback),
            ),
            "sender_external_id": sender_id,
            "text": text,
            "attachments": attachments,
            "delivery_status": (
                SocialMessage.STATUS_SENT
                if is_echo
                else SocialMessage.STATUS_RECEIVED
            ),
            "sent_at": sent_at,
        },
    )
    if not created:
        return

    preview = text or (
        f"[{attachments[0].get('type', 'attachment').title()}]"
        if attachments
        else "[Unsupported message]"
    )
    update_values = {
        "last_message_at": sent_at,
        "last_message_preview": preview[:255],
        "status": Conversation.STATUS_OPEN,
    }
    if direction == SocialMessage.DIRECTION_INBOUND:
        Conversation.objects.filter(id=conversation.id).update(
            unread_count=F("unread_count") + 1,
            **update_values,
        )
        if conversation.linked_lead_id:
            LeadInteraction.objects.create(
                agency=conversation.agency,
                lead=conversation.linked_lead,
                interaction_type=account.platform,
                direction="inbound",
                note=f"Inbound {account.platform} message: {preview}",
            )
            lead = conversation.linked_lead
            lead.last_contacted_at = sent_at
            lead.save(update_fields=["last_contacted_at", "updated_at"])
    else:
        Conversation.objects.filter(id=conversation.id).update(**update_values)


def process_meta_payload(payload):
    object_type = payload.get("object", "")
    for entry in payload.get("entry", []):
        account = find_receiving_account(object_type, str(entry.get("id", "")))
        if not account:
            continue
        for messaging_event in entry.get("messaging", []):
            ingest_messaging_event(account, messaging_event)


def record_and_process_webhook(raw_body):
    payload = json.loads(raw_body.decode("utf-8"))
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    event, created = WebhookEvent.objects.get_or_create(
        payload_hash=payload_hash,
        defaults={
            "provider": "meta",
            "object_type": payload.get("object", ""),
            "raw_payload": payload,
        },
    )
    if not created and event.status == WebhookEvent.STATUS_PROCESSED:
        return event, False

    event.attempts += 1
    try:
        process_meta_payload(payload)
        event.status = WebhookEvent.STATUS_PROCESSED
        event.processed_at = timezone.now()
        event.error_message = ""
    except Exception as exc:
        event.status = WebhookEvent.STATUS_FAILED
        event.error_message = str(exc)
    event.save()
    return event, created
