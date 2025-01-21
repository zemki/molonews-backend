from django.conf import settings
from django.db.models import Count, Q, F
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
from content.models import AppUser, Article, Tag, Organization, Area, Source, User
from content.choices import ORGANIZATION_TYPE_CHOICES
from .article_event_shared import (
    AppUserBaseViewSet,
    BaseViewSet,
    SourceActiveFilter,
    get_source_default_image_url,
)
import django_filters as df
from rest_framework import viewsets
from rest_framework.viewsets import GenericViewSet
from rest_framework.pagination import PageNumberPagination
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
import json
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import ml.news_article_tagging  as ml
import jwt
from rest_framework.response import Response
from email.mime.text import MIMEText
from content.models import Article
import smtplib


logger = getLogger(__name__)

# Fields used for serialization

BASE_LIST_FIELDS = (
    "id",
    "title",
    "abstract",
    "date",
    "image_url",
    "area",
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
    "request_count",
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
    selected = serializers.SerializerMethodField()

    class Meta:
        model = Tag
        fields = ("id", "name", "color", "selected")

    @swagger_serializer_method(serializers.BooleanField)
    def get_selected(self, obj):
        app_user = self.context.get("app_user", None)
        if app_user:
            return app_user.tags.filter(id=obj.id).exists()
        return False
    

class AreaIdNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Area
        fields = ('id', 'name')

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
        """Return True if the article is bookmarked for the current app_user."""
        app_user = get_appuser(self.context.get("request").headers.get("X-Device-ID"))
        if app_user:
            return app_user.bookmarked_articles.filter(id=instance.id).exists()
        return False


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
    bookmarked_count = serializers.IntegerField(read_only=True)
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
            "bookmarked_count",
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
    # get the amount of bookmarks for the article
    bookmarked_count = serializers.SerializerMethodField()
    areas = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = ARTICLE_RETRIEVE_FIELDS + (
            "archived",
            "bookmarked",
            "bookmarked_count",
            "areas",
        )
    
    @swagger_serializer_method(serializers.IntegerField)
    def get_bookmarked_count(self, instance):
        """
        This method returns the amount of bookmarks for the article.
        """
        return instance.articles_bookmarked.count()
    
    @swagger_serializer_method(serializer_or_field=AreaIdNameSerializer(many=True))
    def get_areas(self, instance):
        """
        This method returns all areas of the article.
        """
        #fetch the areas of the article
        areas = instance.area.all()
        #return the areas
        return AreaIdNameSerializer(areas, many=True).data
        
    


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
        #if app_user:
        #    # Add the ids of the user's archived and bookmarked articles to the list of ids to exclude
        #    exclude_article_ids += [
        #        article.id for article in app_user.archived_articles.all()
        #    ]
        #    exclude_article_ids += [
        #        article.id for article in app_user.bookmarked_articles.all()
        #    ]

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

        # Increment request_count for each article in the queryset
        queryset.update(request_count=F('request_count') + 1)

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
   
    # define a swagger auto schema for a delete method and also the delete method   
    @swagger_auto_schema(
        operation_description="Delete an article",
        manual_parameters=[
            header_string_parameter("Authorization", "JWT token", required=True),
        ],
        responses={
            204: "Deleted",
            400: "Invalid Device ID",
            404: "Article not found",
        },
    )
    def destroy(self, request, *args, **kwargs):
        """
        Delete an article.

        Args:
            request (Request): The request object.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            Response: The response object.
        """

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
   
            # Handle DELETE request logic here
            # Get the id from the last section of the URL in the request metapass
            url_parts = self.request.META['PATH_INFO'].split('/')
            article_id = url_parts[-2]

            # Retrieve the article
            article = get_object_or_404(Article, id=article_id)

            source = Source.objects.get(related_user=user)

            # Check if the user is the source of the article
            if article.source == source:
                # Delete the article
                article.delete()
            else: 
                return Response(status=status.HTTP_401_UNAUTHORIZED)    
        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        # Return a response with status code 204
        return Response(status=status.HTTP_204_NO_CONTENT)

    # define the swagger auto schema for the create method
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "title": openapi.Schema(type=openapi.TYPE_STRING),
                "abstract": openapi.Schema(type=openapi.TYPE_STRING),
                "content": openapi.Schema(type=openapi.TYPE_STRING),
                "link": openapi.Schema(type=openapi.TYPE_STRING),
                "area": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER),
                ),
                "article_tags": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER),
                ),  
                "date": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
            },
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
            400: "Invalid Request",
        },
    )
    def create(self, request, *args, **kwargs):

        # get the user from the token
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

        # only delete the user if the user is authenticated
        if user.is_authenticated:
     
            # try do get the source corresponding to the user
            try:
                source = Source.objects.get(related_user=user)
            except:
                return Response({"detail": "User not found."}, status=status.HTTP_400_BAD_REQUEST)
                pass

            # Handle POST request logic here
            article = Article()
            if 'title' in request.data:
                article.title = request.data['title']
            if 'abstract' in request.data:
                article.abstract = request.data['abstract']
            if 'content' in request.data:
                article.content = request.data['content']
            article.source = source

            if 'link' in request.data:
                article.link = request.data['link']
            if 'date' in request.data:
                article.date = request.data['date']


            # set the article as published
            article.published = True

            article.save()
            # Get the area information for the article
            areas = request.data['area']
            # Add the new areas to the article
            for area in areas:
                article.area.add(area)
            # Get the tag information for the article
            tags = request.data['article_tags']
            # Add the new tags to the article
            for tag in tags:
                article.tags.add(tag)
   

        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        # Return a 201 Created response with the article id
        return Response({"id": article.id}, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "title": openapi.Schema(type=openapi.TYPE_STRING),
                "abstract": openapi.Schema(type=openapi.TYPE_STRING),
                "content": openapi.Schema(type=openapi.TYPE_STRING),
                "link": openapi.Schema(type=openapi.TYPE_STRING),
                "area": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER),
                ),
                "article_tags": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(type=openapi.TYPE_INTEGER),
                ),  
                "date": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
            },
        ),
        manual_parameters=[
            header_string_parameter("Authorization", "JWT token", required=True),
        ],
        responses={
            204: "No Content",
            400: "Invalid Request",
        },
    )
    def update(self, request, *args, **kwargs):
        """
        Update an article.

        Args:
            request (Request): The request object.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            Response: The response object.
        """

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

            source = Source.objects.get(related_user=user)

            # Get the id from the last section of the URL in the request metapass
            url_parts = self.request.META['PATH_INFO'].split('/')
            article_id = url_parts[-2]

            # Retrieve the article
            article = get_object_or_404(Article, id=article_id)

            # Check if the user is the source of the article
            if article.source == source:

                # Update the article
                for field, value in request.data.items():
                    if field == 'title' and value:
                        article.title = value
                    elif field == 'abstract' and value:
                        article.abstract = value
                    elif field == 'content' and value:
                        article.content = value
                    elif field == 'link' and value:
                        article.link = value
                    elif field == 'date' and value:
                        article.date = value
                    elif field == 'area':
                        # Remove all areas from the article
                        article.area.clear()
                        # Add the new areas to the article
                        for area in value:
                            article.area.add(area)
                                    
                    elif field == 'article_tags':
                        # Remove all tags from the article
                        article.tags.clear()
                        # Add the new tags to the article
                        for tag in value:
                            article.tags.add(tag)
                        
                    else:
                        logger.error(f"Unknown field: {field}")
                
                    # save the article
                    article.save()
            
            # if article.source == source
            else: 
                return Response(status=status.HTTP_401_UNAUTHORIZED) 
        
        # if user.is_authenticated
        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


        # Return a 204 No Content response
        return Response(status=status.HTTP_204_NO_CONTENT)

   
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

