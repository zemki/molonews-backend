from rest_framework import viewsets, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from content.models import Tag
from rest_framework import serializers
from drf_yasg.openapi import Parameter
from drf_yasg.openapi import IN_QUERY
import ml.news_article_tagging  as ml
from logging import getLogger
import json

logger = getLogger(__name__)

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = (
            'id',
            'name',
            'category'
        )

class TagSerializerId(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = (
            'id',
        )

class ArticleTagViewSet(viewsets.ViewSet):
    """
    This class returns the tags for a posted article 
    """

    # get the parsers for the files, ususally the JSON parser is the default, here we want to get files
    parser_classes = (MultiPartParser,FormParser)

    tagging_engine = ml.MlTagging()

    # Specify the queryset and the serializer class
    queryset = Tag.objects.all()

    @swagger_auto_schema(
        consumes=['multipart/form-data'], 
        manual_parameters=[
            Parameter(name="title",
                            in_=openapi.IN_FORM,
                            type=openapi.TYPE_STRING,
                            description="The title of the article"
                            ),
            Parameter(name="abstract",
                            in_=openapi.IN_FORM,
                            type=openapi.TYPE_STRING,
                            description="The abstract of the article"
                            ),
        ],
        responses={
                    '200': openapi.Response(
                        description='List of Tags',
                        schema=TagSerializerId(many=True)
                    ),
                    '204': openapi.Response(description='No Content'),
                    '400': openapi.Response(description='Bad Request'),
                }
        
    )
    def create(self, request):
        # Get the article data from the request
        title = request.POST.get('title')
        abstract = request.POST.get('abstract')

        # Check if the title and abstract are present
        if not title or not abstract:
            # return no content
            return Response(status=status.HTTP_204_NO_CONTENT)
    
        # Generate the tags
        auto_tags = self.tagging_engine.tag_news_article(title, abstract)

        # Specify the queryset and the serializer class
        all_tags = Tag.objects.all().values()

        # Create a list to store the tags
        tag_list = []
    
        # add the automatically detected tags to the list of tags of the article
        for auto_tag in auto_tags:
            for tag in all_tags:
                if tag['name'] == auto_tag:
                    tag_list.append(tag['id'])

        # Create a list of dictionaries with the structure [{"id": tag_id}]
        tag_list_structure = [{"id": tag_id} for tag_id in tag_list]

        # Return the tag_list_structure as a JSON response
        return Response(tag_list_structure, status=status.HTTP_201_CREATED)

        # Convert tag_list to a JSON string
        #tag_list_json = json.dumps(tag_list)

        # Return the tags as a JSON response
        #return Response(tag_list_json, status=status.HTTP_201_CREATED)