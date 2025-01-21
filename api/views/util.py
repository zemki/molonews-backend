import collections.abc

from drf_yasg import openapi
from rest_framework.versioning import NamespaceVersioning
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework import status


types_dict = {
    int: openapi.TYPE_INTEGER,
    str: openapi.TYPE_STRING
}


def string_parameter(name, description='', required=False):
    if not description:
        description = name
    return openapi.Parameter(
        name, openapi.IN_QUERY, description=description, type=openapi.TYPE_STRING, required=required,
    )


def integer_parameter(name, description='', required=False):
    if not description:
        description = name
    return openapi.Parameter(
        name, openapi.IN_QUERY, description=description, type=openapi.TYPE_INTEGER, required=required,
    )

def number_parameter(name, description='', required=False):
    if not description:
        description = name
    return openapi.Parameter(
        name, openapi.IN_QUERY, description=description, type=openapi.TYPE_NUMBER, required=required,
    )

def boolean_parameter(name, description='', default=None):
    if not description:
        description = name
    return openapi.Parameter(
        name, openapi.IN_QUERY, description=description, type=openapi.TYPE_BOOLEAN, default=default,
    )


def choices_parameter(name, choices, description='', required=False):
    if not description:
        description = name
    if isinstance(choices[0], collections.abc.Sequence) and not isinstance(choices[0], str):
        enum = [c[0] for c in choices]
    else:
        enum = choices
    type_ = types_dict[type(enum[0])]
    return openapi.Parameter(name, openapi.IN_QUERY, description=description, type=type_, enum=enum, required=required)


def isodate_parameter(name, description='', required=False):
    if not description:
        description = "ISO 8601 formatted"
    return openapi.Parameter(name, openapi.IN_QUERY, description=description, type=openapi.TYPE_STRING, required=required)


def header_string_parameter(name, description='', required=False):
    return openapi.Parameter(
        name, openapi.IN_HEADER, description=description, type=openapi.TYPE_STRING, required=required)


class UserPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 50


def bad_request(detail):
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


class MoloVersioning(NamespaceVersioning):
    default_version = 'v1'
    allowed_versions = ['v1', 'v2']
    version_param = 'api_version'
