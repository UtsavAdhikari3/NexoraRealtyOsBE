from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from leads.models import Lead
from properties.models import Property
from users.models import AgencyUser
from .models import (
    AgentReview, Appointment, AppointmentAvailability, AuditLog, Contact, Deal,
    CustomFieldDefinition, Invitation, Notification, Offer, PipelineStage,
    PublicSubmission, SavedProperty, ScheduledJob, Task,
)


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

    def create_available_slot(self, agent=None, days=1, hour=10):
        agent = agent or self.agent
        local_date = timezone.localdate() + timedelta(days=days)
        starts_at = timezone.make_aware(
            datetime.combine(local_date, time(hour, 0)),
            timezone.get_current_timezone(),
        )
        ends_at = starts_at + timedelta(minutes=30)
        AppointmentAvailability.objects.create(
            agency=agent.agency,
            agent=agent,
            weekday=local_date.weekday(),
            start_time=time(hour, 0),
            end_time=time(hour + 2, 0),
            slot_minutes=30,
        )
        return starts_at, ends_at

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

    def test_agents_can_read_but_cannot_mutate_agency_configuration(self):
        self.client.force_authenticate(self.agent)
        self.assertEqual(self.client.get("/api/operations/custom-fields/").status_code, status.HTTP_200_OK)
        response = self.client.post(
            "/api/operations/custom-fields/",
            {"module": "contact", "key": "private_note", "label": "Private note", "field_type": "text"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.post(
            "/api/operations/pipeline-stages/",
            {"module": "lead", "key": "agent_stage", "name": "Agent stage", "sort_order": 9},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_pipeline_stage_integrity_and_in_use_deletion_protection(self):
        created = self.client.post(
            "/api/operations/pipeline-stages/",
            {
                "module": "deal", "key": "legal_review", "name": "Legal review",
                "sort_order": 20, "is_closed": False,
            },
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        duplicate_order = self.client.post(
            "/api/operations/pipeline-stages/",
            {
                "module": "deal", "key": "finance_review", "name": "Finance review",
                "sort_order": 20,
            },
            format="json",
        )
        self.assertEqual(duplicate_order.status_code, status.HTTP_400_BAD_REQUEST)
        invalid_won = self.client.post(
            "/api/operations/pipeline-stages/",
            {
                "module": "deal", "key": "custom_won", "name": "Custom won",
                "sort_order": 30, "is_won": True, "is_closed": False,
            },
            format="json",
        )
        self.assertEqual(invalid_won.status_code, status.HTTP_400_BAD_REQUEST)
        Deal.objects.create(agency=self.agency, title="Protected deal", stage="legal_review")
        denied = self.client.delete(
            f"/api/operations/pipeline-stages/{created.data['id']}/"
        )
        self.assertEqual(denied.status_code, status.HTTP_400_BAD_REQUEST)

    def test_in_use_custom_field_can_be_deactivated_but_not_retyped_or_deleted(self):
        created = self.client.post(
            "/api/operations/custom-fields/",
            {
                "module": "contact", "key": "citizenship_no",
                "label": "Citizenship number", "field_type": "text",
            },
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        contact = Contact.objects.create(
            agency=self.agency,
            full_name="Configured contact",
            custom_data={"citizenship_no": "12-34"},
        )
        endpoint = f"/api/operations/custom-fields/{created.data['id']}/"
        retyped = self.client.patch(endpoint, {"field_type": "number"}, format="json")
        self.assertEqual(retyped.status_code, status.HTTP_400_BAD_REQUEST)
        deactivated = self.client.patch(endpoint, {"is_active": False}, format="json")
        self.assertEqual(deactivated.status_code, status.HTTP_200_OK)
        contact.refresh_from_db()
        self.assertEqual(contact.custom_data["citizenship_no"], "12-34")
        deleted = self.client.delete(endpoint)
        self.assertEqual(deleted.status_code, status.HTTP_400_BAD_REQUEST)

    def test_relation_fields_reject_cross_agency_records(self):
        response = self.client.post(
            "/api/operations/contacts/",
            {"full_name": "Cross tenant", "contact_type": "buyer", "assigned_to": self.other_owner.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_task_assignment_creates_notification(self):
        response = self.client.post("/api/operations/tasks/", {"title": "Call buyer", "assigned_to": self.agent.id, "priority": "high"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Notification.objects.filter(user=self.agent, category="task").exists())

    def test_internal_job_records_health_and_releases_its_lease(self):
        call_command("send_task_reminders")
        job = ScheduledJob.objects.get(name="task-and-lease-reminders")
        self.assertIsNotNone(job.last_succeeded_at)
        self.assertIsNone(job.locked_until)
        self.assertEqual(job.last_result["created"], 0)

    def test_recurring_task_requires_due_date_and_generates_exactly_one_next_task(self):
        missing_due = self.client.post(
            "/api/operations/tasks/",
            {"title": "Weekly owner call", "recurrence": "weekly"},
            format="json",
        )
        self.assertEqual(missing_due.status_code, status.HTTP_400_BAD_REQUEST)

        due_at = timezone.now() + timedelta(days=2)
        created = self.client.post(
            "/api/operations/tasks/",
            {
                "title": "Daily listing check",
                "assigned_to": self.agent.id,
                "due_at": due_at.isoformat(),
                "recurrence": "daily",
            },
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        completed = self.client.patch(
            f"/api/operations/tasks/{created.data['id']}/",
            {"status": "done"},
            format="json",
        )
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        source = Task.objects.get(pk=created.data["id"])
        next_task = source.next_occurrence
        self.assertEqual(next_task.generated_from, source)
        self.assertEqual(next_task.status, "todo")
        self.assertEqual(next_task.due_at, source.due_at + timedelta(days=1))

        self.client.patch(f"/api/operations/tasks/{source.id}/", {"status": "done"}, format="json")
        call_command("process_recurring_tasks")
        self.assertEqual(Task.objects.filter(generated_from=source).count(), 1)

    def test_recurring_task_command_repairs_a_missing_occurrence(self):
        source = Task.objects.create(
            agency=self.agency,
            title="Monthly report",
            status="done",
            recurrence="monthly",
            due_at=timezone.now(),
            created_by=self.owner,
            assigned_to=self.agent,
        )
        call_command("process_recurring_tasks")
        call_command("process_recurring_tasks")
        self.assertEqual(Task.objects.filter(generated_from=source).count(), 1)

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

    def test_saved_searches_can_be_managed_without_cross_customer_access(self):
        self.client.force_authenticate(user=None)
        first = self.client.post(
            f"/api/public/agencies/{self.agency.slug}/customers/",
            {"full_name": "First Customer", "email": "first-search@example.com", "password": "CustomerStrong123!"},
            format="json",
        )
        second = self.client.post(
            f"/api/public/agencies/{self.agency.slug}/customers/",
            {"full_name": "Second Customer", "email": "second-search@example.com", "password": "CustomerStrong123!"},
            format="json",
        )
        collection = f"/api/public/agencies/{self.agency.slug}/customer/saved-searches/"
        created = self.client.post(
            collection,
            {"name": "Kathmandu houses", "filters": {"city": "Kathmandu", "price_max": 20000000}},
            format="json",
            HTTP_X_CUSTOMER_TOKEN=first.data["access_token"],
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        duplicate = self.client.post(
            collection,
            {"name": "Same criteria", "filters": {"city": "Kathmandu", "price_max": 20000000}},
            format="json",
            HTTP_X_CUSTOMER_TOKEN=first.data["access_token"],
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

        detail = f"{collection}{created.data['id']}/"
        hidden = self.client.get(detail, HTTP_X_CUSTOMER_TOKEN=second.data["access_token"])
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)
        paused = self.client.patch(
            detail,
            {"alerts_enabled": False},
            format="json",
            HTTP_X_CUSTOMER_TOKEN=first.data["access_token"],
        )
        self.assertEqual(paused.status_code, status.HTTP_200_OK)
        self.assertFalse(paused.data["alerts_enabled"])
        deleted = self.client.delete(detail, HTTP_X_CUSTOMER_TOKEN=first.data["access_token"])
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)

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
        starts_at, ends_at = self.create_available_slot()
        response = self.client.post(f"/api/public/agencies/{self.agency.slug}/appointments/", {"agent": self.agent.id, "property": self.property.id, "full_name": "Visitor", "email": "visitor@example.com", "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Notification.objects.filter(user=self.agent, category="appointment").exists())

    def test_appointment_must_match_availability_and_prevent_double_booking(self):
        starts_at, ends_at = self.create_available_slot()
        outside = self.client.post(
            "/api/operations/appointments/",
            {"agent": self.agent.id, "full_name": "Outside", "email": "outside@example.com", "starts_at": (starts_at + timedelta(hours=4)).isoformat(), "ends_at": (ends_at + timedelta(hours=4)).isoformat()},
            format="json",
        )
        self.assertEqual(outside.status_code, status.HTTP_400_BAD_REQUEST)

        misaligned = self.client.post(
            "/api/operations/appointments/",
            {"agent": self.agent.id, "full_name": "Misaligned", "email": "misaligned@example.com", "starts_at": (starts_at + timedelta(minutes=15)).isoformat(), "ends_at": (ends_at + timedelta(minutes=15)).isoformat()},
            format="json",
        )
        self.assertEqual(misaligned.status_code, status.HTTP_400_BAD_REQUEST)

        valid = self.client.post(
            "/api/operations/appointments/",
            {"agent": self.agent.id, "full_name": "First", "email": "first@example.com", "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()},
            format="json",
        )
        self.assertEqual(valid.status_code, status.HTTP_201_CREATED)
        conflict = self.client.post(
            "/api/operations/appointments/",
            {"agent": self.agent.id, "full_name": "Second", "email": "second@example.com", "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()},
            format="json",
        )
        self.assertEqual(conflict.status_code, status.HTTP_400_BAD_REQUEST)

    def test_availability_windows_cannot_overlap(self):
        local_date = timezone.localdate() + timedelta(days=1)
        AppointmentAvailability.objects.create(
            agency=self.agency,
            agent=self.agent,
            weekday=local_date.weekday(),
            start_time=time(9, 0),
            end_time=time(12, 0),
            slot_minutes=30,
        )
        response = self.client.post(
            "/api/operations/availability/",
            {"agent": self.agent.id, "weekday": local_date.weekday(), "start_time": "11:00", "end_time": "13:00", "slot_minutes": 30},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        uneven_date = local_date + timedelta(days=1)
        uneven = self.client.post(
            "/api/operations/availability/",
            {"agent": self.agent.id, "weekday": uneven_date.weekday(), "start_time": "09:00", "end_time": "10:10", "slot_minutes": 30},
            format="json",
        )
        self.assertEqual(uneven.status_code, status.HTTP_400_BAD_REQUEST)

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

    def test_appointments_are_tenant_scoped_by_identifier(self):
        other_appointment = Appointment.objects.create(
            agency=self.other_agency,
            agent=self.other_owner,
            full_name="Hidden visitor",
            email="hidden@example.com",
            starts_at=timezone.now() + timedelta(days=2),
            ends_at=timezone.now() + timedelta(days=2, minutes=30),
        )
        response = self.client.get(f"/api/operations/appointments/{other_appointment.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_operations_mutations_create_audit_log(self):
        self.client.post("/api/operations/contacts/", {"full_name": "Audited", "contact_type": "seller"}, format="json")
        self.assertTrue(AuditLog.objects.filter(agency=self.agency, entity_type="contact", action="created").exists())

    def test_invalid_stripe_signature_is_rejected(self):
        response = self.client.post("/api/webhooks/stripe/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