class ArticlePagination(PageNumberPagination):
    page_query_param = 'offset'
    page_size = 10  # Set the page size to your preference
    page_size_query_param = 'limit'  # Set the query parameter for page size
    max_page_size = 100  # Set the maximum page size
    offset_query_param = 'offset'  # Set the query parameter for offset


class ArticleArchiveViewSet(GenericViewSet):
    queryset = Article.objects.filter(published=True)
    serializer_class = ArticleListSerializer
    model_class = Article
    filter_backends = [DeviceIdFilter, SourceActiveFilter]
    pagination_class = ArticlePagination

    # Name of the many-to-many field for archived articles
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
    def list(self, request, *args, **kwargs):
        """
        Lists the articles archived by the user.
        
        Args:
            request: The HTTP request object.
            *args: Additional arguments.
        Returns:
            A paginated list of archived articles.
        """
        device_id = request.headers.get('X-Device-ID')
        if not device_id:
            return Response({"detail": "Device ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        app_user = get_appuser(device_id)
        if not app_user:
            return Response({"detail": "App user not found."}, status=status.HTTP_400_BAD_REQUEST)

        # Retrieve archived articles
        archived_articles = app_user.archived_articles.all()

        # Make a queryset out of the archived articles
        queryset = Article.objects.filter(id__in=[article.id for article in archived_articles])

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
        operation_description="Add article to archive",
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
            201: "Added to archive",
            400: "Invalid Device ID",
            404: "Article not found",
        },
    )
    def update(self, request, *args, **kwargs):
        """
        Adds an article to the user's archive.
        
        Args:
            request: The HTTP request object.
            *args: Additional arguments.
            **kwargs: Additional keyword arguments.
        
        Returns:
            A response indicating the article was added to archive.
        """
        article_id = kwargs.get('pk')
        app_user = get_appuser(request.META.get('HTTP_X_DEVICE_ID'))
        if not app_user:
            return Response("Invalid Device ID", status=status.HTTP_400_BAD_REQUEST)
        
        try:
            article = Article.objects.get(id=article_id)
        except Article.DoesNotExist:
            return Response("Article not found", status=status.HTTP_404_NOT_FOUND)

        # if article not found return 404
        if not article:
            return Response("Article not found", status=status.HTTP_404_NOT_FOUND)
        app_user.archived_articles.add(article)
        return Response(status=status.HTTP_201_CREATED)
    
    @swagger_auto_schema(
        operation_description="Remove article from archive",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={
            204: "Removed from archive",
            400: "Invalid Device ID",
            404: "Article not found",
        },
    )
    def destroy(self, request, *args, **kwargs):
        """
        Removes an article from the user's archive.
        
        Args:
            request: The HTTP request object.
            *args: Additional arguments.
            **kwargs: Additional keyword arguments.
        
        Returns:
            A response indicating the article was removed from archive.
        """
        article_id = kwargs.get('pk')
        article = get_object_or_404(Article, id=article_id)
        device_id = request.META.get("HTTP_X_DEVICE_ID")
        app_user = get_appuser(device_id)
        
        if not app_user:
            return Response("Invalid Device ID", status=status.HTTP_400_BAD_REQUEST)
        
        if article not in app_user.archived_articles.all():
            return Response("Article not found", status=status.HTTP_404_NOT_FOUND)
        
        app_user.archived_articles.remove(article)
        return Response("Removed from archive", status=status.HTTP_204_NO_CONTENT)

