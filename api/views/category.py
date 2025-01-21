from drf_yasg.utils import swagger_auto_schema, swagger_serializer_method
from rest_framework import viewsets, mixins, serializers
from rest_framework.response import Response

from content.models import Category, Tag
from .util import bad_request, header_string_parameter


class CategoryTagsSerializer(serializers.ModelSerializer):

    is_selected = serializers.SerializerMethodField()

    @swagger_serializer_method(serializers.BooleanField)
    def get_is_selected(self, instance):
        device_id = self.context.get('device_id', None)
        if device_id:
            is_selected = bool(instance.appusers_tags.filter(device_id=device_id))
        else:
            is_selected = False

        return is_selected

    class Meta:
        model = Tag
        fields = ('id', 'name', 'is_selected', 'color')


class CategorySerializer(serializers.ModelSerializer):

    tags = CategoryTagsSerializer(read_only=True, many=True)

    class Meta:
        model = Category
        fields = (
            'id',
            'name',
            'title',
            'description',
            'tags',
            'rank',
        )


class BaseCategoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):

    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter('X-Device-ID', 'Device ID', required=True),
        ],
        responses={
            400: 'Device ID missing.',
        },
    )
    def list(self, request, exclude_category_ids=[], *args, **kwargs):

        device_id = request.headers.get('X-Device-ID', None)
        if device_id is None:
            return bad_request('Device ID is missing')
        queryset = self.filter_queryset(self.get_queryset())

        serializer = CategorySerializer(queryset.exclude(
            id__in=exclude_category_ids
        ), many=True, context={'device_id': device_id})

        # sort tags by name
        sorted_serializer_data = []
        for category in serializer.data:
            category['tags'] = sorted(category['tags'], key=lambda _dict: _dict['name'])
            sorted_serializer_data.append(category)

        return Response(sorted_serializer_data)


class CategoryViewSet(BaseCategoryViewSet):

    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter('X-Device-ID', 'Device ID', required=True),
        ],
        responses={
            400: 'Device ID missing.',
        },
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, exclude_category_ids=[2], *args, **kwargs)
