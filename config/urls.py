from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from registry.views_errors import permission_denied_view

handler403 = permission_denied_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sysadmin/", include("sysadmin.urls")),
    path("", include("registry.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
