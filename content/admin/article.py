from logging import getLogger
from django.contrib import admin
from django.conf import settings
from django.forms import CharField
from django.utils.translation import gettext_lazy as _
from django.forms import CharField, Textarea, ModelForm

from ckeditor.widgets import CKEditorWidget

from .article_event_shared import (
    ArticleEventForm,
    ArticleEventAdmin,
    ArticleEventChangeListForm,
)

logger = getLogger("molonews")


class ArticleChangeListForm(ArticleEventChangeListForm):
    tag_category_filter = [1, 3, 4]


class ArticleForm(ArticleEventForm):
    tag_category_filter = [1, 3, 4]
    abstract = CharField(widget=CKEditorWidget(config_name="default"), label=_('Inhalt'))

    # Verlängere das Title-Feld
    title = CharField(
        widget=Textarea(attrs={"cols": 80, "rows": 1}),  
        label=_('title')
    )

    # Schließe das content-Feld explizit aus
    class Meta:
        exclude = ['content']


class ArticleAdmin(ArticleEventAdmin):
    list_display = (
        "id",
        "date",
        "title",
        "abstract",
        "reviewed",
        "published",
        "is_hot",
        "source",
        "request_count_display",
    )
    list_filter = (
        "date",
        "published",
        "reviewed",
        ("source", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("title", "abstract")
    list_editable = ("reviewed", "published")
    readonly_fields = ("date", "draft", "request_count_display")
    ordering = (
        "-draft",
        "-date",
    )
    # exclude = ()
    form = ArticleForm
    changeListForm = ArticleChangeListForm
    queryset_filter = {"draft": False}

        # Custom method to return request_count with a label
    def request_count_display(self, obj):
        return obj.request_count

    # Set the custom label (short_description)
    request_count_display.short_description = 'Anzahl der Abrufe'



    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        if 'content' in fields:
            fields.remove('content')  
        if 'address' in fields:
            fields.remove('address')  
        if 'request_count' in fields:
            fields.remove('request_count') 
        return fields
    

    def save_hook(self, request, obj, form, change):

        published_value = form.cleaned_data.get('published')
        if published_value is not None:
            obj.published = published_value

        if (
            obj.is_hot
            and obj.published
            and settings.FCM_API_KEY
            and not obj.push_notification_sent
        ):
            if not request.user.is_contributor:
                obj.push_notification_queued = True
                logger.error("Article {} queued for push notification".format(obj.id))
            else:
                logger.error("Contributors can't send push messages.")
        # return obj
        obj.save()



class ArticleDraftAdmin(ArticleAdmin):
    queryset_filter = {"draft": True}
    list_display = (
        "id",
        "date",
        "title",
        "source",
        "reviewed",
        "published",
    )
