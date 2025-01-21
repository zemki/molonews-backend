from rest_framework import viewsets, serializers, filters
from drf_yasg.utils import swagger_auto_schema, swagger_serializer_method
import django_filters as df
from rest_framework.response import Response

from .util import MoloVersioning, bad_request, choices_parameter, header_string_parameter
from content.models import Organization, AppUser
from content.choices import ORGANIZATION_TYPE_CHOICES, V1_ORGANIZATION_TYPE_CHOICES


class OrganizationFilter(df.FilterSet):

    type = df.ChoiceFilter(choices=ORGANIZATION_TYPE_CHOICES)

    class Meta:
        model = Organization
        fields = ['type']

def get_appuser(device_id):
    """Try to get an AppUser by device id

    Args:
        device_id (str): device id string

    Returns:
        AppUser or None
    """
    try:
        return AppUser.objects.get(device_id=device_id)
    except AppUser.DoesNotExist:
        return None

class OrganizationActiveFilter(filters.BaseFilterBackend):

    def filter_queryset(self, request, queryset, view):
        """Filter queryset to only include active organizations.

        Args:
            request (Request): current request
            queryset (QuerySet): unfiltered Queryset
            view (View): current view

        Returns:
            filtered QuerySet
        """
        return queryset.filter(active=True)


class OrganizationSerializer(serializers.ModelSerializer):

    is_selected = serializers.SerializerMethodField()

    @swagger_serializer_method(serializers.NullBooleanField)
    def get_is_selected(self, instance):
        # is_selected:
        # True : (selected_all_tags == True)
        # False: (is_selected = True)
        # None: (selected_all_tags == False AND is_selected == False)

        is_selected = None
        org_data = self.context.get('org_data', None)
        device_id = self.context.get('device_id', None)
        if not org_data:
            return None
        selected = instance.id in org_data['selected']
        deselected = instance.id in org_data['deselected']
        if selected is not None and selected and not deselected:
            is_selected = False
        selected_all_tags = instance.id in org_data['selected_all_tags']
        deselected_all_tags = instance.id in org_data['deselected_all_tags']
        if selected_all_tags is not None and selected_all_tags and not deselected_all_tags:
            is_selected = True

        # default to tag selection
        if not selected_all_tags and not selected and not deselected and not deselected_all_tags:
            is_selected = False
            try:
                appuser = AppUser.objects.get(device_id=device_id)
                appuser.organization.add(instance)
                appuser.save()
            except AppUser.DoesNotExist:
                pass

        return is_selected

    class Meta:
        model = Organization
        fields = (
            'id',
            'title',
            'name',
            'description',
            'address',
            'type',
            'image',
            'homepage',
            'is_selected',
        )


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    filter_backends = [
        df.rest_framework.DjangoFilterBackend,
        OrganizationActiveFilter,
    ]
    filterset_class = OrganizationFilter

    def _get_org_data(self, device_id):

        try:
            app_user = AppUser.objects.get(device_id=device_id)
            org_data = {
                "selected": [_org.id for _org in app_user.organization.all()],
                "deselected": [_org.id for _org in app_user.deselected_organization.all()],
                "selected_all_tags": [_org.id for _org in app_user.organization_all_tags.all()],
                "deselected_all_tags": [_org.id for _org in app_user.deselected_organization_all_tags.all()],
            }
        except AppUser.DoesNotExist:
            org_data = {
                "selected": [],
                "deselected": [],
                "selected_all_tags": [],
                "deselected_all_tags": [],
            }
        return org_data

    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter('X-Device-ID', 'Device ID', required=True),
            choices_parameter('type', ORGANIZATION_TYPE_CHOICES),
        ]
    )
    def list(self, *args, **kwargs):
        device_id = self.request.headers.get('X-Device-ID', None)
        if device_id is None:
            return bad_request("Device ID is missing")

        org_data = self._get_org_data(device_id)

        queryset = self.filter_queryset(self.get_queryset()).order_by('name')

        app_user = get_appuser(device_id)
        user_area = app_user.area
        area_id = user_area.__dict__['id']
    
        queryset = queryset.filter(area = area_id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = OrganizationSerializer(page, many=True, context={
                'orgs_data': org_data,
            })
            return self.get_paginated_response(serializer.data)

        serializer = OrganizationSerializer(queryset, many=True, context={
            'org_data': org_data, 'device_id': device_id,
        })
        return Response(serializer.data)


class OrganizationSerializer_V1(OrganizationSerializer):

    # TODO remove temporary workaround, see Ticket 515
    address = serializers.SerializerMethodField()

    @swagger_serializer_method(serializers.URLField)
    def get_address(self, instance):
        return instance.homepage

    # TODO remove temporary workaround, see Ticket 515

    type = serializers.SerializerMethodField()

    def get_type(self, instance):
        if instance.type == 'official':
            return 'collective'
        return instance.type


class OrganizationViewSet_V1(OrganizationViewSet):

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer_V1
    filter_backends = None

    def filter_queryset(self, queryset):
        org_type = self.request.query_params.get('type', None)
        if org_type == 'collectives':
            queryset = queryset.exclude(type='news')
        if org_type == 'news':
            queryset = queryset.filter(type='news')
        # TODO remove workaround
        if org_type == 'official':
            queryset = queryset.filter(type='official')
        return queryset

    @swagger_auto_schema(
        manual_parameters=[
            header_string_parameter('X-Device-ID', 'Device ID', required=True),
            choices_parameter('type', V1_ORGANIZATION_TYPE_CHOICES),
        ]
    )
    def list(self, *args, **kwargs):
        device_id = self.request.headers.get('X-Device-ID', None)
        if device_id is None:
            return bad_request("Device ID is missing")

        org_data = self._get_org_data(device_id)

        queryset = self.filter_queryset(self.get_queryset()).order_by('name')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = OrganizationSerializer_V1(page, many=True, context={
                'orgs_data': org_data,
            })
            return self.get_paginated_response(serializer.data)

        serializer = OrganizationSerializer_V1(queryset, many=True, context={
            'org_data': org_data,
        })
        return Response(serializer.data)
