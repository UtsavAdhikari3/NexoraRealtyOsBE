from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from leads.models import Lead
from properties.models import Property
from users.models import AgencyUser
from .models import AgentReview, AuditLog, Contact, Deal, Invitation, Notification, Offer, PublicSubmission, SavedProperty, Task


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class OperationsApiTests(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(name="Nexora Test", license_number="LIC-OPS", payment_status="paid")
        self.other_agency = Agency.objects.create(name="Other", license_number="LIC-OTHER", payment_status="paid")
        self.owner = AgencyUser.objects.create_user(email="owner@example.com", password="StrongPass123!", full_name="Owner", role="agency_owner", agency=self.agency, is_email_verified=True)
        self.agent = AgencyUser.objects.create_user(email="agent@example.com", password="StrongPass123!", full_name="Agent", role="agent", agency=self.agency, is_email_verified=True)
        self.other_owner = AgencyUser.objects.create_user(email="other@example.com", password="StrongPass123!", full_name="Other", role="agency_owner", agency=self.other_agency, is_email_verified=True)
        self.lead = Lead.objects.create(agency=self.agency, full_name="Buyer One", phone="9800000000", status="negotiating", property_type="house", purpose="sale", preferred_location="Kathmandu", budget_max=Decimal("20000000"), assigned_agent=self.agent)
        self.property = Property.objects.create(agency=self.agency, assigned_agent=self.agent, title="Kathmandu Home", property_type="house", purpose="sale", price=Decimal("18000000"), province="Bagmati", district="Kathmandu", city="Kathmandu", status="available", is_published=True)
        self.client.force_authenticate(self.owner)

    def test_contacts_are_agency_scoped(self):
        Contact.objects.create(agency=self.other_agency, full_name="Hidden")
        response = self.client.post("/api/operations/contacts/", {"full_name": "Visible", "contact_type": "buyer"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.get("/api/operations/contacts/")
        self.assertEqual([row["full_name"] for row in response.data], ["Visible"])

    def test_agent_only_sees_assigned_contacts(self):
        Contact.objects.create(agency=self.agency, full_name="Assigned", assigned_to=self.agent)
        Contact.objects.create(agency=self.agency, full_name="Unassigned")
        self.client.force_authenticate(self.agent)
        response = self.client.get("/api/operations/contacts/")
        self.assertEqual([row["full_name"] for row in response.data], ["Assigned"])

    def test_deal_and_offer_acceptance_updates_pipeline(self):
        deal_response = self.client.post("/api/operations/deals/", {"title": "Home sale", "lead": self.lead.id, "property": self.property.id, "assigned_agent": self.agent.id, "value": "18000000", "stage": "offer"}, format="json")
        self.assertEqual(deal_response.status_code, status.HTTP_201_CREATED)
        offer_response = self.client.post("/api/operations/offers/", {"deal": deal_response.data["id"], "amount": "17500000", "status": "submitted"}, format="json")
        self.assertEqual(offer_response.status_code, status.HTTP_201_CREATED)
        response = self.client.post(f"/api/operations/offers/{offer_response.data['id']}/respond/", {"status": "accepted"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        deal = Deal.objects.get(id=deal_response.data["id"])
        self.assertEqual(deal.stage, "contract")
        self.assertEqual(deal.value, Decimal("17500000"))

    def test_custom_deal_pipeline_stage_is_accepted(self):
        self.client.post("/api/operations/pipeline-stages/", {"module": "deal", "key": "legal_review", "name": "Legal review", "sort_order": 4}, format="json")
        response = self.client.post("/api/operations/deals/", {"title": "Custom stage", "stage": "legal_review"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_required_custom_field_is_enforced(self):
        self.client.post("/api/operations/custom-fields/", {"module": "contact", "key": "citizenship_no", "label": "Citizenship number", "field_type": "text", "is_required": True}, format="json")
        missing = self.client.post("/api/operations/contacts/", {"full_name": "Seller", "contact_type": "seller"}, format="json")
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        valid = self.client.post("/api/operations/contacts/", {"full_name": "Seller", "contact_type": "seller", "custom_data": {"citizenship_no": "12-34"}}, format="json")
        self.assertEqual(valid.status_code, status.HTTP_201_CREATED)

    def test_task_assignment_creates_notification(self):
        response = self.client.post("/api/operations/tasks/", {"title": "Call buyer", "assigned_to": self.agent.id, "priority": "high"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Notification.objects.filter(user=self.agent, category="task").exists())

    def test_invitation_emails_and_can_be_accepted(self):
        response = self.client.post("/api/operations/invitations/", {"full_name": "New Agent", "email": "new@example.com", "role": "agent"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 1)
        invite = Invitation.objects.get(email="new@example.com")
        self.client.force_authenticate(user=None)
        response = self.client.post("/api/operations/invitation/accept/", {"token": str(invite.token), "password": "AnotherStrong123!"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(AgencyUser.objects.filter(email="new@example.com", agency=self.agency).exists())

    def test_expired_invitation_is_rejected(self):
        invite = Invitation.objects.create(agency=self.agency, email="late@example.com", full_name="Late", role="agent", invited_by=self.owner, expires_at=timezone.now() - timedelta(minutes=1))
        self.client.force_authenticate(user=None)
        response = self.client.post("/api/operations/invitation/accept/", {"token": str(invite.token), "password": "AnotherStrong123!"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_410_GONE)

    def test_customer_portal_login_and_saved_property(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(f"/api/public/agencies/{self.agency.slug}/customers/", {"full_name": "Customer", "email": "customer@example.com", "phone": "9800000001", "password": "CustomerStrong123!"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        token = response.data["access_token"]
        response = self.client.post(f"/api/public/agencies/{self.agency.slug}/customer/saved-properties/", {"property": self.property.id}, format="json", HTTP_X_CUSTOMER_TOKEN=token)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SavedProperty.objects.count(), 1)
        login = self.client.post(f"/api/public/agencies/{self.agency.slug}/customers/login/", {"email": "customer@example.com", "password": "CustomerStrong123!"}, format="json")
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_unpublished_website_rejects_customer_registration(self):
        self.agency.is_website_published = False
        self.agency.save(update_fields=["is_website_published"])
        self.client.force_authenticate(user=None)
        response = self.client.post(
            f"/api/public/agencies/{self.agency.slug}/customers/",
            {
                "full_name": "Hidden Customer",
                "email": "hidden@example.com",
                "password": "CustomerStrong123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_appointment_notifies_agent(self):
        response = self.client.post(f"/api/public/agencies/{self.agency.slug}/appointments/", {"agent": self.agent.id, "property": self.property.id, "full_name": "Visitor", "email": "visitor@example.com", "starts_at": (timezone.now() + timedelta(days=1)).isoformat(), "ends_at": (timezone.now() + timedelta(days=1, minutes=30)).isoformat()}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Notification.objects.filter(user=self.agent, category="appointment").exists())

    def test_public_valuation_submission_creates_crm_lead(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            f"/api/public/agencies/{self.agency.slug}/submissions/",
            {
                "kind": "valuation",
                "full_name": "Seller Person",
                "email": "seller@example.com",
                "phone": "9800000042",
                "message": "Please value my home.",
                "metadata": {"address": "Lalitpur", "property_type": "house"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        submission = PublicSubmission.objects.get(id=response.data["id"])
        self.assertIsNotNone(submission.lead_id)
        self.assertEqual(submission.lead.custom_data["public_submission_kind"], "valuation")
        self.assertTrue(Notification.objects.filter(category="website_submission").exists())

    def test_newsletter_submission_does_not_merge_blank_phone_leads(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            f"/api/public/agencies/{self.agency.slug}/submissions/",
            {"kind": "newsletter", "email": "reader@example.com", "metadata": {"preference": "Luxury listings"}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(PublicSubmission.objects.get(id=response.data["id"]).lead_id)

    def test_agent_review_requires_moderation_before_publication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            f"/api/public/agencies/{self.agency.slug}/agents/{self.agent.id}/reviews/",
            {"reviewer_name": "Buyer", "reviewer_email": "buyer@example.com", "rating": 5, "comment": "Excellent service."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        detail_url = f"/api/public/agencies/{self.agency.license_number}/agents/{self.agent.id}/"
        self.assertEqual(self.client.get(detail_url).data["reviews"], [])

        review = AgentReview.objects.get(id=response.data["id"])
        self.client.force_authenticate(self.owner)
        approved = self.client.patch(f"/api/operations/agent-reviews/{review.id}/", {"is_approved": True}, format="json")
        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        public_agent = self.client.get(detail_url).data
        self.assertEqual(public_agent["rating"], 5.0)
        self.assertEqual(public_agent["reviews"][0]["comment"], "Excellent service.")

        review.refresh_from_db()
        approved_by_id = review.approved_by_id
        approved_at = review.approved_at
        renamed = self.client.patch(
            f"/api/operations/agent-reviews/{review.id}/",
            {"title": "Updated title"},
            format="json",
        )
        self.assertEqual(renamed.status_code, status.HTTP_200_OK)
        review.refresh_from_db()
        self.assertEqual(review.approved_by_id, approved_by_id)
        self.assertEqual(review.approved_at, approved_at)

    def test_matching_scores_relevant_property(self):
        response = self.client.get(f"/api/operations/matching/leads/{self.lead.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["property_id"], self.property.id)
        self.assertGreaterEqual(response.data[0]["score"], 80)

    def test_reports_are_agency_scoped(self):
        Deal.objects.create(agency=self.agency, title="Won", stage="closed_won", value=100)
        Deal.objects.create(agency=self.other_agency, title="Hidden", stage="closed_won", value=999)
        response = self.client.get("/api/operations/reports/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["totals"]["won_value"], Decimal("100"))

    def test_regular_owner_cannot_access_platform_admin(self):
        response = self.client.get("/api/operations/admin/summary/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_can_suspend_an_agency(self):
        admin = AgencyUser.objects.create_superuser(email="root@example.com", password="StrongPass123!", full_name="Root")
        self.client.force_authenticate(admin)
        response = self.client.patch(f"/api/operations/platform-agencies/{self.other_agency.id}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.other_agency.refresh_from_db()
        self.assertFalse(self.other_agency.is_active)
        self.assertTrue(AuditLog.objects.filter(agency=self.other_agency, action="platform_updated").exists())

    def test_owner_can_update_team_member_access(self):
        response = self.client.patch(f"/api/operations/team-members/{self.agent.id}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.is_active)

    def test_public_appointment_rejects_cross_agency_agent(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(f"/api/public/agencies/{self.agency.slug}/appointments/", {"agent": self.other_owner.id, "full_name": "Visitor", "email": "visitor@example.com", "starts_at": (timezone.now() + timedelta(days=1)).isoformat(), "ends_at": (timezone.now() + timedelta(days=1, minutes=30)).isoformat()}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_operations_mutations_create_audit_log(self):
        self.client.post("/api/operations/contacts/", {"full_name": "Audited", "contact_type": "seller"}, format="json")
        self.assertTrue(AuditLog.objects.filter(agency=self.agency, entity_type="contact", action="created").exists())

    def test_invalid_stripe_signature_is_rejected(self):
        response = self.client.post("/api/webhooks/stripe/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
