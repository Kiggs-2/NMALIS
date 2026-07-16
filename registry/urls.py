from django.contrib.auth import views as auth_views
from django.urls import path

from . import certificate_views, hospital_views, views
from .mpesa import views as mpesa_views

urlpatterns = [
    # ... existing paths ...
    path("renewal/cancel/<int:tx_id>/", views.cancel_stk_push, name="cancel_stk_push"),
    path("renewal/resend/<int:tx_id>/", views.resend_stk_push, name="resend_stk_push"),
]
