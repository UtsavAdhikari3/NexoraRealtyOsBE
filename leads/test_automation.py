from datetime import timedelta

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from agencies.models import Agency
from operations.models import Notification
from properties.models import Property
from users.models import AgencyUser
from .automation import apply_lead_automation, process_lead_automation
from .models import (
    Lead, LeadAssignmentRule, LeadAutomationEvent, LeadAutomationSettings,
    LeadDuplicateFlag, LeadInteraction,
)


class LeadAutomationTests(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Automation Realty",
            license_number="AUTO-001",
            payment_status="paid",
        )
        self.manager = AgencyUser.objects.create_user(
            email="manager-auto@example.com", password="Password123",
            full_name="Automation Manager", agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_MANAGER,
        )
        self.agent_one = AgencyUser.objects.create_user(
            email="agent-one-auto@example.com", password="Password123",
            full_name="Agent One", agency=self.agency, role=AgencyUser.ROLE_AGENT,
        )
        self.agent_two = AgencyUser.objects.create_user(
            email="agent-two-auto@example.com", password="Password123",
            full_name="Agent Two", agency=self.agency, role=AgencyUser.ROLE_AGENT,
        )
        self.property = Property.objects.create(
            agency=self.agency, assigned_agent=self.agent_one,
            title="Kathmandu House", property_type="house", purpose="sale",
            price=25000000, province="Bagmati", district="Kathmandu",
            city="Kathmandu", municipality="Kathmandu Metropolitan City",
            tole="Baneshwor", address="Ward 10",
        )
        self.settings = LeadAutomationSettings.objects.create(
            agency=self.agency,
            fallback_assignment="listing_agent",
            max_active_leads_per_agent=50,
        )
        self.client.force_authenticate(self.manager)

    def make_lead(self, name="Buyer", phone="9800000000", **kwargs):
        return Lead.objects.create(
            agency=self.agency, full_name=name, phone=phone,
            source="website", **kwargs,
        )

    def test_listing_agent_fallback_assigns_and_starts_sla(self):
        lead = self.make_lead()
        apply_lead_automation(lead, self.property)
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_agent, self.agent_one)
        self.assertIsNotNone(lead.assigned_at)
        self.assertIsNotNone(lead.response_due_at)
        self.assertTrue(LeadAutomationEvent.objects.filter(
            lead=lead, event_type="assigned"
        ).exists())

    def test_location_and_property_type_rules_use_priority(self):
        LeadAssignmentRule.objects.create(
            agency=self.agency, name="Baneshwor houses", priority=1,
            match_location="Baneshwor", match_property_type="house",
            assignment_method="specific_agent", assign_to_agent=self.agent_two,
        )
        lead = self.make_lead(preferred_location="Baneshwor, Kathmandu")
        apply_lead_automation(lead, self.property)
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_agent, self.agent_two)

    def test_highest_matching_rule_uses_fallback_when_its_agent_is_at_capacity(self):
        self.settings.fallback_assignment = "round_robin"
        self.settings.max_active_leads_per_agent = 1
        self.settings.save()
        self.make_lead(
            name="Existing assignment", phone="9800000040",
            assigned_agent=self.agent_one,
        )
        highest = LeadAssignmentRule.objects.create(
            agency=self.agency, name="Primary", priority=1,
            match_location="Kathmandu", assignment_method="specific_agent",
            assign_to_agent=self.agent_one,
        )
        LeadAssignmentRule.objects.create(
            agency=self.agency, name="Lower priority", priority=2,
            match_location="Kathmandu", assignment_method="specific_agent",
            assign_to_agent=self.agent_two,
        )
        lead = self.make_lead(
            name="Capacity fallback", phone="9800000041",
            preferred_location="Kathmandu",
        )
        apply_lead_automation(lead)
        lead.refresh_from_db()
        event = LeadAutomationEvent.objects.get(lead=lead, event_type="assigned")
        self.assertEqual(lead.assigned_agent, self.agent_two)
        self.assertIsNone(event.rule)
        self.assertNotEqual(event.rule_id, highest.id)

    def test_round_robin_respects_capacity(self):
        self.settings.fallback_assignment = "round_robin"
        self.settings.max_active_leads_per_agent = 1
        self.settings.save()
        first = self.make_lead(name="First", phone="9800000001")
        second = self.make_lead(name="Second", phone="9800000002")
        third = self.make_lead(name="Third", phone="9800000003")
        apply_lead_automation(first)
        apply_lead_automation(second)
        apply_lead_automation(third)
        first.refresh_from_db()
        second.refresh_from_db()
        third.refresh_from_db()
        self.assertNotEqual(first.assigned_agent, second.assigned_agent)
        self.assertIsNone(third.assigned_agent)

    def test_duplicate_phone_is_flagged_for_manager_review(self):
        self.make_lead(name="Original Buyer", phone="+977 980-111-1111")
        duplicate = self.make_lead(name="Repeat Buyer", phone="9801111111")
        apply_lead_automation(duplicate)
        flag = LeadDuplicateFlag.objects.get(lead=duplicate)
        self.assertEqual(flag.status, "pending")
        self.assertIn("Same phone number", flag.reasons)
        self.assertTrue(Notification.objects.filter(
            user=self.manager, title="Possible duplicate lead"
        ).exists())

    def test_outbound_interaction_records_first_response_time(self):
        lead = self.make_lead(assigned_agent=self.agent_one)
        apply_lead_automation(lead)
        LeadInteraction.objects.create(
            agency=self.agency, lead=lead, agent=self.agent_one,
            interaction_type="call", direction="outbound", note="Called buyer",
        )
        lead.refresh_from_db()
        self.assertIsNotNone(lead.first_responded_at)
        self.assertIsNotNone(lead.assignment_responded_at)
        self.assertIsNotNone(lead.response_time_seconds)

    def test_neglected_lead_escalates_alerts_and_reassigns(self):
        self.settings.response_sla_minutes = 1
        self.settings.escalation_minutes = 2
        self.settings.manager_alert_hours = 1
        self.settings.inactive_reassign_hours = 2
        self.settings.auto_reassign_inactive = True
        self.settings.round_robin_last_agent = self.agent_one
        self.settings.save()
        old = timezone.now() - timedelta(hours=3)
        lead = self.make_lead(
            assigned_agent=self.agent_one, assigned_at=old,
            response_due_at=old + timedelta(minutes=1), last_agent_activity_at=old,
        )
        counts = process_lead_automation(now=timezone.now(), agency=self.agency)
        lead.refresh_from_db()
        self.assertEqual(counts, {"escalated": 1, "alerts": 1, "reassigned": 1})
        self.assertEqual(lead.assigned_agent, self.agent_two)
        self.assertEqual(lead.reassignment_count, 1)
        self.assertTrue(Notification.objects.filter(
            user=self.manager, title="Lead response SLA missed"
        ).exists())
        second_counts = process_lead_automation(now=timezone.now(), agency=self.agency)
        self.assertEqual(second_counts, {"escalated": 0, "alerts": 0, "reassigned": 0})

    def test_inactive_listing_agent_never_receives_new_lead(self):
        self.agent_one.is_active = False
        self.agent_one.save(update_fields=["is_active"])
        lead = self.make_lead(name="Active agent only", phone="9800000042")
        apply_lead_automation(lead, self.property)
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_agent, self.agent_two)

    def test_manager_can_configure_rules_but_agent_cannot(self):
        response = self.client.post(reverse("lead-automation-rules"), {
            "name": "Kathmandu round robin", "priority": 10,
            "match_location": "Kathmandu", "assignment_method": "round_robin",
        })
        self.assertEqual(response.status_code, 201)
        self.client.force_authenticate(self.agent_one)
        denied = self.client.patch(
            reverse("lead-automation-settings"), {"response_sla_minutes": 45}
        )
        self.assertEqual(denied.status_code, 403)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_configurable_follow_up_window_sends_in_app_and_email_reminder(self):
        self.settings.follow_up_reminder_hours = 4
        self.settings.save()
        lead = self.make_lead(
            assigned_agent=self.agent_one,
            next_follow_up_at=timezone.now() + timedelta(hours=3),
            follow_up_status=Lead.FOLLOW_UP_PENDING,
        )
        call_command("send_due_reminders", hours=1)
        lead.refresh_from_db()
        self.assertIsNotNone(lead.follow_up_reminder_sent_at)
        self.assertTrue(Notification.objects.filter(
            user=self.agent_one, title__startswith="Follow-up due"
        ).exists())
