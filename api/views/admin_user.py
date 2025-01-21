from django.http import HttpResponse
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import viewsets, serializers, filters, generics
from drf_yasg.utils import swagger_auto_schema, swagger_serializer_method
import django_filters
from rest_framework.response import Response
from .util import MoloVersioning, bad_request, choices_parameter, header_string_parameter, string_parameter
from django.shortcuts import get_object_or_404, redirect
from logging import getLogger
from content.models import User, Organization, Source, Category, AppUser, Area
from rest_framework import status
from drf_yasg import openapi
from django.contrib.auth.models import Group
import smtplib
from email.mime.text import MIMEText
import uuid
import jwt
from django.conf import settings
from django.db import transaction
from rest_framework.decorators import action
from rest_framework_simplejwt.views import TokenObtainPairView, TokenVerifyView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenVerifySerializer, TokenRefreshSerializer

logger = getLogger(__name__)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'password']
        extra_kwargs = {'password': {'write_only': True}}

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['street', 'zip', 'town', 'description' ]

class AreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Area
        fields = ['id', 'name']
        ref_name = "areas" 

def add_organization_to_appusers(organization):
        try:
            # Alle AppUser holen
            app_users = AppUser.objects.all()
            
            # Viele-zu-Viele-Beziehung effizient in einem Schritt hinzufügen
            # M2M-Through-Modell nutzen, um die Organisation mit AppUsern zu verknüpfen
            app_user_org_mappings = [
                AppUser.organization.through(appuser_id=app_user.id, organization_id=organization.id)
                for app_user in app_users
            ]
            
            # Bulk-Erstellung der M2M-Beziehungen
            with transaction.atomic():  # Datenbank-Transaktion, um alles zusammen auszuführen
                AppUser.organization.through.objects.bulk_create(app_user_org_mappings, ignore_conflicts=True)
            
            logger.info(f"Organisation {organization.name} erfolgreich zu allen AppUsern hinzugefügt.")
        
        except Exception as e:
            logger.error(f"Fehler beim Hinzufügen der Organisation zu AppUsern: {str(e)}")

class UserGetSerializer(serializers.ModelSerializer):
    town = serializers.SerializerMethodField()
    street = serializers.SerializerMethodField()
    zip = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    picture = serializers.SerializerMethodField()
    image_source = serializers.SerializerMethodField()
    homepage = serializers.SerializerMethodField()
    area = AreaSerializer(many=False, read_only=True)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'description', 'picture', 'image_source','email', 'homepage', 'phone', 'display_name', 'area', 'town', 'street', 'zip' ]
    
    def get_town(self, obj):
        organization = Organization.objects.get(related_user=obj)
        return organization.town if organization else None
    
    def get_street(self, obj):
        organization = Organization.objects.get(related_user=obj)
        return organization.street if organization else None
    
    def get_zip(self, obj):
        organization = Organization.objects.get(related_user=obj)
        return organization.zip if organization else None
    
    def get_description(self, obj):
        organization = Organization.objects.get(related_user=obj)
        return organization.description if organization else None
    
    def get_picture(self, obj):
        organization = Organization.objects.get(related_user=obj)
        return organization.image if organization else None
    
    def get_image_source(self, obj):
        organization = Organization.objects.get(related_user=obj)
        return organization.image_source if organization else None
    
    def get_homepage(self, obj):
        organization = Organization.objects.get(related_user=obj)
        return organization.homepage if organization else None
    
    

