from django.db.models import Count, Q
from datetime import datetime, timedelta
from rest_framework import serializers, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema, swagger_serializer_method
from rest_framework.parsers import MultiPartParser, FormParser
from logging import getLogger
from .util import (
    UserPagination,
    choices_parameter,
    integer_parameter,
    string_parameter,
    boolean_parameter,
    header_string_parameter,
    bad_request,
)
from content.models import AppUser, Article, Tag, Organization, Area, Source
from content.choices import ORGANIZATION_TYPE_CHOICES
from .article_event_shared import (
    AppUserBaseViewSet,
    BaseViewSet,
    SourceActiveFilter,
    get_source_default_image_url,
)
import django_filters as df
from rest_framework import viewsets
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
import json
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
import ml.news_article_tagging  as ml

logger = getLogger(__name__)

# Fields used for serialization

BASE_LIST_FIELDS = (
    "id",
    "title",
    "abstract",
    "date",
    "image_url",
)

ARTICLE_LIST_FIELDS = BASE_LIST_FIELDS + (
    "address",
    "link",
    "is_hot",
    "tags",
    "organization",
    "organization_type",
    "organization_name",
    "image_source",
)

ARTICLE_RETRIEVE_FIELDS = ARTICLE_LIST_FIELDS + (
    "source",
    "content",
)


def get_appuser(device_id):
    """Try to get an AppUser by device id

    Args:
        device_id (str): device id string

    Returns:
        AppUser or None: The AppUser object if found, otherwise None.
    """
    try:
        return AppUser.objects.get(device_id=device_id)
    except AppUser.DoesNotExist:
        return None


class ArticleFilter(df.FilterSet):
    """
    Filter class for the Article model.

    This class defines the filters that can be applied to the Article model.
    It provides filtering options based on organization, tags, and date.

    Attributes:
        organization (df.BaseInFilter): Filter for filtering by organization ID(s).
        organization_all_tags (df.BaseInFilter): Filter for filtering by organization ID(s) without considering tags.
        tags (df.BaseInFilter): Filter for filtering by tag ID(s).
        date_start (df.IsoDateTimeFilter): Filter for filtering by start date.
        date_end (df.IsoDateTimeFilter): Filter for filtering by end date.

    Methods:
        filter_queryset(queryset): Applies the defined filters to the given queryset.

    """

    organization = df.BaseInFilter(
        field_name="source__organization",
        help_text="Organization ID(s) - comma separated | defaults to user settings",
    )

    organization_all_tags = df.BaseInFilter(
        field_name="source__organization",
        help_text="Organization ID(s) - comma separated - not filtered against tags | defaults to user settings",
    )

    tags = df.BaseInFilter(
        field_name="tags",
        distinct=True,
        help_text="Tag ID(s) - comma separated | defaults to user settings",
    )

    date_start = df.IsoDateTimeFilter(
        field_name="date",
        help_text="ISO 8601 formatted",
        lookup_expr="gte",
    )

    date_end = df.IsoDateTimeFilter(
        field_name="date",
        help_text="ISO 8601 formatted",
        lookup_expr="lte",
    )

    def filter_queryset(self, queryset):
        """
        This function is used to get a queryset of articles based on various filters.
        It first fetches the user's preferences based on their device ID.
        Then it applies filters based on the user's preferences and the parameters passed via the API.
        If no user settings are found and no parameters are passed via the API, it selects all tags and organizations.
        Finally, it combines all the queries and filters the articles based on the combined query and the date.
        """

        # Fetch the user's preferences based on their device ID
        appuser = get_appuser(self.request.headers.get("X-Device-ID", None))

        # Initialize the queries
        queries = {
            "organization": Q(),
            "tags": Q(),
            "organization_all_tags": Q(),
        }
        user_queries = {}

        # If the user exists, apply filters based on the user's preferences
        if appuser:
            for name in queries:
                _filter = self.filters[name]
                lookup = "{}__{}".format(_filter.field_name, _filter.lookup_expr)
                # ignore event tags
                if name == "tags":
                    value = [
                        str(_attr.id)
                        for _attr in getattr(appuser, name).all().exclude(category_id=2)
                        if _attr
                    ]
                else:
                    value = [
                        str(_attr.id) for _attr in getattr(appuser, name).all() if _attr
                    ]
                if value is not None and value:
                    user_queries[name] = Q(**{lookup: value})

        # Overwrite filter settings if we get parameters via api
        ignore_usersettings = False
        parameter_queries = {}
        for name, value in self.form.cleaned_data.items():
            if name in ("organization", "tags", "organization_all_tags"):
                f = self.filters[name]
                lookup = "{}__{}".format(f.field_name, f.lookup_expr)
                if value is not None and value:
                    ignore_usersettings = True
                    parameter_queries[name] = Q(**{lookup: value})
            else:
                queryset = self.filters[name].filter(queryset, value)

        # Choose between user queries and parameter queries
        _queries = user_queries if not ignore_usersettings else parameter_queries

        # Update the queries
        for key, value in _queries.items():
            queries[key] = value

        # Select all tags if none is selected
        if (
            appuser is None
            and (
                "tags" not in self.form.cleaned_data.keys()
                or not self.form.cleaned_data["tags"]
            )
            and not ignore_usersettings
        ):
            queries["tags"] = Q(
                **{"tags__in": Tag.objects.filter(category_id__in=[1, 3, 4])}
            )

        # Select all organizations if none is selected
        if (
            appuser is None
            and (
                "organization" not in self.form.cleaned_data.keys()
                or not self.form.cleaned_data["organization"]
            )
            and not ignore_usersettings
        ):
            queries["organization"] = Q(
                **{"source__organization__in": Organization.objects.all()}
            )

        # Combine the queries
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

        # Filter the articles based on the combined query and the date
        now = datetime.now()
        queryset = queryset.filter(queries_combined).filter(date__lte=now)

        return queryset

        class Meta:
            model = Article
            fields = ["organization", "tags", "organization_all_tags", "date_start"]


