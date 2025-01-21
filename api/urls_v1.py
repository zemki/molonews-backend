from django.urls import path, include, re_path

from rest_framework import permissions
from rest_framework import routers
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from . import views

app_name = 'molonews'

schema_view = get_schema_view(
    openapi.Info(
        title="Molonews API", default_version="v1", description="Molonews API",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    re_path(
        r"^swagger(?P<format>\.json|\.yaml)$",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    re_path(
        r"^swagger/$",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    re_path(
        r"^redoc/$", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"
    ),
]


router = routers.DefaultRouter()
router.register(r"articles/archive", views.ArticleArchiveViewSet_V2)
router.register(r"articles/bookmarks", views.ArticleBookmarksViewSet_V2)
router.register(r"articles", views.ArticleViewSet_V2)
router.register(r"categories", views.CategoryViewSet)
router.register(r"organizations", views.OrganizationViewSet_V1)

router.register(r"users/device", views.AppUserKnownViewSet)
router.register(r"users/summary", views.SummaryViewSet)
router.register(r"users/tags", views.AppUserTagViewSet)
router.register(r"users/organizations", views.AppUserOrganizationsViewSet)
router.register(r"users/location", views.AppUserLocationViewSet)
router.register(r"users/push", views.AppUserPushViewSet)

router.register(r"contact/feedback", views.FeedbackContactViewSet, basename="feedback")
router.register(
    r"contact/participate", views.ParticipateContactViewSet, basename="participate"
)

urlpatterns += [
    path("", include(router.urls)),
]
