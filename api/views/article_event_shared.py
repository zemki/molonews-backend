from django.db.models import Count, Q
from datetime import datetime, timedelta

from django.http import Http404
from rest_framework import viewsets, filters, mixins
from drf_yasg.utils import swagger_auto_schema
import django_filters as df
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from .util import UserPagination, header_string_parameter
from content.models import AppUser
from content.choices import ORGANIZATION_TYPE_CHOICES
from .util import bad_request

BASE_LIST_FIELDS = (
    "id",
    "title",
    "abstract",
    "date",
    "image_url",
)


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
        query_parameter = [
            _type
            for _type in source_types
            if request.query_params.get(_type, "true") == "true"
        ]
        queryset = queryset.filter(
            Q(**{"source__organization__type__in": query_parameter})
        )
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
        return queryset.exclude(source__active=False).exclude(
            source__organization__active=False
        )


class BaseViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = None
    serializer_class = None
    model_class = None
    filter_backends = [
        df.rest_framework.DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
        SourceTypeFilter,
        SourceActiveFilter,
    ]
    filterset_class = None

    search_fields = ["title", "content", "tags__name"]

    ordering_fields = ["date"]

    ordering = ["-date"]

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
            "Expected view %s to be called with a URL keyword argument "
            'named "%s". Fix your URL conf, or set the `.lookup_field` '
            "attribute on the view correctly."
            % (self.__class__.__name__, lookup_url_kwarg)
        )

        filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
        try:
            obj = get_object_or_404(queryset, **filter_kwargs)
        except Http404:
            return None

        # Increment the request_count for the article
        try:
            # Increment the request_count for the article
            if self.action == 'retrieve':
                obj.request_count += 1
                obj.save(update_fields=['request_count'])
        except:
            pass

        # May raise a permission denied
        self.check_object_permissions(self.request, obj)

        return obj

    def get_limited_queryset(self, device_id, exclude_ids=[], use_basefilter=True):
        raise NotImplementedError

    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={400: "Device ID missing.", 404: "No such object 1."},
    )
    def retrieve_nooo(self, *args, **kwargs):

        device_id = self.request.headers.get("X-Device-ID", None)
        if device_id is None:
            return bad_request("Device ID is missing")

        app_user, created = AppUser.objects.get_or_create(device_id=device_id)
        instance = self.get_object()

        if not instance:
            return bad_request("No such object 2.")

        # annotate manually
        setattr(
            instance,
            "bookmarked",
            app_user
            in getattr(
                instance, "{}s_bookmarked".format(self.model_class.classname())
            ).all(),
        )
        setattr(
            instance,
            "archived",
            app_user
            in getattr(
                instance, "{}s_archived".format(self.model_class.classname())
            ).all(),
        )

        serializer = self.serializer_class(
            instance,
            context={
                "device_id": device_id,
                "request": self.request,
                "detail": True,
            },
        )

        return Response(serializer.data)

    def list(self, *args, **kwargs):
        raise NotImplementedError

    @action(detail=True)
    def similar(self, request, *args, pk=None, **kwargs):
        """
        Returns a list of similar objects.
        """
        device_id = self.request.headers.get("X-Device-ID", None)
        if device_id is None:
            return bad_request("Device ID is missing")

        instance = self.get_object()
        if not instance:
            return bad_request("No such object 3.")

        tags = instance.tags.all()
        # If the article has no tags, return an empty list
        if not tags.exists():
            return Response([], status=status.HTTP_200_OK)


        queryset, exclude_article_ids, oldest_date = self.get_limited_queryset(
            device_id,
            exclude_ids=[pk],
            use_basefilter=False,
        )

        queryset = (
            queryset
            .exclude(id=instance.id)  # Exclude the current article
            .annotate(similar_count=Count("tags", filter=Q(tags__in=tags))) # Count the number of matching tags
            .filter(similar_count__gt=0)  # Ensure articles have at least one matching tag
            .order_by("-similar_count", "-date")  # Order by similarity first, then by date
        )

        page = self.paginate_queryset(queryset)

        serializer = self.serializer_class(
            page,
            many=True,
            context={
                "device_id": device_id,
                "request": self.request,
            },
        )

        return self.get_paginated_response(serializer.data)


class AppUserBaseViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = None
    serializer_class = None
    model_class = None
    pagination_class = UserPagination
    m2m_field_name = None
    time_period_to_show = 30
    filter_backends = [
        df.rest_framework.DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
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

    def get_manager(self, create=False):
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

    def list(self, request, *args, ignore_object_age_filter=False, **kwargs):
        app_user_objects, error = self.get_manager(create=False)
        if error:
            return error
        current_date = datetime.now().date()
        oldest_date = current_date - timedelta(days=self.time_period_to_show)
        if not ignore_object_age_filter:
            queryset = (
                self.filter_queryset(app_user_objects.all())
                .filter(date__gte=oldest_date.strftime("%Y-%m-%d"))
                .order_by("-date")
            )
        else:
            queryset = self.filter_queryset(app_user_objects.all()).order_by("-date")

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(
                page, many=True, context={"request": request}
            )
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        app_user_objects, error = self.get_manager(create=True)
        if error:
            return error
        _object = self.get_object()
        app_user_objects.add(_object)
        return Response(status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        app_user_objects, error = self.get_manager(create=False)
        if error:
            return error
        _object = self.get_object()
        app_user_objects.remove(_object)
        return Response(status=status.HTTP_204_NO_CONTENT)


def get_source_default_image_url(instance, context):

    if context.get("detail", None) and instance.source.default_image_detail:
        return context["request"].build_absolute_uri(
            instance.source.default_image_detail.url,
        )
    elif instance.source.default_image:
        return context["request"].build_absolute_uri(instance.source.default_image.url)
    else:
        try:
            imgurl = instance.source.organization.image.url
        except:  
            imgurl = None
        
        if instance.source.default_image_url:
            return instance.source.default_image_url
        else:
            return context["request"].build_absolute_uri(
                imgurl,
            )
