from rest_framework import viewsets  # Add this line
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
import jwt
from django.conf import settings
from django.shortcuts import get_object_or_404
from api.views.article_event_shared import BaseViewSet
from api.views.article_v4 import ArticleRetrieveSerializer
from content.models import Article, User
from drf_yasg.utils import swagger_auto_schema, header_string_parameter
from event_v4 import CombinedViewSetEvent
from article_v4 import CombinedViewSetArticle

class CombinedViewSet(viewsets.ViewSet):
    
    queryset = Article.objects.filter(published=True)
    serializer_class = ArticleRetrieveSerializer
    model_class = Article

    @swagger_auto_schema(
        operation_description="List events and articles for a specific user.",
        manual_parameters=[
            header_string_parameter("Authorization", "JWT token", required=True),
        ],
        responses={
            200: "Success",
            401: "Unauthorized",
            404: "User not found",
        },
    )
    def user_events_articles(self, request, *args, **kwargs):
        """
        List events and articles for a specific user.
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
            # Get events for the user
            #event_list = CombinedViewSetEvent.get_user_events(user)
            #event_serializer = CombinedViewSetEvent.get_serializer(event_list, many=True)
            
            # Get articles for the user

            queryset = Article.objects.filter(published=True, user=user).order_by('-date')
            queryset = queryset.filter(source__name=user.display_name)
            article_serializer = ArticleRetrieveSerializer(queryset, many=True)

            #article_serializer = self.get_serializer(queryset, many=True)

            # Combine events and articles in the response
            response_data = {
            #    "events": event_serializer.data,
                "articles": article_serializer.data,
            }

            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
    