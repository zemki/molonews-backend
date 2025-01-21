from logging import getLogger
from rest_framework import status
from rest_framework import viewsets, serializers
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema, swagger_serializer_method

from .util import (
    choices_parameter,
    header_string_parameter,
    string_parameter,
    integer_parameter,
    number_parameter,
)
from content.choices import ORGANIZATION_TYPE_CHOICES
from content.models import AppUser, Tag, Organization, Category
from .category import CategoryTagsSerializer

logger = getLogger("molonews")


def bad_request(detail, return_status=status.HTTP_400_BAD_REQUEST):
    logger.error("Bad request: {}".format(detail))
    return Response({"detail": detail}, status=return_status)


class AppUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = AppUser
        fields = (
            "device_id",
            "firebase_token",
            "tags",
            "organizations",
            "organization_all_tags",
            "location_latitude",
            "location_longitude",
        )


class TagListSerializer(serializers.ModelSerializer):

    class Meta:
        model = AppUser
        fields = ("tags",)


class EventTagListSerializer(serializers.ModelSerializer):

    class Meta:
        model = AppUser
        fields = (
            "tags",
            "filter_events_by_source",
        )


class EventCategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "title",
            "description",
            "rank",
        )


class EventTagListGetSerializer(serializers.ModelSerializer):

    category = EventCategorySerializer(read_only=True)
    tags = CategoryTagsSerializer(read_only=True, many=True)

    class Meta:
        model = AppUser
        fields = (
            "tags",
            "category",
            "filter_events_by_source",
        )


class AppUserBaseViewSet(viewsets.GenericViewSet):

    queryset = AppUser.objects.all()
    serializer_class = None
    http_method_names = ["get", "post"]
    app_user = None

    def get_user(self, create=True):
        device_id = self.request.headers.get("X-Device-ID", None)
        if device_id is None:
            return None, bad_request("Device ID is missing")
        if create:
            app_user, created = AppUser.objects.get_or_create(device_id=device_id)
        else:
            try:
                app_user = AppUser.objects.get(device_id=device_id)
            except AppUser.DoesNotExist:
                return None, bad_request("Device ID does not exist")
        return app_user, None


class AppUserKnownViewSet(AppUserBaseViewSet):

    @swagger_auto_schema(
        operation_description="Is Device known?",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={200: "Device ID is known", 400: "Device ID does not exist"},
    )
    def list(self, request, *args, **kwargs):
        """

        Args:
            request (request): request object
            *args (args): additional args
            **kwargs (kwargs): additional kwargs

        Returns:
            Response
        """
        app_user, error_response = self.get_user(create=False)
        if error_response:
            return error_response
        return Response(status.HTTP_200_OK)


class AppUserTagViewSet(AppUserBaseViewSet):

    serializer_class = TagListSerializer
    tag_filter = [1, 2, 3, 4]
    queryset = Tag.objects.all()

    @swagger_auto_schema(
        operation_description="Set selected tags",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={200: "User Settings saved", 400: "Device ID is missing"},
        request_body=TagListSerializer,
    )
    def create(self, request, *args, **kwargs):
        """

        Args:
            request (request): request object
            *args (args): additional args
            **kwargs (kwargs): additional kwargs

        Returns:
            Response
        """
        app_user, error_response = self.get_user()
        if error_response:
            logger.error(error_response)
            return error_response

        # get user tags to see if some already exist or if the list is empty
        user_tags = app_user.tags.values()
        # if the user has no tags assigned then assign all tags
        if len(user_tags) == 0:
            # get all tags from db
            all_tags = Tag.objects.all().values()
            # add one tag after another to the user
            for tag in all_tags:
                app_user.tags.add(tag["id"])
            app_user.save()

        # get list of all organisations that the user requested
        user_organisations = app_user.organization.values()
        # if there is none the initial values need to be set
        if len(user_organisations) == 0:
            logger.error("user has no organisations")
            # get all organisations that are active from db
            all_organisations = Organization.objects.filter(active=True).values()
            # add all ids the the users list of organisations
            for org in all_organisations:
                app_user.organization.add(org["id"])
            app_user.save()

        data = self.request.data
        # get already selected tags not matching tag filter
        user_tags = [
            tag for tag in app_user.tags.exclude(category_id__in=self.tag_filter)
        ]
        _tags = data.get("tags", None)
        user_tags += [_tag for _tag in Tag.objects.filter(id__in=_tags)]
        app_user.tags.set(user_tags)
        if self.serializer_class == EventTagListSerializer:
            filter_events_by_source = data.get("filter_events_by_source", False)
            app_user.filter_events_by_source = filter_events_by_source
        app_user.save()

        return Response(status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Get selected tags",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={200: TagListSerializer, 400: "Device ID is missing"},
    )
    def list(self, request, *args, **kwargs):
        _filter_events_by_source = True
        app_user, error_response = self.get_user()
        if app_user:
            _filter_events_by_source = app_user.filter_events_by_source

        queryset = self.get_queryset().filter(category_id__in=self.tag_filter)
        serializer = None
        if self.serializer_class == TagListSerializer:
            serializer = TagListSerializer({"tags": queryset})
        elif self.serializer_class in [
            EventTagListSerializer,
            EventTagListGetSerializer,
        ]:
            # serializer = self.serializer_class({'tags': queryset, 'filter_events_by_source': _filter_events_by_source})
            serializer = self.serializer_class(
                {
                    "tags": queryset,
                    "category": Category.objects.get(id=2),
                    "filter_events_by_source": _filter_events_by_source,
                },
                context={"device_id": request.headers.get("X-Device-ID", None)},
            )
        if serializer:
            return Response(serializer.data)


