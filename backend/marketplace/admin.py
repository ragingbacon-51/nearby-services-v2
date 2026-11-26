from django.contrib import admin
from .models import Booking, Category, Offering, Profile


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


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "offering", "status", "scheduled_for")
    list_filter = ("status",)
    readonly_fields = ("customer", "offering", "details", "address", "scheduled_for", "price_kes",
                       "pricing", "status", "created_at")
