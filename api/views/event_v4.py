from django.db.models import Count, Q, Exists, OuterRef, F
from datetime import datetime, timedelta
from django.utils.timezone import localtime
from rest_framework import viewsets, serializers, filters
from rest_framework.viewsets import GenericViewSet
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
from email.mime.text import MIMEText
import smtplib

logger = getLogger(__name__)

from .util import (
    choices_parameter,
    integer_parameter,
    string_parameter,
    boolean_parameter,
    header_string_parameter,
    isodate_parameter,
)
from content.models import AppUser, EventV4, Tag, Organization, Source, Event_Occurrence, User, Area
from content.choices import ORGANIZATION_TYPE_CHOICES
from .util import bad_request
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
    "image_source",
    "start_date",
    "area",
    "request_count",
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


class InFilter:
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
    # Define a custom serializer method field for the selected status
    selected = serializers.SerializerMethodField()
    
    class Meta:
        model = Tag
        fields = ("id", "name", "color", "selected")

    # Define a method to get the selected status, using a boolean field for Swagger documentation
    @swagger_serializer_method(serializers.BooleanField)
    def get_selected(self, obj):
        app_user = self.context.get("app_user", None)
        if app_user:
            return app_user.tags.filter(id=obj.id).exists()
        return False



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
        # get the appuser from the x device id in the header of request
        app_user = get_appuser(self.context.get("request").headers.get("X-Device-ID"))
        if app_user:
            return app_user.bookmarked_events_v4.filter(id=instance.id).exists()
        return False


    # Define a method to get the image URL
    def get_image_url(self, instance):
        # If the instance has an image, return the absolute URL
        if instance.image:
            return self.context["request"].build_absolute_uri(instance.image.url)
        # If the instance has an image_url, return it
        elif instance.image_url:
            return instance.image_url
        # Otherwise, return the default image for the source
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
@swagger_serializer_method(serializers.IntegerField)
def get_bookmarked_count(self, instance):
    """
    This method returns the amount of bookmarks for the event.
    """
    return instance.events_bookmarked.count()

