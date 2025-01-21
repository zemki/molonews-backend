from django.db.models import Count, Q
from datetime import datetime, timedelta

from django.http import Http404
from rest_framework import viewsets, serializers, filters, mixins
from drf_yasg.utils import swagger_auto_schema, swagger_serializer_method
import django_filters as df
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from .util import (
    UserPagination, choices_parameter, integer_parameter, string_parameter, boolean_parameter, header_string_parameter
)
from content.models import AppUser, Article, Event, Tag, Organization
from content.choices import ARTICLE_TYPE_CHOICES, ORGANIZATION_TYPE_CHOICES
from .util import bad_request


BASE_LIST_FIELDS = (
    "id",
    "title",
    "abstract",
    "date",
    "image_url",
)

ARTICLE_LIST_FIELDS = BASE_LIST_FIELDS + (
    'address',
    'link',
    'is_hot',
    'tags',
    'organization',
    'organization_type',
    'organization_name',
    'image_source',
)

ARTICLE_RETRIEVE_FIELDS = ARTICLE_LIST_FIELDS + (
    'source',
    'content',
)


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


class ArticleFilter(df.FilterSet):
    organization = df.BaseInFilter(
        field_name='source__organization',
        help_text='Organization ID(s) - comma separated | defaults to user settings',
    )

    organization_all_tags = df.BaseInFilter(
        field_name='source__organization',
        help_text='Organization ID(s) - comma separated - not filtered against tags | defaults to user settings',
    )

    tags = df.BaseInFilter(
        field_name='tags', distinct=True, help_text='Tag ID(s) - comma separated | defaults to user settings',
    )

    date_start = df.IsoDateTimeFilter(
        field_name='date', help_text='ISO 8601 formatted', lookup_expr='gte',
    )

    date_end = df.IsoDateTimeFilter(
        field_name='date', help_text='ISO 8601 formatted', lookup_expr='lte',
    )

    def filter_queryset(self, queryset):
        appuser = get_appuser(self.request.headers.get("X-Device-ID", None))
        queries = {
            'organization': Q(),
            'tags': Q(),
            'organization_all_tags': Q(),
        }
        user_queries = {}
        if appuser:
            for name in queries:
                _filter = self.filters[name]
                lookup = '{}__{}'.format(_filter.field_name, _filter.lookup_expr)
                value = [str(_attr.id) for _attr in getattr(appuser, name).all() if _attr]
                if value is not None and value:
                    user_queries[name] = Q(**{lookup: value})

        # overwrite filter settings if we get parameters via api
        ignore_usersettings = False
        parameter_queries = {}
        for name, value in self.form.cleaned_data.items():
            if name in ('organization', 'tags', 'organization_all_tags'):
                f = self.filters[name]
                lookup = '{}__{}'.format(f.field_name, f.lookup_expr)
                if value is not None and value:
                    ignore_usersettings = True
                    parameter_queries[name] = Q(**{lookup: value})
            else:
                queryset = self.filters[name].filter(queryset, value)

        _queries = user_queries
        if ignore_usersettings:
            _queries = parameter_queries
        for key, value in _queries.items():
            queries[key] = value

        # select all tags if none is selected
        if appuser is None and (
                'tags' not in self.form.cleaned_data.keys() or not self.form.cleaned_data['tags']
        )and not ignore_usersettings:
            queries['tags'] = Q(**{'tags__in': Tag.objects.all()})
        if appuser is None and (
                'organization' not in self.form.cleaned_data.keys() or not self.form.cleaned_data['organization']
        )and not ignore_usersettings:
            queries['organization'] = Q(**{'source__organization__in': Organization.objects.all()})

        if len(queries['organization'] & queries['tags']) < 2 and len(queries['organization_all_tags']) == 1:
            queries_combined = queries['organization_all_tags']
        elif len(queries['organization'] & queries['tags']) == 2 and len(queries['organization_all_tags']) < 1:
            queries_combined = queries['organization'] & queries['tags']
        else:
            queries_combined = (queries['organization'] & queries['tags']) | queries['organization_all_tags']
        now = datetime.now()
        queryset = queryset.filter(queries_combined).filter(date__lte=now)

        return queryset

    class Meta:
        model = Article
        fields = ['organization', 'tags', 'organization_all_tags', 'date_start']


class DeviceIdFilter(filters.BaseFilterBackend):

    def filter_queryset(self, request, queryset, view):
        device_id = request.headers.get('X-Device-ID', None)
        if device_id is not None:
            queryset = queryset.annotate(bookmarked=Count('pk', filter=Q(articles_bookmarked__device_id=device_id)))
            queryset = queryset.annotate(archived=Count('pk', filter=Q(articles_archived__device_id=device_id)))
        return queryset

    def get_schema_fields(self, view):
        return []


