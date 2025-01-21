from rest_framework import status
from rest_framework import viewsets, serializers
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from django.core.mail import send_mail
from django.conf import settings

from .util import choices_parameter, header_string_parameter, string_parameter
from content.choices import FEEDBACK_CONTACT_TYPE_CHOICES


def send_email(data):
    mail_address = settings.FEEDBACK_MAIL_TARGET
    feedack_type = data.data.get('contact_type', 'participation').upper()

    subject = "[{}] {}".format(feedack_type, data.data['email'])
    message = "Contact: {} \nMessage: {}".format(data.data['email'], data.data['content'])
    send_mail(subject, message, 'contact@redaktion.molo.de', [mail_address])


class ContactSerializer(serializers.Serializer):

    email = serializers.EmailField(required=True)
    content = serializers.CharField(required=True)

    class Meta:
        fields = ('email', 'content')


class FeedbackContactSerializer(ContactSerializer):
    contact_type = serializers.ChoiceField(FEEDBACK_CONTACT_TYPE_CHOICES, required=True)


class ErrorSerializer(serializers.Serializer):

    parameter = serializers.CharField()
    error_message = serializers.CharField()

    class Meta:
        fields = (
            'parameter', 'error_message'
        )


class BaseContactViewSet(viewsets.ViewSet):
    serializer_class = None
    http_method_names = ['post']

    def create(self, request, *args, **kwargs):
        """

        Args:
            request (request): request object
            *args (args): additional args
            **kwargs (kwargs): additional kwargs

        Returns:
            Response
        """
        device_id = self.request.headers.get('X-Device-ID', None)
        if device_id is None:
            return Response('Device ID is missing', status.HTTP_400_BAD_REQUEST)

        data = self.request.query_params

        serializer = self.serializer_class
        validated_data = serializer(data=data)
        if validated_data.is_valid():
            try:
                send_email(validated_data)
                return Response(status.HTTP_200_OK)
            except Exception as error:
                return Response('Error sending email', status.HTTP_400_BAD_REQUEST)
        else:
            errors = [{'parameter': error_field, 'error_message': error_value[0]} for error_field, error_value in
                      validated_data.errors.items()]
            return Response(errors, status.HTTP_400_BAD_REQUEST)


class FeedbackContactViewSet(BaseContactViewSet):

    serializer_class = FeedbackContactSerializer

    @swagger_auto_schema(
        operation_description='Send feedback.',
        manual_parameters=[
            header_string_parameter('X-Device-ID', 'Device ID', required=True),
            choices_parameter('contact_type', FEEDBACK_CONTACT_TYPE_CHOICES, 'Reason for contact', required=True),
            string_parameter('email', 'Sender email address', required=True),
            string_parameter('content', required=True)

        ],
        responses={200: 'Feedback sent', 400: ErrorSerializer(many=True)},
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)


class ParticipateContactViewSet(BaseContactViewSet):
    serializer_class = ContactSerializer

    @swagger_auto_schema(
        operation_description='Send participation request.',
        manual_parameters=[
            header_string_parameter('X-Device-ID', 'Device ID', required=True),
            string_parameter('email', 'Sender email address', required=True),
            string_parameter('content', required=True)

        ],
        responses={200: 'Request sent', 400: ErrorSerializer(many=True)},
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
