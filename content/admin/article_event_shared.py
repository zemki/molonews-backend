# Standardbibliothek Importe
from logging import getLogger
import locale

# Drittanbieterbibliotheken
from django.db.models import Q
from django.contrib import admin, messages
from django.contrib.admin.views.main import ChangeList
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.forms import CharField, Textarea, ModelForm
from django.forms.models import ModelChoiceIterator, ModelMultipleChoiceField
from django.forms.utils import ErrorList
from django.forms.widgets import ChoiceWidget
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django.utils.timezone import localtime
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.template.loader_tags import register
from ckeditor.widgets import CKEditorWidget

# Lokale Anwendungs-/Bibliotheksspezifische Importe
from ..models import Category, Tag
from .mixins import CantModifyRelatedMixin

# Logger für diese Datei einrichten
logger = getLogger("molonews")

# Setzen Sie die Locale für diese Datei auf Deutsch
locale.setlocale(locale.LC_TIME, 'de_DE.UTF-8')


class ArticleEventChangeListForm(CantModifyRelatedMixin, ModelForm):
    # Filter für die Kategorie der Tags
    tag_category_filter = None

    def __init__(
        self,
        data=None,
        files=None,
        auto_id="id_%s",
        prefix=None,
        initial=None,
        error_class=ErrorList,
        label_suffix=None,
        empty_permitted=False,
        instance=None,
        use_required_attribute=None,
        renderer=None,
    ):
        # Initialisierung der Superklasse
        super().__init__(
            data,
            files,
            auto_id,
            prefix,
            initial,
            error_class,
            label_suffix,
            empty_permitted,
            instance,
            use_required_attribute,
            renderer,
        )

        # Wenn eine Instanz vorhanden ist, setzen Sie das Feld "tags"
        if instance:
            if self.tag_category_filter:
                self.fields["tags"] = ModelMultipleChoiceField(
                    # Filtern Sie die Tags nach der Kategorie
                    queryset=Tag.objects.filter(category_id__in=self.tag_category_filter),
                    initial=list(instance.tags.values_list("id", flat=True)),
                    required=False,
                )
            else:
                self.fields["tags"] = ModelMultipleChoiceField(
                    # Wenn kein Filter vorhanden ist, verwenden Sie alle Tags
                    queryset=Tag.objects.all(),
                    initial=list(instance.tags.values_list("id", flat=True)),
                    required=False,
                )


class ArticleEventChangeList(ChangeList):
    def __init__(
        self,
        request,
        model,
        list_display,
        list_display_links,
        list_filter,
        date_hierarchy,
        search_fields,
        list_select_related,
        list_per_page,
        list_max_show_all,
        list_editable,
        model_admin,
        sortable_by,
    ):
        # Initialisierung der Superklasse
        super().__init__(
            request,
            model,
            list_display,
            list_display_links,
            list_filter,
            date_hierarchy,
            search_fields,
            list_select_related,
            list_per_page,
            list_max_show_all,
            list_editable,
            model_admin,
            sortable_by,
        )

        # Fügen Sie "tags" zu den anzuzeigenden und bearbeitbaren Listen hinzu
        self.list_display = tuple(list_display) + ("tags",)
        self.list_editable = tuple(list_editable) + ("tags",)


class CheckboxSelectMultiple(ChoiceWidget):
    allow_multiple_selected = True
    input_type = "checkbox"
    template_name = "admin/multiple_input_grouped.html"
    option_template_name = "django/forms/widgets/checkbox_option.html"

    def use_required_attribute(self, initial):
        # Don't use the 'required' attribute because browser validation would
        # require all checkboxes to be checked instead of at least one.
        return False

    def value_omitted_from_data(self, data, files, name):
        # HTML checkboxes don't appear in POST data if not checked, so it's
        # never known if the value is actually omitted.
        return False

    def id_for_label(self, id_, index=None):
        """ "
        Don't include for="field_0" in <label> because clicking such a label
        would toggle the first checkbox.
        """
        if index is None:
            return ""
        return super().id_for_label(id_, index)


