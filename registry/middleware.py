"""
Session idle timeout middleware and security headers.
"""
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


class SessionIdleTimeoutMiddleware:
    """
    Log out users after a period of inactivity (default: 3600 seconds / 1 hour).
    The timer resets on each request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip for non-authenticated users, AJAX, and login/logout pages
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Skip for exempt URL patterns
        path = request.path_info
        exempt_paths = getattr(settings, "SESSION_IDLE_TIMEOUT_EXEMPT", [])
        for exempt in exempt_paths:
            if path.startswith(exempt):
                return self.get_response(request)

        idle_seconds = getattr(settings, "SESSION_IDLE_TIMEOUT_SECONDS", 120)

        last_activity = request.session.get("last_activity")
        now = datetime.now(timezone.utc) if settings.USE_TZ else datetime.now()

        if last_activity is not None:
            # Parse stored timestamp
            if isinstance(last_activity, str):
                try:
                    last_activity = datetime.fromisoformat(last_activity)
                except (ValueError, TypeError):
                    last_activity = None

            if last_activity is not None:
                elapsed = (now - last_activity).total_seconds()
                if elapsed > idle_seconds:
                    from django.contrib.auth import logout

                    logout(request)
                    messages.warning(
                        request,
                        "Your session has timed out due to inactivity. Please log in again.",
                    )
                    return redirect(reverse("login"))

        # Update last activity timestamp
        request.session["last_activity"] = now.isoformat()
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """
    Apply security-related HTTP headers to every response.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Security headers
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "DENY"
        response["X-XSS-Protection"] = "1; mode=block"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if not settings.DEBUG:
            response["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response["Permissions-Policy"] = (
                "camera=(), microphone=(), geolocation=(), interest-cohort=()"
            )

        return response
