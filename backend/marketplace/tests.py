from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.contrib.admin.models import LogEntry
from django.test import TestCase, override_settings
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Booking, Category, InAppNotification, Offering, Profile, SandboxPayment

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

    @patch("marketplace.views.mpesa.configuration")
    @patch("marketplace.views.mpesa.start_checkout")
    @patch("marketplace.views.mpesa.query_checkout")
    def test_sandbox_checkout_only_after_confirmation_and_query(self, query, start, config):
        config.return_value = {"mock": "configuration"}
        start.return_value = {"ResponseCode": "0", "CheckoutRequestID": "sandbox-checkout"}
        booking_id = self.create_booking()
        url = f"/api/bookings/{booking_id}/sandbox-payment/"
        self.assertEqual(self.client.post(url, {"phone": "254712345678"}, format="json").status_code, 400)
        booking = Booking.objects.get(pk=booking_id)
        booking.status = Booking.Status.PAYMENT_DUE
        booking.save()
        self.client.force_authenticate(self.provider)
        self.assertEqual(self.client.post(url, {"phone": "254712345678"}, format="json").status_code, 404)
        self.client.force_authenticate(self.customer)
        response = self.client.post(url, {"phone": "254712345678"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["sandbox_payment"]["commission_kes"], "75.00")
        self.assertEqual(response.data["sandbox_payment"]["provider_share_kes"], "1425.00")
        self.assertEqual(self.client.post(url, {"phone": "254712345678"}, format="json").status_code, 409)
        self.client.force_authenticate(user=None)
        self.client.post("/api/payments/mpesa/callback/", {"ResultCode": 0}, format="json")
        payment = SandboxPayment.objects.get(booking_id=booking_id)
        payment.refresh_from_db()
        self.assertEqual(payment.status, SandboxPayment.Status.PENDING)
        self.client.force_authenticate(self.customer)
        query.return_value = {"ResponseCode": "0", "ResultCode": "0", "CheckoutRequestID": "sandbox-checkout"}
        response = self.client.post(f"{url}status/")
        self.assertEqual(response.data["sandbox_payment"]["status"], "succeeded")
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PAYMENT_DUE)

    @patch("marketplace.views.mpesa.configuration")
    @patch("marketplace.views.mpesa.start_checkout")
    def test_sandbox_timeout_does_not_allow_a_second_attempt(self, start, config):
        from .mpesa import MpesaError
        config.return_value = {"mock": "configuration"}
        start.side_effect = MpesaError("timeout")
        booking_id = self.create_booking()
        Booking.objects.filter(pk=booking_id).update(status=Booking.Status.PAYMENT_DUE)
        url = f"/api/bookings/{booking_id}/sandbox-payment/"
        self.assertEqual(self.client.post(url, {"phone": "254712345678"}, format="json").status_code, 502)
        self.assertEqual(SandboxPayment.objects.get(booking_id=booking_id).status, "unknown")
        self.assertEqual(self.client.post(url, {"phone": "254712345678"}, format="json").status_code, 409)
        self.assertEqual(start.call_count, 1)

    @patch("marketplace.views.mpesa.configuration")
    def test_sandbox_checkout_rejects_fractional_shillings(self, config):
        config.return_value = {"mock": "configuration"}
        booking_id = self.create_booking()
        Booking.objects.filter(pk=booking_id).update(status=Booking.Status.PAYMENT_DUE, price_kes=Decimal("100.50"))
        url = f"/api/bookings/{booking_id}/sandbox-payment/"
        self.assertEqual(self.client.post(url, {"phone": "254712345678"}, format="json").status_code, 400)
        self.assertFalse(SandboxPayment.objects.filter(booking_id=booking_id).exists())

    @override_settings(DEBUG=False)
    @patch.dict("os.environ", {"MPESA_SANDBOX_ENABLED": "1"})
    def test_sandbox_cannot_be_enabled_outside_debug(self):
        from .mpesa import MpesaError, configuration
        with self.assertRaises(MpesaError):
            configuration()

    @patch("marketplace.mpesa.requests.request")
    def test_sandbox_uses_safaricom_endpoints_and_correct_checkout_body(self, request):
        from .mpesa import start_checkout
        token = Mock()
        token.json.return_value = {"access_token": "test-token"}
        checkout = Mock()
        checkout.json.return_value = {"ResponseCode": "0", "CheckoutRequestID": "test-id"}
        request.side_effect = [token, checkout]
        config = {"MPESA_CONSUMER_KEY": "key", "MPESA_CONSUMER_SECRET": "secret", "MPESA_SHORTCODE": "174379",
                  "MPESA_PASSKEY": "test-passkey", "MPESA_CALLBACK_URL": "https://example.com/api/payments/mpesa/callback/"}
        start_checkout(config, 1500, "254712345678", 42)
        self.assertEqual(request.call_args_list[0].args[1].split("?")[0],
                         "https://sandbox.safaricom.co.ke/oauth/v1/generate")
        self.assertEqual(request.call_args_list[1].args[1],
                         "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest")
        payload = request.call_args_list[1].kwargs["json"]
        self.assertEqual(payload["Amount"], 1500)
        self.assertEqual(payload["CallBackURL"], config["MPESA_CALLBACK_URL"])
        self.assertEqual(payload["AccountReference"], "BOOK42")

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

    def test_booking_contact_only_shared_after_confirmation_with_participants(self):
        booking_id = self.create_booking()
        self.assertIsNone(self.client.get("/api/bookings/").data[0]["contact_phone"])
        self.client.force_authenticate(self.provider)
        self.assertIsNone(self.client.get("/api/bookings/").data[0]["contact_phone"])
        path = f"/api/bookings/{booking_id}/action/"
        self.assertEqual(self.client.post(path, {"action": "accept"}, format="json").data["contact_phone"],
                         self.customer.profile.phone)
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get("/api/bookings/").data[0]["contact_phone"], self.profile.phone)
        other = User.objects.create_user(username="other", password="strong-password-123")
        Profile.objects.create(user=other, role="customer", phone="+254712345670")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get("/api/bookings/").data, [])
        self.assertEqual(self.client.post(path, {"action": "complete"}, format="json").status_code, 404)

    def test_quote_and_declined_requests_do_not_share_contact(self):
        self.offering.pricing, self.offering.price_kes = "quote", None
        self.offering.save()
        self.booking_data.pop("accepted_fixed_price_kes")
        booking_id = self.create_booking()
        path = f"/api/bookings/{booking_id}/action/"
        self.client.force_authenticate(self.provider)
        self.assertIsNone(self.client.post(path, {"action": "quote", "price_kes": "800"}, format="json").data["contact_phone"])
        self.client.force_authenticate(self.customer)
        self.assertIsNone(self.client.post(path, {"action": "decline"}, format="json").data["contact_phone"])

    def test_admin_resolves_disputes_with_private_note_and_notifies_participants(self):
        booking_id = self.create_booking()
        booking = Booking.objects.get(pk=booking_id)
        booking.status = Booking.Status.DISPUTED
        booking.save()
        staff = User.objects.create_superuser(username="admin", password="strong-password-123")
        admin_client = Client()
        admin_client.force_login(staff)
        url = f"/admin/marketplace/booking/{booking_id}/change/"
        response = admin_client.post(url, {
            "dispute_outcome": "payment_due", "dispute_resolution_note": "",
        })
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.DISPUTED)
        response = admin_client.post(url, {
            "dispute_outcome": "payment_due", "dispute_resolution_note": "Work was completed; payment remains due.",
        })
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PAYMENT_DUE)
        self.assertEqual(booking.dispute_outcome, Booking.DisputeOutcome.PAYMENT_DUE)
        self.assertEqual(booking.dispute_resolution_note, "Work was completed; payment remains due.")
        self.assertEqual(booking.dispute_resolved_by, staff)
        self.assertIsNotNone(booking.dispute_resolved_at)
        self.assertTrue(LogEntry.objects.filter(user=staff, object_id=str(booking_id)).exists())
        self.assertEqual(InAppNotification.objects.filter(
            booking=booking, recipient__in=[self.customer, self.provider], kind=InAppNotification.Kind.DISPUTE,
        ).count(), 2)
        self.assertFalse(SandboxPayment.objects.filter(booking=booking).exists())
        booking.status = Booking.Status.DISPUTED
        booking.save()
        response = admin_client.post(url, {
            "dispute_outcome": "closed_no_payment", "dispute_resolution_note": "Provider did not complete the work.",
        })
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CLOSED_NO_PAYMENT)

    def test_booking_chat_and_notifications_are_private_to_participants(self):
        booking_id = self.create_booking()
        self.assertTrue(InAppNotification.objects.filter(
            recipient=self.provider, booking_id=booking_id, kind=InAppNotification.Kind.BOOKING,
        ).exists())
        messages_url = f"/api/bookings/{booking_id}/messages/"
        response = self.client.post(messages_url, {"body": "Hello"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["is_mine"])
        self.assertEqual(InAppNotification.objects.filter(recipient=self.provider, kind="message").count(), 1)

        self.client.force_authenticate(self.provider)
        response = self.client.get(messages_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["body"], "Hello")
        self.assertFalse(response.data[0]["is_mine"])
        provider_notice = self.client.get("/api/notifications/").data[0]
        self.assertEqual(provider_notice["kind"], "message")
        self.assertEqual(self.client.post(f"/api/notifications/{provider_notice['id']}/read/").status_code, 204)
        self.assertIsNotNone(InAppNotification.objects.get(pk=provider_notice["id"]).read_at)

        other = User.objects.create_user(username="other", password="strong-password-123")
        Profile.objects.create(user=other, role="customer", phone="+254712345670")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(messages_url).status_code, 404)
        self.assertEqual(self.client.post(messages_url, {"body": "intrude"}, format="json").status_code, 404)
        self.assertEqual(self.client.get("/api/notifications/").data, [])

    def test_customer_can_review_completed_booking_once_and_reviews_are_visible(self):
        booking_id = self.create_booking()
        review_url = f"/api/bookings/{booking_id}/review/"
        self.assertEqual(self.client.post(review_url, {"rating": 5}, format="json").status_code, 400)
        action_url = f"/api/bookings/{booking_id}/action/"
        self.client.force_authenticate(self.provider)
        self.client.post(action_url, {"action": "accept"}, format="json")
        self.client.post(action_url, {"action": "complete"}, format="json")
        self.client.force_authenticate(self.customer)
        self.client.post(action_url, {"action": "confirm_completion"}, format="json")
        response = self.client.post(review_url, {"rating": 5, "comment": "Excellent service."}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.post(review_url, {"rating": 4}, format="json").status_code, 409)
        self.assertEqual(InAppNotification.objects.filter(recipient=self.provider, kind="review").count(), 1)

        self.client.force_authenticate(self.provider)
        booking = self.client.get("/api/bookings/").data[0]
        self.assertEqual(booking["review"]["rating"], 5)
        self.client.force_authenticate(None)
        response = self.client.get(f"/api/offerings/{self.offering.pk}/reviews/")
        self.assertEqual(response.data["average_rating"], 5)
        self.assertEqual(response.data["review_count"], 1)
        self.assertEqual(response.data["reviews"][0]["comment"], "Excellent service.")
        search_url = f"/api/nearby/?latitude=-1.286389&longitude=36.817223&category={self.category.pk}"
        self.client.force_authenticate(self.customer)
        result = self.client.get(search_url).data[0]
        self.assertEqual(result["average_rating"], 5)
        self.assertEqual(result["review_count"], 1)

    def test_offering_price_change_preserves_booking_snapshot_and_owner_access(self):
        booking_id = self.create_booking()
        url = f"/api/offerings/{self.offering.pk}/"
        self.assertEqual(self.client.patch(url, {"pricing": "quote", "price_kes": None}, format="json").status_code, 404)
        self.client.force_authenticate(self.provider)
        self.assertEqual(self.client.patch(url, {"pricing": "fixed", "price_kes": "2000"}, format="json").status_code, 200)
        self.assertEqual(Booking.objects.get(pk=booking_id).price_kes, Decimal("1500.00"))
        self.assertEqual(self.client.patch(url, {"pricing": "quote", "price_kes": None}, format="json").status_code, 200)
        self.assertEqual(self.client.patch(url, {"pricing": "fixed", "price_kes": None}, format="json").status_code, 400)

    def test_browser_session_requires_csrf_and_survives_new_requests(self):
        client = Client(enforce_csrf_checks=True)
        url = "/api/session/login/"
        self.assertEqual(client.post(url, {"username": "customer", "password": "strong-password-123"},
                                     content_type="application/json").status_code, 403)
        csrf = client.get("/api/session/csrf/").json()["csrf_token"]
        response = client.post(url, {"username": "customer", "password": "strong-password-123"},
                               content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("token", response.json())
        self.assertEqual(client.get("/api/profile/").json()["role"], "customer")
        self.assertEqual(client.post("/api/session/logout/").status_code, 403)
        csrf = client.get("/api/session/csrf/").json()["csrf_token"]
        self.assertEqual(client.post("/api/session/logout/", HTTP_X_CSRFTOKEN=csrf).status_code, 204)
        self.assertIn(client.get("/api/profile/").status_code, (401, 403))

    def test_browser_registration_requires_csrf_and_does_not_expose_token(self):
        client = Client(enforce_csrf_checks=True)
        payload = {"username": "new_customer", "password": "uncommon-password-48932",
                   "first_name": "New", "last_name": "Customer", "phone": "+254712345670", "role": "customer"}
        self.assertEqual(client.post("/api/session/register/", payload, content_type="application/json").status_code, 403)
        csrf = client.get("/api/session/csrf/").json()["csrf_token"]
        response = client.post("/api/session/register/", payload, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("token", response.json())
        self.assertTrue(response.cookies["sessionid"]["httponly"])
        self.assertEqual(client.get("/api/profile/").status_code, 200)

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
