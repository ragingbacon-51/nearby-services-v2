from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register),
    path("login/", views.login),
    path("logout/", views.logout),
    path("profile/", views.profile),
    path("categories/", views.categories),
    path("offerings/", views.offerings),
    path("offerings/<int:offering_id>/", views.offering_detail),
    path("nearby/", views.nearby),
    path("bookings/", views.bookings),
    path("bookings/<int:booking_id>/action/", views.booking_action),
    path("verify/phone/start/", views.phone_start),
    path("verify/phone/check/", views.phone_check),
    path("verify/identity/start/", views.identity_start),
    path("verify/identity/status/", views.identity_status),
]