class DeviceIdFilter(filters.BaseFilterBackend):
    """
    This class is a custom filter backend for Django Rest Framework.
    It filters a queryset based on the device ID provided in the request headers.
    It also annotates the queryset with the count of bookmarked and archived articles for the given device ID.
    """

    def filter_queryset(self, request, queryset, view):
        """
        This method overrides the filter_queryset method of the BaseFilterBackend class.
        It first retrieves the device ID from the request headers.
        If a device ID is provided, it annotates the queryset with the count of bookmarked and archived articles for that device ID.
        """

        # Get the device ID from the request headers
        device_id = request.headers.get("X-Device-ID", None)

        # If a device ID is provided, annotate the queryset
        if device_id is not None:
            # Annotate the queryset with the count of bookmarked articles for the device ID
            queryset = queryset.annotate(
                bookmarked=Count(
                    "pk", filter=Q(articles_bookmarked__device_id=device_id)
                )
            )
            # Annotate the queryset with the count of archived articles for the device ID
            queryset = queryset.annotate(
                archived=Count("pk", filter=Q(articles_archived__device_id=device_id))
            )

        # Return the annotated queryset
        return queryset

    def get_schema_fields(self, view):
        """
        This method overrides the get_schema_fields method of the BaseFilterBackend class.
        It returns an empty list because this filter backend does not add any fields to the schema.
        """

        # Return an empty list
        return []
    

class ArticleTagsSerializer(serializers.ModelSerializer):
    """
    Serializer for the ArticleTags model.

    This serializer is used to convert ArticleTags model instances into JSON
    representation and vice versa. It specifies the fields that should be
    included in the serialized output.

    Attributes:
        model (ArticleTags): The ArticleTags model class.
        fields (tuple): The fields to include in the serialized output.

    """
    class Meta:
        model = Tag
        fields = ("id", "name", "color")


