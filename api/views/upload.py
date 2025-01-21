from rest_framework import viewsets
from drf_yasg.utils import swagger_auto_schema
from rest_framework.response import Response
from api.views.util import header_string_parameter
from content.models import  Article, EventV4, Organization, User, Source
from logging import getLogger
from rest_framework.parsers import MultiPartParser, FormParser
from drf_yasg import openapi
from rest_framework import status
import uuid
from PIL import Image
from drf_yasg.openapi import Parameter
from drf_yasg.openapi import IN_QUERY
from django.conf import settings
import jwt
from django.shortcuts import get_object_or_404

logger = getLogger(__name__)

# the ViewSet doesnt have any commands implemented by default, 
# we will manually implement the POST command

class PictureUploadArticleViewSet(viewsets.ViewSet):

    # get the parsers for the files, ususally the JSON parser is the default, here we want to get files
    parser_classes = (MultiPartParser,FormParser)

    # get the queryset of the articles 
    queryset = Article.objects.all()

    # this create method implements the POST command for the viewset
    @swagger_auto_schema(
        consumes=['multipart/form-data'], 
        manual_parameters=[
            Parameter(name="picture",
                            in_=openapi.IN_FORM,
                            type=openapi.TYPE_FILE,
                            required=False,
                            description="The picture file to upload"
                            ),
            Parameter(
                            name="Authorization",
                            in_=openapi.IN_HEADER,
                            type=openapi.TYPE_STRING,
                            required=False,
                            description="JWT token"
                            ),
            Parameter(
                            name="image_source",
                            in_=openapi.IN_FORM,
                            type=openapi.TYPE_STRING,
                            required=False,
                            description="Source of the image"
                            )
        ],
        responses={
            status.HTTP_201_CREATED: openapi.Response(
                description="Picture uploaded successfully",
                examples={
                    "application/json": {
                        "message": "Picture uploaded successfully",
                        "article_id": "123",
                        "image_url": "https://example.com/media/appuploads/your-uploaded-image.jpg"
                    }
                }
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Invalid request - missing picture, invalid file format, or missing article ID",
                examples={
                    "application/json": {"message": "No picture file present"}
                }
            ),
            status.HTTP_404_NOT_FOUND: openapi.Response(
                description="Article does not exist",
                examples={
                    "application/json": {"message": "Article does not exist"}
                }
            ),
            status.HTTP_500_INTERNAL_SERVER_ERROR: openapi.Response(
                description="Error occurred while saving the file",
                examples={
                    "application/json": {"message": "Error occurred while saving the file"}
                }
            )
        }
    )
    def upload_picture(self, request, id=None):

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

            article_id = id

            # check if the article id is valid and if not return a bad request
            if not article_id:
                return Response({"message": "Invalid Request"}, status=status.HTTP_400_BAD_REQUEST)
            
            # save the file path inside the article image_url
            try:
                article = Article.objects.get(id=article_id)
            except Article.DoesNotExist:
                return Response({"message": "Article does not exist"}, status=status.HTTP_404_NOT_FOUND)
            
            # get the details of the refernced source of the article
            source = Source.objects.get(id=article.source_id)
            # check if the article belongs to the user
            if source.related_user != user:
                return Response({"message": "User does not have permission to upload image for this article"}, status=status.HTTP_401_UNAUTHORIZED)

            # check if the request has a picture file
            if 'picture' not in request.FILES:
                image_source = request.data.get('image_source')
                if image_source:
                    article.image_source = image_source
                    #save the event
                    article.save()
                    return Response({
                        "message": "Image source updated successfully"
                    }, status=status.HTTP_201_CREATED)
                else:
                    return Response("No picture file present", status=status.HTTP_201_CREATED)
            
            # get the picture file from the request
            picture = request.FILES['picture']

            # check if the file is an image of any type
            try:
                # open the file using PIL
                img = Image.open(picture)
                # check if the file format is supported by PIL
                supported_formats = ['JPEG', 'PNG', 'GIF', 'JPG']
                if img.format not in supported_formats:
                    return Response({"message": "Invalid file format"}, status=status.HTTP_400_BAD_REQUEST)
            except IOError:
                return Response({"message": "Invalid image file"}, status=status.HTTP_400_BAD_REQUEST)

            # generate a unique filename using UUID
            filename = str(uuid.uuid4()) 

            # get the file extension of the picture.name and make it lowercase
            file_extension = picture.name.split('.')[-1].lower()

            # if the file extension is not empty, add a dot before the extension
            filename = filename + '.' + file_extension

            # construct the file path with the unique filename
            file_path = '/home/molonews/molonews/www/media/appuploads/' + filename 
            try:
                with open(file_path, 'wb') as file:
                    for chunk in picture.chunks():
                        file.write(chunk)
            except Exception as e:
                return Response({"message": "Error occurred while saving the file"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # get the server hostname 
            server_hostname = request.get_host()
            article.image_url = 'https://' + server_hostname + '/media/appuploads/' + filename
            
            # get the image source from the request
            image_source = request.data.get('image_source')
            if image_source:
                article.image_source = image_source

            article.save()

            return Response({
                "message": "Picture uploaded successfully",
                "article_id": str(article_id),
                "image_url": article.image_url
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({"message": "User not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)




# the ViewSet doesnt have any commands implemented by default, 
# we will manually implement the POST command

class PictureUploadEventViewSet(viewsets.ViewSet):

    # get the parsers for the files, ususally the JSON parser is the default, here we want to get files
    parser_classes = (MultiPartParser,FormParser)

    # get the queryset of the events 
    queryset = EventV4.objects.all()

    # this create method implements the POST command for the viewset
    @swagger_auto_schema(
        consumes=['multipart/form-data'], 
        manual_parameters=[
            Parameter(name="picture",
                            in_=openapi.IN_FORM,
                            type=openapi.TYPE_FILE,
                            required=False,
                            description="The picture file to upload"
                            ),
            Parameter(
                            name="Authorization",
                            in_=openapi.IN_HEADER,
                            type=openapi.TYPE_STRING,
                            required=False,
                            description="JWT token"
                            ),
            Parameter(
                            name="image_source",
                            in_=openapi.IN_FORM,
                            type=openapi.TYPE_STRING,
                            required=False,
                            description="Source of the image"
                            )
        ],
        responses={
            status.HTTP_201_CREATED: openapi.Response(
                description="Picture uploaded successfully",
                examples={
                    "application/json": {
                        "message": "Picture uploaded successfully",
                        "event_id": "123",
                        "image_url": "https://example.com/media/appuploads/your-uploaded-image.jpg"
                    }
                }
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Invalid request - missing picture, invalid file format, or missing event ID",
                examples={
                    "application/json": {"message": "No picture file present"}
                }
            ),
            status.HTTP_404_NOT_FOUND: openapi.Response(
                description="Event does not exist",
                examples={
                    "application/json": {"message": "Event does not exist"}
                }
            ),
            status.HTTP_500_INTERNAL_SERVER_ERROR: openapi.Response(
                description="Error occurred while saving the file",
                examples={
                    "application/json": {"message": "Error occurred while saving the file"}
                }
            )
        }
    )
    def upload_picture(self, request, id=None):

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
            
            event_id = id

            # check if the event id is valid and if not return a bad request
            if not event_id:
                logger.error("Invalid Request no event id")
                return Response({"message": "Invalid Request"}, status=status.HTTP_400_BAD_REQUEST)
                
            
            # save the file path inside the event image_url
            try:
                event = EventV4.objects.get(id=event_id)
            except EventV4.DoesNotExist:
                logger.error("Event does not exist")
                return Response({"message": "Event does not exist"}, status=status.HTTP_404_NOT_FOUND)
            
            # get the details of the refernced source of the article
            source = Source.objects.get(id=event.source_id)
            # check if the article belongs to the user
            if source.related_user != user:
                logger.error("User does not have permission to upload image for this event")
                return Response({"message": "User does not have permission to upload image for this article"}, status=status.HTTP_401_UNAUTHORIZED)
            
            # check if the request has a picture file
            if 'picture' not in request.FILES:
                image_source = request.data.get('image_source')
                if image_source:
                    event.image_source = image_source
                    #save the event
                    event.save()
                    return Response({
                        "message": "Image source updated successfully"
                    }, status=status.HTTP_201_CREATED)
                else:
                    return Response("No picture file present", status=status.HTTP_201_CREATED)
            
            # get the picture file from the request
            picture = request.FILES['picture']

            # check if the file is an image of any type
            try:
                # open the file using PIL
                img = Image.open(picture)
                # check if the file format is supported by PIL
                supported_formats = ['JPEG', 'PNG', 'GIF', 'JPG', 'jpeg', 'png', 'gif', 'jpg']
                if img.format not in supported_formats:
                    logger.error("Invalid file format")
                    return Response({"message": "Invalid file format"}, status=status.HTTP_400_BAD_REQUEST)
            except IOError:
                logger.error("Invalid image file")
                return Response({"message": "Invalid image file"}, status=status.HTTP_400_BAD_REQUEST)

            # generate a unique filename using UUID
            filename = str(uuid.uuid4()) 

            # get the file extension of the picture.name and make it lowercase
            file_extension = picture.name.split('.')[-1].lower()

            # if the file extension is not empty, add a dot before the extension
            filename = filename + '.' + file_extension

            # construct the file path with the unique filename
            file_path = '/home/molonews/molonews/www/media/appuploads/' + filename 
            try:
                with open(file_path, 'wb') as file:
                    for chunk in picture.chunks():
                        file.write(chunk)
            except Exception as e:
                return Response({"message": "Error occurred while saving the file"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            

            # get the server hostname 
            server_hostname = request.get_host()
            event.image_url = 'https://' + server_hostname + '/media/appuploads/' + filename

            image_source = request.data.get('image_source')
            if image_source:
                event.image_source = image_source

            #save the event
            event.save()

            return Response({
                "message": "Picture uploaded successfully",
                "event_id": str(event_id),
                "image_url": event.image_url
            }, status=status.HTTP_201_CREATED)
        else:
            logger.error("User not authenticated")
            return Response({"message": "User not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)


# the ViewSet doesnt have any commands implemented by default, 
# we will manually implement the POST command

class PictureUploadUserViewSet(viewsets.ViewSet):

    # get the parsers for the files, ususally the JSON parser is the default, here we want to get files
    parser_classes = (MultiPartParser,FormParser)

    # get the queryset of the events 
    queryset = Organization.objects.all()

    # this create method implements the POST command for the viewset
    @swagger_auto_schema(
        consumes=['multipart/form-data'], 
         manual_parameters=[
            Parameter(name="picture",
                            in_=openapi.IN_FORM,
                            type=openapi.TYPE_FILE,
                            required=False,
                            description="The picture file to upload"
                            ),
            Parameter(
                            name="Authorization",
                            in_=openapi.IN_HEADER,
                            type=openapi.TYPE_STRING,
                            required=False,
                            description="JWT token"
                            ),
            Parameter(
                            name="image_source",
                            in_=openapi.IN_FORM,
                            type=openapi.TYPE_STRING,
                            required=False,
                            description="Source of the image"
                            )
        ],
        responses={
            status.HTTP_201_CREATED: openapi.Response(
                description="Picture uploaded successfully",
                examples={
                    "application/json": {
                        "message": "Picture uploaded successfully",
                        "event_id": "123",
                        "image_url": "https://example.com/media/appuploads/your-uploaded-image.jpg"
                    }
                }
            ),
            status.HTTP_400_BAD_REQUEST: openapi.Response(
                description="Invalid request - missing picture, invalid file format, or missing event ID",
                examples={
                    "application/json": {"message": "No picture file present"}
                }
            ),
            status.HTTP_404_NOT_FOUND: openapi.Response(
                description="Event does not exist",
                examples={
                    "application/json": {"message": "Event does not exist"}
                }
            ),
            status.HTTP_500_INTERNAL_SERVER_ERROR: openapi.Response(
                description="Error occurred while saving the file",
                examples={
                    "application/json": {"message": "Error occurred while saving the file"}
                }
            )
        }
    )
    def upload_picture(self, request, id=None):

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

            # check if the request has a picture file
            if 'picture' not in request.FILES:
                image_source = request.data.get('image_source')
                if image_source:
                    organization = Organization.objects.get(related_user=user)
                    organization.image_source = image_source
                    organization.save()
                    return Response({
                        "message": "Image source updated successfully"
                    }, status=status.HTTP_201_CREATED)
                else:
                    return Response("No picture file present", status=status.HTTP_201_CREATED)
            
            # get the picture file from the request
            picture = request.FILES['picture']

            # check if the file is an image of any type
            try:
                # open the file using PIL
                img = Image.open(picture)
                # check if the file format is supported by PIL
                supported_formats = ['JPEG', 'PNG', 'GIF', 'JPG', 'jpeg', 'png', 'gif', 'jpg']
                if img.format not in supported_formats:
                    return Response({"message": "Invalid file format"}, status=status.HTTP_400_BAD_REQUEST)
            except IOError:
                return Response({"message": "Invalid image file"}, status=status.HTTP_400_BAD_REQUEST)

            # generate a unique filename using UUID
            filename = str(uuid.uuid4()) 

            # get the file extension of the picture.name and make it lowercase
            file_extension = picture.name.split('.')[-1].lower()

            # if the file extension is not empty, add a dot before the extension
            filename = filename + '.' + file_extension

            # construct the file path with the unique filename
            file_path = '/home/molonews/molonews/www/media/' + filename 
            try:
                with open(file_path, 'wb') as file:
                    for chunk in picture.chunks():
                        file.write(chunk)
            except Exception as e:
                return Response({"message": "Error occurred while saving the file"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # get organization of user
            organization = Organization.objects.get(related_user=user)

            # get the server hostname 
            server_hostname = request.get_host()
            organization.image = filename
            image_url = 'https://' + server_hostname + '/media/' + filename

            image_source = request.data.get('image_source')
            if image_source:
                organization.image_source = image_source

            #save the organization
            organization.save()

            # update default images of the source
            source = Source.objects.get(related_user=user)
            source.default_image  = '/' + filename
            source.default_image_detail = '/' + filename
            source.save()

            return Response({
                "message": "Picture uploaded successfully",
                "image_url": image_url
            }, status=status.HTTP_201_CREATED)
        
        else:
            return Response({"message": "User not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)