class AdminUserViewSet(viewsets.ViewSet):
    queryset = User.objects.all()

    # create a new admin user
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING),
                'first_name': openapi.Schema(type=openapi.TYPE_STRING),
                'last_name': openapi.Schema(type=openapi.TYPE_STRING),
                'phone': openapi.Schema(type=openapi.TYPE_STRING),
                'email': openapi.Schema(type=openapi.TYPE_STRING),
                'password': openapi.Schema(type=openapi.TYPE_STRING),
                'display_name': openapi.Schema(type=openapi.TYPE_STRING),
                'street': openapi.Schema(type=openapi.TYPE_STRING),
                'zip': openapi.Schema(type=openapi.TYPE_STRING),
                'town': openapi.Schema(type=openapi.TYPE_STRING),
                'area': openapi.Schema(type=openapi.TYPE_INTEGER),
            }
        ),
         manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={
            status.HTTP_204_NO_CONTENT: "User created successfully",
            status.HTTP_400_BAD_REQUEST: "Invalid data provided"
        }
    )
    def create(self, request):

        try:
            with transaction.atomic():
                # Benutzer erstellen
                user = User()
                if 'username' in request.data:
                    user.username = request.data['username']
                    # replace all spaces in the username with underscores
                    user.username = user.username.replace(" ", "_")
                    # remove all whitespaces at the beginning and end of user.username
                    user.username = user.username.strip()

                else:
                    logger.error("Username is required")
                    return Response(data={"message": "Username is required"}, status=status.HTTP_400_BAD_REQUEST)

                if 'first_name' in request.data:
                    user.first_name = request.data['first_name']

                if 'last_name' in request.data:
                    user.last_name = request.data['last_name']

                if 'display_name' in request.data:
                    display_name = request.data['display_name']
                    if not display_name:
                        logger.error("Empty display_name")
                        return Response(data={"message": "Empty display_name"}, status=status.HTTP_400_BAD_REQUEST)
                    
                    if User.objects.filter(display_name=display_name).exclude(username=request.data['username']).exists():
                        logger.error("User display name already exists")
                        return Response(data={"message": "User display name already exists"}, status=status.HTTP_400_BAD_REQUEST)
                    user.display_name = display_name
                else:
                    logger.error("display name is required")
                    return Response(data={"message": "Display name is required"}, status=status.HTTP_400_BAD_REQUEST)

                if 'email' in request.data:
                    if User.objects.filter(email=request.data['email']).exists():
                        logger.error("Email address already taken")
                        return Response(data={"message": "Email address already taken"}, status=status.HTTP_400_BAD_REQUEST)
                    user.email = request.data['email']
                else:
                    return Response(data={"message": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

                if 'phone' in request.data:
                    user.phone = request.data['phone']
                else:
                    user.phone = ""

                if 'password' in request.data:
                    user.set_password(request.data['password'])
                else:
                    return Response(data={"message": "Password is required"}, status=status.HTTP_400_BAD_REQUEST)

                user.is_staff = True
                user.is_superuser = False
                user.can_publish = True
                user.is_active = False
                user.activation_key = uuid.uuid4()

                user.save()

                # Bereich (Area) zuweisen
                if 'area' in request.data:
                    try:
                        area = Area.objects.get(id=request.data['area'])
                        user.area.clear()
                        user.area.add(area)
                    except Area.DoesNotExist:
                        logger.error("invalid area id")
                        return Response(data={"message": "Invalid area ID"}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    app_device_id = request.headers.get('X-Device-ID')
                    try:
                        app_user = AppUser.objects.get(device_id=app_device_id)
                        user.area.add(app_user.area)
                    except:
                        user.area.add(3)
                
                # Gruppe zuweisen
                group = Group.objects.get(name="Contributors")
                user.groups.add(group)
                user.save()

                # Organisation erstellen und Benutzer zuweisen
                organization = Organization()
                organization.related_user = user
                organization.name = display_name
                organization.title = display_name

                if 'street' in request.data:
                    organization.street = request.data['street']
                else:
                    organization.street = ""

                if 'zip' in request.data:
                    organization.zip = request.data['zip']
                else:
                    organization.zip = ""

                if 'town' in request.data:
                    organization.town = request.data['town']
                else:
                    organization.town = ""
                organization.type = "collective"
                organization.active = True
                organization.description = ""
                organization.homepage = ""
                organization.image_source = ""
                organization.image = ""
                organization.save()

                if 'area' in request.data:
                    organization.area.clear()
                    organization.area.add(area)
                else:
                    try:
                        organization.area.add(app_user.area)
                    except AppUser.DoesNotExist:
                        organization.area.add(3)

                organization.save()
                """
                Fügt die gegebene Organisation zu allen bestehenden AppUsern hinzu.
                """
                add_organization_to_appusers(organization)
                # Quelle erstellen und Benutzer zuweisen
                source = Source()
                source.related_user = user
                source.name = display_name
                source.type = "local"
                source.active = True
                source.default_category = Category.objects.get(id=1)
                source.organization = organization
                source.save()

                # Quelle zu Benutzer hinzufügen
                user.sources.add(source)
                user.save()
                if 'area' in request.data:
                    source.area.clear()
                    source.area.add(area)
                else:
                    try:
                        source.area.add(app_user.area)
                    except AppUser.DoesNotExist:
                        source.area.add(3)
                source.save()

                # Bestätigungs-E-Mail senden
                sender_email = settings.MAIL_SENDING['DEFAULT_FROM_EMAIL']
                mail_activation_url = settings.MAIL_SENDING['ACTIVATION_URL']
                receiver_email = request.data['email']
                subject = 'Bestätigungsmail'
                message = (
                    f'<html><body>'
                    f'<p>Liebe(r) {user.first_name} {user.last_name},</p>'
                    f'<p>bitte bestätigen Sie Ihre E-Mail-Adresse.</p>'
                    f'<p>Klicken Sie auf den folgenden Link, um Ihre E-Mail-Adresse zu bestätigen:</p>'
                    f'<p><a href="{mail_activation_url}/?token={user.activation_key}">E-Mail bestätigen</a></p>'
                    f'</body></html>'
                )
  
                email = MIMEText(message, 'html')
                email['Subject'] = subject
                email['From'] = sender_email
                email['To'] = receiver_email

                with smtplib.SMTP(settings.MAIL_SENDING['EMAIL_HOST'], settings.MAIL_SENDING['EMAIL_PORT']) as server:
                    server.starttls()
                    server.login(settings.MAIL_SENDING['EMAIL_HOST_USER'], settings.MAIL_SENDING['EMAIL_HOST_PASSWORD'])
                    server.sendmail(sender_email, receiver_email, email.as_string())
                    logger.error(email.as_string())

        except Exception as e:
            logger.error(f"Error during user creation: {str(e)}")
            return Response(data={"message": f"Error creating user or related entities: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)


    # update an existing user
    @swagger_auto_schema(
        operation_description='Update a molo user',
        manual_parameters=[
            header_string_parameter("Authorization", "JWT token", required=True),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING),
                'first_name': openapi.Schema(type=openapi.TYPE_STRING),
                'last_name': openapi.Schema(type=openapi.TYPE_STRING),
                'phone': openapi.Schema(type=openapi.TYPE_STRING),
                'email': openapi.Schema(type=openapi.TYPE_STRING),
                'homepage': openapi.Schema(type=openapi.TYPE_STRING),
                'area': openapi.Schema(type=openapi.TYPE_INTEGER),
                'display_name': openapi.Schema(type=openapi.TYPE_STRING),
                'description': openapi.Schema(type=openapi.TYPE_STRING),
                'street': openapi.Schema(type=openapi.TYPE_STRING),
                'zip': openapi.Schema(type=openapi.TYPE_STRING),
                'town': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),

        responses={
            status.HTTP_204_NO_CONTENT: "User updated successfully",
            status.HTTP_400_BAD_REQUEST: "Invalid data provided",
            status.HTTP_401_UNAUTHORIZED: "Unauthorized"
        }
    )
    def update_user(self, request):
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

        if not user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            with transaction.atomic():
                # Update User Details
                if 'username' in request.data:
                    user.username = request.data['username']
                if 'first_name' in request.data:
                    user.first_name = request.data['first_name']
                if 'last_name' in request.data:
                    user.last_name = request.data['last_name']
                if 'display_name' in request.data:
                    new_display_name = request.data['display_name']
                    if User.objects.filter(display_name=new_display_name).exclude(id=user.id).exists():
                        return Response(data={"message": "User display name already exists"}, status=status.HTTP_400_BAD_REQUEST)
                    if new_display_name.strip():
                        user.display_name = new_display_name

                if 'email' in request.data and User.objects.filter(email=request.data['email']).exclude(id=user.id).exists():
                    return Response(data={"message": "Email address already taken"}, status=status.HTTP_400_BAD_REQUEST)
                if 'email' in request.data:
                    user.email = request.data['email']
                if 'phone' in request.data:
                    user.phone = request.data['phone']
                if 'area' in request.data:
                    try:
                        area = Area.objects.get(id=request.data['area'])
                        user.area.clear()
                        user.area.add(area)
                    except Area.DoesNotExist:
                        return Response(data={"message": "Invalid area ID"}, status=status.HTTP_400_BAD_REQUEST)

                user.save()

                # Update Organization Details
                organization = Organization.objects.filter(related_user=user).first()
                if organization:
                    if 'display_name' in request.data:
                        if new_display_name.strip():
                            organization.name = new_display_name
                            organization.title = new_display_name
                    if 'street' in request.data:
                        organization.street = request.data['street']
                    if 'zip' in request.data:
                        organization.zip = request.data['zip']
                    if 'description' in request.data:
                        organization.description = request.data['description']
                    if 'town' in request.data:
                        organization.town = request.data['town']
                    if 'area' in request.data:
                        organization.area.clear()
                        organization.area.add(area)
                    if 'homepage' in request.data:
                        new_homepage = request.data['homepage']
                        if new_homepage.strip():
                            organization.homepage = new_homepage
                    organization.save()

                # Update Source Details
                source = Source.objects.filter(related_user=user).first()
                if source:
                    if 'display_name' in request.data:
                        if new_display_name.strip():
                            source.name = new_display_name
                    if 'area' in request.data:
                        source.area.clear()
                        source.area.add(area)
                    source.organization = organization
                    source.save()

        except Exception as e:
            return Response(data={"message": f"Error updating user or related entities: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)


    # method to activate a user
    @swagger_auto_schema(
        operation_description='Activate a user',
        manual_parameters=[
            string_parameter("token", "Activation token", required=True),
        ],
        responses={
            status.HTTP_200_OK: "User activated successfully",
            status.HTTP_400_BAD_REQUEST: "Invalid token provided",
            status.HTTP_404_NOT_FOUND: "User not found"
        }
    )
    def activate_user(self, request):
        # get the activation token from the request
        token = request.GET.get('token')

        if not token:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        
        # find the user with the matching activation token
        try:
            user = User.objects.get(activation_key=token)# create user
        except:
            html = """
            <html>
            <head>
            </head>
            <body>
            Das Konto ist bereits aktiviert.</br>
            <a href="molonews://already-activated">zur App</a>
            </body>
            </html>
            """
            return HttpResponse(html)
        
        # activate the user
        user.is_active = True
        # remove the activation key
        user.activation_key = None
        user.save()

        html = """
        <html>
        <head>
            <meta http-equiv="refresh" content="0; url=molonews://activate" />
        </head>
        <body>
        Das Konto wurde erfolgreich aktiviert.</br>
        </body>
        </html>
        """
        return HttpResponse(html)

    # method to delete a user
    @swagger_auto_schema(
        operation_description='Delete an admin user',
        manual_parameters=[
            header_string_parameter("Authorization", "JWT token", required=True),
        ],
        responses={
            status.HTTP_204_NO_CONTENT: "User deleted successfully",
            status.HTTP_404_NOT_FOUND: "User not found"
        }
    )
    def delete_user(self, request):
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

        if not user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            with transaction.atomic():
                # Lösche alle Organisationen, die mit dem Benutzer verknüpft sind
                organizations = Organization.objects.filter(related_user=user)
                for organization in organizations:
                    organization.delete()

                # Lösche alle Quellen, die mit dem Benutzer verknüpft sind
                sources = Source.objects.filter(related_user=user)
                for source in sources:
                    source.delete()

                # Lösche den Benutzer
                user.delete()

        except Exception as e:
            logger.error(f"Error deleting user or related entities: {str(e)}")
            return Response(data={"message": f"Error deleting user or related entities: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)
  

    @swagger_auto_schema(
        operation_description='Change user password',
        manual_parameters=[
            header_string_parameter("Authorization", "JWT token", required=True),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'new_password': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={
            status.HTTP_200_OK: "Password changed successfully",
            status.HTTP_400_BAD_REQUEST: "Invalid data provided",
            status.HTTP_401_UNAUTHORIZED: "Unauthorized",
            status.HTTP_404_NOT_FOUND: "User not found"
        }
    )
    def change_password(self, request):
       
        # get the user from the token
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

        # only delete the user if the user is authenticated
        if user.is_authenticated:
            # get the new password from the request
            new_password = request.data.get('new_password')

            if not new_password:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            # create password hash
            user.set_password(new_password)
            user.save() 
        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


        return Response(status=status.HTTP_200_OK)


    # this method is used to reset the password of a user 
    # using a token provided in a reset email
    @swagger_auto_schema(
        operation_description='Change user password based on reset token',
        manual_parameters=[
            header_string_parameter("Authorization", "Reset token", required=True),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'new_password': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={
            status.HTTP_204_NO_CONTENT: "Password reset successful",
            status.HTTP_400_BAD_REQUEST: "Invalid data provided",
            status.HTTP_401_UNAUTHORIZED: "Unauthorized",
        }
    )
    def reset_password_with_token(self, request, *args, **kwargs):
       
        # get the user from the token
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return Response({"detail": "Authorization header missing."}, status=status.HTTP_401_UNAUTHORIZED)

        token = auth_header

        try:
            user = User.objects.get(password_reset_token=token)
        except User.DoesNotExist:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        # only delete the user if the user is authenticated
        try:
            # get the new password from the request
            new_password = request.data.get('new_password')

            if not new_password:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            # create password hash
            user.set_password(new_password)
            user.password_reset_token = None
            user.save() 
        except:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)



    # method to get user data
    @swagger_auto_schema(
        operation_description='Get user data',
        manual_parameters=[
            header_string_parameter("Authorization", "JWT token", required=True),
        ],
        responses={
            200: UserGetSerializer,
            401: "Unauthorized",
            404: "User not found",
        },
    )
    def get_user_details(self, request):
         # get the user from the token
         
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return Response({"detail": "Authorization header missing."}, status=status.HTTP_401_UNAUTHORIZED)

        token = auth_header

        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get('user_id')

            logger.error (user_id)

            if not user_id:
                return Response({"detail": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)
            user = get_object_or_404(User, id=user_id)

        except jwt.ExpiredSignatureError:
            return Response({"detail": "Token has expired."}, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError:
            return Response({"detail": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)

        # only delete the user if the user is authenticated
        if user.is_authenticated:

            try:
                organization = Organization.objects.get(related_user=user)
            except:
                logger.error("Organization not found")
                return Response(status=status.HTTP_404_NOT_FOUND)

            # get the picture url and image source from the organization db if it exists
            try:
                picture = str(organization.image)
                image_source = str(organization.image_source)
                homepage = str(organization.homepage)
                server_hostname = request.get_host()
                picture_url = 'https://' + server_hostname + '/media/' + picture
            except: 
                picture = None
                image_source = None

            data = {
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'description': organization.description,
                'phone': user.phone,
                'email': user.email,
                'homepage': homepage,
                'display_name': str(user.display_name),
                'picture': picture_url,
                'image_source': image_source,
                'street': organization.street,
                'zip': organization.zip,
                'town': organization.town,
            }

            areas = user.area.all()
            # create an area object containing the first area of the user
            for area in areas:            
                area_list = {'id': area.id, 'name': area.name} 
                break
            
            # add the area_list to the data
            data['area'] = area_list

            return Response(data, status=status.HTTP_200_OK)
            
        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        

    @swagger_auto_schema(
        operation_description='Redirect user into app and reset password with token',
        manual_parameters=[
            string_parameter("token", "Reset token", required=True),
        ],
        responses={
            status.HTTP_302_FOUND: "Redirect to app",
            status.HTTP_400_BAD_REQUEST: "Token missing",
        }
    )
    def redirect_user_into_app(self, request):
        # get token from url
        token = request.GET.get('token')
        if not token:
            return Response({"detail": "Token missing"}, status=status.HTTP_400_BAD_REQUEST)
        link = settings.MAIL_SENDING['PASSWORD_RESET_URL'] + '?token=' + token

        # create a html redirect using javascript and also put a link into the html body
        html = """
                <html>
                <head>
                    <meta http-equiv="refresh" content="0; url=""" + link + """">
                </head>
                <body>
                <a href='""" + link + """'>Klicke hier um dein Passwort zurückzusetzen. Dieser Link muss auf dem Smartphone geöffnet werden 
                auf dem die molo.news App installiert ist.</a>
                
                <script>
                    window.location.href = '""" + link + """';
                </script>
                </body>
                </html>
             """
        
        return HttpResponse(html)


    @swagger_auto_schema(
        operation_description='Reset password',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={
            status.HTTP_204_NO_CONTENT: "No Content",
            status.HTTP_404_NOT_FOUND: "Email not found",
        }
    )
    def request_password_reset(self, request):
        email = request.data.get('email')

        # Check if the email exists in the database
        if not User.objects.filter(email=email).exists():
            return Response({"detail": "Email not found"}, status=status.HTTP_404_NOT_FOUND)

        # Generate a random password reset token
        token = str(uuid.uuid4())

        # Save the token in the user's database record
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(data={"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # save the token in the user's database record
        user.password_reset_token = token
        # save the changes
        user.save()

        try:
            # Send confirmation email
            sender_email = settings.MAIL_SENDING['DEFAULT_FROM_EMAIL']
            receiver_email = email
            subject = 'Passwort zurücksetzen'
            message = '<html><body>'
            message += f'<p>Liebe(r) {user.first_name} {user.last_name}, </p>'
            message += '<p>klicke auf den folgenden Link auf deinem Smartphone, um dein Passwort in der molo-App zurückzusetzen:</p>'
            
            server_url = request.build_absolute_uri('/')[:-1]
            link = server_url + settings.MAIL_SENDING['REDIRECT_AFTER_PASSWORD_RESET_REQUEST_PATH'] + '?token=' + token
            message += '<p><a href="' + link +  '">Passwort zurücksetzen</a></p>'
            message += '</body></html>'

            
            # Create a MIMEText object with the email content
            email = MIMEText(message, 'html')
            email['Subject'] = subject
            email['From'] = sender_email
            email['To'] = receiver_email
            
            # Connect to the SMTP server and send the email
            with smtplib.SMTP(settings.MAIL_SENDING['EMAIL_HOST'], settings.MAIL_SENDING['EMAIL_PORT']) as server:
                server.starttls()
                server.login(settings.MAIL_SENDING['EMAIL_HOST_USER'], settings.MAIL_SENDING['EMAIL_HOST_PASSWORD'])
                server.sendmail(sender_email, receiver_email, email.as_string())

        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)
        

# Custom TokenObtainPairSerializer to add user_id to the token
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    # add user_id to the token
    def validate(self, attrs):
        username = attrs.get("username", None)
        password = attrs.get("password", None)

        if not username or not password:
            raise serializers.ValidationError('Username/email and password are required.')

        # Try to get the user using the username
        try:
            user = User.objects.get(username=username)
            logger.error(username)
        except User.DoesNotExist:
            # Try to get the user using the email if username not found
            try:
                user = User.objects.get(email=username)
                logger.error ("checking email as username")
            except User.DoesNotExist:
                raise serializers.ValidationError('No active account found with the given credentials')

        if user and user.check_password(password):
            attrs['username'] = user.username
        else:
            raise serializers.ValidationError('No active account found with the given credentials')
        
        # get the token from the request
        data = super().validate(attrs)
        # get the token from the data
        token = data.get('access')#

        # get the user_id from the token
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get('user_id')
            if not user_id:
                return Response({"detail": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.ExpiredSignatureError:
            return Response({"detail": "Token has expired."}, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError:
            return Response({"detail": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)    
       
        # add user_id to the token
        data['user_id'] = user_id

        return data


# Custom TokenObtainPairView to use the custom serializer
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    class TokenResponse(serializers.Serializer):
        refresh = serializers.CharField()
        access = serializers.CharField()
        user_id = serializers.IntegerField()

    @swagger_auto_schema(
        operation_description='Obtain a JWT token',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING),
                'password': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={
            status.HTTP_200_OK: TokenResponse,
            status.HTTP_400_BAD_REQUEST: "Invalid credentials",
        }
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
    

class CustomTokenVerifyView(TokenVerifyView):
    serializer_class = TokenVerifySerializer

    class TokenResponse(serializers.Serializer):
        token = serializers.CharField()

    @swagger_auto_schema(
        operation_description='Verify a JWT token',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'token': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={
            status.HTTP_201_CREATED: "Token verified successfully",
            status.HTTP_400_BAD_REQUEST: "Invalid token",
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            return Response({"message": "Token verified successfully", "token": request.data["token"]}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"message": "Token verification failed"}, status=status.HTTP_400_BAD_REQUEST)

