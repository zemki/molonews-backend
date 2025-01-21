from rest_framework import viewsets, serializers
import django_filters as df

from content.models import Source


class SourceFilter(df.FilterSet):

    class Meta:
        model = Source
        fields = ['organization']


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = (
            'id',
            'name',
            'type',
            'organization',
        )

    image_url = serializers.SerializerMethodField()

    def get_image_url(self, instance):
        if instance.image:
            return instance.image.url
        else:
            return instance.image_url


class SourceViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = Source.objects.all()
    serializer_class = SourceSerializer
    filter_backends = [df.rest_framework.DjangoFilterBackend]
    filterset_class = SourceFilter