class ArticleBaseSerializer(serializers.ModelSerializer):
    """
    This class is a serializer for the Article model.
    It extends the ModelSerializer class provided by Django Rest Framework.
    It defines several fields that are serialized in a custom way.
    """

    # Define the fields that are serialized in a custom way
    date = serializers.SerializerMethodField()
    tags = ArticleTagsSerializer(read_only=True, many=True)
    organization = serializers.SerializerMethodField()
    organization_type = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    archived = serializers.SerializerMethodField()
    bookmarked = serializers.SerializerMethodField()

    @swagger_serializer_method(serializers.DateTimeField)
    def get_date(self, instance):
        """
        This method returns the date of the article in ISO format.
        It removes the microseconds from the date before converting it to ISO format.
        """
        return instance.date.replace(microsecond=0).isoformat()

    @swagger_serializer_method(serializers.BooleanField)
    def get_archived(self, instance):
        """
        This method returns whether the article is archived.
        It gets the 'archived' attribute from the instance and converts it to a boolean.
        """
        archived = bool(getattr(instance, "archived", False))
        return archived

    @swagger_serializer_method(serializers.BooleanField)
    def get_bookmarked(self, instance):
        """
        This method returns whether the article is bookmarked.
        It gets the 'bookmarked' attribute from the instance and converts it to a boolean.
        """
        bookmarked = bool(getattr(instance, "bookmarked", False))
        return bookmarked

    def get_image_url(self, instance):
        """
        This method returns the URL of the article's image.
        If the 'detail' context is set and the instance has a 'image_detail' attribute, it returns the absolute URL of 'image_detail'.
        If the instance has a 'image' attribute, it returns the absolute URL of 'image'.
        If the instance has a 'image_url' attribute, it returns 'image_url'.
        Otherwise, it returns the default image URL for the source of the article.
        """
        if self.context.get("detail", None) and instance.image_detail:
            return self.context["request"].build_absolute_uri(instance.image_detail.url)
        elif instance.image:
            return self.context["request"].build_absolute_uri(instance.image.url)
        elif instance.image_url:
            return instance.image_url
        else:
            return get_source_default_image_url(instance, self.context)

    @swagger_serializer_method(serializers.IntegerField)
    def get_organization(self, instance):
        """
        This method returns the ID of the organization that the article's source belongs to.
        """
        return instance.source.organization.id

    def get_organization_type(self, instance):
        """
        This method returns the type of the organization that the article's source belongs to.
        """
        return instance.source.organization.type

    def get_organization_name(self, instance):
        """
        This method returns the name of the organization that the article's source belongs to.
        """
        return instance.source.organization.name


class ArticleListSerializer(ArticleBaseSerializer):
    """
    This class is a serializer for the Article model for list views.
    It extends the ArticleBaseSerializer class.
    It includes all the fields defined in ARTICLE_LIST_FIELDS, as well as 'archived' and 'bookmarked'.
    """
    class Meta:
        model = Article
        fields = ARTICLE_LIST_FIELDS + (
            "archived",
            "bookmarked",
        )


class ArticleBookmarkedArchivedSerializer(ArticleBaseSerializer):
    """
    This class is a serializer for the Article model for bookmarked and archived views.
    It extends the ArticleBaseSerializer class.
    It includes all the fields defined in BASE_LIST_FIELDS, as well as 'archived' and 'bookmarked'.
    """
    class Meta:
        model = Article
        fields = BASE_LIST_FIELDS + (
            "archived",
            "bookmarked",
        )


class PaginatedArticleBookmarkedArchivedSerializer(serializers.Serializer):
    """
    This class is a serializer for paginated responses of bookmarked and archived articles.
    It includes fields for the count of results, the URL of the next page, the URL of the previous page, and the results themselves.
    The results are serialized using the ArticleBookmarkedArchivedSerializer.
    """
    count = serializers.IntegerField()
    next = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    previous = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    results = ArticleBookmarkedArchivedSerializer(many=True)


