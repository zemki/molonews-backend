from django.db.models import Count, Q
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

logger = getLogger(__name__)

from .util import (
    choices_parameter,
    integer_parameter,
    string_parameter,
    boolean_parameter,
    header_string_parameter,
    isodate_parameter,
)
from content.models import AppUser, Event, EventChild, Tag, Organization, Source
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
    "area",
)

EVENT_LIST_FIELDS = BASE_LIST_FIELDS + (
    "event_date",
    "event_end_date",
    "event_location",
    "address",
    "link",
    "tags",
    "organization",
    "organization_type",
    "organization_name",
    "image_source",
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

FILTER_DATE_FIELDS = FILTER_BASE_FIELDS + [
    "event_date",
    "event_end_date",
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
        self.field_name = field_name
        self.lookup_expr = lookup_expr


class EventBaseFilter(filters.BaseFilterBackend):

    filters = {
        "organization": InFilter("source__organization"),
        "organization_all_tags": InFilter("source__organization"),
        "tags": InFilter("tags"),
    }

    class Meta:
        model = Event
        fields = FILTER_BASE_FIELDS

    def filter_queryset(self, request, queryset, view):
        # TODO
        appuser = get_appuser(request.headers.get("X-Device-ID", None))
        queries = {
            "organization": Q(),
            "tags": Q(),
            "organization_all_tags": Q(),
        }
        user_queries = {}

        if appuser:

            _filter_fields = ["organization", "tags", "organization_all_tags"]
            filter_by_source = appuser.filter_events_by_source
            if not filter_by_source:
                _filter_fields = ["tags"]

            for name in _filter_fields:
                _filter = self.filters[name]
                lookup = "{}__{}".format(_filter.field_name, _filter.lookup_expr)
                # only use event tags
                if name == "tags":
                    value = [
                        str(_attr.id)
                        for _attr in getattr(appuser, name).filter(category_id=2)
                        if _attr
                    ]
                else:
                    value = [
                        str(_attr.id) for _attr in getattr(appuser, name).all() if _attr
                    ]
                if value is not None and value:
                    user_queries[name] = Q(**{lookup: value})

        if (
            "organization" in request.query_params.keys()
            and request.query_params["organization"] is not None
        ):
            user_queries["organization"] = Q(
                **{
                    "source__organization__in": [
                        param
                        for param in request.query_params["organization"].split(",")
                    ]
                }
            )

        for key, value in user_queries.items():
            queries[key] = value

        if appuser is None:
            queries["tags"] = Q(**{"tags__in": Tag.objects.filter(category_id=2)})
        if appuser is None and "organization" not in request.query_params.keys():
            queries["organization"] = Q(
                **{"source__organization__in": Organization.objects.all()}
            )
        if (
            len(queries["organization"] & queries["tags"]) < 2
            and len(queries["organization_all_tags"]) == 1
        ):
            queries_combined = queries["organization_all_tags"]
        elif (
            len(queries["organization"] & queries["tags"]) == 2
            and len(queries["organization_all_tags"]) < 1
        ):
            queries_combined = queries["organization"] & queries["tags"]
        else:
            queries_combined = (queries["organization"] & queries["tags"]) | queries[
                "organization_all_tags"
            ]
        queryset = queryset.filter(queries_combined)

        if (
            "organization" in request.query_params.keys()
            and request.query_params["organization"] is not None
        ):
            queryset = queryset.filter(event_date__gte=datetime.now().date())

        return queryset


class EventDateFilter(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        date_start = request.query_params.get("date_start", None)
        date_end = request.query_params.get("date_end", None)

        if date_start and date_end:
            date_start = datetime.fromisoformat(date_start)
            date_end = datetime.fromisoformat(date_end)

            # event_end_date >= date_start && event_date <= date_end
            return queryset.filter(
                (
                    Q(**{"event_date__lte": date_end})
                    & Q(**{"event_end_date__gte": date_start})
                )
                | (
                    Q(**{"event_date__lte": date_end})
                    & Q(**{"event_date__gte": date_start})
                    & Q(**{"event_end_date__isnull": True})
                )
            )
        return queryset


class DeviceIdFilter(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        device_id = request.headers.get("X-Device-ID", None)
        if device_id is not None:
            queryset = queryset.annotate(
                bookmarked=Count("pk", filter=Q(events_bookmarked__device_id=device_id))
            )
            queryset = queryset.annotate(
                archived=Count("pk", filter=Q(events_archived__device_id=device_id))
            )
        return queryset

    def get_schema_fields(self, view):
        return []


class EventTagsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "name", "color")


class EventBaseSerializer(serializers.ModelSerializer):

    tags = EventTagsSerializer(read_only=True, many=True)
    organization = serializers.SerializerMethodField()
    organization_type = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    archived = serializers.SerializerMethodField()
    bookmarked = serializers.SerializerMethodField()

    @swagger_serializer_method(serializers.BooleanField)
    def get_archived(self, instance):
        archived = bool(getattr(instance, "archived", False))
        return archived

    @swagger_serializer_method(serializers.BooleanField)
    def get_bookmarked(self, instance):
        bookmarked = bool(getattr(instance, "bookmarked", False))
        return bookmarked

    def get_image_url(self, instance):
        if instance.image:
            return self.context["request"].build_absolute_uri(instance.image.url)
        elif instance.image_url:
            return instance.image_url
        else:
            return get_source_default_image_url(instance, self.context)

    @swagger_serializer_method(serializers.IntegerField)
    def get_organization(self, instance):
        return instance.source.organization.id

    def get_organization_type(self, instance):
        return instance.source.organization.type

    def get_organization_name(self, instance):
        return instance.source.organization.name


class EventListSerializer(EventBaseSerializer):

    link = serializers.SerializerMethodField()
    event_end_date = serializers.SerializerMethodField()
    event_start_date = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = EVENT_LIST_FIELDS + (
            "archived",
            "bookmarked",
            "event_start_date",
        )

    @swagger_serializer_method(serializers.URLField)
    def get_link(self, instance):
        if instance.is_child:
            _event_child = EventChild.objects.get(event=instance)
            return _event_child.parent.link
        return instance.link

    @swagger_serializer_method(serializers.DateTimeField)
    def get_event_end_date(self, instance):
        return localtime(instance.event_end_date) or localtime(instance.event_date)

    @swagger_serializer_method(serializers.DateTimeField)
    def get_event_start_date(self, instance):
        _now = localtime().replace(microsecond=0, second=0)
        if (
            instance.event_date.date() < _now.date()
            and instance.event_end_date
            and instance.event_end_date.date() >= _now.date()
        ):
            return _now.replace(hour=0, minute=0)
        return instance.event_date


class PaginatedEventBookmarkedArchivedSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    previous = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    results = EventListSerializer(many=True)


class EventRetrieveSerializer(EventBaseSerializer):

    link = serializers.SerializerMethodField()
    event_end_date = serializers.SerializerMethodField()
    event_start_date = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = EVENT_RETRIEVE_FIELDS + (
            "archived",
            "bookmarked",
            "event_start_date",
        )

    @swagger_serializer_method(serializers.URLField)
    def get_link(self, instance):
        if instance.is_child:
            return Event.objects.get(
                pk=EventChild.objects.get(event_id=instance.id).parent_id
            ).link
        return instance.link

    @swagger_serializer_method(serializers.DateTimeField)
    def get_event_end_date(self, instance):
        return instance.event_end_date or instance.event_date

    @swagger_serializer_method(serializers.DateTimeField)
    def get_event_start_date(self, instance):
        _now = localtime().replace(microsecond=0, second=0)
        if instance.event_date.date() < _now.date():
            return _now.replace(hour=0, minute=0)
        return instance.event_date


class PaginatedEventRetrieveSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    previous = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    results = EventRetrieveSerializer(many=True)


class EventViewSet(BaseViewSet):

    queryset = Event.objects.filter(published=True)
    serializer_class = EventRetrieveSerializer
    model_class = Event
    filter_backends = BaseViewSet.filter_backends + [
        DeviceIdFilter,
        EventBaseFilter,
    ]
    # filterset_class = EventBaseFilter
    time_period_to_show_in_advance = 30
    time_period_to_show_retrospectively = 1

    ordering_fields = ["event_date"]

    ordering = ["event_date"]

    def get_limited_queryset(self, device_id, exclude_ids=[], use_basefilter=True):
        """Get a query set limited by time and without bookmarked / archived events.

        Args:
            device_id (str): device id
            exclude_ids (list): list of ids to exclude from queryset
            use_basefilter (bool): use all base filters or if set to False
                only  DeviceIdFilter and  SourceActiveFilter

        Returns:
            queryset, excluded_articles_ids, newsest_date
        """
        if not use_basefilter:
            self.filter_backends = [DeviceIdFilter, SourceActiveFilter]

        current_date = datetime.now().date()
        oldest_date = current_date - timedelta(
            days=self.time_period_to_show_retrospectively
        )
        base_queryset = self.filter_queryset(self.get_queryset()).exclude(
            id__in=exclude_ids
        )

        app_user = get_appuser(device_id)
        user_area = app_user.area
        area_id = user_area.__dict__['id']
        events = [event for event in base_queryset]
        event_list = []

        for event in events:

            # filter out organisations that are not located in the users area
            found = False
            event_areas = event.area.values()
            for area in event_areas:
                if area_id == area["id"]:
                    found = True
            
            if found == False:
                continue

            event_list.append(event)


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
        responses={400: "Device ID missing."},
    )
    def list(self, *args, **kwargs):
        self.filter_backends = EventViewSet.filter_backends + [EventDateFilter]
        device_id = self.request.headers.get("X-Device-ID", None)
        if device_id is None:
            return bad_request("Device ID is missing")

        queryset_list, exclude_ids, oldest_date = self.get_limited_queryset(device_id)
        page = self.paginate_queryset(queryset_list)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset_list, many=True)
        return Response(serializer.data)

    def get_serializer_class(self):
        action = self.action.lower()
        if action == "list":
            self.serializer_class = EventListSerializer
        return super().get_serializer_class()

    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
            integer_parameter("limit", "Number of results to return per page."),
            integer_parameter(
                "offset", "The initial index from which to return the results."
            ),
        ],
        responses={
            200: PaginatedEventRetrieveSerializer,
            400: "Device ID missing.",
            404: "No such event.",
        },
    )
    @action(detail=True)
    def similar(self, request, *args, pk=None, **kwargs):
        """
        Returns a list of similar events.
        """
        return super().similar(request, *args, pk, **kwargs)



