from django.core.management.base import BaseCommand
from content.models import AppUser, Organization
from django.core.exceptions import ObjectDoesNotExist
from logging import getLogger

logger = getLogger(__name__)

class Command(BaseCommand):
    help = 'Adds an organization to all app users'

    def add_arguments(self, parser):
        # Positional argument for organization ID
        parser.add_argument('organization_id', type=int, help='The ID of the organization to add to all app users')

    def handle(self, *args, **kwargs):
        organization_id = kwargs['organization_id']

        try:
            # Get the organization by ID
            organization = Organization.objects.get(id=organization_id)
        except ObjectDoesNotExist:
            self.stdout.write(self.style.ERROR(f'Organization with ID {organization_id} does not exist.'))
            return

        # Get all AppUsers
        app_users = AppUser.objects.all()

        if not app_users.exists():
            self.stdout.write(self.style.WARNING('No app users found.'))
            return

        # Add the organization to all AppUsers
        for app_user in app_users:
            app_user.organization.add(organization)
            app_user.save()

        self.stdout.write(self.style.SUCCESS(f'Successfully added organization "{organization.name}" to all app users.'))
        logger.info(f'Organization {organization.name} added to all app users.')