# Define an empty serializer
class EmptySerializer(serializers.Serializer):
    pass

class ArticleBookmarksViewSet(GenericViewSet):
    queryset = Article.objects.filter(published=True)
    serializer_class = ArticleListSerializer
    model_class = Article
    filter_backends = [DeviceIdFilter, SourceActiveFilter]
    pagination_class = ArticlePagination
    m2m_field_name = "bookmarked_articles"

    def get_serializer_class(self):
       
        if self.action == 'list':
            return ArticleListSerializer
        elif self.action == 'update':
            return None

        if getattr(self, 'swagger_fake_view', False):
            # If the request is made by Swagger for schema generation, return the default serializer class
            return super().get_serializer_class()
        

        return super().get_serializer_class()


    @swagger_auto_schema(
        operation_description="List bookmarked articles",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        
        responses={
            200: PaginatedArticleBookmarkedArchivedSerializer,
            400: "Invalid Device ID",
        },
    )
    def list(self, request, *args, **kwargs):
        """
        Lists the articles bookmarked by the user.
        
        Args:
            request: The HTTP request object.
            *args: Additional arguments.
        Returns:
            A paginated list of bookmarked articles.
        """
        device_id = request.headers.get('X-Device-ID')
        if not device_id:
            return Response({"detail": "Device ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        app_user = get_appuser(device_id)
        if not app_user:
            return Response({"detail": "App user not found."}, status=status.HTTP_400_BAD_REQUEST)

        # Retrieve bookmarked articles
        bookmarked_articles = app_user.bookmarked_articles.all()

        # Make a queryset out of the bookmarked articles
        queryset = Article.objects.filter(id__in=[article.id for article in bookmarked_articles])

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
        operation_description="Add article to bookmarks",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        request_body=None,
        responses={
            201: "Added to bookmarks",
            400: "Invalid Device ID",
            404: "Article not found",
        },
    )
    def update(self, request, *args, **kwargs):
        """
        Adds an article to the user's bookmarks.
        
        Args:
            request: The HTTP request object.
            *args: Additional arguments.
            **kwargs: Additional keyword arguments.
        
        Returns:
            A response indicating the article was added to bookmarks.
        """
        # Override get_serializer to ensure no data is expected
        def get_serializer(*args, **kwargs):
            return None

        article_id = kwargs.get('pk')
        app_user = get_appuser(request.META.get('HTTP_X_DEVICE_ID'))
        if not app_user:
            return Response("Invalid Device ID", status=status.HTTP_400_BAD_REQUEST)
        
        try:
            article = Article.objects.get(id=article_id)
        except Article.DoesNotExist:
            return Response("Article not found", status=status.HTTP_404_NOT_FOUND)
        # if article not found return 404
        if not article:
            return Response("Article not found", status=status.HTTP_404_NOT_FOUND)
        app_user.bookmarked_articles.add(article)

        logger.error(f"Article {article_id} added to bookmarks for user {app_user.device_id}")
        
        return Response(status=status.HTTP_201_CREATED)
    
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
    def destroy(self, request, *args, **kwargs):
        """
        Removes an article from the user's bookmarks.
        
        Args:
            request: The HTTP request object.
            *args: Additional arguments.
            **kwargs: Additional keyword arguments.
        
        Returns:
            A response indicating the article was removed from bookmarks.
        """
        article_id = kwargs.get('pk')
        article = get_object_or_404(Article, id=article_id)
        device_id = request.META.get("HTTP_X_DEVICE_ID")
        app_user = get_appuser(device_id)
        
        if not app_user:
            return Response("Invalid Device ID", status=status.HTTP_400_BAD_REQUEST)
        
        if article not in app_user.bookmarked_articles.all():
            return Response("Article not found", status=status.HTTP_404_NOT_FOUND)
        
        app_user.bookmarked_articles.remove(article)
        return Response("Removed from bookmarks", status=status.HTTP_204_NO_CONTENT)


    
class ArticleFlagViewSet(viewsets.ViewSet):
    queryset = Article.objects.all()

    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'article_id': openapi.Schema(type=openapi.TYPE_INTEGER),
            }
        ),
        responses={
            200: "Value of the article",
            400: "Device ID missing.",
            404: "No such article.",
        },
    )
    def flag(self, request, *args, **kwargs):

        article_id =  request.data['article_id']

        if article_id is None:
            return Response(data={"message": "Article ID is missing"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Send confirmation email
            sender_email = settings.MAIL_SENDING['DEFAULT_FROM_EMAIL']
            receiver_email = "ohlei@uni-bremen.de"
            subject = 'Problematic Article Reported'
            
            message = f'<html><body>Article ID: {article_id}<br>This article has been flagged as problematic.</br>'
            try:
                # add the article title and description to the message
                article = Article.objects.get(id=article_id)
                message += f'Title: {article.title}<br>Abstract: {article.abstract}</br>'
                # add the source name of the article to the message
                message += f'Source: {article.source.name}<br>'
                # add the user's device id to the message
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

class ArticleTagReceiveViewSet(viewsets.ViewSet):
    queryset = Tag.objects.all()

    # route that returns all possible tags for an article
    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={
            200: ArticleTagsSerializer(many=True),
            400: "Device ID missing.",
        },
    )
    def get_all_tags(self, request, *args, **kwargs):

        try:
            # Ermitteln des AppUser anhand der device_id
            device_id = request.headers.get("X-Device-ID")
            app_user = get_appuser(device_id)

            # Tags abrufen
            tags = Tag.objects.filter(color="")
            tags = tags.order_by('name')
            tags = sorted(tags, key=lambda tag: tag.name if tag.name != "andere Sportarten" else "Fußball" + tag.name)

            # Serialisierung der Tags mit dem zusätzlichen Feld "selected"
            serializer = ArticleTagsSerializer(tags, many=True, context={'app_user': app_user})

        except Exception as e:
            return Response(data={"message": f"Error retrieving tags: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.data)
    

class CombinedViewSetArticle(BaseViewSet):

    # Define the queryset, serializer class, model class, filter backends, filterset class, time period to show, ordering fields, ordering, and pagination class
    queryset = Article.objects.filter(published=True).select_related('area')
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
    
    @swagger_auto_schema(
        operation_description="List articles for a specific user.",
        manual_parameters=[
            header_string_parameter("Authorization", "JWT token", required=True),
        ],
        responses={
            200: PaginatedArticleRetrieveSerializer,
            400: "Device ID missing.",
            401: "Unauthorized",
        },
    )
    @action(detail=False, methods=['get'], url_path='user-articles')
    def list_user_articles(self, request, *args, **kwargs):
        """
        List articles for a specific user.
        """
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
            queryset = Article.objects.filter(published=True).order_by('-date')

            # filter the queryset by source where the related_user is the user
            queryset = queryset.filter(source__related_user=user)

            # Annotate the queryset with the bookmarked count
            queryset = queryset.annotate(bookmarked_count=Count('articles_bookmarked'))

            # Paginate the queryset if pagination is set up
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


   