class GroupedModelMultipleChoiceField(ModelMultipleChoiceField):
    def __init__(self, *args, group_label=None, category_filter=None, **kwargs):
        """Custom Multiple
        ``group_label`` is a function to return a label for each choice group

        """
        self.category_filter = category_filter
        super(GroupedModelMultipleChoiceField, self).__init__(*args, **kwargs)
        if group_label is None:
            self.group_label = lambda group: group
        else:
            self.group_label = group_label

    def _get_choices(self):
        if hasattr(self, "_choices"):
            return self._choices
        return GroupedModelChoiceIterator(self, category_filter=self.category_filter)

    choices = property(_get_choices, ModelMultipleChoiceField._set_choices)


class GroupedModelChoiceIterator(ModelChoiceIterator):
    def __init__(self, *args, category_filter=None, **kwargs):
        # Initialisierung der Kategorie Filter
        self.category_filter = category_filter
        super().__init__(*args, **kwargs)

    def __iter__(self):
        """Yield choices with custom sorting and split into two columns."""
        if self.field.empty_label is not None:
            yield "", self.field.empty_label

        # Collect all tags in a list
        tags = list(self.queryset.all())

        # Sort the tags alphabetically
        sorted_tags = sorted(tags, key=lambda tag: tag.name)

        # Find "Fußball" and "Andere Sportarten"
        football_tag = None
        other_sports_tag = None

        for tag in sorted_tags:
            if tag.name == "Fußball":
                football_tag = tag
            elif tag.name == "andere Sportarten":
                other_sports_tag = tag

        # Remove "Andere Sportarten" from the sorted list
        if other_sports_tag:
            sorted_tags.remove(other_sports_tag)

        # Place "Andere Sportarten" right after "Fußball"
        if football_tag and other_sports_tag:
            football_index = sorted_tags.index(football_tag)
            sorted_tags.insert(football_index + 1, other_sports_tag)

        # Split the sorted tags into two even groups for two columns
        half_length = (len(sorted_tags) + 1) // 2  # Split into two nearly equal halves
        group1 = sorted_tags[:half_length]
        group2 = sorted_tags[half_length:]

        # Yield two separate groups for display in the UI
        yield _("Group 1"), [self.choice(tag) for tag in group1]
        yield _("Group 2"), [self.choice(tag) for tag in group2]


class ArticleEventForm(CantModifyRelatedMixin, ModelForm):
    # Initialisierung der Felder
    dont_modify_related = "source"
    tag_category_filter = []
    title = CharField(widget=Textarea(attrs={"size": "300"}), label=_('title'))
    # content = CharField(widget=CKEditorWidget(config_name="default"), required=False, label=_('content'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance", None)

        # Überprüfen Sie, ob ein Kategorie Filter vorhanden ist
        if not self.tag_category_filter:
            tag_queryset = Tag.objects.all()
        else:
            tag_queryset = Tag.objects.filter(category_id__in=self.tag_category_filter)

        # Überprüfen Sie, ob der Benutzer ein Editor ist
        _required = True
        if self.user.is_editor:
            _required = False

        # Initialisierung des Tags Feldes
        self.fields["tags"] = GroupedModelMultipleChoiceField(
            queryset=tag_queryset,
            widget=CheckboxSelectMultiple,
            required=_required,
            category_filter=self.tag_category_filter,
            label=_("tags")
        )
        self.fields["tags"].widget.attrs = {"class": "vCheckboxLabel"}

        # Überprüfen Sie, ob der Benutzer ein Mitwirkender ist
        if not self.user.is_contributor:
            return

        sources_queryset = self.user.sources.all()
        if "source" in self.fields:
            self.fields["source"].queryset = sources_queryset

        # Überprüfen Sie, ob nur eine Quelle vorhanden ist
        if sources_queryset.count() != 1:
            return

        # Überprüfen Sie, ob eine Instanz vorhanden ist
        if instance:
            return

        # Setzen Sie die Standard-Tags, wenn keine Instanz vorhanden ist
        source = sources_queryset.first()
        self.initial["tags"] = list(source.default_tags.all())


def unset_image_properties(obj):
    """Strip image and image_detail properties from object if needed.

    Args:
        obj (object): current object

    Returns:
        tuple (object, image, image_detail)
    """

    image = None
    image_detail = None
    if obj.image is not None:
        image = obj.image
    if obj.image_detail is not None:
        image_detail = obj.image_detail
    if (image or image_detail) and obj.id is None:
        # obj needs an id before images can be saved
        obj.image = None
        obj.image_detail = None
    return obj, image, image_detail


