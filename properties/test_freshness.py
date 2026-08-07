from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from agencies.models import Agency
from operations.models import Notification, PublicSubmission
from users.models import AgencyUser
from .freshness import detect_duplicate_listings, process_listing_freshness
from .models import Property, PropertyDuplicateFlag, PropertyHistory


class ListingFreshnessAPITests(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Fresh Realty", license_number="FRESH-001", payment_status="paid",
            is_website_published=True,
        )
        self.owner = AgencyUser.objects.create_user(
            email="fresh-owner@example.com", password="Password123", full_name="Fresh Owner",
            agency=self.agency, role="agency_owner",
        )
        self.agent = AgencyUser.objects.create_user(
            email="fresh-agent@example.com", password="Password123", full_name="Fresh Agent",
            agency=self.agency, role="agent",
        )
        self.property = Property.objects.create(
            agency=self.agency, assigned_agent=self.agent, title="Fresh Plot", property_type="land",
            purpose="sale", price=12000000, province="Bagmati", district="Kathmandu",
            city="Kathmandu", address="Ward 9, Sample Road", land_area_value=4,
            land_area_unit="aana", status="available", is_published=True,
        )
        self.client.force_authenticate(self.owner)

    def test_publishing_initializes_thirty_day_freshness_window(self):
        self.assertIsNotNone(self.property.availability_verified_at)
        self.assertAlmostEqual(
            (self.property.listing_expires_at - self.property.availability_verified_at).total_seconds(),
            timedelta(days=30).total_seconds(), delta=2,
        )

    def test_reserved_and_under_negotiation_are_public_availability_states(self):
        self.property.status = "reserved"
        self.property.save()
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse(
            "public-property-detail",
            kwargs={"license_number": self.agency.license_number, "pk": self.property.id},
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["availability_status_display"], "Reserved")

    def test_reconfirmation_reminders_are_deduplicated_for_each_expiry_window(self):
        expiry = timezone.now() + timedelta(days=6)
        Property.objects.filter(pk=self.property.pk).update(listing_expires_at=expiry)
        first_count = process_listing_freshness()
        second_count = process_listing_freshness()
        self.assertGreater(first_count, 0)
        self.assertEqual(second_count, 0)

    def test_expired_listing_is_hidden_publicly_and_reminder_is_sent(self):
        expired_at = timezone.now() - timedelta(minutes=1)
        Property.objects.filter(pk=self.property.pk).update(listing_expires_at=expired_at, is_published=True)
        public_url = reverse("public-property-list", kwargs={"license_number": self.agency.license_number})
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(public_url).data, [])
        process_listing_freshness()
        self.property.refresh_from_db()
        self.assertFalse(self.property.is_published)
        self.assertTrue(self.property.requires_republish_approval)
        self.assertTrue(Notification.objects.filter(category="listing_freshness").exists())

    def test_republish_requires_request_and_manager_approval(self):
        Property.objects.filter(pk=self.property.pk).update(
            listing_expires_at=timezone.now() - timedelta(days=1),
            is_published=False, requires_republish_approval=True,
        )
        self.property.refresh_from_db()
        self.client.force_authenticate(self.agent)
        confirm = self.client.post(
            reverse("property-freshness-confirm", kwargs={"property_id": self.property.id}),
            {"valid_for_days": 30, "owner_confirmed": True}, format="json",
        )
        self.assertEqual(confirm.status_code, 200)
        self.assertFalse(confirm.data["is_published"])
        request_response = self.client.post(
            reverse("property-republish-request", kwargs={"property_id": self.property.id}), {}, format="json",
        )
        self.assertEqual(request_response.status_code, 200)
        self.assertEqual(request_response.data["republish_approval_status"], "pending")
        self.client.force_authenticate(self.owner)
        approval = self.client.post(
            reverse("property-republish-decision", kwargs={"property_id": self.property.id}),
            {"decision": "approve"}, format="json",
        )
        self.assertEqual(approval.status_code, 200)
        self.assertTrue(approval.data["is_published"])
        self.assertTrue(PropertyHistory.objects.filter(event_type="republish_approved").exists())

    def test_withdrawal_requires_reason_and_creates_history(self):
        url = reverse("property-detail", kwargs={"pk": self.property.id})
        response = self.client.patch(url, {"status": "withdrawn"}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(
            url, {"status": "withdrawn", "withdrawal_reason": "Owner no longer wishes to sell"}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_published"])
        self.assertTrue(PropertyHistory.objects.filter(property=self.property, event_type="withdrawn").exists())

    def test_duplicate_detection_flags_matching_address_and_area(self):
        duplicate = Property.objects.create(
            agency=self.agency, title="Another Plot", property_type="land", purpose="sale",
            price=12500000, province="Bagmati", district="Kathmandu", city="Kathmandu",
            address="Ward 9 Sample Road", land_area_value=4, land_area_unit="aana",
        )
        flags = detect_duplicate_listings(duplicate)
        self.assertEqual(len(flags), 1)
        self.assertGreaterEqual(flags[0].score, 50)
        self.assertTrue(PropertyDuplicateFlag.objects.filter(property=duplicate, candidate=self.property).exists())

    def test_public_can_report_listing_without_accessing_private_workflows(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            reverse("public-submission-create", kwargs={"slug": self.agency.slug}),
            {
                "kind": "listing_report", "property": self.property.id,
                "message": "Owner says this was sold.",
                "metadata": {"reason": "already_sold"},
            }, format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(PublicSubmission.objects.filter(kind="listing_report", property=self.property).exists())
        self.assertTrue(Notification.objects.filter(category="website_submission").exists())
        self.assertTrue(PropertyHistory.objects.filter(property=self.property, event_type="report_received").exists())
