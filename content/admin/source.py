from django import forms
from django.contrib import admin
from logging import getLogger
from ..models import Tag
from .mixins import CantModifyRelatedMixin
logger = getLogger("molonews")

class SourceForm(CantModifyRelatedMixin, forms.ModelForm):

    dont_modify_related = ('organization', 'default_category')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance', None)

        if instance:
            queryset = Tag.objects.filter(category=instance.default_category).all()
        else:
            queryset = Tag.objects.none()

        self.fields['default_tags'] = forms.ModelMultipleChoiceField(
            queryset=queryset,
            required=False
        )


class SourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'organization', 'active', 'import_date', 'display_errors')
    list_editable = ('active',)
    readonly_fields = ('import_date', 'display_errors')
    form = SourceForm

    def display_errors(self, instance):
        """
        Gibt die ersten 30 Zeichen der Import-Fehler zurück, falls vorhanden.
        Falls keine Fehler vorhanden sind oder `import_errors` None ist, wird ein leerer String zurückgegeben.
        """
        if instance.id:
            return instance.import_errors[:30] if instance.import_errors else ''
        else:
            return ''

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user

        # Filtert Organisationen heraus, die sich nicht in den Bereichen des Benutzers befinden
        user_areas = user.area.values()
        all_user_areas = []
        for area in user_areas:
            all_user_areas.append(area["id"])

        qs = qs.filter(area__in=all_user_areas)
            
        return qs

    def save_model(self, request, obj, form, change):
        default_image = None
        default_image_detail = None
        if obj.id is None and (obj.default_image is not None or obj.default_image_detail is not None):
            default_image = obj.default_image
            default_image_detail = obj.default_image_detail
            obj.default_image = None
            obj.default_image_detail = None

        super().save_model(request, obj, form, change)

        if default_image or default_image_detail:
            obj.default_image = default_image
            obj.default_image_detail = default_image_detail
            super().save_model(request, obj, form, change)