class SourceTypeFilter(filters.BaseFilterBackend):

    def filter_queryset(self, request, queryset, view):
        """Filter queryset to only include articles from selected organization types.

        Args:
            request (Request): current request
            queryset (QuerySet): unfiltered Queryset
            view (View): current view

        Returns:
            filtered QuerySet
        """
        source_types = [type[0] for type in ORGANIZATION_TYPE_CHOICES]
        query_parameter = [_type for _type in source_types if request.query_params.get(_type, 'true') == 'true']
        queryset = queryset.filter(Q(**{'source__organization__type__in': query_parameter}))
        return queryset


class SourceActiveFilter(filters.BaseFilterBackend):

    def filter_queryset(self, request, queryset, view):
        """Filter queryset to only include articles from active sources.

        Args:
            request (Request): current request
            queryset (QuerySet): unfiltered Queryset
            view (View): current view

        Returns:
            filtered QuerySet
        """
        return queryset.exclude(source__active=False).exclude(source__organization__active=False)


class ArticleTagsSerializer(serializers.ModelSerializer):

    class Meta:
        model = Tag
        fields = ('id', 'name')


def get_source_default_image_url(instance, context):
    if context.get('detail', None) and instance.source.default_image_detail:
        return context['request'].build_absolute_uri(instance.source.default_image_detail.url)
    elif instance.source.default_image:
        return context['request'].build_absolute_uri(instance.source.default_image.url)
    else:
        return instance.source.default_image_url


class ArticleBaseSerializer(serializers.ModelSerializer):

    tags = ArticleTagsSerializer(read_only=True, many=True)
    organization = serializers.SerializerMethodField()
    organization_type = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    archived = serializers.SerializerMethodField()
    bookmarked = serializers.SerializerMethodField()

    @swagger_serializer_method(serializers.BooleanField)
    def get_archived(self, instance):
        archived = bool(getattr(instance, 'archived', False))
        return archived

    @swagger_serializer_method(serializers.BooleanField)
    def get_bookmarked(self, instance):
        bookmarked = bool(getattr(instance, 'bookmarked', False))
        return bookmarked

    def get_image_url(self, instance):
        if self.context.get('detail', None) and instance.image_detail:
            return self.context['request'].build_absolute_uri(instance.image_detail.url)
        elif instance.image:
            return self.context['request'].build_absolute_uri(instance.image.url)
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


class ArticleListSerializer(ArticleBaseSerializer):

    class Meta:
        model = Article
        fields = ARTICLE_LIST_FIELDS + ('archived', 'bookmarked',)


class ArticleBookmarkedArchivedSerializer(ArticleBaseSerializer):

    class Meta:
        model = Article
        fields = BASE_LIST_FIELDS + ('archived', 'bookmarked',)


class PaginatedArticleBookmarkedArchivedSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    previous = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    results = ArticleBookmarkedArchivedSerializer(many=True)


class ArticleRetrieveSerializer(ArticleBaseSerializer):

    type = serializers.SerializerMethodField()

    def get_type(self, instance):
        return 'news'

    class Meta:
        model = Article
        fields = ARTICLE_RETRIEVE_FIELDS + ('archived', 'bookmarked', 'type',)


class PaginatedArticleRetrieveSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    previous = serializers.URLField(allow_blank=True, allow_null=True, required=False)
    results = ArticleRetrieveSerializer(many=True)


def get_is_hot_queryset(exclude_article_ids, oldest_date):
    """Get a queryset containing recent articles flagge "is_hot".

    Args:
        exclude_article_ids (list): article ids to be excluded
        oldest_date (date): oldes date for articles

    Returns:
        queryset
    """
    return Article.objects.filter(is_hot=True).exclude(
        id__in=exclude_article_ids
    ).exclude(source__active=False).exclude(source__organization__active=False).filter(
        date__gte=oldest_date.strftime("%Y-%m-%d")
    ).order_by('-date')


class ArticleViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = Article.objects.filter(published=True)
    serializer_class = ArticleRetrieveSerializer
    model_class = [Article, Event]
    filter_backends = [
        df.rest_framework.DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
        DeviceIdFilter,
        SourceTypeFilter,
        SourceActiveFilter,
    ]
    filterset_class = ArticleFilter
    time_period_to_show = 14

    search_fields = ['title', 'abstract', 'content']

    ordering_fields = ['date']

    ordering = ['-date']

    pagination_class = UserPagination

    def get_object(self):
        """
        Returns the object the view is displaying.

        You may want to override this if you need to provide non-standard
        queryset lookups.  Eg if objects are referenced using multiple
        keyword arguments in the url conf.
        """
        queryset = self.get_queryset()

        # Perform the lookup filtering.
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field

        assert lookup_url_kwarg in self.kwargs, (
                'Expected view %s to be called with a URL keyword argument '
                'named "%s". Fix your URL conf, or set the `.lookup_field` '
                'attribute on the view correctly.' %
                (self.__class__.__name__, lookup_url_kwarg)
        )

        filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
        try:
            obj = get_object_or_404(queryset, **filter_kwargs)
        except Http404:
            return None

        # May raise a permission denied
        self.check_object_permissions(self.request, obj)

        return obj

    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter('X-Device-ID', 'Device ID', required=True),
        ],
        responses={400: 'Device ID missing.', 404: 'No such object.'},
    )
    def retrieve(self, *args, **kwargs):

        device_id = self.request.headers.get('X-Device-ID', None)
        if device_id is None:
            return bad_request('Device ID is missing')

        app_user, created = AppUser.objects.get_or_create(device_id=device_id)
        instance = self.get_object()

        # annotate manually
        setattr(instance, 'bookmarked', app_user in instance.get('{}s_bookmarked'.format(self.model_class.classname())).all())
        setattr(instance, 'archived', app_user in instance.get('{}s_archived'.format(self.model_class.classname)).all())

        if not instance:
            return bad_request("No such article.")

        serializer = ArticleRetrieveSerializer(instance, context={
            'device_id': device_id, 'request': self.request, 'detail': True,
        })

        return Response(serializer.data)

    def get_limited_queryset(self, device_id, exclude_ids=[], use_basefilter=True, type='article'):
        """ Get a query set limited by time and without bookmarked / archived articles.

        Args:
            device_id (str): device id

        Returns:
            queryset, excluded_articles_ids, oldest_date
        """
        current_date = datetime.now().date()
        oldest_date = current_date - timedelta(days=self.time_period_to_show)
        app_user = get_appuser(device_id)
        if app_user:
            exclude_ids += [article.id for article in getattr(
                app_user, 'archived_{}s'.format(type),
            ) .all()]
            exclude_ids += [article.id for article in getattr(
                app_user, 'bookmarked_{}s'.format(type),
            ).all()]

        if not use_basefilter:

            device_id_filter = DeviceIdFilter
            self.filter_backends = [device_id_filter, SourceActiveFilter]
        queryset = self.filter_queryset(self.get_queryset())

        # exclude bookmarked and archived
        queryset = queryset.exclude(id__in=exclude_ids).filter(
            date__gte=oldest_date.strftime("%Y-%m-%d")
        )
        return queryset, exclude_ids, oldest_date

    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter('X-Device-ID', 'Device ID', required=True),
        ],
        responses={400: 'Device ID missing.', 404: 'No such article.'},
    )
    def retrieve(self, *args, **kwargs):

        device_id = self.request.headers.get('X-Device-ID', None)
        if device_id is None:
            return bad_request('Device ID is missing')

        app_user, created = AppUser.objects.get_or_create(device_id=device_id)
        instance = self.get_object()

        # annotate manually
        setattr(instance, 'bookmarked', app_user in instance.articles_bookmarked.all())
        setattr(instance, 'archived', app_user in instance.articles_archived.all())

        if not instance:
            return bad_request("No such article.")

        serializer = ArticleRetrieveSerializer(instance, context={
            'device_id': device_id, 'request': self.request, 'detail': True,
        })

        return Response(serializer.data)

    @swagger_auto_schema(
        manual_parameters=[
            choices_parameter('type', ARTICLE_TYPE_CHOICES, 'The article type'),
            string_parameter('search', 'Search term - searches in title, abstract and content'),
            choices_parameter('ordering', ('date', '-date'), 'Ordering (default is "date")'),
        ] + [
            boolean_parameter(
                article_type[0], 'Include articles with type "{}", defaults to true'.format(article_type[0]), default=True
            ) for article_type in ORGANIZATION_TYPE_CHOICES
        ] + [
            header_string_parameter('X-Device-ID', 'Device ID', required=True),
        ],
        operation_description='''List published articles.\n
        If any of the parameters "search, tag, organization_all_tags, organization" is supplied
         then no articles flagged as "is_hot" will be inserted as the first article.
        In addition using one of the parameters "tag, organization_all_tags, organization" will supersede stored user settings and filters. 
         ''',
        responses={400: 'Device ID missing.'},
    )
    def list(self, *args, **kwargs):
        parameters = self.request.query_params

        device_id = self.request.headers.get('X-Device-ID', None)
        if device_id is None:
            return bad_request('Device ID is missing')

        if parameters.get('type', None) == 'event':
            setattr(parameters, 'type', 'news')

        queryset, exclude_article_ids, oldest_date = self.get_limited_queryset(device_id)

        ignore_is_hot = any(
            [
                keyword in parameters.keys() and parameters.get(keyword, '') != '' for keyword in [
                    'organization', 'organization_all_tags', 'tags', 'search'
                ]
            ]
        )

        hottest = None
        is_hot_queryset = get_is_hot_queryset(exclude_article_ids, oldest_date)
        if len(is_hot_queryset) > 0 and not ignore_is_hot:
            hottest = is_hot_queryset[0]
            # exclude from normal queryset
            queryset = queryset.exclude(id=hottest.id)
            articles = [hottest] + list(queryset)

            page = self.paginate_queryset(articles)
        else:
            page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def get_serializer_class(self):
        action = self.action.lower()
        if action == 'list':
            self.serializer_class = ArticleListSerializer
        return super().get_serializer_class()

    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter('X-Device-ID', 'Device ID', required=True),
            integer_parameter('limit', 'Number of results to return per page.'),
            integer_parameter('offset', 'The initial index from which to return the results.'),
        ],
        responses={
            200: PaginatedArticleRetrieveSerializer, 400: 'Device ID missing.', 404: 'No such article.',
        },
    )
    @action(detail=True)
    def similar(self, request, *args, pk=None, **kwargs):
        """
        Returns a list of similar articles.
        """
        device_id = self.request.headers.get('X-Device-ID', None)
        if device_id is None:
            return bad_request('Device ID is missing')

        instance = self.get_object()
        if not instance:
            return bad_request("No such article.")

        tags = instance.tags.all()

        queryset, exclude_article_ids, oldest_date = self.get_limited_queryset(
            device_id, exclude_ids=[pk], use_basefilter=False,
        )

        queryset = queryset.annotate(
            similar=Count('tags', filter=Q(tags__id__in=tags))
        ).filter(similar__gte=1).order_by('-similar', '-date')

        page = self.paginate_queryset(queryset)

        serializer = ArticleRetrieveSerializer(page, many=True, context={
            'device_id': device_id, 'request': self.request,
        })

        return self.get_paginated_response(serializer.data)


class ArticleAppUserBaseViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):

    queryset = Article.objects.all()
    event_queryset = Event.objects.all()

    serializer_class = ArticleBookmarkedArchivedSerializer
    pagination_class = UserPagination
    m2m_field_name = None
    time_period_to_show = 30
    filter_backends = [
        df.rest_framework.DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
        DeviceIdFilter,
    ]

    def get_serializer_class(self, *args, **kwargs):
        action = self.action.lower()
        if action == "list":
            return self.serializer_class
        else:
            return None

    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        if serializer_class is None:
            return None
        else:
            return serializer_class(*args, **kwargs)

    def get_articles_manager(self, create=False):
        device_id = self.request.headers.get("X-Device-ID", None)
        if device_id is None:
            return None, bad_request("Device ID is missing")
        else:
            if create:
                app_user, created = AppUser.objects.get_or_create(device_id=device_id)
            else:
                try:
                    app_user = AppUser.objects.get(device_id=device_id)
                except AppUser.DoesNotExist:
                    return None, bad_request("Device ID does not exist")
            return getattr(app_user, self.m2m_field_name), None

    def list(self, request, *args, **kwargs):
        app_user_articles, error = self.get_articles_manager(create=False)
        if error:
            return error
        current_date = datetime.now().date()
        oldest_date = current_date - timedelta(days=self.time_period_to_show)
        queryset = (
            self.filter_queryset(app_user_articles.all())
                .filter(date__gte=oldest_date.strftime("%Y-%m-%d"))
                .order_by("-date")
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        app_user_articles, error = self.get_articles_manager(create=True)
        if error:
            return error
        article = self.get_object()
        app_user_articles.add(article)
        return Response(status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        app_user_articles, error = self.get_articles_manager(create=False)
        if error:
            return error
        article = self.get_object()
        app_user_articles.remove(article)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ArticleArchiveViewSet(ArticleAppUserBaseViewSet):

    m2m_field_name = "archived_articles"

    @swagger_auto_schema(
        operation_description="List archived articles",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={200: PaginatedArticleBookmarkedArchivedSerializer, 400: "Invalid Device ID"},
    )
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
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class ArticleBookmarksViewSet(ArticleAppUserBaseViewSet):

    m2m_field_name = "bookmarked_articles"

    @swagger_auto_schema(
        operation_description="List bookmarked articles",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={200: PaginatedArticleBookmarkedArchivedSerializer, 400: "Invalid Device ID"},
    )
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
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
