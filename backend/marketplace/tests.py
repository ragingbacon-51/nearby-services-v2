from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Booking, Category, Offering, Profile

User = get_user_model()


class MarketplaceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(username="customer", password="strong-password-123",
                                                 first_name="Cora", last_name="Example")
        Profile.objects.create(user=self.customer, role="customer", phone="+254712345678", phone_verified=True)
        self.provider = User.objects.create_user(username="provider", password="strong-password-123",
                                                 first_name="Alex", last_name="Example")
        self.profile = Profile.objects.create(user=self.provider, role="provider", phone="+254712345679",
                                              phone_verified=True, identity_status="approved",
                                              latitude=-1.286389, longitude=36.817223)
        self.category = Category.objects.create(name="Test category")
        self.offering = Offering.objects.create(provider=self.profile, category=self.category, pricing="fixed",
                                                price_kes="1500.00", profession_verified=True)
        self.booking_data = {"offering_id": self.offering.pk, "details": "Repair tap", "address": "Nairobi",
                             "scheduled_for": (timezone.now() + timedelta(days=1)).isoformat(),
                             "accepted_fixed_price_kes": "1500.00"}

    def create_booking(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post("/api/bookings/", self.booking_data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["id"]

    def test_categories_are_admin_managed_and_search_respects_approval_and_distance(self):
        self.assertTrue(Category.objects.filter(name="Laundry & Dry Cleaning").exists())
        self.client.force_authenticate(self.customer)
        path = f"/api/nearby/?latitude=-1.286389&longitude=36.817223&category={self.category.pk}"
        self.assertEqual(len(self.client.get(path).data), 1)
        self.offering.profession_verified = False
        self.offering.save()
        self.assertEqual(self.client.get(path).data, [])
        self.offering.profession_verified = True
        self.offering.save()
        self.category.active = False
        self.category.save()
        self.assertEqual(self.client.get(path).data, [])
        self.assertFalse(any(c["id"] == self.category.pk for c in self.client.get("/api/categories/").data))

    def test_fixed_price_booking_requires_current_explicit_price(self):
        self.client.force_authenticate(self.customer)
        self.booking_data["accepted_fixed_price_kes"] = "1200.00"
        self.assertEqual(self.client.post("/api/bookings/", self.booking_data, format="json").status_code, 409)
        self.assertFalse(Booking.objects.exists())
        self.booking_data["accepted_fixed_price_kes"] = "1500.00"
        self.assertEqual(self.client.post("/api/bookings/", self.booking_data, format="json").status_code, 201)

    def test_booking_completion_and_payment_due_authorization(self):
        booking_id = self.create_booking()
        path = f"/api/bookings/{booking_id}/action/"
        self.assertEqual(self.client.post(path, {"action": "accept"}, format="json").status_code, 400)
        self.client.force_authenticate(self.provider)
        self.assertEqual(self.client.post(path, {"action": "accept"}, format="json").data["status"], "confirmed")
        self.assertEqual(self.client.post(path, {"action": "confirm_completion"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(path, {"action": "complete"}, format="json").data["status"], "completed")
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.post(path, {"action": "confirm_completion"}, format="json").data["status"], "payment_due")
        self.assertEqual(self.client.post(path, {"action": "confirm_completion"}, format="json").status_code, 400)

    def test_quote_and_dispute_are_separate_from_payment(self):
        self.offering.pricing, self.offering.price_kes = "quote", None
        self.offering.save()
        self.booking_data.pop("accepted_fixed_price_kes")
        booking_id = self.create_booking()
        path = f"/api/bookings/{booking_id}/action/"
        self.client.force_authenticate(self.provider)
        self.assertEqual(self.client.post(path, {"action": "quote", "price_kes": "800"}, format="json").data["status"], "quoted")
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.post(path, {"action": "accept"}, format="json").data["status"], "confirmed")
        self.client.force_authenticate(self.provider)
        self.client.post(path, {"action": "complete"}, format="json")
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.post(path, {"action": "dispute"}, format="json").data["status"], "disputed")
        self.assertEqual(self.client.post(path, {"action": "confirm_completion"}, format="json").status_code, 400)

    def test_unverified_or_inactive_provider_and_unverified_customer_cannot_book(self):
        self.client.force_authenticate(self.customer)
        self.customer.profile.phone_verified = False
        self.customer.profile.save()
        self.assertEqual(self.client.post("/api/bookings/", self.booking_data, format="json").status_code, 403)
        self.customer.profile.phone_verified = True
        self.customer.profile.save()
        self.profile.identity_status = "pending"
        self.profile.save()
        self.assertEqual(self.client.post("/api/bookings/", self.booking_data, format="json").status_code, 404)

    def test_provider_can_add_an_offering_but_not_approve_it(self):
        self.client.force_authenticate(self.provider)
        category = Category.objects.create(name="Another category")
        response = self.client.post("/api/offerings/", {"category": category.pk, "pricing": "quote",
                                    "profession_verified": True}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["profession_verified"])
        self.assertEqual(self.client.post("/api/offerings/", {"category": category.pk, "pricing": "quote"},
                                          format="json").status_code, 400)

    def test_new_categories_can_be_listed_and_offered(self):
        response = self.client.get("/api/categories/")
        categories = response.data
        for name in ("Barbering & Shaving", "House Managers"):
            with self.subTest(category=name):
                category = next(item for item in categories if item["name"] == name)
                self.client.force_authenticate(self.provider)
                response = self.client.post("/api/offerings/", {"category": category["id"], "pricing": "quote"}, format="json")
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.data["category_name"], name)
                self.assertFalse(response.data["profession_verified"])

    @patch("marketplace.views.verification.check_phone")
    @patch("marketplace.views.verification.start_phone")
    def test_phone_verification_requires_matching_approved_result(self, start, check):
        self.customer.profile.phone_verified = False
        self.customer.profile.save()
        self.client.force_authenticate(self.customer)
        start.return_value = {"verification_id": "ver_1"}
        self.assertEqual(self.client.post("/api/verify/phone/start/").status_code, 200)
        check.return_value = {"status": "approved", "verification_id": "wrong"}
        self.assertEqual(self.client.post("/api/verify/phone/check/", {"code": "123456"}, format="json").status_code, 400)
        check.return_value = {"status": "approved", "verification_id": "ver_1"}
        self.assertEqual(self.client.post("/api/verify/phone/check/", {"code": "123456"}, format="json").status_code, 200)
        self.customer.profile.refresh_from_db()
        self.assertTrue(self.customer.profile.phone_verified)

    @patch("marketplace.views.verification.identity_decision")
    @patch("marketplace.views.verification.start_identity")
    def test_identity_verification_requires_all_checks_and_matching_registry(self, start, decision):
        self.profile.identity_status = "not_started"
        self.profile.save()
        self.client.force_authenticate(self.provider)
        session_id = "11111111-2222-3333-4444-555555555555"
        start.return_value = {"session_id": session_id, "url": "https://verify.didit.me/session/example"}
        self.assertEqual(self.client.post("/api/verify/identity/start/").status_code, 200)
        decision.return_value = {"session_id": session_id, "status": "Approved",
            "id_verifications": [{"status": "Approved"}], "liveness_checks": [{"status": "Approved"}],
            "face_matches": [], "database_validations": [{"status": "Approved", "issuing_state": "KEN",
                "match_type": "full_match", "validations": [{"service_id": "ken_national_id", "outcome_code": "MATCH",
                    "source_data": {"first_name": "Alex", "last_name": "Example"}}]}]}
        self.assertEqual(self.client.post("/api/verify/identity/status/").data["identity_status"], "pending")
        decision.return_value["face_matches"] = [{"status": "Approved"}]
        self.assertEqual(self.client.post("/api/verify/identity/status/").data["identity_status"], "approved")