class ArticleRetrieveSerializer(ArticleBaseSerializer):
    """
    This class is a serializer for the Article model for retrieve views.
    It extends the ArticleBaseSerializer class.
    It includes all the fields defined in ARTICLE_RETRIEVE_FIELDS, as well as 'archived' and 'bookmarked'.
    """
    class Meta:
        model = Article
        fields = ARTICLE_RETRIEVE_FIELDS + (
            "archived",
            "bookmarked",
        )


class PaginatedArticleRetrieveSerializer(serializers.Serializer):
    """
    This class is a serializer for paginated responses of retrieved articles.
    It includes fields for the count of results, the URL of the next page, the URL of the previous page, and the results themselves.
    The results are serialized using the ArticleRetrieveSerializer.
    """
    count = serializers.IntegerField()
    next = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    previous = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    results = ArticleRetrieveSerializer(many=True)


def get_is_hot_queryset(exclude_article_ids, oldest_date, area_id=3):
    """Get a queryset containing recent articles flagge "is_hot".

    Args:
        exclude_article_ids (list): article ids to be excluded
        oldest_date (date): oldes date for articles

    Returns:
        queryset
    """
    return (
        Article.objects.filter(is_hot=True)
        .exclude(id__in=exclude_article_ids)
        .exclude(source__active=False)
        .exclude(source__organization__active=False)
        .filter(date__gte=oldest_date.strftime("%Y-%m-%d"))
        .filter(area=area_id)
        .order_by("-date")
    )


        
       
