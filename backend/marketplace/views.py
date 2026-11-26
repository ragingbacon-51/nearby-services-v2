import math
import uuid
from urllib.parse import urlparse

from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from . import verification
from .models import Booking, Category, Offering, Profile
from .serializers import (BookingCreateSerializer, BookingSerializer, CategorySerializer, OfferingSerializer,
                          ProfileSerializer, QuoteSerializer, RegisterSerializer)


class VerificationThrottle(UserRateThrottle):
    scope = "verification"


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
    request.auth.delete()
    return Response(status=204)


@api_view(["GET", "PATCH"])
def profile(request):
    item = request.user.profile
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
    ).select_related("provider__user", "category")
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
                           "distance_km": round(distance, 1)})
    result.sort(key=lambda item: item["distance_km"])
    return Response(result[:100])


@api_view(["GET", "POST"])
def bookings(request):
    if request.method == "GET":
        items = Booking.objects.filter(Q(customer=request.user) | Q(offering__provider__user=request.user)).select_related(
            "customer", "offering__provider__user", "offering__category"
        )
        return Response(BookingSerializer(items, many=True).data)
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
    return Response(BookingSerializer(booking).data, status=201)


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
        if action == "quote" and is_provider and item.status == Booking.Status.PENDING and item.pricing == Offering.Pricing.QUOTE:
            quote = QuoteSerializer(data=request.data)
            quote.is_valid(raise_exception=True)
            item.price_kes = quote.validated_data["price_kes"]
            item.status = Booking.Status.QUOTED
        elif action == "accept" and ((is_provider and item.status == Booking.Status.PENDING and item.pricing == Offering.Pricing.FIXED)
                                      or (is_customer and item.status == Booking.Status.QUOTED)):
            item.status = Booking.Status.CONFIRMED
        elif action == "decline" and item.status in (Booking.Status.PENDING, Booking.Status.QUOTED):
            item.status = Booking.Status.DECLINED
        elif action == "complete" and is_provider and item.status == Booking.Status.CONFIRMED:
            item.status = Booking.Status.COMPLETED
        elif action == "confirm_completion" and is_customer and item.status == Booking.Status.COMPLETED:
            item.status = Booking.Status.PAYMENT_DUE
        elif action == "dispute" and is_customer and item.status == Booking.Status.COMPLETED:
            item.status = Booking.Status.DISPUTED
        else:
            return Response({"detail": "This action is not available."}, status=400)
        item.save(update_fields=["status", "price_kes"])
    return Response(BookingSerializer(item).data)


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
