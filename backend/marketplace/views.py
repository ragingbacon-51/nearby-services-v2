import math
import re
import uuid
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse

from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from . import mpesa, verification
from .models import (Booking, BookingMessage, Category, InAppNotification, Offering, Profile, Review,
                     SandboxPayment)
from .serializers import (BookingCreateSerializer, BookingMessageSerializer, BookingSerializer,
                          CategorySerializer, InAppNotificationSerializer, MessageCreateSerializer,
                          OfferingSerializer, ProfileSerializer, QuoteSerializer, RegisterSerializer,
                          ReviewSerializer)


class VerificationThrottle(UserRateThrottle):
    scope = "verification"


def _notify(recipient, booking, kind, message):
    InAppNotification.objects.create(
        recipient=recipient, booking=booking, kind=kind, message=message,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def session_csrf(request):
    return Response({"csrf_token": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
@csrf_protect
def session_register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    django_login(request, user)
    return Response({"profile": ProfileSerializer(user.profile).data}, status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
@csrf_protect
def session_login(request):
    username, password = request.data.get("username"), request.data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return Response({"detail": "Username and password are required."}, status=400)
    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({"detail": "Invalid username or password."}, status=400)
    if not hasattr(user, "profile"):
        return Response({"detail": "This account cannot sign in to the app."}, status=403)
    django_login(request, user)
    return Response({"profile": ProfileSerializer(user.profile).data})


@api_view(["POST"])
@csrf_protect
def session_logout(request):
    django_logout(request)
    return Response(status=204)


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    token = Token.objects.create(user=user)
    return Response({"token": token.key, "profile": ProfileSerializer(user.profile).data}, status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    username, password = request.data.get("username"), request.data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return Response({"detail": "Username and password are required."}, status=400)
    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({"detail": "Invalid username or password."}, status=400)
    if not hasattr(user, "profile"):
        return Response({"detail": "This account cannot sign in to the app."}, status=403)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "profile": ProfileSerializer(user.profile).data})


@api_view(["POST"])
def logout(request):
    if not isinstance(request.auth, Token):
        return Response({"detail": "Use browser session sign-out for this account."}, status=400)
    request.auth.delete()
    return Response(status=204)


@api_view(["GET", "PATCH"])
def profile(request):
    item = Profile.objects.filter(user=request.user).first()
    if item is None:
        return Response({"detail": "This account cannot sign in to the app."}, status=403)
    if request.method == "PATCH":
        serializer = ProfileSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
    return Response(ProfileSerializer(item).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def categories(request):
    return Response(CategorySerializer(Category.objects.filter(active=True), many=True).data)


@api_view(["GET", "POST"])
def offerings(request):
    if request.user.profile.role != Profile.Role.PROVIDER:
        return Response({"detail": "Only providers can manage offerings."}, status=403)
    if request.method == "GET":
        items = Offering.objects.filter(provider=request.user.profile).select_related("category")
        return Response(OfferingSerializer(items, many=True).data)
    serializer = OfferingSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    try:
        with transaction.atomic():
            item = serializer.save(provider=request.user.profile)
    except IntegrityError:
        return Response({"detail": "You already have an offering for this category."}, status=400)
    return Response(OfferingSerializer(item).data, status=201)


@api_view(["PATCH"])
def offering_detail(request, offering_id):
    item = Offering.objects.filter(pk=offering_id, provider=request.user.profile).first()
    if item is None:
        return Response({"detail": "Offering not found."}, status=404)
    serializer = OfferingSerializer(item, data=request.data, partial=True, context={"request": request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


class NearbySearchSerializer(serializers.Serializer):
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    category = serializers.IntegerField(min_value=1)
    radius = serializers.FloatField(min_value=0.1, max_value=100, default=20)


@api_view(["GET"])
def nearby(request):
    serializer = NearbySearchSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    query = serializer.validated_data
    items = Offering.objects.filter(
        category_id=query["category"], category__active=True, active=True, profession_verified=True,
        provider__role=Profile.Role.PROVIDER, provider__phone_verified=True,
        provider__identity_status="approved", provider__latitude__isnull=False,
        provider__longitude__isnull=False, provider__user__is_active=True,
    ).select_related("provider__user", "category").annotate(
        review_count=Count("bookings__review"),
        average_rating=Avg("bookings__review__rating"),
    )
    result = []
    for item in items:
        lat1, lat2 = math.radians(query["latitude"]), math.radians(item.provider.latitude)
        dlat, dlon = lat2 - lat1, math.radians(item.provider.longitude - query["longitude"])
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        distance = 6371 * 2 * math.asin(min(1, math.sqrt(a)))
        if distance <= query["radius"]:
            result.append({"id": item.pk, "provider_name": item.provider.user.get_full_name(),
                           "category_name": item.category.name, "description": item.provider.description,
                           "pricing": item.pricing, "price_kes": str(item.price_kes) if item.price_kes else None,
                           "distance_km": round(distance, 1), "review_count": item.review_count,
                           "average_rating": round(float(item.average_rating), 1) if item.average_rating is not None else None})
    result.sort(key=lambda item: item["distance_km"])
    return Response(result[:100])


@api_view(["GET", "POST"])
def bookings(request):
    if request.method == "GET":
        items = Booking.objects.filter(Q(customer=request.user) | Q(offering__provider__user=request.user)).select_related(
            "customer__profile", "offering__provider__user", "offering__category", "sandbox_payment", "review"
        )
        return Response(BookingSerializer(items, many=True, context={"request": request}).data)
    if request.user.profile.role != Profile.Role.CUSTOMER or not request.user.profile.phone_verified:
        return Response({"detail": "A verified customer phone is required."}, status=403)
    serializer = BookingCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    with transaction.atomic():
        item = Offering.objects.select_for_update().filter(
            pk=data["offering_id"], active=True, category__active=True, profession_verified=True,
            provider__role=Profile.Role.PROVIDER, provider__phone_verified=True,
            provider__identity_status="approved", provider__user__is_active=True,
        ).first()
        if not item:
            return Response({"detail": "This provider is unavailable."}, status=404)
        if item.pricing == Offering.Pricing.FIXED and data.get("accepted_fixed_price_kes") != item.price_kes:
            return Response({"detail": "The fixed price changed or was not accepted. Search again."}, status=409)
        if item.pricing == Offering.Pricing.QUOTE and data.get("accepted_fixed_price_kes") is not None:
            return Response({"detail": "Pricing changed. Search again."}, status=409)
        booking = Booking.objects.create(customer=request.user, offering=item, pricing=item.pricing,
                                         price_kes=item.price_kes, details=data["details"],
                                         address=data["address"], scheduled_for=data["scheduled_for"])
        _notify(
            item.provider.user, booking, InAppNotification.Kind.BOOKING,
            f"New booking request from {request.user.get_full_name() or request.user.get_username()}.",
        )
    return Response(BookingSerializer(booking, context={"request": request}).data, status=201)


@api_view(["POST"])
def booking_action(request, booking_id):
    with transaction.atomic():
        item = Booking.objects.select_for_update().filter(
            Q(customer=request.user) | Q(offering__provider__user=request.user), pk=booking_id
        ).select_related("offering__provider__user", "offering__category", "customer").first()
        if item is None:
            return Response({"detail": "Booking not found."}, status=404)
        action = request.data.get("action")
        is_provider = item.offering.provider.user_id == request.user.id
        is_customer = item.customer_id == request.user.id
        recipient = None
        notification_text = None
        if action == "quote" and is_provider and item.status == Booking.Status.PENDING and item.pricing == Offering.Pricing.QUOTE:
            quote = QuoteSerializer(data=request.data)
            quote.is_valid(raise_exception=True)
            item.price_kes = quote.validated_data["price_kes"]
            item.status = Booking.Status.QUOTED
            recipient = item.customer
            notification_text = "The provider sent a quote for your booking."
        elif action == "accept" and ((is_provider and item.status == Booking.Status.PENDING and item.pricing == Offering.Pricing.FIXED)
                                      or (is_customer and item.status == Booking.Status.QUOTED)):
            item.status = Booking.Status.CONFIRMED
            recipient = item.customer if is_provider else item.offering.provider.user
            notification_text = "The booking was accepted."
        elif action == "decline" and item.status in (Booking.Status.PENDING, Booking.Status.QUOTED):
            item.status = Booking.Status.DECLINED
            recipient = item.customer if is_provider else item.offering.provider.user
            notification_text = "The booking was declined."
        elif action == "complete" and is_provider and item.status == Booking.Status.CONFIRMED:
            item.status = Booking.Status.COMPLETED
            recipient = item.customer
            notification_text = "The provider marked your booking complete."
        elif action == "confirm_completion" and is_customer and item.status == Booking.Status.COMPLETED:
            item.status = Booking.Status.PAYMENT_DUE
            recipient = item.offering.provider.user
            notification_text = "The customer confirmed the work is complete."
        elif action == "dispute" and is_customer and item.status == Booking.Status.COMPLETED:
            item.status = Booking.Status.DISPUTED
            recipient = item.offering.provider.user
            notification_text = "The customer raised a dispute for this booking."
        else:
            return Response({"detail": "This action is not available."}, status=400)
        item.save(update_fields=["status", "price_kes"])
        if recipient and notification_text:
            _notify(recipient, item, InAppNotification.Kind.DISPUTE if action == "dispute"
                    else InAppNotification.Kind.BOOKING, notification_text)
    return Response(BookingSerializer(item, context={"request": request}).data)


@api_view(["GET", "POST"])
def booking_messages(request, booking_id):
    booking = Booking.objects.filter(
        Q(customer=request.user) | Q(offering__provider__user=request.user), pk=booking_id
    ).select_related("customer", "offering__provider__user").first()
    if booking is None:
        return Response({"detail": "Booking not found."}, status=404)
    if request.method == "GET":
        messages = list(BookingMessage.objects.filter(booking=booking).select_related("sender")
                        .order_by("-created_at", "-id")[:100])
        messages.reverse()
        return Response(BookingMessageSerializer(messages, many=True, context={"request": request}).data)
    if booking.status in (Booking.Status.DECLINED, Booking.Status.CLOSED_NO_PAYMENT):
        return Response({"detail": "Messaging is closed for this booking."}, status=409)
    serializer = MessageCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        booking = Booking.objects.select_for_update().filter(
            Q(customer=request.user) | Q(offering__provider__user=request.user), pk=booking_id
        ).select_related("customer", "offering__provider__user").first()
        if booking is None:
            return Response({"detail": "Booking not found."}, status=404)
        if booking.status in (Booking.Status.DECLINED, Booking.Status.CLOSED_NO_PAYMENT):
            return Response({"detail": "Messaging is closed for this booking."}, status=409)
        recipient = booking.offering.provider.user if booking.customer_id == request.user.id else booking.customer
        message = BookingMessage.objects.create(
            booking=booking, sender=request.user, body=serializer.validated_data["body"],
        )
        _notify(recipient, booking, InAppNotification.Kind.MESSAGE, "You have a new booking message.")
    return Response(BookingMessageSerializer(message, context={"request": request}).data, status=201)


@api_view(["POST"])
def booking_review(request, booking_id):
    serializer = ReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        with transaction.atomic():
            booking = Booking.objects.select_for_update().filter(
                pk=booking_id, customer=request.user,
            ).select_related("offering__provider__user").first()
            if booking is None:
                return Response({"detail": "Booking not found."}, status=404)
            if booking.status != Booking.Status.PAYMENT_DUE:
                return Response({"detail": "You can review after confirming the work is complete."}, status=400)
            review = Review.objects.create(booking=booking, **serializer.validated_data)
            _notify(
                booking.offering.provider.user, booking, InAppNotification.Kind.REVIEW,
                "A customer left a review for your service.",
            )
    except IntegrityError:
        if Review.objects.filter(booking_id=booking_id).exists():
            return Response({"detail": "A review has already been submitted for this booking."}, status=409)
        raise
    return Response(ReviewSerializer(review).data, status=201)


@api_view(["GET"])
@permission_classes([AllowAny])
def offering_reviews(request, offering_id):
    if not Offering.objects.filter(pk=offering_id).exists():
        return Response({"detail": "Offering not found."}, status=404)
    queryset = Review.objects.filter(booking__offering_id=offering_id)
    summary = queryset.aggregate(average_rating=Avg("rating"), review_count=Count("id"))
    reviews = queryset.order_by("-created_at", "-id")[:50]
    return Response({
        "average_rating": round(float(summary["average_rating"]), 1) if summary["average_rating"] is not None else None,
        "review_count": summary["review_count"],
        "reviews": ReviewSerializer(reviews, many=True).data,
    })


@api_view(["GET"])
def notifications(request):
    items = InAppNotification.objects.filter(recipient=request.user)[:50]
    return Response(InAppNotificationSerializer(items, many=True).data)


@api_view(["POST"])
def notification_read(request, notification_id):
    updated = InAppNotification.objects.filter(
        pk=notification_id, recipient=request.user, read_at__isnull=True,
    ).update(read_at=timezone.now())
    if not updated and not InAppNotification.objects.filter(pk=notification_id, recipient=request.user).exists():
        return Response({"detail": "Notification not found."}, status=404)
    return Response(status=204)


@api_view(["POST"])
@throttle_classes([VerificationThrottle])
def sandbox_payment(request, booking_id):
    try:
        config = mpesa.configuration()
    except mpesa.MpesaError as exc:
        return Response({"detail": str(exc)}, status=503)
    phone = request.data.get("phone")
    if not isinstance(phone, str) or not re.fullmatch(r"254[17]\d{8}", phone):
        return Response({"detail": "Enter a sandbox test phone number in 2547XXXXXXXX format."}, status=400)
    with transaction.atomic():
        booking = Booking.objects.select_for_update().filter(pk=booking_id, customer=request.user).first()
        if booking is None:
            return Response({"detail": "Booking not found."}, status=404)
        if booking.status != Booking.Status.PAYMENT_DUE:
            return Response({"detail": "The customer must confirm completion before checkout."}, status=400)
        if booking.price_kes is None or booking.price_kes != booking.price_kes.to_integral_value():
            return Response({"detail": "Sandbox checkout requires a whole-shilling service price."}, status=400)
        if SandboxPayment.objects.filter(booking=booking).exists():
            return Response({"detail": "A sandbox payment attempt already exists for this booking."}, status=409)
        commission = (booking.price_kes * Decimal("0.05")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        try:
            with transaction.atomic():
                payment = SandboxPayment.objects.create(
                    booking=booking, amount_kes=int(booking.price_kes), commission_kes=commission,
                    provider_share_kes=booking.price_kes - commission,
                )
        except IntegrityError:
            return Response({"detail": "A sandbox payment attempt already exists for this booking."}, status=409)
    try:
        result = mpesa.start_checkout(config, payment.amount_kes, phone, booking.pk)
    except mpesa.MpesaError:
        payment.status = SandboxPayment.Status.UNKNOWN
        payment.save(update_fields=["status"])
        return Response({"detail": "Checkout outcome is unknown. Do not retry; investigate the sandbox transaction."}, status=502)
    checkout_id = result.get("CheckoutRequestID")
    if str(result.get("ResponseCode")) != "0" or not isinstance(checkout_id, str) or not checkout_id or len(checkout_id) > 200:
        payment.status = SandboxPayment.Status.UNKNOWN
        payment.save(update_fields=["status"])
        return Response({"detail": "Checkout response was inconclusive. Do not retry; investigate the sandbox transaction."}, status=502)
    payment.checkout_request_id = checkout_id
    payment.status = SandboxPayment.Status.PENDING
    payment.save(update_fields=["checkout_request_id", "status"])
    return Response(BookingSerializer(booking, context={"request": request}).data, status=201)


@api_view(["POST"])
@throttle_classes([VerificationThrottle])
def sandbox_payment_status(request, booking_id):
    try:
        config = mpesa.configuration()
    except mpesa.MpesaError as exc:
        return Response({"detail": str(exc)}, status=503)
    payment = SandboxPayment.objects.filter(booking_id=booking_id, booking__customer=request.user).first()
    if payment is None:
        return Response({"detail": "Sandbox payment not found."}, status=404)
    if not payment.checkout_request_id:
        return Response({"detail": "The checkout outcome is unknown and requires investigation."}, status=409)
    if payment.status == SandboxPayment.Status.SUCCEEDED:
        return Response(BookingSerializer(payment.booking, context={"request": request}).data)
    try:
        result = mpesa.query_checkout(config, payment.checkout_request_id)
    except mpesa.MpesaError as exc:
        return Response({"detail": str(exc)}, status=503)
    if result.get("CheckoutRequestID") != payment.checkout_request_id or str(result.get("ResponseCode")) != "0":
        return Response({"detail": "M-Pesa returned an inconclusive status. Try again later."}, status=502)
    code = str(result.get("ResultCode"))
    if code == "0":
        payment.status = SandboxPayment.Status.SUCCEEDED
        payment.save(update_fields=["status"])
    elif code != "9999":
        payment.status = SandboxPayment.Status.UNKNOWN
        payment.save(update_fields=["status"])
    return Response(BookingSerializer(payment.booking, context={"request": request}).data)


@csrf_exempt
@require_POST
def mpesa_callback(request):
    # Callbacks are not authenticated; only a separate Daraja status query changes payment state.
    return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})


def _verification_error(exc):
    return Response({"detail": str(exc)}, status=503)


@api_view(["POST"])
@throttle_classes([VerificationThrottle])
def phone_start(request):
    item = request.user.profile
    if item.phone_verified:
        return Response({"detail": "Phone is already verified."})
    try:
        result = verification.start_phone(item.phone)
    except verification.ProviderError as exc:
        return _verification_error(exc)
    verification_id = result.get("verification_id")
    if not isinstance(verification_id, str) or not verification_id or len(verification_id) > 100:
        return Response({"detail": "Phone verification returned an invalid response."}, status=502)
    item.phone_verification_id = verification_id
    item.save(update_fields=["phone_verification_id"])
    return Response({"detail": "Verification code requested."})


@api_view(["POST"])
@throttle_classes([VerificationThrottle])
def phone_check(request):
    item, code = request.user.profile, request.data.get("code")
    if not item.phone_verification_id or not isinstance(code, str) or not code.isdigit() or not 4 <= len(code) <= 8:
        return Response({"detail": "Start verification and enter a valid code."}, status=400)
    try:
        result = verification.check_phone(item.phone_verification_id, code)
    except verification.ProviderError as exc:
        return _verification_error(exc)
    if result.get("status") != "approved" or result.get("verification_id") != item.phone_verification_id:
        return Response({"detail": "Code not approved. Check the code or request a new one."}, status=400)
    item.phone_verified, item.phone_verification_id = True, ""
    item.save(update_fields=["phone_verified", "phone_verification_id"])
    return Response(ProfileSerializer(item).data)


@api_view(["POST"])
@throttle_classes([VerificationThrottle])
def identity_start(request):
    item = request.user.profile
    if item.role != Profile.Role.PROVIDER:
        return Response({"detail": "Identity verification is for providers."}, status=403)
    if item.identity_status == "approved":
        return Response({"detail": "Identity is already verified."}, status=400)
    try:
        result = verification.start_identity(request.user)
    except verification.ProviderError as exc:
        return _verification_error(exc)
    try:
        session_id = uuid.UUID(str(result["session_id"]))
        url = result["url"]
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "verify.didit.me":
            raise ValueError("Unexpected verification URL")
    except (KeyError, ValueError, TypeError):
        return Response({"detail": "Identity verification returned an invalid response."}, status=502)
    item.identity_session_id, item.identity_status = session_id, "pending"
    item.save(update_fields=["identity_session_id", "identity_status"])
    return Response({"url": url})


@api_view(["POST"])
@throttle_classes([VerificationThrottle])
def identity_status(request):
    item = request.user.profile
    if not item.identity_session_id:
        return Response({"detail": "Start identity verification first."}, status=400)
    try:
        decision = verification.identity_decision(item.identity_session_id)
    except verification.ProviderError as exc:
        return _verification_error(exc)
    if str(decision.get("session_id")) != str(item.identity_session_id):
        return Response({"detail": "Identity verification returned an invalid response."}, status=502)
    if verification.identity_approved(decision, request.user):
        item.identity_status = "approved"
    elif decision.get("status") in ("Declined", "Abandoned"):
        item.identity_status = "declined"
    else:
        item.identity_status = "pending"
    item.save(update_fields=["identity_status"])
    return Response(ProfileSerializer(item).data)
