from django.contrib import admin
from django.conf import settings
from django.conf.urls import url
from django.urls import path, include, re_path
from django.conf.urls.static import static
from django.views.i18n import JavaScriptCatalog

from content.admin import moloadmin

urlpatterns = [
    re_path(r"^jet/", include("jet.urls", "jet")),
    path("", moloadmin.urls),
    #path("", admin.site.urls),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += [
    path("api/v1/", include("api.urls_v1", namespace="v1")),
    path("api/v2/", include("api.urls_v2", namespace="v2")),
    path("api/v3/", include("api.urls", namespace="v3")),
    path("api/v4/", include("api.urls_v4", namespace="v4")),
]

urlpatterns += [path("", include("loginas.urls"))]

# django-recurrence
urlpatterns += [path('jsi18n.js', JavaScriptCatalog.as_view(packages=['recurrence']), name='jsi18n'),]

#admin.sites.AdminSite.site_title = "Molonews"
