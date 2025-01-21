from django.urls import path, include, re_path

from rest_framework import permissions
from rest_framework import routers
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from . import views

app_name = 'molonews'

schema_view = get_schema_view(
    openapi.Info(
        title="Molonews API", default_version="v3", description="Molonews API",
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
router.register(r"articles", views.ArticleViewSet)
router.register(r"articles/archive", views.ArticleArchiveViewSet)
router.register(r"articles/bookmarks", views.ArticleBookmarksViewSet)
router.register(r"articles/picture-upload", views.PictureUploadArticleViewSet)

router.register(r"AI/generate-article-tags", views.ArticleTagViewSet)

router.register(r"events/picture-upload", views.PictureUploadEventViewSet)
router.register(r"events/archive", views.EventArchiveViewSet)
router.register(r"events/bookmarks", views.EventBookmarksViewSet)
router.register(r"events/summary", views.EventOverviewViewSet)
router.register(r"events", views.EventViewSet)

router.register(r"categories", views.CategoryViewSet)
router.register(r"organizations", views.OrganizationViewSet)

router.register(r"users/device", views.AppUserKnownViewSet)
router.register(r"users/summary", views.SummaryViewSet)
router.register(r"users/articletags", views.AppUserArticleTagViewSet)
router.register(r"users/eventtags", views.AppUserEventTagViewSet)
router.register(r"users/organizations", views.AppUserOrganizationsViewSet)
router.register(r"users/location", views.AppUserLocationViewSet)
router.register(r"users/push", views.AppUserPushViewSet)
router.register(r"appurls", views.AppUrlsViewSet)
router.register(r"area", views.AreaViewSet)


router.register(r"contact/feedback", views.FeedbackContactViewSet, basename="feedback")
router.register(r"contact/participate", views.ParticipateContactViewSet, basename="participate"
                
)

urlpatterns += [
    path("", include(router.urls)),
]

urlpatterns += [
   
]