class AppUserArticleTagViewSet(AppUserTagViewSet):
    tag_filter = [1, 3, 4]


class AppUserEventTagViewSet(AppUserTagViewSet):

    serializer_class = EventTagListSerializer
    tag_filter = [2]

    @swagger_auto_schema(
        operation_description="Set selected event tags",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={200: "User Settings saved", 400: "Device ID is missing"},
        request_body=EventTagListSerializer,
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_description="Get selected tags",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={200: EventTagListGetSerializer, 400: "Device ID is missing"},
    )
    def list(self, request, *args, **kwargs):
        self.serializer_class = EventTagListGetSerializer
        return super().list(request, *args, **kwargs)


def save_organizations(
    app_user, organization=None, organization_all_tags=None, organization_type=None
):

    # get the area id so it can be used for filtering the results
    app_user_vales = app_user.__dict__
    area_id = app_user_vales["area_id"]

    if (
        organization is None
        and organization_all_tags is None
        and organization_type is None
    ):
        app_user.organization.set(Organization.objects.all())
        app_user.deselected_organization_all_tags.set(Organization.objects.all())
    else:
        if organization_type:

            # get current selected orgs but exclude current organization_type
            # exclude them because the current organization type is being passed by the incoming variables

            # nach Themen - alle ausser aktueller typ
            selected_orgs = [
                org.id for org in app_user.organization.exclude(type=organization_type)
            ]
            # nach themen - nur aktuellen typ in anderen Gebieten
            selected_orgs_other_areas = [
                org.id
                for org in app_user.organization.filter(type=organization_type).exclude(
                    area=area_id
                )
            ]
            selected_orgs = selected_orgs + selected_orgs_other_areas

            # logger.error("sooa filtered")
            # logger.error (len(selected_orgs_other_areas))
            # logger.error(selected_orgs_other_areas)
            # logger.error("----")

            selected_orgs_all_tags = [
                org.id
                for org in app_user.organization_all_tags.exclude(
                    type=organization_type
                )
            ]
            selected_orgs_all_tags_other_areas = [
                org.id
                for org in app_user.organization_all_tags.filter(
                    type=organization_type
                ).exclude(area=area_id)
            ]
            selected_orgs_all_tags = (
                selected_orgs_all_tags + selected_orgs_all_tags_other_areas
            )

            organization = selected_orgs + organization
            organization_all_tags = selected_orgs_all_tags + organization_all_tags

        # old variant
        # check if can be removed
        app_user.organization.set(Organization.objects.filter(id__in=organization))
        app_user.deselected_organization.set(
            Organization.objects.exclude(id__in=organization)
        )

        app_user.organization_all_tags.set(
            Organization.objects.filter(id__in=organization_all_tags)
        )

        app_user.deselected_organization_all_tags.set(
            Organization.objects.exclude(id__in=organization_all_tags)
        )

    app_user.save()


class UserOrganizationsSerializer(serializers.ModelSerializer):

    class Meta:
        model = AppUser
        fields = (
            "organization",
            "organization_all_tags",
        )


class AppUserOrganizationsViewSet(AppUserBaseViewSet):

    @swagger_auto_schema(
        operation_description="Set selected organizations",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
            choices_parameter(
                "organization_type",
                ORGANIZATION_TYPE_CHOICES,
                "The type of an organization",
            ),
        ],
        responses={200: "User Settings saved", 400: "Device ID is missing"},
        request_body=UserOrganizationsSerializer,
    )
    def create(self, request, *args, **kwargs):
        """

        Args:
            request (request): request object
            *args (args): additional args
            **kwargs (kwargs): additional kwargs

        Returns:
            Response
        """
        app_user, error_response = self.get_user()
        if error_response:
            return error_response

        data = self.request.data

        _organization_type = request.query_params.get("organization_type", None)
        _organization = data.get("organization", None)
        _organization_all_tags = data.get("organization_all_tags", None)

        save_organizations(
            app_user, _organization, _organization_all_tags, _organization_type
        )

        return Response(status.HTTP_200_OK)


class UserLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppUser
        fields = (
            "location_latitude",
            "location_longitude",
            "area",
        )


class AppUserLocationViewSet(AppUserBaseViewSet):

    @swagger_auto_schema(
        operation_description="Get user location",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={200: UserLocationSerializer(), 400: "Device ID does not exist"},
    )
    def list(self, request, *args, **kwargs):
        """Get user location from db if exists.

        Args:
            request (request): request object
            *args (args): additional args
            **kwargs (kwargs): additional kwargs

        Returns:
            Response
        """
        app_user, error_response = self.get_user(create=True)
        if error_response:
            return error_response

            # get user tags to see if some already exist or if the list is empty
        user_tags = app_user.tags.values()
        # if the user has no tags assigned then assign all tags
        if len(user_tags) == 0:
            # get all tags from db
            all_tags = Tag.objects.all().values()
            # add one tag after another to the user
            for tag in all_tags:
                app_user.tags.add(tag["id"])

        # get list of all organisations that the user requested
        user_organisations = app_user.organization.values()
        # if there is none the initial values need to be set
        if len(user_organisations) == 0:
            logger.error("user has no organisations")
            # get all organisations that are active from db
            all_organisations = Organization.objects.filter(active=True).values()
            # add all ids the the users list of organisations
            for org in all_organisations:
                app_user.organization.add(org["id"])

        app_user.save()

        serializer = UserLocationSerializer(app_user)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Set user location",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={200: "User Settings saved", 400: "Device ID is missing"},
        request_body=UserLocationSerializer,
    )
    def create(self, request, *args, **kwargs):
        """Save user location to db.

        Args:
            request (request): request object
            *args (args): additional args
            **kwargs (kwargs): additional kwargs

        Returns:
            Response
        """
        app_user, error_response = self.get_user()
        if error_response:
            logger.error(error_response)
            return error_response

        data = self.request.data

        location_latitude = data.get("location_latitude", None)
        location_longitude = data.get("location_longitude", None)

        if isinstance(location_latitude, str):
            location_latitude = float(location_latitude)
        if isinstance(location_longitude, str):
            location_longitude = float(location_latitude)

        app_user.location_latitude = location_latitude
        app_user.location_longitude = location_longitude

        area_id = data.get("area", None)
        if isinstance(area_id, int) and area_id > 0:
            app_user.area_id = area_id

        # write out appuser id
        # logger.error (app_user.__dict__["id"])

        # get user tags to see if some already exist or if the list is empty
        user_tags = app_user.tags.values()
        # if the user has no tags assigned then assign all tags
        if len(user_tags) == 0:
            # get all tags from db
            all_tags = Tag.objects.all().values()
            # add one tag after another to the user
            for tag in all_tags:
                app_user.tags.add(tag["id"])

        # get list of all organisations that the user requested
        user_organisations = app_user.organization.values()
        # if there is none the initial values need to be set
        if len(user_organisations) == 0:
            logger.error("user has no organisations")
            # get all organisations that are active from db
            all_organisations = Organization.objects.filter(active=True).values()
            # add all ids the the users list of organisations
            for org in all_organisations:
                try:
                    app_user.organization.add(org["id"])
                except Exception as e:
                    logger.error(e)

        app_user.save()

        return Response(status.HTTP_200_OK)


PUSH_SETTINGS_FIELDS = [
    "firebase_token",
    "push_news",
    "push_collective",
    "push_official",
]


class UserPushSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppUser
        fields = PUSH_SETTINGS_FIELDS


class AppUserPushViewSet(AppUserBaseViewSet):

    @swagger_auto_schema(
        operation_description="Get user push settings",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True)
        ],
        responses={200: UserPushSerializer(), 400: "Device ID does not exist"},
    )
    def list(self, request, *args, **kwargs):
        """Return push settings of user if exists in db.

        Args:
            request (request): request object
            *args (args): additional args
            **kwargs (kwargs): additional kwargs

        Returns:
            Response
        """
        app_user, error_response = self.get_user(create=False)
        if error_response:
            return error_response

        serializer = UserPushSerializer(app_user)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Set user push settings",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={200: "User Settings saved", 400: "Device ID is missing"},
        request_body=UserPushSerializer,
    )
    def create(self, request, *args, **kwargs):
        """Save user push settings to db.

        Args:
            request (request): request object
            *args (args): additional args
            **kwargs (kwargs): additional kwargs

        Returns:
            Response
        """
        app_user, error_response = self.get_user()
        if error_response:
            return error_response

        data = self.request.data

        for field in PUSH_SETTINGS_FIELDS:
            setattr(app_user, field, data.get(field, None))
        app_user.save()

        firebase_token = data.get("firebase_token", None)
        if firebase_token:
            appusers_with_firebase_token = AppUser.objects.filter(
                firebase_token=firebase_token
            )
            if len(appusers_with_firebase_token) > 1:
                logger.debug("Duplicates for firebase id {}".format(firebase_token))
                # there are duplicates !
                # delete the dupes
                duplicates = appusers_with_firebase_token.exclude(app_user)
                logger.debug(
                    "Deleting devices: {}".format(
                        [device.device_id for device in duplicates]
                    )
                )
                duplicates.delete()

        return Response(status.HTTP_200_OK)


class OrganizationChoiceSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    push = serializers.SerializerMethodField()
    all_tags = serializers.SerializerMethodField()
    by_tag = serializers.SerializerMethodField()
    deselected = serializers.SerializerMethodField()

    class Meta:
        model = AppUser
        fields = (
            "type",
            "name",
            "push",
            "all_tags",
            "by_tag",
            "deselected",
        )

    @swagger_serializer_method(serializers.BooleanField)
    def get_push(self, instance):
        return getattr(instance, "push_{}".format(self.context["type"][0]))

    @swagger_serializer_method(serializers.CharField)
    def get_type(self, instance):
        return self.context["type"][0]

    @swagger_serializer_method(serializers.CharField)
    def get_name(self, instance):
        return self.context["type"][1]

    @swagger_serializer_method(serializers.IntegerField)
    def get_all_tags(self, instance):
        # convert the instance which is an instance of the app user into dictionary
        app_user = instance.__dict__
        # get the area id so it can be used for filtering the results
        user_area_id = app_user["area_id"]
        # filter the user instance organisation by the area id
        return len(
            instance.organization_all_tags.filter(type=self.context["type"][0])
            .filter(area=user_area_id)
            .values()
        )

    @swagger_serializer_method(serializers.IntegerField)
    def get_by_tag(self, instance):

        # convert the instance which is an instance of the app user into dictionary
        app_user = instance.__dict__
        # get the area id so it can be used for filtering the results
        user_area_id = app_user["area_id"]
        # filter the user instance organisation by the area id
        all_organisations_in_user_area = (
            instance.organization.filter(type=self.context["type"][0])
            .filter(area=user_area_id)
            .values()
        )

        return len(all_organisations_in_user_area)

    @swagger_serializer_method(serializers.IntegerField)
    def get_deselected(self, instance):
        # convert the instance which is an instance of the app user into dictionary
        app_user = instance.__dict__
        # get the area id so it can be used for filtering the results
        user_area_id = app_user["area_id"]

        selected = instance.organization.filter(type=self.context["type"][0]).filter(
            active=True
        )
        selected_all_tags = instance.organization_all_tags.filter(
            type=self.context["type"][0]
        ).filter(active=True)
        _selected = set(list(set(selected)) + list(set(selected_all_tags)))
        available = (
            Organization.objects.filter(type=self.context["type"][0])
            .filter(active=True)
            .filter(area=user_area_id)
        )
        _deselected = [org for org in available if org not in _selected and org.active]
        return len(_deselected)


class SummarySerializer(serializers.ModelSerializer):

    overview = serializers.SerializerMethodField()

    class Meta:
        model = AppUser
        fields = ("overview",)

    @swagger_serializer_method(OrganizationChoiceSerializer(many=True))
    def get_overview(self, instance):
        overview = []
        for choice_type in ORGANIZATION_TYPE_CHOICES:
            _choice_serializer = OrganizationChoiceSerializer(
                instance,
                context={
                    "type": choice_type,
                },
            )
            overview.append(_choice_serializer.data)

        return overview


class SummaryViewSet(AppUserBaseViewSet):
    http_method_names = ["get"]

    @swagger_auto_schema(
        operation_description="Get a summary of selected organizations and tags",
        manual_parameters=[
            header_string_parameter("X-Device-ID", "Device ID", required=True),
        ],
        responses={200: SummarySerializer, 400: "Device ID is missing"},
    )
    def list(self, request, *args, **kwargs):
        """Overview of number of selected organizations and tags.

        Args:
            request (request): request object
            *args (args): additional args
            **kwargs (kwargs): additional kwargs

        Returns:
            Response
        """
        app_user, error_response = self.get_user(create=False)
        if error_response:
            if error_response.data["detail"] == "Device ID is missing":
                return error_response
            app_user, error_response = self.get_user()
            save_organizations(app_user)

        serializer = SummarySerializer(app_user)
        return Response(serializer.data)
