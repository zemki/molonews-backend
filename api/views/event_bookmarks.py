from django.db.models import Count, Q, Exists, OuterRef
from datetime import datetime, timedelta
from django.utils.timezone import localtime
from rest_framework import viewsets, serializers, filters
from drf_yasg.utils import swagger_auto_schema, swagger_serializer_method
import django_filters as df
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from logging import getLogger
from django.shortcuts import get_object_or_404
from django.conf import settings
import jwt
import pytz
from rest_framework.pagination import PageNumberPagination

logger = getLogger(__name__)

from .util import (
    choices_parameter,
    integer_parameter,
    string_parameter,
    boolean_parameter,
    header_string_parameter,
    isodate_parameter,
    bad_request
)
from content.models import AppUser, EventV4, Tag, Organization, Source, Event_Occurrence, User
from content.choices import ORGANIZATION_TYPE_CHOICES
from drf_yasg import openapi

from .article_event_shared import (
    BaseViewSet,
    AppUserBaseViewSet,
    SourceTypeFilter,
    SourceActiveFilter,
    get_source_default_image_url,
)

BASE_LIST_FIELDS = (
    "id",
    "title",
    "content",
    "image_url",
    'start_date',
    "area",
)

EVENT_LIST_FIELDS = BASE_LIST_FIELDS + (
    "event_location",
    "link",
    "tags",
    "organization",
    "organization_type",
    "organization_name",
)
EVENT_RETRIEVE_FIELDS = EVENT_LIST_FIELDS + (
    "source",
    "content",
)

FILTER_BASE_FIELDS = [
    "organization",
    "tags",
    "organization_all_tags",
]

def get_appuser(device_id):
    """Try to get an AppUser by device id

    Args:
        device_id (str): device id string

    Returns:
        AppUser or None
    """
    try:
        return AppUser.objects.get(device_id=device_id)
    except AppUser.DoesNotExist:
        return None


class InFilter(df.FilterSet):
    def __init__(self, field_name, lookup_expr="in"):
        """
        Initializes a new instance of the InFilter class.

        Args:
            field_name (str): The name of the field to filter on.
            lookup_expr (str, optional): The lookup expression to use for filtering. Defaults to "in".
        """
        self.field_name = field_name
        self.lookup_expr = lookup_expr


# Define a custom filter backend class named DeviceIdFilter
class DeviceIdFilter(filters.BaseFilterBackend):
    
    # Define the method to filter the queryset based on the device ID from the request headers
    def filter_queryset(self, request, queryset, view):
        # Retrieve the device ID from the request headers
        device_id = request.headers.get("X-Device-ID", None)
        
        # If a device ID is found in the headers
        if device_id is not None:
            try:
                # Retrieve the AppUser instance
                app_user = AppUser.objects.get(device_id=device_id)
                # Annotate the queryset with 'bookmarked' field
                queryset = queryset.annotate(
                    bookmarked=Exists(
                        app_user.bookmarked_events.filter(pk=OuterRef('pk'))
                    )
                )
                
                # Annotate the queryset with 'archived' field
                queryset = queryset.annotate(
                    archived=Exists(
                        app_user.archived_events.filter(pk=OuterRef('pk'))
                    )
                )
            except AppUser.DoesNotExist:
                # Handle the case where the AppUser does not exist
                pass
    
        # Return the modified queryset
        return queryset

    # Define the method to get schema fields, which is required by the BaseFilterBackend
    def get_schema_fields(self, view):
        # Return an empty list as this filter does not add any fields to the schema
        return []


# Define a serializer class named EventTagsSerializer inheriting from ModelSerializer
class EventTagsSerializer(serializers.ModelSerializer):
    # Meta class to specify the model and fields to be serialized
    class Meta:
        # Specify the model to be used for this serializer
        model = Tag
        # Specify the fields of the model that should be included in the serialization
        fields = ("id", "name", "color")


