from rest_framework import viewsets, serializers
import django_filters as df

from content.models import Tag


class TagFilter(df.FilterSet):

    category = df.BaseInFilter(field_name='category')

    class Meta:
        model = Tag
        fields = ['category']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = (
            'id',
            'name',
            'category'
        )


class TagViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    filter_backends = [df.rest_framework.DjangoFilterBackend]
    filterset_class = TagFilter