class EventAppUserBaseViewSet(AppUserBaseViewSet):

    queryset = Event.objects.all()
    serializer_class = EventListSerializer
    model_class = Event
    filter_backends = AppUserBaseViewSet.filter_backends + [
        DeviceIdFilter,
        EventBaseFilter,
    ]


class EventArchiveViewSet(EventAppUserBaseViewSet):

    m2m_field_name = "archived_events"

    @swagger_auto_schema(
        operation_description="List archived events",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            200: PaginatedEventBookmarkedArchivedSerializer,
            400: "Invalid Device ID",
        },
    )
    def list(self, request, *args, **kwargs):
        self.serializer_class = EventRetrieveSerializer
        return super().list(request, *args, ignore_object_age_filter=True, **kwargs)

    @swagger_auto_schema(
        operation_description="Add event to archive",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            201: "Added to archive",
            400: "Invalid Device ID",
            404: "Event not found",
        },
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

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
    # TODO
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


# TODO
class EventBookmarksViewSet(EventAppUserBaseViewSet):

    m2m_field_name = "bookmarked_events"

    @swagger_auto_schema(
        operation_description="List bookmarked events",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            200: PaginatedEventBookmarkedArchivedSerializer,
            400: "Invalid Device ID",
        },
    )
    # TODO
    def list(self, request, *args, **kwargs):
        self.serializer_class = EventRetrieveSerializer
        return super().list(request, *args, ignore_object_age_filter=True, **kwargs)

    @swagger_auto_schema(
        operation_description="Add events to bookmarks",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            201: "Added to bookmarks",
            400: "Invalid Device ID",
            404: "Event not found",
        },
    )
    # TODO
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

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
    # TODO
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class DateRangeException(Exception):
    pass