# Define a serializer class named EventBaseSerializer inheriting from ModelSerializer
class EventBaseSerializer(serializers.ModelSerializer):

    # Define a nested serializer for tags using EventTagsSerializer, set to read-only, and allowing multiple entries
    tags = EventTagsSerializer(read_only=True, many=True)
    # Define custom serializer method fields for organization-related attributes
    organization = serializers.SerializerMethodField()
    organization_type = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    # Define a custom serializer method field for the image URL
    image_url = serializers.SerializerMethodField()
    # Define custom serializer method fields for archived and bookmarked status
    archived = serializers.SerializerMethodField()
    bookmarked = serializers.SerializerMethodField()

    # Define a method to get the archived status, using a boolean field for Swagger documentation
    @swagger_serializer_method(serializers.BooleanField)
    def get_archived(self, instance):
        # Get the archived attribute from the instance, defaulting to False if not present, and convert to boolean
        archived = bool(getattr(instance, "archived", False))
        return archived

    # Define a method to get the bookmarked status, using a boolean field for Swagger documentation
    @swagger_serializer_method(serializers.BooleanField)
    def get_bookmarked(self, instance):
        # Get the bookmarked attribute from the instance, defaulting to False if not present, and convert to boolean
        bookmarked = bool(getattr(instance, "bookmarked", False))
        return bookmarked

    # Define a method to get the image URL
    def get_image_url(self, instance):
        # If the instance has an image, build an absolute URI using the request context
        if instance.image:
            return self.context["request"].build_absolute_uri(instance.image.url)
        # If the instance has an image URL, return it
        elif instance.image_url:
            return instance.image_url
        # If neither is present, use a utility function to get a default image URL
        else:
            return get_source_default_image_url(instance, self.context)

    # Define a method to get the organization ID, using an integer field for Swagger documentation
    @swagger_serializer_method(serializers.IntegerField)
    def get_organization(self, instance):
        return instance.source.organization.id

    # Define a method to get the organization type
    def get_organization_type(self, instance):
        return instance.source.organization.type

    # Define a method to get the organization name
    def get_organization_name(self, instance):
        return instance.source.organization.name
    
class EventOccurrenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event_Occurrence
        fields = (
            "start_datetime",
            "end_datetime",
        )

# Serializer for the event list, inheriting from EventBaseSerializer
class EventListSerializer(EventBaseSerializer):

    # Define a SerializerMethodField to handle custom serialization for the 'link' field
    link = serializers.SerializerMethodField()
    occurrences_list = serializers.SerializerMethodField()

    # Meta class to specify the model and fields to be included in the serialization
    class Meta:
        model = EventV4  # The model that this serializer is associated with
        fields = EVENT_LIST_FIELDS + (  # Include predefined fields and additional fields
            "archived",
            "bookmarked",
            "occurrences_list",
        )

    # Custom method to get the link, decorated for swagger documentation
    @swagger_serializer_method(serializers.URLField)
    def get_link(self, instance):
        # If the instance is a child event, retrieve the parent event's link
        if instance.is_child:
            pass
            #_event_child = EventChild.objects.get(event=instance)  # Fetch the EventChild instance
            #return _event_child.parent.link  # Return the parent event's link
        # If the instance is not a child event, return its own link
        return instance.link
    
    @swagger_serializer_method(serializer_or_field=EventOccurrenceSerializer(many=True))
    def get_occurrences_list(self, obj):
        # This method will fetch the occurrences for the event
        event_occurrences = Event_Occurrence.objects.filter(event=obj)
        return EventOccurrenceSerializer(event_occurrences, many=True).data


# Serializer for paginated events with bookmarked and archived status
class PaginatedEventBookmarkedArchivedSerializer(serializers.Serializer):
    
    # Field to store the total count of events
    count = serializers.IntegerField()

    # Field to store the URL of the next page of results, if available
    next = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    
    # Field to store the URL of the previous page of results, if available
    previous = serializers.URLField(allow_blank=True, allow_null=True, required=False)

    # Field to store the list of event results, using EventListSerializer for each event
    results = EventListSerializer(many=True)


