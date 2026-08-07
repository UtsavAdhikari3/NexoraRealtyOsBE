from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APITestCase

from agencies.models import Agency
from users.models import AgencyUser
from .models import Property, PropertyVerificationDocument


class PropertyVerificationAPITests(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Verified Realty", license_number="VERIFY-001", payment_status="paid"
        )
        self.owner = AgencyUser.objects.create_user(
            email="verify-owner@example.com", password="Password123", full_name="Verification Owner",
            agency=self.agency, role="agency_owner",
        )
        self.property = Property.objects.create(
            agency=self.agency, title="Verified Kathmandu Plot", property_type="land",
            purpose="sale", price=10000000, province="Bagmati", district="Kathmandu",
            city="Kathmandu", status="available", is_published=True,
        )
        self.client.force_authenticate(self.owner)
        self.verification_url = reverse(
            "property-verification-detail", kwargs={"property_id": self.property.id}
        )

    def document_url(self, document_type):
        return reverse("property-verification-document-detail", kwargs={
            "property_id": self.property.id, "document_type": document_type,
        })

    def test_get_initializes_fixed_ten_document_checklist(self):
        response = self.client.get(self.verification_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["documents"]), 10)
        self.assertEqual(
            {item["document_type"] for item in response.data["documents"]},
            {value for value, _ in PropertyVerificationDocument.DOCUMENT_TYPES},
        )
        self.assertEqual(response.data["verification_level"], "unverified")

    def test_document_upload_moves_missing_document_to_received(self):
        self.client.get(self.verification_url)
        upload = SimpleUploadedFile("lalpurja.pdf", b"sample", content_type="application/pdf")
        response = self.client.patch(self.document_url("lalpurja"), {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "received")

    def test_milestones_are_sequential_and_fully_verified_is_guarded(self):
        self.client.get(self.verification_url)
        response = self.client.patch(self.verification_url, {"fully_verified": True}, format="json")
        self.assertEqual(response.status_code, 400)

        self.client.patch(self.document_url("lalpurja"), {"status": "received"}, format="json")
        response = self.client.patch(self.verification_url, {
            "owner_identity_verified": True,
            "ownership_document_received": True,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["verification_level"], "ownership_document_received")

        for document_type, _ in PropertyVerificationDocument.DOCUMENT_TYPES:
            self.client.patch(self.document_url(document_type), {"status": "approved"}, format="json")
        response = self.client.patch(self.verification_url, {
            "owner_identity_verified": True,
            "ownership_document_received": True,
            "physically_inspected": True,
            "documents_reviewed": True,
            "fully_verified": True,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["fully_verified"])
        self.assertEqual(response.data["approved_document_count"], 10)

    def test_public_payload_exposes_summary_but_never_private_documents(self):
        self.client.get(self.verification_url)
        response = self.client.get(reverse("public-property-detail", kwargs={
            "license_number": self.agency.license_number, "pk": self.property.id,
        }))
        self.assertEqual(response.status_code, 200)
        self.assertIn("verification_summary", response.data)
        self.assertNotIn("verification", response.data)
        self.assertNotIn("documents", response.data["verification_summary"])
