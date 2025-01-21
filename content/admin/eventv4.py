import os
from django.contrib import admin
from ..models import EventV4, Tag, Area, Event_Occurrence
from django.utils.translation import gettext_lazy as _
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from django import forms
from ckeditor.widgets import CKEditorWidget
import time
from logging import getLogger
from django.contrib.auth.models import Group
from django.db.models import Q
from django.forms import CharField, Textarea

logger = getLogger(__name__)

# Define the inline for the Event_Occurrence model
class EventOccurrenceInline(admin.TabularInline):
    model = Event_Occurrence
    extra = 1
    fields = ('start_datetime', 'end_datetime')
    show_change_link = True
    verbose_name = "Termin"  # Singular name
    verbose_name_plural = "Termine"  # Plural name

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Rename the start_datetime and end_datetime fields."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)

        # Rename start_datetime to "Startdatum und Uhrzeit"
        if db_field.name == 'start_datetime':
            formfield.label = "Startdatum und Uhrzeit"
        
        # Rename end_datetime to "Enddatum und Uhrzeit"
        if db_field.name == 'end_datetime':
            formfield.label = "Enddatum und Uhrzeit"
        
        return formfield


# Define the form to include CKEditor for the 'content' field
class EventV4Form(forms.ModelForm):
    content = forms.CharField(widget=CKEditorWidget(config_name="default"), label=_('Inhalt'))

    class Meta:
        model = EventV4
        fields = '__all__'

    # Verlängere das Title-Feld
    title = CharField(
        widget=Textarea(attrs={"cols": 80, "rows": 1}),  
        label=_('title')
    )

    def __init__(self, *args, **kwargs):
        """Override the form initialization to remove the 'source' field for contributors."""
        self.request = kwargs.pop('request', None)  # Pop the request from kwargs
        super().__init__(*args, **kwargs)


    def clean(self):
        """Ensure that the source is automatically set for contributors."""
        cleaned_data = super().clean()
        if self.request and self.request.user.groups.filter(name='Contributors').exists():
            # Automatically assign the source based on the user's source
            user_source = self.request.user.sources.first()
            if user_source:
                cleaned_data['source'] = user_source
        return cleaned_data


