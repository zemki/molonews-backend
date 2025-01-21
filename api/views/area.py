from rest_framework import viewsets, serializers, filters, generics
from drf_yasg.utils import swagger_auto_schema, swagger_serializer_method
from django.conf import settings
from math import acos, sin, cos, radians
import django_filters
from rest_framework.response import Response
from rest_framework import status
from .util import MoloVersioning, bad_request, choices_parameter, header_string_parameter, string_parameter
from content.models import Area, AppUser, User, Article, Source
from django.shortcuts import get_object_or_404
from logging import getLogger
import jwt
from drf_yasg import openapi
from django.utils import timezone

logger = getLogger(__name__)

from math import radians, sin, cos, acos

def calculate_distance(lon1, lat1, lon2, lat2):
    """
    Calculate the distance between two points on the Earth's surface using the Haversine formula.
    https://stackoverflow.com/questions/69644740/filter-users-within-a-given-distance-in-django-rest-framework

    Parameters:
    lon1 (float): The longitude of the first point in degrees.
    lat1 (float): The latitude of the first point in degrees.
    lon2 (float): The longitude of the second point in degrees.
    lat2 (float): The latitude of the second point in degrees.

    Returns:
    float: The distance between the two points in kilometers.
    """
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    return 6371 * (
        acos(sin(lat1) * sin(lat2) + cos(lat1) * cos(lat2) * cos(lon1 - lon2))
    )

class AreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Area
        fields = (
            'id',
            'name',
            'longitude',
            'latitude',
        )

class ListAreaSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = AreaSerializer(many=True)