# Serializer for the event list, inheriting from EventBaseSerializer
class EventListSerializer(EventBaseSerializer):

    # Define a SerializerMethodField to handle custom serialization for the 'link' field
    link = serializers.SerializerMethodField()
    occurrences_list = serializers.SerializerMethodField()
    bookmarked_count = serializers.SerializerMethodField()

    # Meta class to specify the model and fields to be included in the serialization
    class Meta:
        model = EventV4  # The model that this serializer is associated with
        fields = EVENT_LIST_FIELDS + (  # Include predefined fields and additional fields
            "archived",
            "bookmarked",
            "occurrences_list",
            "longitude",
            "latitude",
            "street",
            "town",
            "zip_code",
            "bookmarked_count",
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
    
    # get the bookmarked status of the event out of the m2m database
 

    @swagger_serializer_method(serializers.IntegerField)
    def get_bookmarked_count(self, instance):
        """
        This method returns the amount of bookmarks for the event.
        """
        return instance.events_bookmarked.count()

    # Define a method to get the bookmarked status, using a boolean field for Swagger documentation
    @swagger_serializer_method(serializers.BooleanField)
    def get_bookmarked(self, instance):
        # get the appuser from the x device id in the header of request
        app_user = get_appuser(self.context.get("request").headers.get("X-Device-ID"))
        if app_user:
            return app_user.bookmarked_events_v4.filter(id=instance.id).exists()
        return False

  

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
    bookmarked_count = serializers.SerializerMethodField()

    class Meta:
        # Specify the model associated with this serializer
        model = EventV4
        # Define the fields to be included in the serialized output
        fields = EVENT_RETRIEVE_FIELDS + (
            "archived",
            "bookmarked",
            "occurrences_list", 
            "longitude",
            "latitude",
            "street",
            "town",
            "zip_code",
            "bookmarked_count",
        )

    def get_occurrences_list(self, obj):
        # This method will fetch the occurrences for the event
        event_occurrences = Event_Occurrence.objects.filter(event=obj)
        return EventOccurrenceSerializer(event_occurrences, many=True).data
    
    @swagger_serializer_method(serializers.IntegerField)
    def get_bookmarked_count(self, instance):
        """
        This method returns the amount of bookmarks for the event.
        """
        return instance.events_bookmarked.count()
    

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
    results = EventListSerializer(many=True)



class EventViewSet(BaseViewSet):
    # Define the queryset to fetch only published EventV4 objects
    queryset = EventV4.objects.filter(published=True)
    # Specify the serializer class to be used
    serializer_class = EventListSerializer
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

    def get_limited_queryset(self, device_id, areas = None,  exclude_ids=[], tag_filter = [], organization_filer= [], town = "",  use_basefilter=True):
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

        # Aktueller Zeitpunkt (UTC)
        now = datetime.now(pytz.utc)
        # Filter and exclude specific IDs from the base queryset
        base_queryset = (
        self.filter_queryset(self.get_queryset())
            .exclude(id__in=exclude_ids)
            .filter(
                Q(occurrences__start_datetime__gte=now) |
                Q(occurrences__end_datetime__gte=now)
            )
            .distinct()
        )

        # Get all events from the base queryset
        events = [event for event in base_queryset]
        # Initialize an empty list to store filtered events
        event_list = []
        # copy into str variable
        areas_str = areas
        # build a clean list
        areas = []
        if areas_str:
            areas = [int(x) for x in areas_str.split(",") if x.isdigit()]


        # Iterate over each event in the events list
        for event in events:
            # get the areas of the event
            event_area_ids = event.area.values_list("id", flat=True)

            # Flag to check if the event is located in the user's area
            found = False

            for event_area_id in event_area_ids:
                for area in areas:
                    if event_area_id == area:
                        found = True
                        break
                if found:
                    break

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
                for org in organization_filer:
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

            #try:
                # check if the event is bookmarked 
            #    if app_user.bookmarked_events_v4.filter(pk=event.id).exists():
            #        event.bookmarked = True
            #    else:
            #        event.bookmarked = False
            #except:
            #    pass
            
            #try: 
                # check if the event is archived
            #    if app_user.archived_events_v4.filter(pk=event.id).exists():
            #        event.archived = True
            #    else:
            #        event.archived = False
            #except:
            #    pass

            # if the event is not bookmarked or archived
            #if not event.bookmarked and not event.archived:
            # add the event to the event list
            event_list.append(event)
           

        # Return the filtered event list, excluded IDs, and the oldest date
        return event_list, exclude_ids, oldest_date
    

    @swagger_auto_schema(
        manual_parameters=[
            string_parameter(
                "search", "Search term - searches in title, abstract, content and tags"
            ),
            choices_parameter(
                "ordering",
                ("event_date", "-event_date"),
                'Ordering (default is "event_date")',
            ),
            isodate_parameter(
                "date_start",
                "ISO 8601 formatted",
            ),
            isodate_parameter(
                "date_end",
                "ISO 8601 formatted",
            ),
            string_parameter(
                "tags",
                "Tag ID(s) - comma separated",
            ),
            openapi.Parameter(
                "area", 
                openapi.IN_QUERY, 
                description="Area ID(s) - comma separated",
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(type=openapi.TYPE_INTEGER),
                required = False 
                ),
            string_parameter(
                "town",
                "Town",
                required=False,
            ),
            string_parameter(
                "organization",
                "Organization ID(s) - comma separated | defaults to user settings, if supplied min date of events will be current date",
                required=False,
            ),
        ]
        + [
            boolean_parameter(
                event_type[0],
                'Include events with type "{}", defaults to true'.format(event_type[0]),
                default=True,
            )
            for event_type in ORGANIZATION_TYPE_CHOICES
        ]
        + [
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],

        operation_description="""List published events.\n
         """,
        responses={
            200: PaginatedEventRetrieveSerializer,
            400: "Device ID missing."
            },
    )

    def list(self, *args, **kwargs):

        # Adding a custom filter to the filter backends
        self.filter_backends = EventViewSet.filter_backends

        # Extracting the Device ID from the request headers
        device_id = self.request.headers.get("X-Device-ID")
        
        # If Device ID is not provided, return a 400 bad request response
        if not device_id:
            return bad_request("Device ID is missing")

        # Get the string value of the tags parameter and create a list of integers
        tags = self.request.query_params.get("tags", "")

        tags_list = [int(tag) for tag in tags.split(",")] if tags else []

        # Get the string value of the organization parameter and create a list of integers
        organization = self.request.query_params.get("organization", "")
        organization_list = [int(org) for org in organization.split(",")] if organization else []

        # Get the town parameter
        town = self.request.query_params.get("town")
        # Get the list of areas
        areas = self.request.query_params.get("area")
        # log all areas
  
        # Get the limited queryset based on the device ID
        try:
            queryset_list, exclude_ids, oldest_date = self.get_limited_queryset(
                device_id, areas=areas, tag_filter=tags_list, town=town, organization_filer=organization_list
            )
        except ValueError as e:
            return Response(str(e), status=status.HTTP_400_BAD_REQUEST)

        # Get the current datetime with timezone information
        now = datetime.now(pytz.utc)

        # Filter out events that have no future occurrences
        for event in queryset_list:
            occurrences = event.occurrences.all()
            if occurrences:
                # Filter occurrences to include only those in the future
                future_occurrences = [occurrence for occurrence in occurrences if occurrence.start_datetime >= now]
                if not future_occurrences:
                    future_occurrences = [occurrence for occurrence in occurrences if occurrence.end_datetime >= now]

                # Update event start date to the start date of the first future occurrence
                if future_occurrences:
                    first_occurrence = min(future_occurrences, key=lambda x: x.start_datetime)
                    event.start_date = first_occurrence.start_datetime

        # Filter events by date range if provided
        date_start = self.request.query_params.get("date_start")
        date_end = self.request.query_params.get("date_end")

        #if date_start is not provided then use current date as date_start as string
        if not date_start:
            date_start = now.date().strftime("%Y-%m-%d")

        try:
            if date_start:
                date_start = datetime.strptime(date_start, "%Y-%m-%d").replace(tzinfo=pytz.utc)
            if date_end:
                date_end = datetime.strptime(date_end, "%Y-%m-%d").replace(tzinfo=pytz.utc)
        except ValueError as e:
            return bad_request(f"Invalid date format: {e}")
        
        if date_start or date_end:
            filtered_queryset = []
            for event in queryset_list:

                for occurrence in event.occurrences.all():
                    occurrence_start = occurrence.start_datetime.replace(tzinfo=pytz.utc)
                    occurrence_end = occurrence.end_datetime.replace(tzinfo=pytz.utc)
                    if date_start and date_end:
                        # Check if both dates are on the same day and time is set to midnight
                        if date_start.date() == date_end.date() and date_end.time() == datetime.min.time():
                            # Adjust date_end to the end of the day
                            date_end = datetime.combine(date_end.date(), datetime.max.time()).replace(tzinfo=pytz.utc)

                        if date_start <= occurrence_end and date_end >= occurrence_start:
                            filtered_queryset.append(event)
                            break
                    elif date_start:
                        if date_start <= occurrence_end:
                            filtered_queryset.append(event)
                            break
                    elif date_end:
                        if date_end >= occurrence_start:
                            filtered_queryset.append(event)
                            break
            queryset_list = filtered_queryset

        # sort the queryset by start date
        queryset_list = sorted(queryset_list, key=lambda x: x.start_date)

        # Increment request_count for each event in the queryset
        EventV4.objects.filter(id__in=[event.id for event in queryset_list]).update(request_count=F('request_count') + 1)

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
        manual_parameters=[
            # Define a required header parameter for "X-Device-ID"
            header_string_parameter("X-Device-ID", "Device ID", required=True),
            # Define an optional query parameter for "limit"
            integer_parameter("limit", "Number of results to return per page."),
            # Define an optional query parameter for "offset"
            integer_parameter(
                "offset", "The initial index from which to return the results."
            ),
        ],
        responses={
            # Specify the response schema for HTTP 200 status
            200: PaginatedEventRetrieveSerializer,
            # Define response message for HTTP 400 status
            400: "Device ID missing.",
            # Define response message for HTTP 404 status
            404: "No such event.",
        },
    )
    @action(detail=True)
    def similar(self, request, *args, pk=None, **kwargs):
        """
        Returns a list of similar events.
        
        This method handles GET requests to retrieve a list of events that are similar to a specific event identified by its primary key (pk).
        
        The method uses Swagger to document the API, including:
        - A required header parameter for the device ID (X-Device-ID).
        - Optional query parameters for pagination (limit and offset).
        - Possible response schemas and messages for various HTTP status codes (200, 400, 404).
        """
        # Call the parent class's similar method to handle the request and return a response
        return super().similar(request, *args, pk, **kwargs)


     # define a swagger auto schema for a delete method and also the delete method   
    @swagger_auto_schema(
        operation_description="Delete an Event",
        manual_parameters=[
            header_string_parameter("Authorization", "JWT token", required=True),
        ],
        responses={
            204: "Deleted",
            400: "Invalid Device ID",
            404: "Event not found",
        },
    )
    def destroy(self, request, *args, **kwargs):
        """
        Delete an event.

        Args:
            request (Request): The request object.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            Response: The response object.
        """
         # Handle DELETE request logic here
        # Get the id from the last section of the URL in the request metapass
        url_parts = self.request.META['PATH_INFO'].split('/')
        event_id = url_parts[-2]
        # Retrieve the event
        event = get_object_or_404(EventV4, id=event_id)
        # if event does not exist return 404
        if not event:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return Response({"detail": "Authorization header missing."}, status=status.HTTP_401_UNAUTHORIZED)

        token = auth_header
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get('user_id')
            if not user_id:
                return Response({"detail": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)
            user = get_object_or_404(User, id=user_id)
        except jwt.ExpiredSignatureError:
            return Response({"detail": "Token has expired."}, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError:
            return Response({"detail": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)

        # Check if the user is allowed to update the event
        source = Source.objects.get(related_user=user)
        if event.source != source:
            return Response({"detail": "User not authenticated."}, status=status.HTTP_401_UNAUTHORIZED)

        if user.is_authenticated:
            # Delete the event
            event.delete()
        else:
            return Response({"detail": "User not authenticated."}, status=status.HTTP_401_UNAUTHORIZED)

        # Return a response with status code 204
        return Response(status=status.HTTP_204_NO_CONTENT)

    
    # define the swagger auto schema for the create method
    
    @swagger_auto_schema(
        operation_description="Create a new Event",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'title': openapi.Schema(type=openapi.TYPE_STRING),
                'content': openapi.Schema(type=openapi.TYPE_STRING),
                'link': openapi.Schema(type=openapi.TYPE_STRING),
                "date": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
                'street': openapi.Schema(type=openapi.TYPE_STRING),
                'town': openapi.Schema(type=openapi.TYPE_STRING),
                'zip_code': openapi.Schema(type=openapi.TYPE_STRING),
                'image_url': openapi.Schema(type=openapi.TYPE_STRING),
                'event_location': openapi.Schema(type=openapi.TYPE_STRING),
                'longitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                'latitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                'image_source': openapi.Schema(type=openapi.TYPE_STRING),
                'occurrences': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'event_start_date': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                            'event_end_date': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                        }
                    )
                ),
                'area': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER)
                ),
                'event_tags': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER)
                ),
            },
            required=['title', 'content',  'area', 'event_tags']
        ),
        manual_parameters=[
            header_string_parameter("Authorization", "JWT token", required=True),
        ],
        responses={
            201: openapi.Response(
                description="Event created",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'id': openapi.Schema(type=openapi.TYPE_INTEGER)
                    }
                )
            ),
            400: "Bad Request"
        }
    )
    def create(self, request, *args, **kwargs):

        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return Response({"detail": "Authorization header missing."}, status=status.HTTP_401_UNAUTHORIZED)

        token = auth_header

        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get('user_id')
            if not user_id:
                return Response({"detail": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)
            user = get_object_or_404(User, id=user_id)
        except jwt.ExpiredSignatureError:
            return Response({"detail": "Token has expired."}, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError:
            return Response({"detail": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)

        if user.is_authenticated:
            # Handle POST request logic here
            event = EventV4()
            event.link = ""

            if 'title' in request.data:
                event.title = request.data['title']
            if 'content' in request.data:
                event.content = request.data['content']
            if 'link' in request.data:
                event.link = request.data['link']
            if 'date' in request.data:
                event.date = request.data['date']
            if 'street' in request.data:
                event.street = request.data['street']
            if 'town' in request.data:
                event.town = request.data['town']
            if 'zip_code' in request.data:
                event.zip_code = request.data['zip_code']
            if 'image_url' in request.data:
                event.image_url = request.data['image_url']
            if 'event_location' in request.data:
                event.event_location = request.data['event_location']
            if 'longitude' in request.data:
                event.longitude = float(request.data['longitude'])
            if 'latitude' in request.data:
                event.latitude = float(request.data['latitude'])
            if 'image_source' in request.data:
                event.image_source = request.data['image_source']
            #ToDo from Token
            try: 
                event.source = Source.objects.get(related_user=user)
            except:
                logger.error("User not found for source.")
                logger.error(user_id)
                return Response({"detail": "User not found for source."}, status=status.HTTP_401_UNAUTHORIZED)

            # initialize event occurrences
            event.published = True

            # if no street is provided return bad request
            if not event.street:
                return Response({"detail": "Street is required."}, status=status.HTTP_400_BAD_REQUEST)
            # if no occurrence is provided return bad request
            if not request.data['occurrences']:
                return Response({"detail": "Occurrences are required."}, status=status.HTTP_400_BAD_REQUEST)
            
            event.save()

            # Get the occurrences information for the event
            occurrences = request.data['occurrences']
            # Create and save the occurrences for the event
            for occurrence in occurrences:
                event_occurrence = Event_Occurrence()
                event_occurrence.event = event
                event_occurrence.start_datetime = occurrence['event_start_date']
                event_occurrence.end_datetime = occurrence['event_end_date']
                event_occurrence.save()

            # Get the first occurrence from the occurrences list
            #first_occurrence = min(occurrences, key=lambda x: x['start_datetime'])
            # Set the start date of the event to the start date of the first occurrence
            #event.start_date = first_occurrence['start_datetime']


            # save the event
            event.save()

            # Get the area information from the request data
            # areas = user.area.values_list('id', flat=True)
            # Add the new areas to the event
            #   for area_id in areas:
            #    event.area.add(area_id)

            event.area.clear()

            # find matching areas case-insensitive
            matching_areas = Area.objects.filter(name__iexact=event.town)

            # add the areas 
            for area in matching_areas:
                event.area.add(area)

            # Get the tag information for the event
            tags = request.data['event_tags']
            # Add the new tags to the event
            for tag in tags:
                event.tags.add(tag)

            # Return a 201 Created response with the event id
            return Response({"id": event.id}, status=status.HTTP_201_CREATED)
        else:
            return Response({"detail": "User not authenticated."}, status=status.HTTP_401_UNAUTHORIZED)


    @swagger_auto_schema(
        operation_description="Update an event",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'title': openapi.Schema(type=openapi.TYPE_STRING),
                'content': openapi.Schema(type=openapi.TYPE_STRING),
                'link': openapi.Schema(type=openapi.TYPE_STRING),
                "date": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
                'street': openapi.Schema(type=openapi.TYPE_STRING),
                'town': openapi.Schema(type=openapi.TYPE_STRING),
                'zip_code': openapi.Schema(type=openapi.TYPE_STRING),
                'image_url': openapi.Schema(type=openapi.TYPE_STRING),
                'event_location': openapi.Schema(type=openapi.TYPE_STRING),
                'longitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                'latitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                'image_source': openapi.Schema(type=openapi.TYPE_STRING),
                'occurrences': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'event_start_date': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                            'event_end_date': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                        }
                    )
                ),
                'area': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER)
                ),
                'event_tags': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER)
                ),
            },
            #required=['title', 'content', 'link', 'date', 'zip_code', 'event_location', 'area', 'event_tags']
        ),
        manual_parameters=[
            header_string_parameter("Authorization", "JWT token", required=True),
        ],
        responses={
            204: "Event updated",
            400: "Bad Request",
            404: "Event not found"
        }
    )
    def update(self, request, *args, **kwargs):
        """
        Update an event.

        Args:
            request (Request): The request object.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            Response: The response object.
        """

        # Get the id from the last section of the URL in the request metapass
        url_parts = self.request.META['PATH_INFO'].split('/')
        event_id = url_parts[-2]

        # Retrieve the event
        event = get_object_or_404(EventV4, id=event_id)
        
        # Check if event exists
        if not event:
            return Response(status=status.HTTP_404_NOT_FOUND)

        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return Response({"detail": "Authorization header missing."}, status=status.HTTP_401_UNAUTHORIZED)

        token = auth_header

        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get('user_id')
            if not user_id:
                return Response({"detail": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)
            user = get_object_or_404(User, id=user_id)
        except jwt.ExpiredSignatureError:
            return Response({"detail": "Token has expired."}, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError:
            return Response({"detail": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)

        # Check if the user is allowed to update the event
        source = Source.objects.get(related_user=user)
        if event.source != source:
            return Response({"detail": "User not authenticated."}, status=status.HTTP_401_UNAUTHORIZED)

        if user.is_authenticated:

            # Update the event
            event.link = ""
            for field, value in request.data.items():
                if field == 'title' and value:
                    event.title = value
                elif field == 'content' and value:
                    event.content = value
                elif field == 'link' and value:
                    event.link = value
                elif field == 'date' and value:
                    event.date = value
                elif field == 'street' and value:
                    event.street = value
                elif field == 'town' and value:
                    event.town = value
                elif field == 'zip_code' and value:
                    event.zip_code = value
                elif field == 'image_url' and value:
                    event.image_url = value
                elif field == 'event_location' and value:
                    event.event_location = value
                elif field == 'longitude' and value:
                    event.longitude = float(value)
                elif field == 'latitude' and value:
                    event.latitude = float(value)
                elif field == 'image_source' and value:
                    event.image_source = value
                elif field == 'occurrences' and value:
                    # Get the occurrences information for the event
                    occurrences = value
                    # Remove all occurrences from the event
                    event.occurrences.all().delete()
                    # Add the new occurrences to the event
                    for occurrence in occurrences:
                        event_occurrence = Event_Occurrence()
                        event_occurrence.event = event
                        event_occurrence.start_datetime = occurrence['event_start_date']
                        event_occurrence.end_datetime = occurrence['event_end_date']
                        event_occurrence.save()

                    # Get the first occurrence from the occurrences list
                    first_occurrence = min(occurrences, key=lambda x: x['event_start_date'])
                    # Set the start date of the event to the start date of the first occurrence
                    event.start_date = first_occurrence['event_start_date']
                elif field == 'area':
                    # Ignore this field
                    pass
                    # Remove all areas from the event
                    # event.area.clear()
                    # Add the new areas to the event
                    # for area in value:
                    #    event.area.add(area)               
                elif field == 'event_tags':
                    # Remove all tags from the event
                    event.tags.clear()
                    # Add the new tags to the event
                    for tag in value:
                        event.tags.add(tag)
                else:
                    logger.error(f"Unknown field: {field}")


                # add the area 
                # clear the area old list
                event.area.clear()

                # find matching areas case-insensitive
                matching_areas = Area.objects.filter(name__iexact=event.town)

                # add the areas 
                for area in matching_areas:
                    event.area.add(area)

                # save the event
                event.save()
        else: 
            return Response({"detail": "User not authenticated."}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Return a 204 No Content response
        return Response(status=status.HTTP_204_NO_CONTENT)


    @swagger_auto_schema(
        manual_parameters=[
            # Define a required header parameter for "X-Device-ID"
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={
            # Specify the response schema for HTTP 200 status
            200: EventRetrieveSerializer,
            # Define response message for HTTP 400 status
            400: "Device ID missing.",
            # Define response message for HTTP 404 status
            404: "No such event.",
        },
    )

    @action(detail=True, methods=["get"], url_path="retrieve")
    def retrieve_event(self, request, pk=None):
        """
        Retrieves a single event by its ID.
        """
        # Get the device ID from the request headers
        device_id = request.headers.get("X-Device-ID")
        if not device_id:
            return Response({"detail": "Device ID is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Try to get the event by its ID
        event = get_object_or_404(EventV4, pk=pk, published=True)
        
        # Get the app user based on the device ID
        app_user = get_appuser(device_id)
        
        # Check if app_user exists
        if not app_user:
            return Response("Bad Request", status=status.HTTP_400_BAD_REQUEST)
        
        # Annotate the event with bookmarked and archived status
        event.bookmarked = app_user.bookmarked_events_v4.filter(pk=event.pk).exists()
        event.archived = app_user.archived_events_v4.filter(pk=event.pk).exists()
        
        # Serialize the event
        serializer = EventRetrieveSerializer(event, context={"request": request})
        return Response(serializer.data)



class CombinedViewSetEvent(BaseViewSet):
    # Define the queryset to fetch only published EventV4 objects
    queryset = EventV4.objects.filter(published=True)
    # Specify the serializer class to be used
    serializer_class = EventListSerializer
    # Define the model class associated with this view set
    model_class = EventV4
    # Specify the filter backends to be used for filtering the queryset
    filter_backends = BaseViewSet.filter_backends + [
        DeviceIdFilter,
    ]

    def get_user_events(self, user):
        """
        Get events for a specific user.

        Args:
            user (User): User object

        Returns:
            queryset: Filtered events for the user
        """
        # Filter the events based on the user's areas and annotate the count of bookmarked events
        events = self.queryset.annotate(
            bookmarked_count=Count('events_bookmarked')
        )
       
        # Initialize an empty list to store filtered events
        event_list = []

        # Iterate over each event in the events list
        for event in events:
            # check if the source belongs to the user
            if event.source.related_user != user:
                continue
            # Add all occurrences to the event
            event_occurrences = Event_Occurrence.objects.filter(event=event)   
            # Add a new field to the event object
            event.occurrences_list = list(event_occurrences)
            # Add the event to the event list
            event_list.append(event)

        return event_list

    @swagger_auto_schema(
        operation_description="List events for a specific user.",
        manual_parameters=[
            header_string_parameter("Authorization", "JWT token", required=True),
        ],
        responses={
            200: PaginatedEventRetrieveSerializer,  # Successful response
            400: "Bad Request",  # Bad request error
            401: "Unauthorized",  # Unauthorized error
            404: "No events found for the user",  # No events found error
        },
    )
    @action(detail=False, methods=['get'], url_path='user-events')
    def list_user_events(self, request, *args, **kwargs):
        """
        List events for a specific user.
        """
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return Response({"detail": "Authorization header missing."}, status=status.HTTP_401_UNAUTHORIZED)

        token = auth_header

        try:
            # Decode the JWT token
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get('user_id')
            if not user_id:
                return Response({"detail": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)
            user = get_object_or_404(User, id=user_id)
        except jwt.ExpiredSignatureError:
            return Response({"detail": "Token has expired."}, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError:
            return Response({"detail": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)

        if user.is_authenticated:
            # Get the events for the specific user
            event_list = self.get_user_events(user)

            # If no events are found, return a 404 response
            if not event_list:
                return Response("No events found for the user", status=status.HTTP_404_NOT_FOUND)
                
            # Paginate the queryset
            page = self.paginate_queryset(event_list)
            if page is not None:
                # If pagination is applied, serialize the paginated data
                serializer = self.get_serializer(page, many=True)
                # Return the paginated response
                return self.get_paginated_response(serializer.data)
            
            # If no pagination is applied, serialize the full queryset
            serializer = self.get_serializer(event_list, many=True)
            # Return the full response
            return Response(serializer.data)
        else:
            return Response({"detail": "User not authenticated."}, status=status.HTTP_401_UNAUTHORIZED)



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

class EventPagination(PageNumberPagination):
    page_query_param = 'offset'
    page_size = 10  # Set the page size to your preference
    page_size_query_param = 'limit'  # Set the query parameter for page size
    max_page_size = 100  # Set the maximum page size
    offset_query_param = 'offset'  # Set the query parameter for offset

class EventArchiveViewSet(GenericViewSet):
    queryset = EventV4.objects.filter(published=True)
    serializer_class = EventListSerializer
    model_class = EventV4
    filter_backends = [DeviceIdFilter, SourceActiveFilter]
    pagination_class = EventPagination

    # Name of the many-to-many field for archived events
    m2m_field_name = "archived_events"

 
    @swagger_auto_schema(
        operation_description="List Archived events",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={
            200: PaginatedEventRetrieveSerializer,
            400: "Invalid Device ID",
        },
    )
    def list(self, request, *args, **kwargs):
        """
        Lists the events archived by the user.
        
        Args:
            request: The HTTP request object.
            *args: Additional arguments.
        Returns:
            A paginated list of archived events.
        """

        device_id = request.headers.get('X-Device-ID')
        if not device_id:
            return Response({"detail": "Device ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        app_user = get_appuser(device_id)
        if not app_user:
            return Response({"detail": "App user not found."}, status=status.HTTP_400_BAD_REQUEST)

        # Retrieve archived events
        archived_events = app_user.archived_events_v4.all()

        # Make a queryset out of the archived events
        queryset = EventV4.objects.filter(id__in=[event.id for event in archived_events])

        # Paginate the queryset
        page = self.paginate_queryset(queryset)
        if page is not None:
            # If pagination is applied, serialize the paginated data
            serializer = self.get_serializer(page, many=True)
            # Return the paginated response
            return self.get_paginated_response(serializer.data)

        # If no pagination is applied, serialize the full queryset
        serializer = self.get_serializer(queryset, many=True)
        # Return the full response
        return Response(serializer.data)
        

    @swagger_auto_schema(
        operation_description="Add events to archive",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={},
            required=[],
            description='No data is required in the request body'
        ),
        responses={
            204: "Added to archive",
            400: "Invalid Device ID",
            404: "Event not found",
        },
        required=False  # Set the request body as not required
    )
    def update(self, request, *args, **kwargs):
        """
        Adds an event to the user's archive.
        
        Args:
            request: The HTTP request object.
            *args: Additional arguments.
            **kwargs: Additional keyword arguments.
        
        Returns:
            A response indicating the event was added to archive.
        """
        event_id = kwargs.get('pk')
        app_user = get_appuser(request.META.get('HTTP_X_DEVICE_ID'))
        if not app_user:
            return Response("Invalid Device ID", status=status.HTTP_400_BAD_REQUEST)
        
        try:
            event = EventV4.objects.get(id=event_id)
        except EventV4.DoesNotExist:
            return Response("Event not found", status=status.HTTP_404_NOT_FOUND)

        # if event not found return 404
        if not event:
            return Response(status=status.HTTP_404_NOT_FOUND)
        app_user.archived_events_v4.add(event)
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @swagger_auto_schema(
        operation_description="Remove event from archive",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            204: "Removed from archive",
            400: "Invalid Device ID",
            404: "Event not found",
        },
    )
    def destroy(self, request, *args, **kwargs):
        """
        Removes an event from the user's archive.
        
        Args:
            request: The HTTP request object.
            *args: Additional arguments.
            **kwargs: Additional keyword arguments.
        
        Returns:
            A response indicating the event was removed from archive.
        """
        event_id = kwargs.get('pk')
        event = get_object_or_404(EventV4, id=event_id)
        device_id = request.META.get("HTTP_X_DEVICE_ID")
        app_user = get_appuser(device_id)
        
        if not app_user:
            return Response("Invalid Device ID", status=status.HTTP_400_BAD_REQUEST)
        
        if event not in app_user.archived_events_v4.all():
            return Response("Event not found", status=status.HTTP_404_NOT_FOUND)
        
        app_user.archived_events_v4.remove(event)
        return Response("Removed from bookmarks", status=status.HTTP_204_NO_CONTENT)
        
# Define an empty serializer
class EmptySerializer(serializers.Serializer):
    pass

class EventsBookmarksViewSet(GenericViewSet):
    queryset = EventV4.objects.filter(published=True)
    serializer_class = EventListSerializer
    model_class = EventV4
    filter_backends = [DeviceIdFilter, SourceActiveFilter]
    pagination_class = EventPagination
    m2m_field_name = "bookmarked_events_v4"

    def get_serializer_class(self):
        # Check if the view is being called for Swagger schema generation
        

        if self.action == 'list':
            return EventListSerializer
        if self.action == 'update':
            return None

        if getattr(self, 'swagger_fake_view', False):
            # If the request is made by Swagger for schema generation, return the default serializer class
            return EventListSerializer
       
        return super().get_serializer_class()


    @swagger_auto_schema(
        operation_description="List bookmarked events",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        
        responses={
            200: PaginatedEventRetrieveSerializer,
            400: "Invalid Device ID",
        },
    )
    def list(self, request, *args, **kwargs):
        """
        Lists the events bookmarked by the user.
        
        Args:
            request: The HTTP request object.
            *args: Additional arguments.
        Returns:
            A paginated list of bookmarked events.
        """

        device_id = request.headers.get('X-Device-ID')
        if not device_id:
            return Response({"detail": "Device ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        app_user = get_appuser(device_id)
        if not app_user:
            return Response({"detail": "App user not found."}, status=status.HTTP_400_BAD_REQUEST)

        # Retrieve bookmarked events
        bookmarked_events = app_user.bookmarked_events_v4.all()

        #logger.error(f"Bookmarked events: {bookmarked_events}")

        # Make a queryset out of the bookmarked events
        queryset = EventV4.objects.filter(id__in=[event.id for event in bookmarked_events])

        # Paginate the queryset
        page = self.paginate_queryset(queryset)
        if page is not None:
            # If pagination is applied, serialize the paginated data
            serializer = self.get_serializer(page, many=True)
            # Return the paginated response
            return self.get_paginated_response(serializer.data)

        # If no pagination is applied, serialize the full queryset
        serializer = self.get_serializer(queryset, many=True)
        # Return the full response
        return Response(serializer.data)
        

    @swagger_auto_schema(
        operation_description="Add events to bookmarks",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        request_body=None,
        responses={
            201: "Added to bookmarks",
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
         # Override get_serializer to ensure no data is expected
        def get_serializer(*args, **kwargs):
            return None
        
        event_id = kwargs.get('pk')
        app_user = get_appuser(request.META.get('HTTP_X_DEVICE_ID'))
        if not app_user:
            return Response("Invalid Device ID", status=status.HTTP_400_BAD_REQUEST)
        
        event = EventV4.objects.get(id=event_id)

        # if event not found return 404
        if not event:
            return Response(status=status.HTTP_404_NOT_FOUND)
        app_user.bookmarked_events_v4.add(event)

        logger.error(f"Event {event_id} added to bookmarks of user {app_user.id}")

        return Response(status=status.HTTP_201_CREATED)
    
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
    
    @swagger_auto_schema(
        operation_description="Add event to bookmarks",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            201: "Added to bookmarks",
            400: "Invalid Device ID",
            404: "Event not found",
        },
    )
    def create(self, request, *args, **kwargs):
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

        logger.error(f"Event {event_id} added to bookmarks of user {app_user.id}")

        return Response(status=status.HTTP_201_CREATED)



class EventTagReceiveViewSet(viewsets.ViewSet):
    queryset = Tag.objects.all()

    # route that returns all possible tags for an article
    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={
            200: EventTagsSerializer(many=True),
            400: "Device ID missing.",
        },
    )
    def get_all_event_tags(self, request, *args, **kwargs):
        try:
            # Ermitteln des AppUser anhand der device_id
            device_id = request.headers.get("X-Device-ID")
            app_user = get_appuser(device_id)

            # Tags abrufen
            tags = Tag.objects.exclude(color="")
            tags = tags.order_by('name')

            # Serialisierung der Tags mit dem zusätzlichen Feld "selected"
            serializer = EventTagsSerializer(tags, many=True, context={'app_user': app_user})

        except Exception as e:
            return Response(data={"message": f"Error retrieving tags: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.data)


class EventFlagViewSet(viewsets.ViewSet):
    queryset = EventV4.objects.all()

    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'event_id': openapi.Schema(type=openapi.TYPE_INTEGER),
            }
        ),
        responses={
            200: "Value of the event",
            400: "Device ID missing.",
            404: "No such event.",
        },
    )
    def flag(self, request, *args, **kwargs):

        event_id =  request.data['event_id']

        if event_id is None:
            return Response(data={"message": "Event ID is missing"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Send confirmation email
            sender_email = settings.MAIL_SENDING['DEFAULT_FROM_EMAIL']
            receiver_email = "ohlei@uni-bremen.de"
            subject = 'Problematic Event Reported'
            
            message = f'<html><body>Event ID: {event_id}<br>This event has been flagged as problematic.</br>'
           
            try:
                 # add the event title and description to the message
                event = EventV4.objects.get(pk=event_id)
                message += f'Title: {event.title}<br>Description: {event.content}</br>'
                # add the event start date to the message
                message += f'Start Date: {event.start_date}</br>'
                # add the user device id to the message
                message += f'Device ID: {request.headers.get("X-Device-ID")}</body></html>'
            except: 
                pass
            
            # Create a MIMEText object with the email content
            email = MIMEText(message, 'html')
            email['Subject'] = subject
            email['From'] = sender_email
            email['To'] = receiver_email
            
            # Connect to the SMTP server and send the email
            with smtplib.SMTP(settings.MAIL_SENDING['EMAIL_HOST'], settings.MAIL_SENDING['EMAIL_PORT']) as server:
                server.starttls()
                server.login(settings.MAIL_SENDING['EMAIL_HOST_USER'], settings.MAIL_SENDING['EMAIL_HOST_PASSWORD'])
                server.sendmail(sender_email, receiver_email, email.as_string())

        except Exception as e:
            return Response(data={"message": f"Error sending confirmation email: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(status=status.HTTP_204_NO_CONTENT)