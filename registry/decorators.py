from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def _role_values(roles):
    values = set()
    for role in roles:
        values.add(role.value if hasattr(role, "value") else role)
    return values


def role_required(*roles):
    allowed = _role_values(roles)

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.user.role not in allowed:
                raise PermissionDenied("You do not have access to this area.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
