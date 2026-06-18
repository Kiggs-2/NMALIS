from django import template

from registry.models import status_badge_color, status_label

register = template.Library()


@register.filter
def status_display(value):
    return status_label(value)


@register.filter
def status_color(value):
    return status_badge_color(value)
