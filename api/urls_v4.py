from django.urls import path, include, re_path
from rest_framework import permissions
from rest_framework import routers
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

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

# Article Routes
router.register(r"articles", views.ArticleViewSet_V4)
router.register(r"users/article-archive", views.ArticleArchiveViewSet_V4)
router.register(r"users/article-bookmarks", views.ArticleBookmarksViewSet_V4)
router.register(r"articles/picture-upload", views.PictureUploadArticleViewSet)

# AI Routes
router.register(r"AI/generate-article-tags", views.ArticleTagViewSet)

# Event Routes
router.register(r"events", views.EventViewSet_V4)
router.register(r"users/event-archive", views.EventArchiveViewSet_V4)
router.register(r'users/event-bookmarks', views.EventBookmarksViewSet_V4, basename='bookmarked-events')

#router.register(r"events/summary", views.EventOverviewViewSet_V4)
router.register(r"events/picture-upload", views.PictureUploadEventViewSet)

# Category Routes
router.register(r"categories", views.CategoryViewSet)

# Organization Routes
router.register(r"organizations", views.OrganizationViewSet)

# User Routes
router.register(r"users/device", views.AppUserKnownViewSet)
router.register(r"users/summary", views.SummaryViewSet)
router.register(r"users/article-tags", views.AppUserArticleTagViewSet)
router.register(r"users/event-tags", views.AppUserEventTagViewSet)
router.register(r"users/organizations", views.AppUserOrganizationsViewSet)
router.register(r"users/location", views.AppUserLocationViewSet)
router.register(r"users/push", views.AppUserPushViewSet)

# create admin user
router.register(r"users", views.AdminUserViewSet)

# General Routes
router.register(r"general/appurls", views.AppUrlsViewSet)
router.register(r"area", views.AreaViewSet)

# Contact Routes
router.register(r"contact/feedback", views.FeedbackContactViewSet, basename="feedback")
router.register(r"contact/participate", views.ParticipateContactViewSet, basename="participate"
                
)

# urls for version 4
urlpatterns += [
    path("", include(router.urls)),
    path('events/<int:pk>/', views.EventViewSet_V4.as_view({'get': 'retrieve_event'}), name='retrieve_event'),
    path('articles/<int:id>/picture-upload/', views.PictureUploadArticleViewSet.as_view({'post': 'upload_picture'}), name='article-picture-upload'),
    path('tags/get-all-article-tags/', views.ArticleTagReceiveViewSet_V4.as_view({'get': 'get_all_tags'}), name='get_all_tags'),
    path('tags/get-all-event-tags/', views.EventTagReceiveViewSet_V4.as_view({'get': 'get_all_event_tags'}), name='get_all_event_tags'),
    path('events/<int:id>/picture-upload/', views.PictureUploadEventViewSet.as_view({'post': 'upload_picture'}), name='events-picture-upload'),
    path('general/flag-article/', views.ArticleFlagViewSet_V4.as_view({'post': 'flag'}), name='flag'),
    path('general/flag-event/', views.EventFlagViewSet_V4.as_view({'post': 'flag'}), name='flag'),
    path('users/delete/', views.AdminUserViewSet.as_view({'delete': 'delete_user'}), name='delete_user'),
    path('users/activate/', views.AdminUserViewSet.as_view({'get': 'activate_user'}), name='activate_user'),
    path('users/reset-password-with-token/', views.AdminUserViewSet.as_view({'post': 'reset_password_with_token'}), name='reset_password_with_token'),
    path('users/request-password-reset/', views.AdminUserViewSet.as_view({'post': 'request_password_reset'}), name='request_password_reset'),
    path('users/redirect-user-into-app/', views.AdminUserViewSet.as_view({'get': 'redirect_user_into_app'}), name='redirect_user_into_app'),
    path('users/change-password/', views.AdminUserViewSet.as_view({'post': 'change_password'}), name='change_password'),
    path('users/update-user/', views.AdminUserViewSet.as_view({'put': 'update_user'}), name='update_user'),
    path('users/get-user-details/', views.AdminUserViewSet.as_view({'get': 'get_user_details'}), name='get_user_data'),
    path('token/', views.CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', views.CustomTokenVerifyView.as_view(), name='token_verify'),
    path('redirect/', views.RedirectView.as_view(), name='redirect_to_website'),
    path('users/events/', views.CombinedViewSetEvent_V4.as_view({'get': 'list_user_events'}), name='list_user_events'),
    path('users/articles/', views.CombinedViewSetArticle_V4.as_view({'get': 'list_user_articles'}), name='list_user_articles'),
    path('users/picture-upload/', views.PictureUploadUserViewSet.as_view({'post': 'upload_picture'}), name='organizations-picture-upload'),
    path('area/closest/', views.AreaViewSet.as_view({'get': 'closest'}), name='closest'),

]

