from django.contrib import admin

from .models import Conversation, SocialContact, SocialMessage, WebhookEvent

admin.site.register(SocialContact)
admin.site.register(Conversation)
admin.site.register(SocialMessage)
admin.site.register(WebhookEvent)
