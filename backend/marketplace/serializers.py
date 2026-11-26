from decimal import Decimal
from django.contrib.auth import get_user_model, password_validation
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from .models import Booking, BookingMessage, Category, InAppNotification, Offering, Profile, Review

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone = serializers.RegexField(r"^\+254[17]\d{8}$")
    role = serializers.ChoiceField(choices=Profile.Role.choices)

    def validate(self, attrs):
        if User.objects.filter(username__iexact=attrs["username"]).exists():
            raise serializers.ValidationError({"username": "This username is already in use."})
        user = User(username=attrs["username"], first_name=attrs["first_name"], last_name=attrs["last_name"])
        password_validation.validate_password(attrs["password"], user)
        return attrs

    @transaction.atomic
    def create(self, data):
        role = data.pop("role")
        phone = data.pop("phone")
        user = User.objects.create_user(**data)
        Profile.objects.create(user=user, role=role, phone=phone)
        return user


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name")


class ProfileSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = Profile
        fields = ("name", "role", "phone", "phone_verified", "identity_status", "description", "latitude", "longitude")
        read_only_fields = ("name", "role", "phone", "phone_verified", "identity_status")

    def validate(self, attrs):
        if self.instance.role != Profile.Role.PROVIDER:
            raise serializers.ValidationError("Only providers can update service details.")
        latitude = attrs.get("latitude", self.instance.latitude)
        longitude = attrs.get("longitude", self.instance.longitude)
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError("Latitude and longitude are both required.")
        return attrs


class OfferingSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.filter(active=True))
    price_kes = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True,
                                         required=False, min_value=Decimal("1"))

    class Meta:
        model = Offering
        fields = ("id", "category", "category_name", "pricing", "price_kes", "active", "profession_verified")
        read_only_fields = ("id", "profession_verified")

    def validate(self, attrs):
        pricing = attrs.get("pricing", getattr(self.instance, "pricing", None))
        price = attrs.get("price_kes", getattr(self.instance, "price_kes", None))
        if (pricing == Offering.Pricing.FIXED and price is None) or (pricing == Offering.Pricing.QUOTE and price is not None):
            raise serializers.ValidationError("A fixed price is required for fixed pricing; quote pricing must not have a price.")
        if self.instance and "category" in attrs and attrs["category"] != self.instance.category:
            raise serializers.ValidationError({"category": "Create a separate offering for a different category."})
        if not self.instance and Offering.objects.filter(provider=self.context["request"].user.profile,
                                                         category=attrs["category"]).exists():
            raise serializers.ValidationError({"category": "You already have an offering for this category."})
        return attrs


class BookingCreateSerializer(serializers.Serializer):
    offering_id = serializers.IntegerField(min_value=1)
    details = serializers.CharField(max_length=1000)
    address = serializers.CharField(max_length=250)
    scheduled_for = serializers.DateTimeField()
    accepted_fixed_price_kes = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("1"),
                                                        required=False)

    def validate_scheduled_for(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("Choose a future date and time.")
        return value


class BookingSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.get_full_name", read_only=True)
    provider_name = serializers.CharField(source="offering.provider.user.get_full_name", read_only=True)
    category_name = serializers.CharField(source="offering.category.name", read_only=True)
    sandbox_payment = serializers.SerializerMethodField()
    contact_phone = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = ("id", "customer_name", "provider_name", "category_name", "details", "address",
                  "scheduled_for", "pricing", "price_kes", "status", "created_at", "sandbox_payment",
                  "contact_phone", "review")
        read_only_fields = fields

    def get_contact_phone(self, obj):
        request = self.context.get("request")
        if not request or obj.status not in (
            Booking.Status.CONFIRMED, Booking.Status.COMPLETED, Booking.Status.PAYMENT_DUE,
            Booking.Status.DISPUTED, Booking.Status.CLOSED_NO_PAYMENT,
        ):
            return None
        if request.user.pk == obj.customer_id:
            profile = obj.offering.provider
        elif request.user.pk == obj.offering.provider.user_id:
            profile = obj.customer.profile
        else:
            return None
        return profile.phone if profile.phone_verified else None

    def get_sandbox_payment(self, obj):
        payment = getattr(obj, "sandbox_payment", None)
        if payment is None:
            return None
        return {"status": payment.status, "amount_kes": payment.amount_kes,
                "commission_kes": str(payment.commission_kes), "provider_share_kes": str(payment.provider_share_kes)}

    def get_review(self, obj):
        review = getattr(obj, "review", None)
        if review is None:
            return None
        return {"rating": review.rating, "comment": review.comment, "created_at": review.created_at}


class QuoteSerializer(serializers.Serializer):
    price_kes = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("1"))


class BookingMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.get_full_name", read_only=True)
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = BookingMessage
        fields = ("id", "sender_name", "is_mine", "body", "created_at")
        read_only_fields = fields

    def get_is_mine(self, obj):
        request = self.context.get("request")
        return bool(request and request.user.pk == obj.sender_id)


class MessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=2000, trim_whitespace=True)


class ReviewSerializer(serializers.ModelSerializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=1000, allow_blank=True, required=False)

    class Meta:
        model = Review
        fields = ("rating", "comment", "created_at")
        read_only_fields = ("created_at",)


class InAppNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InAppNotification
        fields = ("id", "booking_id", "kind", "message", "created_at", "read_at")
        read_only_fields = fields