class EventRetrieveSerializer(EventBaseSerializer):
    # Serializer method field to dynamically get the 'link' attribute
    link = serializers.SerializerMethodField()
    occurrences_list = serializers.SerializerMethodField()

    class Meta:
        # Specify the model associated with this serializer
        model = EventV4
        # Define the fields to be included in the serialized output
        fields = EVENT_RETRIEVE_FIELDS + (
            "archived",
            "bookmarked",
            "occurrences_list", 
        )

    def get_occurrences_list(self, obj):
        # This method will fetch the occurrences for the event
        event_occurrences = Event_Occurrence.objects.filter(event=obj)
        return EventOccurrenceSerializer(event_occurrences, many=True).data
    

    @swagger_serializer_method(serializers.URLField)
    def get_link(self, instance):
        """
        Method to retrieve the 'link' field of the EventV4 instance.
        This method uses swagger_serializer_method decorator to specify
        the field type in the Swagger documentation.
        """
        return instance.link

    # TODO: go through List
    @swagger_serializer_method(serializers.DateTimeField)
    def get_event_end_date(self, instance):
        """
        Method to retrieve the 'event_end_date' field of the EventV4 instance.
        This method uses swagger_serializer_method decorator to specify
        the field type in the Swagger documentation.
        """
        return instance.event_end_date 
    
    # TODO: go through List
    @swagger_serializer_method(serializers.DateTimeField)
    def get_event_start_date(self, instance):
        """
        Method to retrieve the start_dates of the EventV4 instance.
        Adjusts the event start date if the event date has passed.
        This method uses swagger_serializer_method decorator to specify
        the field type in the Swagger documentation.
        """
        _now = localtime().replace(microsecond=0, second=0)
        if instance.event_date.date() < _now.date():
            return _now.replace(hour=0, minute=0)
        return instance.event_date


class PaginatedEventRetrieveSerializer(serializers.Serializer):
    # Field to store the total count of events
    count = serializers.IntegerField()
    
    # Field to store the URL of the next page of results
    # allow_blank and allow_null are set to True to handle cases where there is no next page
    next = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    
    # Field to store the URL of the previous page of results
    # allow_blank and allow_null are set to True to handle cases where there is no previous page
    previous = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    
    # Field to store the list of event results
    # This uses the EventRetrieveSerializer to serialize each event
    results = EventRetrieveSerializer(many=True)


