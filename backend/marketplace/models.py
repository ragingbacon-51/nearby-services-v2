from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Profile(models.Model):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        PROVIDER = "provider", "Provider"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices)
    phone = models.CharField(max_length=16)
    phone_verified = models.BooleanField(default=False)
    phone_verification_id = models.CharField(max_length=100, blank=True)
    identity_status = models.CharField(max_length=20, default="not_started")
    identity_session_id = models.UUIDField(null=True, blank=True)
    description = models.CharField(max_length=500, blank=True)
    latitude = models.FloatField(null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)])

    def __str__(self):
        return self.user.get_username()


class Offering(models.Model):
    class Pricing(models.TextChoices):
        FIXED = "fixed", "Fixed price"
        QUOTE = "quote", "Quote required"

    provider = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="offerings")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="offerings")
    pricing = models.CharField(max_length=10, choices=Pricing.choices)
    price_kes = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    profession_verified = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "category"], name="one_offering_per_category"),
            models.CheckConstraint(
                condition=(Q(pricing="quote", price_kes__isnull=True) |
                           Q(pricing="fixed", price_kes__isnull=False, price_kes__gte=1)),
                name="offering_valid_price",
            ),
        ]

    def __str__(self):
        return f"{self.provider} - {self.category}"


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting provider"
        QUOTED = "quoted", "Awaiting customer"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Awaiting customer completion confirmation"
        PAYMENT_DUE = "payment_due", "Payment due"
        DISPUTED = "disputed", "Under review"
        DECLINED = "declined", "Declined"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings")
    offering = models.ForeignKey(Offering, on_delete=models.PROTECT, related_name="bookings")
    details = models.CharField(max_length=1000)
    address = models.CharField(max_length=250)
    scheduled_for = models.DateTimeField()
    price_kes = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    pricing = models.CharField(max_length=10, choices=Offering.Pricing.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
