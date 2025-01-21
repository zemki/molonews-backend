from rest_framework import viewsets, serializers
from content.models import App_urls
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from .util import UserPagination, header_string_parameter

class AppUrlSerializer(serializers.ModelSerializer):

    class Meta:
        model = App_urls
        fields = (
            'name',
            'url',
        )

class ListAppUrlSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = AppUrlSerializer(many=True)


class AppUrlsViewSet(viewsets.ViewSet):
    """
    Method to retrieve the urls used inside the app 
    """
    queryset = App_urls.objects.all()
    serializer_class = AppUrlSerializer

    @swagger_auto_schema(
        operation_description='Get a list of URLs used in the side menu of the app',
        responses={200: ListAppUrlSerializer(), 400: 'Device ID does not exist'},
    )
    def list(self, request):
       
        serializer = AppUrlSerializer(self.queryset, many=True)
    
        return Response({
            'count': self.queryset.count(),
            'results': serializer.data
        })


