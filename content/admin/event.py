# Import Django admin modules
from django.contrib import admin
from django.contrib.admin.options import InlineModelAdmin
from django.forms import ChoiceField, RadioSelect
from django.utils.translation import gettext_lazy as _
from ckeditor.widgets import CKEditorWidget
from django import forms

# Import locale for setting the locale
import locale

# Import project-specific models and forms
from ..models import Event, EventChild
from .article_event_shared import (
    ArticleEventForm,
    ArticleEventAdmin,
    ArticleEventChangeListForm,
)

# Import project-specific signals and choices
from ..signals import EVENT_SAVED
from ..choices import RECURRING_EVENT_CHOICES

# Import logging module and create logger
from logging import getLogger
logger = getLogger("molonews")

# Set the locale to German (Germany)
locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")


EVENT_UPDATE_PROPERTIES = [
    "title",
    "content",
    "foreign_id",
    "image_url",
    "image",
    "image_source",
    "address",
    "source",
    "published",
    "reviewed",
    "event_location",
    "recurring",
    "recurring_event_end_date",
]


class EventRadioSelect(RadioSelect):
    input_type = "radio"
    template_name = "admin/multiple_input.html"
    option_template_name = "admin/input_option.html"


class EventForm(ArticleEventForm):
    tag_category_filter = [2]

    recurring = ChoiceField(
        widget=EventRadioSelect(attrs={"class": "inline"}),
        choices=RECURRING_EVENT_CHOICES,
        required=True,
        label=_("recurring"),
    )

    content = forms.CharField(widget=CKEditorWidget(config_name="default"), label=_("Content"))

    recurring_child_placeholder = '<span class="inline_childs"></span>'

    def __init__(self, *args, **kwargs):
        # instance = kwargs.get("instance", None)

        # TODO
        # if instance and instance.is_child:
        #    parent = Event.objects.get(pk=instance.parent_id)
        #    instance.link = parent.link

        super().__init__(*args, **kwargs)

        # set zip code to be required
        setattr(self.fields["zip_code"], "required", True)
        setattr(self.fields["recurring_event_end_date"], "required", True)

    def clean(self):
        super().clean()
        recurring = self.cleaned_data.get("recurring")
        if recurring in ["0", "2"] and "recurring_event_end_date" in self._errors:
            del self._errors["recurring_event_end_date"]

        return self.cleaned_data


class EventChangeListForm(ArticleEventChangeListForm):
    tag_category_filter = [2]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class EventTabularInline(InlineModelAdmin):
    template = "admin/event_tabular.html"


class EventChildsInline(EventTabularInline):
    insert_after = "event_end_date"
    extra = 0
    model = EventChild
    fk_name = "parent"
    fields = [
        "event_date",
        "event_end_date",
    ]
    ordering = ["event_date"]


class EventAdmin(ArticleEventAdmin):

    list_display = (
        "id",
        "event_date_range",
        "title",
        "reviewed",
        "published",
        "recurring",
        "source",
    )
    list_filter = (
        "event_date",
        "published",
        "reviewed",
        "recurring",
        ("source", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("title", "content")
    list_editable = ()
    readonly_fields = ("date", "draft")
    ordering = ("-event_date",)
    form = EventForm
    changeListForm = EventChangeListForm

    queryset_filter = {"draft": False, "auto_generated": False, "is_child": False}

    __delete__current__object = False

    exclude = ("image_detail",)

    change_form_template = "admin/event_change_form.html"

    inlines = [EventChildsInline]

    recurring_list_parent = None

    def event_date_range(self, obj):
        if obj.recurring != 0 and not obj.is_child and not self.recurring_list_parent:
            try:
                last_event = (
                    EventChild.objects.filter(
                        parent=obj,
                    )
                    .order_by("-event_date")[0]
                    .event_date
                )
                return "{} - {}".format(
                    obj.event_date.strftime("%d. %B %Y"),
                    last_event.strftime("%d. %B %Y"),
                )
            except IndexError:
                pass
        return obj.event_date

    event_date_range.short_description = _("event date range")

    def get_changelist_form(self, request, **kwargs):
        if request.user.can_publish or request.user.is_superuser:
            self.list_editable += ("published",)
        if request.user.is_editor:
            self.list_editable += ("reviewed",)

        return EventChangeListForm

    def get_queryset(self, request):

        if self.recurring_list_parent:
            childs = EventChild.objects.filter(parent__id=self.recurring_list_parent)
            ids = [int(self.recurring_list_parent)] + [event.id for event in childs]
            queryset = Event.objects.filter(pk__in=ids).order_by("-event_date")
            return queryset

        return super().get_queryset(request)

    def recurring_changelist_view(self, request, object_id=None, extra_context=None):
        # changelist_view = super().changelist_view(request, extra_context=extra_context)
        # extra_context = {'object_id': object_id}
        return super().changelist_view(request, extra_context=extra_context)

    def changelist_view(self, request, extra_context=None):
        if self.recurring_list_parent:
            self.recurring_list_parent = None
        return super().changelist_view(request, extra_context=extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):

        obj = self.get_object(request, object_id)
        if obj.recurring != 0 and not obj.is_child and not self.recurring_list_parent:
            self.recurring_list_parent = object_id
            return self.recurring_changelist_view(
                request, object_id=object_id, extra_context=extra_context
            )
        # TODO if parent event redirect to new listview
        elif self.recurring_list_parent and object_id == self.recurring_list_parent:
            self.recurring_list_parent = None
        return super().change_view(
            request, object_id, form_url=form_url, extra_context=extra_context
        )

    def get_fields(self, request, obj=None):

        # TODO
        fields = [
            "title",
            "content",
            "moddate",
            "link",
            # "foreign_id",
            "image_url",
            "image",
            # "image_source",
            "tags",
            "source",
            "zip_code",
            "address",
            "event_location",
            "recurring",
            "event_date",
            "event_end_date",
            # "is_recurring",
            "recurrences",
            "recurring_event_end_date",
            # "child_event_dates",
            "published",
            "reviewed",
            "up_for_review",
            "date",
            # "is_child",
            # "parent_id",
            "draft",
            "area",
        ]

        exclude = self.get_exclude(request, obj=obj)
        for ex in exclude:
            if ex in fields:
                fields.remove(ex)

        return fields

    def save_hook(self, request, obj, form, change):
        EVENT_SAVED.send("EventAdmin", instance=obj)


class EventDraftAdmin(EventAdmin):
    queryset_filter = {"draft": True}
    list_display = (
        "id",
        "event_date",
        "title",
        "recurring",
        "source",
    )