class ArticleViewSet(BaseViewSet):
    """
    This methods can be used to create, update, delete and list articles
    """

    # Define the queryset, serializer class, model class, filter backends, filterset class, time period to show, ordering fields, ordering, and pagination class
    queryset = Article.objects.filter(published=True)
    serializer_class = ArticleRetrieveSerializer
    model_class = Article
    filter_backends = BaseViewSet.filter_backends + [
        DeviceIdFilter,
    ]
    filterset_class = ArticleFilter
    time_period_to_show = 14
    ordering_fields = ["date"]
    ordering = ["-date"]
    pagination_class = UserPagination

    def get_limited_queryset(self, device_id, exclude_ids=[], use_basefilter=True):
        """
        Get a query set limited by time and without bookmarked / archived articles.

        Args:
            device_id (str): device id
            exclude_ids (list): list of ids to exclude from queryset
            use_basefilter (bool): use all base filters or if set to False
                only  DeviceIdFilter and  SourceActiveFilter

        Returns:
            queryset, excluded_articles_ids, oldest_date
        """
        # Define the current date and the oldest date for the query
        current_date = datetime.now().date()
        oldest_date = current_date - timedelta(days=self.time_period_to_show)
        app_user = get_appuser(device_id)

        # Define the list of article ids to exclude
        exclude_article_ids = exclude_ids
        if app_user:
            # Add the ids of the user's archived and bookmarked articles to the list of ids to exclude
            exclude_article_ids += [
                article.id for article in app_user.archived_articles.all()
            ]
            exclude_article_ids += [
                article.id for article in app_user.bookmarked_articles.all()
            ]

        # If not using base filter, set the filter backends to DeviceIdFilter and SourceActiveFilter
        if not use_basefilter:
            self.filter_backends = [DeviceIdFilter, SourceActiveFilter]

        # Define the queryset
        self.queryset = Article.objects.filter(published=True)
        queryset = self.filter_queryset(self.get_queryset())

        # Get or create the AppUser object for the given device id
        app_user, created = AppUser.objects.get_or_create(device_id=device_id)

        # Try to get the user's area id, if it doesn't exist, set it to 3
        try:
            user_area = app_user.area
            area_id = user_area.__dict__["id"]
        except:
            area_id = 3

        # If the AppUser object was just created, assign all tags and active organizations to the user
        if created:
            # Assign all tags to the user if they don't have any
            user_tags = app_user.tags.values()
            if len(user_tags) == 0:
                all_tags = Tag.objects.all().values()
                for tag in all_tags:
                    app_user.tags.add(tag["id"])
                app_user.save()

            # Assign all active organizations to the user if they don't have any
            user_organisations = app_user.organization.values()
            if len(user_organisations) == 0:
                logger.error("user has no organisations")
                all_organisations = Organization.objects.filter(active=True).values()
                for org in all_organisations:
                    app_user.organization.add(org["id"])
                app_user.save()

        # Exclude bookmarked and archived articles, filter by area and date
        queryset = (
            queryset.exclude(id__in=exclude_article_ids)
            .filter(area=area_id)
            .filter(date__gte=oldest_date.strftime("%Y-%m-%d"))
        )
        return queryset, exclude_article_ids, oldest_date

    @swagger_auto_schema(
        manual_parameters=[
            string_parameter(
                "search", "Search term - searches in title, abstract, content and tags"
            ),
            choices_parameter(
                "ordering", ("date", "-date"), 'Ordering (default is "-date")'
            ),
        ]
        + [
            boolean_parameter(
                article_type[0],
                'Include articles with type "{}", defaults to true'.format(
                    article_type[0]
                ),
                default=True,
            )
            for article_type in ORGANIZATION_TYPE_CHOICES
        ]
        + [
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        operation_description="""List published articles.\n
        If any of the parameters "search, tag, organization_all_tags, organization" is supplied
         then no articles flagged as "is_hot" will be inserted as the first article.
        In addition using one of the parameters "tag, organization_all_tags, organization" will supersede stored user settings and filters. 
         """,
        responses={400: "Device ID missing."},
    )
    def list(self, *args, **kwargs):
        # Get the device id from the request headers
        device_id = self.request.headers.get("X-Device-ID", None)
        if device_id is None:
            return bad_request("Device ID is missing")

        # Get the limited queryset
        queryset, exclude_article_ids, oldest_date = self.get_limited_queryset(
            device_id
        )

        # Check if any of the parameters "organization", "organization_all_tags", "tags", "search" are supplied
        parameters = self.request.query_params
        ignore_is_hot = any(
            [
                keyword in parameters.keys() and parameters.get(keyword, "") != ""
                for keyword in [
                    "organization",
                    "organization_all_tags",
                    "tags",
                    "search",
                ]
            ]
        )

        # Get the user's area id, if it doesn't exist, set it to 3
        app_user = get_appuser(device_id)
        area_id = 3
        try:
            user_area = app_user.area
            area_id = user_area.__dict__["id"]
        except:
            area_id = 3

        # Assign all tags and active organizations to the user if they don't have any
        user_tags = app_user.tags.values()
        if len(user_tags) == 0:
            all_tags = Tag.objects.all().values()
            for tag in all_tags:
                app_user.tags.add(tag["id"])
        user_organisations = app_user.organization.values()
        if len(user_organisations) == 0:
            logger.error("user has no organisations")
            all_organisations = Organization.objects.filter(active=True).values()
            for org in all_organisations:
                try:
                    app_user.organization.add(org["id"])
                except Exception as e:
                    logger.error(e)
            app_user.save()

        # Get the hottest article if it exists and the "is_hot" flag is not ignored
        hottest = None
        is_hot_queryset = get_is_hot_queryset(exclude_article_ids, oldest_date, area_id)
        if len(is_hot_queryset) > 0 and not ignore_is_hot:
            hottest = is_hot_queryset[0]
            queryset = queryset.exclude(id=hottest.id)
            querysetlist = list(queryset)
            for element in querysetlist:
                element.is_hot = False
            articles = [hottest] + querysetlist
            page = self.paginate_queryset(articles)
        else:
            page = self.paginate_queryset(queryset)

        # Serialize the page and return the paginated response
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # Serialize the queryset and return the response
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # Define the get_serializer_class method, which returns the appropriate serializer class based on the action
    def get_serializer_class(self):
        action = self.action.lower()
        if action == "list":
            self.serializer_class = ArticleListSerializer
        return super().get_serializer_class()
   
   
    # Define the similar method, which handles requests for similar articles
    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
            integer_parameter("limit", "Number of results to return per page."),
            integer_parameter(
                "offset", "The initial index from which to return the results."
            ),
        ],
        responses={
            200: PaginatedArticleRetrieveSerializer,
            400: "Device ID missing.",
            404: "No such article.",
        },
    )
    @action(detail=True)
    def similar(self, request, *args, pk=None, **kwargs):
        return super().similar(request, *args, pk=pk, **kwargs)
    


