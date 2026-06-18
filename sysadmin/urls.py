from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="sysadmin_dashboard"),
    path("users/", views.user_list, name="sysadmin_user_list"),
    path("users/create/", views.user_create, name="sysadmin_user_create"),
    path("users/<int:pk>/", views.user_detail, name="sysadmin_user_detail"),
    path("users/<int:pk>/edit/", views.user_edit, name="sysadmin_user_edit"),
    path("users/<int:pk>/reset-password/", views.user_reset_password, name="sysadmin_user_reset_password"),
    path("tickets/", views.ticket_list, name="sysadmin_ticket_list"),
    path("tickets/<int:pk>/", views.ticket_detail, name="sysadmin_ticket_detail"),
    path("audit/", views.system_audit, name="sysadmin_audit"),
]
