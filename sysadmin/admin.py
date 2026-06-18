from django.contrib import admin

from .models import SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("pk", "subject", "submitted_by", "status", "priority", "assigned_to", "created_at")
    list_filter = ("status", "priority")
    search_fields = ("subject", "description")
