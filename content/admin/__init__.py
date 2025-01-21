from django.contrib import admin
from django.contrib.auth.models import Group

from ..models import (
    User,
    Article,
    ArticleDraft,
    Event,
    EventV4,
    EventDraft,
    Source,
    Category,
    Organization,
    Tag,
    AppUser,
)
from .article import ArticleAdmin, ArticleDraftAdmin
from .event import EventAdmin, EventDraftAdmin
from .eventv4 import EventV4Admin
from .source import SourceAdmin
from .user import CustomUserAdmin
from .organization import OrganizationAdmin

from logging import getLogger
logger = getLogger(__name__)


class MoloAdminSite(admin.AdminSite):

    def get_app_list(self, request):
        """
        Return a sorted list of all the installed apps that have been
        registered in this site.
        """
        app_dict = self._build_app_dict(request)

        # Sort the apps alphabetically.
        app_list = sorted(app_dict.values(), key=lambda x: x['name'].lower())

        # Sort the models alphabetically within each app, ignore succeeding 's' and '-'.
        for app in app_list:
            app['models'].sort(key=lambda x: x['name'].rstrip('s').strip('-').lower())

        return app_list


class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "title", "description")


class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "category")
    list_filter = ("category",)


class AppUserAdmin(admin.ModelAdmin):
    list_display = ("id", "date_joined", "device_id")
    # Allow sorting by date_joined (default ascending order)
    ordering = ('-date_joined',)  # Change to 'date_joined' for ascending order


moloadmin = MoloAdminSite(name='Moloadmin')
moloadmin.register(Group)
moloadmin.register(Article, ArticleAdmin)
moloadmin.register(ArticleDraft, ArticleDraftAdmin)
#moloadmin.register(Event, EventAdmin)
#moloadmin.register(EventDraft, EventDraftAdmin)
moloadmin.register(EventV4, EventV4Admin)
moloadmin.register(Source, SourceAdmin)
moloadmin.register(User, CustomUserAdmin)
moloadmin.register(Organization, OrganizationAdmin)
moloadmin.register(Category, CategoryAdmin)
moloadmin.register(Tag, TagAdmin)
moloadmin.register(AppUser, AppUserAdmin)
