import hashlib
import hmac
import json
from datetime import datetime, timezone as datetime_timezone

import requests
from django.conf import settings
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone

from leads.automation import apply_lead_automation
from leads.models import Lead, LeadInteraction, LeadStatusHistory
from social_media.models import SocialAccount, SocialPublishResult
from social_media.services.meta import MetaAPIError, get_meta_messaging_profile

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


def extract_referral(event, message, postback):
    for candidate in (
        event.get("referral"),
        (message or {}).get("referral"),
        (postback or {}).get("referral"),
    ):
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def find_referral_post(account, referral):
    identifiers = {
        str(referral.get(key))
        for key in ("post_id", "media_id", "publication_id")
        if referral.get(key)
    }
    if not identifiers:
        return None
    result = SocialPublishResult.objects.select_related("post").filter(
        social_account=account,
    ).filter(
        models.Q(external_post_id__in=identifiers)
        | models.Q(external_media_id__in=identifiers)
    ).first()
    return result.post if result else None


def contact_profile_is_stale(contact):
    if not contact.profile_synced_at:
        return True
    refresh_before = timezone.now() - timezone.timedelta(
        hours=settings.SOCIAL_PROFILE_REFRESH_HOURS
    )
    return contact.profile_synced_at <= refresh_before


def refresh_social_contact_profile(contact, force=False):
    """Enrich a social contact without ever blocking message ingestion on failure."""
    if not settings.SOCIAL_PROFILE_LOOKUP_ENABLED:
        return contact
    if not force and not contact_profile_is_stale(contact):
        return contact

    synced_at = timezone.now()
    try:
        profile = get_meta_messaging_profile(
            contact.social_account,
            contact.external_user_id,
        )
    except (MetaAPIError, requests.RequestException) as exc:
        contact.profile_synced_at = synced_at
        contact.profile_lookup_error = str(exc)[:1000]
        if contact.display_name == contact.external_user_id:
            contact.display_name = ""
        contact.save(
            update_fields=[
                "display_name",
                "profile_synced_at",
                "profile_lookup_error",
                "last_seen_at",
            ]
        )
        return contact

    first_name = str(profile.get("first_name") or "").strip()
    last_name = str(profile.get("last_name") or "").strip()
    display_name = str(profile.get("name") or "").strip()
    if not display_name:
        display_name = " ".join(value for value in (first_name, last_name) if value)
    username = str(profile.get("username") or "").strip().lstrip("@")
    profile_image_url = str(
        profile.get("profile_pic") or profile.get("profile_picture_url") or ""
    ).strip()
    safe_profile_data = {
        key: profile[key]
        for key in (
            "follower_count",
            "is_user_follow_business",
            "is_business_follow_user",
            "is_verified_user",
        )
        if key in profile and profile[key] is not None
    }
    contact.display_name = display_name
    contact.username = username
    contact.profile_image_url = profile_image_url
    contact.profile_data = safe_profile_data
    contact.profile_synced_at = synced_at
    contact.profile_lookup_error = ""
    contact.save(
        update_fields=[
            "display_name",
            "username",
            "profile_image_url",
            "profile_data",
            "profile_synced_at",
            "profile_lookup_error",
            "last_seen_at",
        ]
    )

    if contact.linked_lead_id and (display_name or username):
        lead = contact.linked_lead
        generated_names = {
            contact.external_user_id,
            f"{contact.platform.title()} contact {contact.external_user_id[-6:]}",
        }
        if not lead.full_name or lead.full_name in generated_names:
            lead.full_name = display_name or f"@{username}"
            lead.save(update_fields=["full_name", "updated_at"])
    return contact


def ensure_automatic_social_lead(conversation, contact, referral=None):
    if conversation.linked_lead_id:
        lead = conversation.linked_lead
        custom_data = dict(lead.custom_data or {})
        if referral:
            custom_data["social_referral"] = referral
        if conversation.source_social_post_id:
            custom_data["source_social_post_id"] = conversation.source_social_post_id
        if custom_data != (lead.custom_data or {}):
            lead.custom_data = custom_data
            lead.save(update_fields=["custom_data", "updated_at"])
        return lead

    contact = SocialContact.objects.select_for_update().get(pk=contact.pk)
    if contact.linked_lead_id:
        conversation.linked_lead = contact.linked_lead
        conversation.save(update_fields=["linked_lead", "updated_at"])
        return contact.linked_lead

    social_key = f"{contact.social_account_id}:{contact.external_user_id}"
    lead = Lead.objects.filter(
        agency=conversation.agency,
        custom_data__social_contact_key=social_key,
    ).first()
    if lead is None:
        display_name = contact.username
        if not display_name and contact.display_name != contact.external_user_id:
            display_name = contact.display_name
        display_name = display_name or (
            f"{conversation.platform.title()} contact {contact.external_user_id[-6:]}"
        )
        custom_data = {
            "social_contact_key": social_key,
            "social_account_id": contact.social_account_id,
            "social_external_id": contact.external_user_id,
            "social_platform": conversation.platform,
        }
        if referral:
            custom_data["social_referral"] = referral
        if conversation.source_social_post_id:
            custom_data["source_social_post_id"] = conversation.source_social_post_id
        lead = Lead.objects.create(
            agency=conversation.agency,
            assigned_agent=conversation.assigned_agent,
            full_name=display_name,
            phone="",
            source=conversation.platform,
            status="new",
            custom_data=custom_data,
            notes="Automatically created from the first inbound social message.",
            last_contacted_at=conversation.last_message_at,
        )
        LeadStatusHistory.objects.create(
            agency=conversation.agency,
            lead=lead,
            to_status=lead.status,
        )
        apply_lead_automation(lead)

    contact.linked_lead = lead
    conversation.linked_lead = lead
    contact.save(update_fields=["linked_lead"])
    conversation.save(update_fields=["linked_lead", "updated_at"])
    return lead


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
    referral = extract_referral(event, message, postback)
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
        defaults={"display_name": ""},
    )
    conversation, _ = Conversation.objects.get_or_create(
        agency=account.agency,
        social_account=account,
        contact=contact,
        platform=account.platform,
        external_conversation_id=contact_external_id,
        defaults={"linked_lead": contact.linked_lead},
    )
    if referral:
        conversation.referral_data = referral
        source_post = find_referral_post(account, referral)
        if source_post:
            conversation.source_social_post = source_post
        conversation.save(
            update_fields=[
                "referral_data",
                "source_social_post",
                "updated_at",
            ]
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
            "referral_data": referral,
            "delivery_status": (
                SocialMessage.STATUS_SENT
                if is_echo
                else SocialMessage.STATUS_RECEIVED
            ),
            "sent_at": sent_at,
        },
    )
    if not created:
        return contact

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
        conversation.last_message_at = sent_at
        if settings.SOCIAL_AUTO_CREATE_LEADS:
            lead = ensure_automatic_social_lead(conversation, contact, referral)
            contact.linked_lead = lead
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
    return contact


def process_meta_payload(payload):
    object_type = payload.get("object", "")
    for entry in payload.get("entry", []):
        account = find_receiving_account(object_type, str(entry.get("id", "")))
        if not account:
            continue
        for messaging_event in entry.get("messaging", []):
            contact = ingest_messaging_event(account, messaging_event)
            if contact:
                refresh_social_contact_profile(contact)


def process_webhook_event(event):
    payload = event.raw_payload
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
    return event


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
    return process_webhook_event(event), created