class EventOverviewSerializer(serializers.ModelSerializer):

    event_dates = serializers.SerializerMethodField()

    @swagger_serializer_method(serializers.ListField(child=serializers.DateTimeField()))
    def get_event_dates(self, instance):
        return instance

    class Meta:
        model = Event
        fields = ["event_dates"]


class EventDateRangeFilter(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):

        year = int(request.query_params["year"])
        month = int(request.query_params["month"])

        return queryset.filter(
            Q(**{"event_date__year": year, "event_date__month": month})
            | Q(**{"event_end_date__year": year, "event_end_date__month": month})
            | Q(
                **{
                    "event_date__year": year,
                    "event_date__month__lte": month,
                    "event_end_date__year": year,
                    "event_end_date__month__gte": month,
                }
            )
        )


class EventOverviewViewSet(viewsets.GenericViewSet):
    queryset = Event.objects.filter(published=True)
    serializer_class = EventOverviewSerializer
    http_method_names = ["get"]
    model_class = Event
    search_fields = None
    pagination_class = None
    filter_backends = [
        df.rest_framework.DjangoFilterBackend,
        SourceTypeFilter,
        SourceActiveFilter,
        EventDateRangeFilter,
        EventBaseFilter,
    ]
    # filterset_class = EventBaseFilter

    def validate_user_input(self):

        month = self.request.query_params["month"]
        year = self.request.query_params["year"]

        try:
            month = int(month)
            year = int(year)
            if month < 1 or month > 12:
                raise DateRangeException
            if year < 2020 or year > 2050:
                raise DateRangeException
        except (ValueError, DateRangeException):
            return False

        return True

    @swagger_auto_schema(
        manual_parameters=[
            integer_parameter("year", "Year to query event info for", required=True),
            integer_parameter("month", "Month to query event info for", required=True),
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
        operation_description="""Get all dates with events for a given month\n
         """,
        responses={
            200: EventOverviewSerializer,
            400: "Device ID is missing",
            416: "Invalid date supplied",
        },
    )
    def list(self, request, *args, **kwargs):

        device_id = self.request.headers.get("X-Device-ID", None)
        if device_id is None:
            return bad_request("Device ID is missing")

        if not self.validate_user_input():
            return Response(
                "Invalid date supplied",
                status=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            )

        queryset = self.filter_queryset(self.queryset)

        app_user = get_appuser(device_id)
        user_area = app_user.area
        area_id = user_area.__dict__['id']
        logger.error(area_id)
       
        month = int(self.request.query_params["month"])
        events = [event for event in queryset]
        event_dates = []
        
        for event in events:

            # filter out organisations that are not located in the users area
            found = False
            event_areas = event.area.values()
            for area in event_areas:
                if area_id == area["id"]:
                    found = True
            
            if found == False:
                continue

            if event.event_end_date:
                event_dates += [
                    event.event_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    + timedelta(days=i)
                    for i in range(
                        0,
                        (event.event_end_date.date() - event.event_date.date()).days
                        + 1,
                    )
                ]
            event_dates += [
                event.event_date.replace(hour=0, minute=0, second=0, microsecond=0)
            ]
        event_dates = [
            event.isoformat()
            for event in sorted(set(event_dates))
            if event.month == month
        ]

        serializer = EventOverviewSerializer(event_dates)

        return Response(serializer.data)