class AreaViewSet(viewsets.ViewSet):

    queryset = Area.objects.all()
    serializer_class = AreaSerializer

    @swagger_auto_schema(
        operation_description='Get locations where molo.news is available',
        manual_parameters=[string_parameter('area', ''), string_parameter('longitude', ''), string_parameter('latitude', '') ],
        responses={200: ListAreaSerializer(), 400: 'Device ID does not exist'},
    )
    def list(self, request, *args, **kwargs):
        
        arealist = list(self.queryset)
        data = self.request.GET.dict()

        try:
            longitude = float(data['longitude'])
            latitude = float(data['latitude'])
        except:
            longitude = ""
            latitude = ""

        try:
            area_name = data['area']
        except:
            area_name = 0

        calculated_distance = False

        if longitude and latitude:
            # add all distances into List
            for item in arealist:
                item.distance = calculate_distance(lon1=longitude, lat1=latitude, lon2=item.longitude, lat2=item.latitude)    

            # order the list by distance
            def sortFn(value):
                return value.distance
            arealist.sort(key=sortFn)
            # store that a calculation of the distance has happened
            # the result of this is preferred over the search field
            calculated_distance = True
            
        # if only the area name is provided

        if calculated_distance == False and isinstance(area_name, str) == True: 
            # check if its in the list
            # if its in the list only return the requested item
            # otherwise leave the list untouched and return it in complete
            arealist_temp = arealist.copy()
            arealist_temp.clear()

            for item in arealist:
                if area_name.lower() in item.name.lower():
                    arealist_temp.append(item)
            
            arealist = arealist_temp

        serializer = AreaSerializer(arealist, many=True)
    
        return Response({
            'count': len(arealist),
            'results': serializer.data
        })  

    @swagger_auto_schema(
        operation_description='Create a new location where molo.news is available',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'area': openapi.Schema(type=openapi.TYPE_STRING, description='Name of the area'),
                'longitude': openapi.Schema(type=openapi.TYPE_NUMBER, description='Longitude of the area'),
                'latitude': openapi.Schema(type=openapi.TYPE_NUMBER, description='Latitude of the area'),
                'zip_code': openapi.Schema(type=openapi.TYPE_STRING, description='Zip code of the area'),
            },
            required=['area', 'longitude', 'latitude', 'zip_code'],
        ),
        responses={
            201: 'Created',
            400: 'Bad Request',
            401: 'Unauthorized',
            409: 'Conflict - Area already exists',
        },
    )

    def create(self, request, *args, **kwargs):
        data = request.data

        # Replace commas with dots if longitude/latitude are provided as strings
        if isinstance(data.get('longitude'), str):
            data['longitude'] = data['longitude'].replace(',', '.')
        if isinstance(data.get('latitude'), str):
            data['latitude'] = data['latitude'].replace(',', '.')

        # Safely convert longitude/latitude to floats
        try:
            longitude = float(data['longitude'])
            latitude = float(data['latitude'])
        except (TypeError, ValueError) as e:
            logger.error("An error occurred while converting longitude/latitude to float: %s", e)
            return bad_request("Longitude or latitude format is invalid.")

        # Extract the remaining required fields
        try:
            area_name = data['area']
            zip_code = data['zip_code']
        except KeyError:
            # If any of these keys are missing in the incoming JSON
            logger.error("An error occurred: missing one of the required keys (area, zip_code).")
            return bad_request('Bad Request')

        # Validate area_name, zip_code, and make sure float conversion didn't yield None
        # (which shouldn't happen, but good to be safe).
        if area_name is None or zip_code is None or longitude is None or latitude is None:
            logger.error("Missing required fields. One of area, longitude, latitude, or zip_code is None.")
            return bad_request('Bad Request')

        # Disallow empty strings for area_name or zip_code if that’s your requirement
        if not area_name.strip() or not zip_code.strip():
            logger.error("An error occurred: area or zip_code is an empty string.")
            return bad_request('Bad Request')

        # At this point, zero is allowed as a valid coordinate if that’s intended.
        # We only bail if they’re missing, which we’ve already checked.

        # Check if the area already exists
        try:
            Area.objects.get(name=area_name)
            return Response({"detail": "Area already exists."}, status=status.HTTP_409_CONFLICT)
        except Area.DoesNotExist:
            pass
        except Exception as e:
            logger.error("An unexpected error occurred while checking if area exists: %s", e)
            return Response({"detail": "An error occurred while creating the area."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # If we’re here, the area does not exist; create it
        try:
            area = Area.objects.create(
                name=area_name,
                longitude=longitude,
                latitude=latitude,
                zip=zip_code
            )

            # Assign the new area to all admin (superuser) accounts
            admin_users = User.objects.filter(is_superuser=True)
            for admin_user in admin_users:
                admin_user.area.add(area)

            # Attempt to load the known Source
            try:
                source = Source.objects.get(name="molo.redaktion Quelle")
            except Source.DoesNotExist:
                source = None  # Fallback

            # Build your welcome message abstract
            try:
                abstract = (
                    "<p>Du möchtest Infos aus <strong>"
                    + str(area.name)
                    + "</strong> lesen? Dann hast du jetzt die Möglichkeit, "
                    "eine*r der Ersten zu sein und selber Infos zu veröffentlichen.</p>"
                    "<p>Teile der Community mit, was hier los ist. Poste und veröffentliche "
                    "ganz einfach Infos und Veranstaltungen direkt hier in der App und weise "
                    "andere Menschen auf diese Möglichkeit hin. So wird die molo-Community in "
                    + "<strong>" + str(area.name) + "</strong> immer größer.</p>"
                    "<p>Bei Fragen oder Feedback, sende uns eine Nachricht an "
                    "kontakt@molo.news.</p>"
                    "<p>Viel Spaß beim Posten wünscht dir das molo-Team!</p>"
                )
            except Exception as e:
                logger.error("An error occurred while building the abstract: %s", e)
                abstract = ""

            # Create a welcome article for the new area
            try:
                new_article = Article.objects.create(
                    title="Willkommen bei molo!",
                    abstract=abstract,
                    link="",
                    date=timezone.now(),
                    moddate=timezone.now(),
                    source=source,
                    published=True,
                    up_for_review=False,
                    image=None,
                    image_source=None,
                    foreign_id=None,
                    image_url=None,
                )
                new_article.area.add(area)
                # Add a known “welcome” tag; adjust `19` to whatever your tag ID is
                new_article.tags.add(19)
                new_article.save()
            except Exception as e:
                logger.error("An error occurred while creating the welcome article: %s", e)

            return Response({"detail": "Area created successfully."},
                            status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error("An error occurred while creating the area or assigning users: %s", e)
            return Response({"detail": "An error occurred while creating the area."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    # get the closes area by longitude and latitude only as internal function
    def get_closest_area(self, longitude, latitude):
        arealist = list(self.queryset)
        for item in arealist:
            item.distance = calculate_distance(lon1=longitude, lat1=latitude, lon2=item.longitude, lat2=item.latitude)    

        # order the list by distance
        def sortFn(value):
            return value.distance
        arealist.sort(key=sortFn)
        return arealist[0]
    
    # destroy an area by id
    @swagger_auto_schema(
        operation_description='Delete a location where molo.news is available',
        responses={200: 'Deleted', 400: 'Bad Request'},
    )
    def destroy(self, request, *args, **kwargs):
        
        return bad_request('Not Implemented') 
    
        # The IP address allowed to access this method:
        ALLOWED_IP = "134.102.30.184"


        # Try to get the client IP from HTTP_X_FORWARDED_FOR first (if behind proxy),
        # otherwise fall back to REMOTE_ADDR.
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # Often x_forwarded_for is a comma-separated list of IPs
            # The "real" IP is usually the first one
            client_ip = x_forwarded_for.split(',')[0].strip()
        else:
            client_ip = request.META.get('REMOTE_ADDR')

        # Compare the client IP to the allowed IP
        if client_ip != ALLOWED_IP:
            # Log or handle unauthorized attempt
            logger.error(f"Unauthorized attempt to delete area from IP: {client_ip}")
            return bad_request("Access denied.")

        try:
            # Now proceed with your existing logic—only runs if IP check passed
            id = kwargs.get('pk')
            logger.error("Deleting area with id: " + str(id))
        except:
            return bad_request('Bad Request')

        try:
            area = Area.objects.get(id=id)
            logger.error("Deleting area with name: " + area.name)
            
            # Delete all articles associated with the area
            Article.objects.filter(area=area).delete()
            logger.error("Deleted all articles associated with the area")
            
            # Finally, delete the area itself
            area.delete()
            return Response("Deleted")
        except:
            return bad_request('Bad Request')

    
    # get the closest area by longitude and latitude as api endpoint
    @swagger_auto_schema(
        operation_description='Get the closest location where molo.news is available',
        manual_parameters=[string_parameter('longitude', ''), string_parameter('latitude', '') ],
        responses={200: AreaSerializer(), 400: 'Bad Request'},
    )   
    def closest(self, request, *args, **kwargs):
        data = request.GET.dict()

        try:
            longitude = float(data['longitude'])
            latitude = float(data['latitude'])
        except:
            return bad_request('Bad Request')

        area = self.get_closest_area(longitude, latitude)
        serializer = AreaSerializer(area)
        return Response(serializer.data)