class EventBookmarksViewSet(BaseViewSet):
    # Define the queryset to fetch only published EventV4 objects
    queryset = EventV4.objects.filter(published=True)
    # Specify the serializer class to be used
    serializer_class = EventRetrieveSerializer
    # Define the model class associated with this view set
    model_class = EventV4
    # Specify the filter backends to be used for filtering the queryset
    filter_backends = BaseViewSet.filter_backends + [
        DeviceIdFilter,
    ]
    # Uncomment to use a specific filter set class
    # filterset_class = EventBaseFilter
    # Define the time period to show events in advance (in days)
    time_period_to_show_in_advance = 30
    # Define the time period to show events retrospectively (in days)
    time_period_to_show_retrospectively = 1

    # Specify the fields that can be used for ordering the queryset
    ordering_fields = ["start_date"]
    # Set the default ordering for the queryset
    ordering = ["start_date"]

    def get_limited_queryset(self, device_id, exclude_ids=[], tag_filter = [], organization_filer= [], use_basefilter=True):
        """
        Get a query set limited by time and without bookmarked / archived events.

        Args:
            device_id (str): Device ID
            exclude_ids (list): List of IDs to exclude from queryset
            use_basefilter (bool): Use all base filters or if set to False,
                only DeviceIdFilter and SourceActiveFilter

        Returns:
            queryset, excluded_articles_ids, newest_date
        """
        # If not using the base filter, redefine the filter backends
        if not use_basefilter:
            self.filter_backends = [DeviceIdFilter, SourceActiveFilter]

        # Calculate the current date
        current_date = datetime.now().date()
        # Calculate the oldest date based on the retrospective time period
        oldest_date = current_date - timedelta(
            days=self.time_period_to_show_retrospectively
        )
        # Filter and exclude specific IDs from the base queryset
        base_queryset = self.filter_queryset(self.get_queryset()).exclude(
            id__in=exclude_ids
        )

        # Get the app user based on the device ID
        app_user = get_appuser(device_id)
        
        # Check if app_user exists
        if not app_user:
            return Response("Bad Request", status=status.HTTP_400_BAD_REQUEST)
        
        # Get the user's area
        user_area = app_user.area
        # Extract the area ID from the user's area
        area_id = user_area.__dict__['id']
        # Get all events from the base queryset
        events = [event for event in base_queryset]
        # Initialize an empty list to store filtered events
        event_list = []

        # Iterate over each event in the events list
        for event in events:
            # Flag to check if the event is located in the user's area
            found = False
            # Get the areas associated with the event
            event_areas = event.area.values()
            # Check if any of the event's areas match the user's area
            for area in event_areas:
                if area_id == area["id"]:
                    found = True

            # If no matching area is found, skip to the next event
            if found == False:
                continue
            
            # Get the tag IDs associated with the event
            tag_ids = [tag.id for tag in event.tags.all()]
            foundtag = False
            # Check if the event has any of the tags mentioned in the tag_filter list
            if len(tag_filter) > 0:
                for tag_f in tag_filter:
                    for tag_e in tag_ids:
                        if tag_f == tag_e:
                            foundtag = True
                            break
            else:
                # If no tag filter is provided, set the flag to True 
                foundtag = True

            # If no matching tag is found, skip to the next event
            if foundtag == False:
                continue

            
            # check if the event is associated with any of the organizations in the organization_filer list
            found_org = False
            if len(organization_filer) > 0:
                logger.error(organization_filer)
                for org in organization_filer:
                    logger.error(org)
                    logger.error(event.source.organization.id)
                    if event.source.organization.id == org:
                        found_org = True
                        break
            else:
                # If no organization filter is provided, set the flag to True
                found_org = True
            
            # If no matching organization is found, skip to the next event
            if found_org == False:
                continue

            # add all occurrences to the event

            event_occurrences = Event_Occurrence.objects.filter(event=event)   
            
            # add a new field to the event object
            event.occurrences_list = list(event_occurrences)
            
            # Add the event to the event list if it matches the user's area
            event_list.append(event)

        # Return the filtered event list, excluded IDs, and the oldest date
        return event_list, exclude_ids, oldest_date
    

    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        operation_description="""List bookmarked events.\n
         """,
        responses={
            200: PaginatedEventRetrieveSerializer,
            400: "Device ID missing."
            },
    )

    def list(self, *args, **kwargs):
        
        # Adding a custom filter to the filter backends
        #self.filter_backends = EventViewSet.filter_backends # + [EventDateFilter]
        
        # Extracting the Device ID from the request headers
        device_id = self.request.headers.get("X-Device-ID", None)
        
        # If Device ID is not provided, return a 400 bad request response
        if device_id is None:
            return bad_request("Device ID is missing")
        
        
        # Get the limited queryset based on the device ID
        queryset_list, exclude_ids, oldest_date = self.get_limited_queryset(device_id)

        # Get the current datetime with timezone information
        now = datetime.now(pytz.utc)

        # Iterate over each event in the queryset list
        for event in queryset_list:
            # Get all occurrences of the event
            occurrences = event.occurrences.all()
            # Check if there are any occurrences
            if occurrences:
                # Filter occurrences to include only those in the future
                future_occurrences = [occurrence for occurrence in occurrences if occurrence.start_datetime > now]
                # Check if there are any future occurrences
                if future_occurrences:
                    # Get the first occurrence from the future occurrences list
                    first_occurrence = min(future_occurrences, key=lambda x: x.start_datetime)
                    # Set the start date of the event to the start date of the first occurrence
                    event.start_date = first_occurrence.start_datetime
        
        # Paginate the queryset
        page = self.paginate_queryset(queryset_list)
        if page is not None:
            # If pagination is applied, serialize the paginated data
            serializer = self.get_serializer(page, many=True)
            # Return the paginated response
            return self.get_paginated_response(serializer.data)
        
        # If no pagination is applied, serialize the full queryset
        serializer = self.get_serializer(queryset_list, many=True)
        # Return the full response
        return Response(serializer.data)


    def get_serializer_class(self):
        """
        Overrides the default get_serializer_class method to provide a custom 
        serializer class based on the action.

        If the action is "list", it assigns EventListSerializer to self.serializer_class.

        Returns:
            The serializer class to be used.
        """
        # Convert the action to lowercase for case-insensitive comparison
        action = self.action.lower()
        
        # Check if the action is "list"
        if action == "list":
            # Assign EventListSerializer to self.serializer_class
            self.serializer_class = EventListSerializer
        
        # Call the parent class's get_serializer_class method and return its result
        return super().get_serializer_class()
    

    @swagger_auto_schema(
        operation_description="Add events to bookmarks",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            204: "Added to bookmarks",
            400: "Invalid Device ID",
            404: "Event not found",
        },
    )
    def update(self, request, *args, **kwargs):
        """
        Adds an event to the user's bookmarks.
        
        Args:
            request: The HTTP request object.
            *args: Additional arguments.
            **kwargs: Additional keyword arguments.
        
        Returns:
            A response indicating the event was added to bookmarks.
        """
        event_id = kwargs.get('pk')
        app_user = get_appuser(request.META.get('HTTP_X_DEVICE_ID'))
        if not app_user:
            return Response("Invalid Device ID", status=status.HTTP_400_BAD_REQUEST)
        
        event = EventV4.objects.get(id=event_id)

        # if event not found return 404
        if not event:
            return Response(status=status.HTTP_404_NOT_FOUND)
        app_user.bookmarked_events_v4.add(event)
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @swagger_auto_schema(
        operation_description="Remove event from bookmarks",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            204: "Removed from bookmarks",
            400: "Invalid Device ID",
            404: "Event not found",
        },
    )
    def destroy(self, request, *args, **kwargs):
        """
        Removes an event from the user's bookmarks.
        
        Args:
            request: The HTTP request object.
            *args: Additional arguments.
            **kwargs: Additional keyword arguments.
        
        Returns:
            A response indicating the event was removed from bookmarks.
        """
        event_id = kwargs.get('pk')
        event = get_object_or_404(EventV4, id=event_id)
        device_id = request.META.get("HTTP_X_DEVICE_ID")
        app_user = get_appuser(device_id)
        
        if not app_user:
            return Response("Invalid Device ID", status=status.HTTP_400_BAD_REQUEST)
        
        if event not in app_user.bookmarked_events_v4.all():
            return Response("Event not found", status=status.HTTP_404_NOT_FOUND)
        
        app_user.bookmarked_events_v4.remove(event)
        return Response("Removed from bookmarks", status=status.HTTP_204_NO_CONTENT)


# Define a class `EventAppUserBaseViewSet` that inherits from `AppUserBaseViewSet`
class EventAppUserBaseViewSet(AppUserBaseViewSet):

    # Set the queryset to retrieve all objects of `EventV4`
    queryset = EventV4.objects.all()
    
    # Set the serializer class to `EventListSerializer` for serializing the retrieved objects
    serializer_class = EventListSerializer
    
    # Set the model class to `EventV4`, indicating the type of model being used
    model_class = EventV4
    
    # Extend the filter backends from `AppUserBaseViewSet` with an additional filter `DeviceIdFilter`
    filter_backends = AppUserBaseViewSet.filter_backends + [
        DeviceIdFilter,
    ]