@admin.register(EventV4)
class EventV4Admin(admin.ModelAdmin):
    form = EventV4Form  # Assign the custom form with CKEditor

    queryset_filter = None  # Define queryset_filter as None by default

    # Customize the change form template to include a custom save dialog with just one button at the bottom of the form
    change_form_template = "/home/molonews/molonews/content/templates/admin/change_eventv4_form.html"

    list_display = ('id', 'title', 'start_date', 'source', 'event_location', 'published', 'reviewed', 'draft')
    list_filter = ('published', 'reviewed', 'draft', 'tags', 'area')
    search_fields = ('title', 'content', 'street', 'town', 'zip_code')
    ordering = ('start_date',)
    date_hierarchy = 'start_date'
    readonly_fields = ('request_count', 'longitude', 'latitude')
    filter_horizontal = ('tags', 'area')

    # Override formfield_for_manytomany to filter tags
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "tags":
            kwargs["queryset"] = Tag.objects.filter(category_id=2)  # Only show tags with category_id == 2
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    # Define the form contents for the page separated into two fieldsets
    fieldsets = (
        (None, {
            'fields': ('title', 'content', 'source', 'link', 'image_url', 'image', 'image_source', 'published', 'tags', 'area')
        }),
        ('Veranstaltungsort', {
            'fields': ('event_location', 'street', 'zip_code', 'town' )
        }),
    )

    # This is the third fieldset containing the occurrences inline
    inlines = [
        EventOccurrenceInline,
    ]

    def get_fieldsets(self, request, obj=None):
        """Customize the fieldsets based on the user's group."""
        fieldsets = super().get_fieldsets(request, obj)
        
        # Check if the user is a contributor and modify fieldsets
        if request.user.groups.filter(name='Contributors').exists():
            # Remove the 'source' field from the fieldsets for contributors
            new_fieldsets = []
            for fieldset in fieldsets:
                title, field_options = fieldset
                fields = field_options.get('fields', [])
                # Remove 'source' field from each fieldset
                fields = tuple(field for field in fields if field != 'source')
                new_fieldsets.append((title, {'fields': fields}))
            return new_fieldsets
        
        return fieldsets

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        """Customize form before rendering in the admin UI."""
        form = context['adminform'].form
        
        # Check if the user is a contributor and not a superuser
        if request.user.groups.filter(name='Contributors').exists() and 'source' in form.fields:
            # Automatically set and disable the 'source' field
            user_source = request.user.sources.first()
            if user_source:
                form.fields['source'].initial = user_source
                form.fields['source'].disabled = True
                form.fields['source'].required = False

        # Disable the 'Add Another' button for the related fields
        if 'source' in form.fields:
            form.fields['source'].widget.can_add_related = False
            form.fields['source'].widget.can_change_related = False
            form.fields['source'].widget.can_delete_related = False
        if 'tags' in form.fields:
            form.fields['tags'].widget.can_add_related = False
            form.fields['tags'].widget.can_change_related = False
            form.fields['tags'].widget.can_delete_related = False

        # Update the context with any additional adjustments
        context.update({
            'show_save_and_continue': False,
            'show_save_as_draft': False,
            'show_delete_link': True,
            'show_save_and_add_another': False
        })

        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)

        # Modify the 'source' field for contributors
        if db_field.name == 'source' and request.user.groups.filter(name='Contributors').exists():
            formfield.required = False

        return formfield

    def get_form(self, request, obj=None, **kwargs):
        """Customize the form to rename event_location field label."""
        form = super().get_form(request, obj, **kwargs)
        
        # Rename the 'event_location' label
        form.base_fields['event_location'].label = "Name Veranstaltungsort"
        
        return form

 


    def save_model(self, request, obj, form, change):
        # Combine address fields to form a full address
        address = f"{obj.street}, {obj.town}, {obj.zip_code}"
        # Set default latitude and longitude
        obj.latitude = 0.00
        obj.longitude = 0.00

        # Retry mechanism for geocoding
        attempts = 5
        for attempt in range(attempts):
            try:
                # Geocode the address
                geolocator = Nominatim(user_agent="molo.news.backend/4.1 (contact: molonews@uni-bremen.de)")
                location = geolocator.geocode(address, timeout=10)
                if location:
                    # Set the latitude and longitude on the model instance
                    obj.latitude = location.latitude
                    obj.longitude = location.longitude
                    break  # Exit the loop if geocoding is successful
            except GeocoderTimedOut:
                # Handle timeout exception
                logger.error("Geocoding TimeOut for address: %s, attempt: %d", address, attempt + 1)
                if attempt < attempts - 1:
                    time.sleep(2)  # Wait for 2 seconds before retrying
            except Exception as e:
                # Handle other exceptions
                logger.error("Geocoding failed for address: %s, error: %s", address, str(e))
                if attempt < attempts - 1:
                    time.sleep(2)  # Wait for 2 seconds before retrying

        # Automatically set the source for contributors if not already set
        if request.user.groups.filter(name='Contributors').exists() and not request.user.is_superuser:
            user_source = request.user.sources.first()
            if user_source:
                obj.source = user_source

         # Check what the form contains
        temp_image = form.cleaned_data.get('image', None)  # Store the image temporarily

        # If the object is new (no primary key yet)
        if obj.pk is None:
            # Temporarily set image to None
            form.cleaned_data['image'] = None  # Set the image field to None for now

            # Save the object without the image to generate an ID (pk)
            super().save_model(request, obj, form, change)

            # After the object has been saved and has an ID, reassign and save the image
            if temp_image:
                obj.image = temp_image  # Reassign the image to the object
                obj.save()  # Save the object again, this time with the image
        else:
            # If the object already has a primary key, save it normally
            super().save_model(request, obj, form, change)


    def get_queryset(self, request):
        """Customize the queryset based on the user's permissions and filters."""
        qs = super().get_queryset(request)
        user = request.user

        # Apply additional filters if any exist
        if self.queryset_filter:
            qs = qs.filter(Q(**self.queryset_filter))

        # Contributors should only see events related to their source
        if user.groups.filter(name='Contributors').exists() and not user.is_superuser:
            qs = qs.filter(source__related_user=user)

        # Editors can see events up for review or related to their sources
        if user.groups.filter(name='editors').exists():
            qs = qs.filter(Q(up_for_review=True) | Q(source__related_user=user))

        return qs.distinct()



