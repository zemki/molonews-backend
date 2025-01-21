from django.core.management.base import BaseCommand
from content.models import User, Organization, Source  # Importiere die Modelle aus deiner App
from django.db import transaction

class Command(BaseCommand):
    help = 'Updates related_user field in Organization and Source models based on display_name'

    def handle(self, *args, **kwargs):
        self.update_organizations()
        self.update_sources()

    def update_organizations(self):
        with transaction.atomic():
            organizations = Organization.objects.filter(related_user__isnull=True)
            for organization in organizations:
                user = User.objects.filter(display_name=organization.name).first()
                if user:
                    organization.related_user = user
                    organization.save()
                    self.stdout.write(self.style.SUCCESS(f'Updated Organization {organization.name} with related_user {user.username}'))
                else:
                    self.stdout.write(self.style.WARNING(f'No User found for Organization {organization.name}'))

    def update_sources(self):
        with transaction.atomic():
            sources = Source.objects.filter(related_user__isnull=True)
            for source in sources:
                user = User.objects.filter(display_name=source.name).first()
                if user:
                    source.related_user = user
                    source.save()
                    self.stdout.write(self.style.SUCCESS(f'Updated Source {source.name} with related_user {user.username}'))
                else:
                    self.stdout.write(self.style.WARNING(f'No User found for Source {source.name}'))
