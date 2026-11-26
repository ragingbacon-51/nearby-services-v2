from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Booking, Category, InAppNotification, Offering, Profile


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    list_editable = ("active",)
    search_fields = ("name",)


@admin.register(Offering)
class OfferingAdmin(admin.ModelAdmin):
    list_display = ("provider", "category", "pricing", "profession_verified", "active")
    list_filter = ("category", "profession_verified", "active")
    readonly_fields = ("provider", "category", "pricing", "price_kes", "active")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone_verified", "identity_status")
    readonly_fields = ("user", "role", "phone", "phone_verified", "phone_verification_id",
                       "identity_status", "identity_session_id", "description", "latitude", "longitude")


class BookingAdminForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and self.instance.status == Booking.Status.DISPUTED:
            outcome = cleaned.get("dispute_outcome")
            note = cleaned.get("dispute_resolution_note", "").strip()
            if outcome and not note:
                self.add_error("dispute_resolution_note", "Enter an internal resolution note.")
            elif note and not outcome:
                self.add_error("dispute_outcome", "Choose a resolution outcome.")
        return cleaned


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "offering", "status", "scheduled_for")
    list_filter = ("status",)
    form = BookingAdminForm
    fields = (
        "customer", "offering", "details", "address", "scheduled_for", "pricing", "price_kes",
        "status", "created_at", "dispute_outcome", "dispute_resolution_note",
        "dispute_resolved_at", "dispute_resolved_by",
    )
    readonly_fields = (
        "customer", "offering", "details", "address", "scheduled_for", "price_kes",
        "pricing", "status", "created_at", "dispute_resolved_at", "dispute_resolved_by",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.method == "POST" and request.resolver_match.url_name == "marketplace_booking_change":
            return queryset.select_for_update()
        return queryset

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is None or obj.status != Booking.Status.DISPUTED:
            readonly.extend(("dispute_outcome", "dispute_resolution_note"))
        return readonly

    def save_model(self, request, obj, form, change):
        was_disputed = change and obj.status == Booking.Status.DISPUTED
        if was_disputed and obj.dispute_outcome:
            if not obj.dispute_resolution_note.strip():
                raise ValidationError({"dispute_resolution_note": "Enter an internal resolution note."})
            obj.status = obj.dispute_outcome
            obj.dispute_resolved_at = timezone.now()
            obj.dispute_resolved_by = request.user
        super().save_model(request, obj, form, change)
        if was_disputed and obj.status != Booking.Status.DISPUTED:
            message = f"An administrator resolved a dispute for booking {obj.pk}."
            for recipient in (obj.customer, obj.offering.provider.user):
                InAppNotification.objects.create(
                    recipient=recipient, booking=obj, kind=InAppNotification.Kind.DISPUTE, message=message,
                )