class ArticleAppUserBaseViewSet(AppUserBaseViewSet):
    """
    This class is a base ViewSet for the Article model in the context of an AppUser.
    It extends the AppUserBaseViewSet class.
    It includes several properties for handling different types of requests.
    """

    # Define the queryset, serializer class, pagination class, many-to-many field name, time period to show, and filter backends
    queryset = Article.objects.all()  # All instances of the Article model
    serializer_class = ArticleBookmarkedArchivedSerializer  # Serializer class for the Article model
    pagination_class = UserPagination  # Pagination class for the Article model
    m2m_field_name = None  # Name of the many-to-many field in the Article model
    time_period_to_show = 30  # Time period (in days) to show in the queryset
    filter_backends = AppUserBaseViewSet.filter_backends + [
        DeviceIdFilter,  # Additional filter backend for filtering by device id
    ]


class ArticleArchiveViewSet(ArticleAppUserBaseViewSet):
    """
    This class is a ViewSet for the Article model in the context of an AppUser's archived articles.
    It extends the ArticleAppUserBaseViewSet class.
    It includes several methods for handling different types of requests.
    """

    # Define the many-to-many field name for the archived articles
    m2m_field_name = "archived_articles"

    @swagger_auto_schema(
        operation_description="List archived articles",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            200: PaginatedArticleBookmarkedArchivedSerializer,
            400: "Invalid Device ID",
        },
    )
    # Define the list method, which handles GET requests and returns a list of archived articles
    def list(self, request, *args, **kwargs):
        self.serializer_class = ArticleRetrieveSerializer
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_description="Add article to archive",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            201: "Added to archive",
            400: "Invalid Device ID",
            404: "Article not found",
        },
    )
    # Define the update method, which handles PUT requests and adds an article to the archive
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_description="Remove article from archive",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            204: "Removed from archive",
            400: "Invalid Device ID",
            404: "Article not found",
        },
    )
    # Define the destroy method, which handles DELETE requests and removes an article from the archive
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
    

class ArticleBookmarksViewSet(ArticleAppUserBaseViewSet):
    """
    This class is a ViewSet for the Article model in the context of an AppUser's bookmarked articles.
    It extends the ArticleAppUserBaseViewSet class.
    It includes several methods for handling different types of requests.
    """

    # Define the many-to-many field name for the bookmarked articles
    m2m_field_name = "bookmarked_articles"

    @swagger_auto_schema(
        operation_description="List bookmarked articles",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            200: PaginatedArticleBookmarkedArchivedSerializer,
            400: "Invalid Device ID",
        },
    )
    # Define the list method, which handles GET requests and returns a list of bookmarked articles
    def list(self, request, *args, **kwargs):
        self.serializer_class = ArticleRetrieveSerializer
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_description="Add article to bookmarks",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            201: "Added to bookmarks",
            400: "Invalid Device ID",
            404: "Article not found",
        },
    )
    # Define the update method, which handles PUT requests and adds an article to the bookmarks
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_description="Remove article from bookmarks",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            204: "Removed from bookmarks",
            400: "Invalid Device ID",
            404: "Article not found",
        },
    )
    # Define the destroy method, which handles DELETE requests and removes an article from the bookmarks
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
    