def get_images_from_original_object(obj, request):
    """Get images fro original object.

    Args:
        obj (object): current object
        request (request): current request

    Returns:
        image, image_detail
    """
    original_pk = request.resolver_match.kwargs["object_id"]
    original_obj = obj._meta.concrete_model.objects.get(id=original_pk)
    return original_obj.image, getattr(original_obj, "image_detail", None)


class ArticleEventAdmin(admin.ModelAdmin):
    # Configuration for list display in the admin interface
    list_display = ["id", "date", "title", "draft", "reviewed", "published", "source"]
    list_filter = ["date", "published", "reviewed", ("source", admin.RelatedOnlyFieldListFilter)]
    search_fields = ("title")
    list_editable = ()
    readonly_fields = ("date",)
    ordering = ("-draft", "-date")
    exclude = ("is_child", "parent_id")
    form = ArticleEventForm
    changeList = ArticleEventChangeList
    changeListForm = ArticleEventChangeListForm

    # Template for the change form
    change_form_template = "admin/custom_change_form.html"

    # Fields to exclude for contributors
    contributor_exclude = (
        "is_hot", "reviewed", "moddate", "image_source",
        "foreign_id", "is_child", "parent_id", "source",
    )

    # Optional filter to apply to the queryset
    queryset_filter = None

    # ---------------------
    # Overriding built-in methods
    # ---------------------
    
    def get_changeform_initial_data(self, request):
        """Set initial data for the change form based on the user's source."""
        user = request.user
        if user.is_contributor and user.sources.count() == 1:
            return {"source": user.sources.first()}

    def get_list_display(self, request):
        """Customize list display fields based on the user's permissions."""
        fields = super().get_list_display(request)
        if request.user.is_contributor and request.user.sources.count() == 1:
            fields = [field for field in fields if field not in self.contributor_exclude]
        return fields

    def get_fields(self, request, obj=None):
        """Customize form fields based on the user's permissions."""
        fields = [field for field in super().get_fields(request, obj) if field not in self.exclude]
        if request.user.is_contributor:
            fields = [field for field in fields if field not in self.contributor_exclude]
            if "published" not in fields:
                fields.append("published")  # Only append 'published' if not already present
    
        return fields

    def get_form(self, request, obj=None, change=False, **kwargs):
        """Get the form for the admin change page."""
        form = super().get_form(request, obj=obj, change=change, **kwargs)

        class ArticleEventForm(form):
            user = request.user

        return ArticleEventForm

    def get_changelist_form(self, request, **kwargs):
        """Customize changelist form based on the user's permissions."""
        self.list_editable = ("reviewed", "published")

        return self.changeListForm

    def get_queryset(self, request):
        """Customize the queryset based on the user's permissions and filters."""
        qs = super().get_queryset(request)
        user = request.user

        # Apply additional filters if any
        if self.queryset_filter:
            qs = qs.filter(Q(**self.queryset_filter))
        
        # Filter based on user role
        if user.is_contributor:
            qs = qs.filter(source__in=user.sources.all())
        if user.is_editor:
            qs = qs.filter(Q(up_for_review=True) | Q(source__in=user.sources.all()))

        return qs.distinct()

    def get_exclude(self, request, obj=None):
        """Determine which fields to exclude based on the user's permissions."""
        exclude = super().get_exclude(request, obj) or ()
        user = request.user

        if user.is_superuser:
            return ()
        
        exclude += ("push_notification_sent", "push_notification_queued")

        if not user.is_editor:
            exclude += ("is_hot", "reviewed", "moddate")
        if user.can_publish and user.is_contributor:
            exclude += ("up_for_review",)

        return exclude

    # ---------------------
    # Custom hooks and methods
    # ---------------------

    def pre_save_hook(self, request, obj, form, change):
        """ Hook to be executed before saveing an object"""
        if request.user.is_contributor and request.user.sources.count() == 1:
            setattr(obj, "source", request.user.sources.first())

        return obj

    def save_hook(self, request, obj, form, change):
        """ Hook to be executed after the save of an object"""
        pass

    def save_model(self, request, obj, form, change):
        """Custom save_model method.

        Args:
            request:
            obj:
            form:
            change:

        Returns:

        """

        if request.user.is_contributor and change:
            if obj.published or obj.reviewed:
                obj.published = False
                obj.reviewed = False
                obj.date = localtime()

        if obj.id is not None:
            obj.tags.set(form.cleaned_data["tags"])

        image = None
        image_detail = None
        if obj.id is None and (obj.image is not None or getattr(obj, 'image_detail') is not None):
            image = obj.image
            if hasattr(obj, 'image_detail'):
                image_detail = obj.image_detail
                obj.image_detail = None
            obj.image = None

        if "_draft" in request.POST or "_continue" in request.POST:
            obj.published = False
            obj.up_for_review = False

            if "_draft" in request.POST:
                obj.draft = True

        elif "_save" in request.POST or "_saveasnew" in request.POST:
            if "_saveasnew" in request.POST:
                image, image_detail = get_images_from_original_object(obj, request)
            if "_saveasnew" in request.POST or not obj.draft:
                obj.published = True
                obj.up_for_review = True
                obj.draft = False

            if obj.published and not obj.up_for_review:
                obj.up_for_review = True

        obj = self.pre_save_hook(request, obj, form, change)

        super().save_model(request, obj, form, change)

        # re add image porperties if needed
        if image:
            obj.image = image
            if hasattr(obj, 'image_detail'):
                obj.image_detail = image_detail
            super().save_model(request, obj, form, change)

        # call the hook
        self.save_hook(request, obj, form, change)

    def delete_hook(self, request, obj):
        pass

    def delete_model(self, request, obj):
        # call hook prior to deletion
        self.delete_hook(request, obj)
        super().delete_model(request, obj)

    def response_change(self, request, obj):
        opts = self.model._meta
        pk_value = obj._get_pk_val()
        preserved_filters = self.get_preserved_filters(request)

        if "_draft" in request.POST:

            obj_repr = str(obj)
            msg_dict = {
                "name": opts.verbose_name,
                "obj": obj_repr,
            }
            msg = _('The {name}draft "{obj}" was added successfully.')
            self.message_user(request, format_html(msg, **msg_dict), messages.SUCCESS)

            redirect_url = reverse(
                "admin:%s_%s_change" % (opts.app_label, opts.model_name),
                args=(pk_value,),
                current_app=self.admin_site.name,
            )
            redirect_url = add_preserved_filters(
                {"preserved_filters": preserved_filters, "opts": opts}, redirect_url
            )
            return HttpResponseRedirect(redirect_url)

        else:
            return super().response_change(request, obj)

    @register.inclusion_tag("admin/custom_submit_line.html", takes_context=True)
    def custom_submit_row(context):
        """
        Displays the row of buttons for delete and save.
        """
        opts = context["opts"]

        is_draft = False
        is_published = False

        if context["object_id"] is not None:
            obj = opts.model.objects.get(pk=context["object_id"])
            is_draft = obj.draft
            is_published = obj.published

        request = context["request"]

        change = context["change"]
        add = context["add"]

        verbose_name_new = opts.verbose_name.split('-')[0]

        is_popup = context["is_popup"]
        ctx = {
            "opts": opts,
            "verbose_name_new": verbose_name_new,
            "is_draft": is_draft,
            "is_published": is_published,
            "user_can_publish": request.user.can_publish or request.user.is_superuser,
            "show_delete_link": (
                    not is_popup
                    and context["has_delete_permission"]
                    and change
                    and context.get("show_delete", True)
            ),
            "show_save_as_new": not is_popup and change and is_draft,
            "show_save_as_draft": not is_popup and (change or add) and not is_draft,
            "show_save_and_continue": not is_popup and context["has_change_permission"],
            "is_popup": is_popup,
            "preserved_filters": context.get("preserved_filters"),
        }
        if context.get("original") is not None:
            ctx["original"] = context["original"]
        return ctx

    def get_object(self, request, object_id, from_field=None):
        obj = super().get_object(request, object_id, from_field=from_field)
        # circumvent filter
        if not obj:
            try:
                obj = self.model.objects.get(pk=object_id)
            except self.model.DoesNotExist:
                pass

        return obj
