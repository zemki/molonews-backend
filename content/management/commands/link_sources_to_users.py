import logging
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from content.models import User, Source, Organization

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    
    help = 'Check and execute changes to related users in sources and organizations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run the command without making any changes to the database.',
        )

    def handle(self, *args, **options):
        # Check the current timezone of the database connection
        with connection.cursor() as cursor:
            cursor.execute("SHOW timezone;")
            db_timezone = cursor.fetchone()[0]
        
        self.stdout.write(f"Database connection timezone: {db_timezone}")
        logger.info(f"Database connection timezone: {db_timezone}")

        if db_timezone.lower() != 'utc':
            self.stderr.write(
                self.style.ERROR(
                    f"Database connection timezone is set to '{db_timezone}', expected 'UTC'."
                )
            )
            logger.error(
                f"Database connection timezone is set to '{db_timezone}', expected 'UTC'."
            )
            return  # Exit the command to prevent further execution
        

        dry_run = options['dry_run']
        changes = []
        executed_changes = []
        errors = []

        try:

            with transaction.atomic():
                for user in User.objects.all():
                    self.stdout.write(f"Processing User: {user.username}")

                    for source in user.sources.all():
                        if not source.related_user:
                            if dry_run:
                                change = f"[Dry Run] Would set related_user of Source '{source.name}' to '{user.username}'."
                            else:
                                source.related_user = user
                                source.save()
                                change = f"Set related_user of Source '{source.name}' to '{user.username}'."
                            changes.append(change)
                            executed_changes.append(change)
                            logger.info(change)

                        if source.organization:
                            organization = source.organization
                            if not organization.related_user:
                                if source.related_user:
                                    if dry_run:
                                        change = (
                                            f"[Dry Run] Would set related_user of Organization '{organization.name}' to "
                                            f"'{source.related_user.username}'."
                                        )
                                    else:
                                        organization.related_user = source.related_user
                                        organization.save()
                                        change = (
                                            f"Set related_user of Organization '{organization.name}' to "
                                            f"'{source.related_user.username}'."
                                        )
                                    changes.append(change)
                                    executed_changes.append(change)
                                    logger.info(change)
                                else:
                                    change = (
                                        f"Organization '{organization.name}' has no related_user and source "
                                        f"'{source.name}' has no related_user. No changes."
                                    )
                                    changes.append(change)
                                    logger.info(change)

                    self.stdout.write("")

                if dry_run:
                    self.stdout.write(self.style.WARNING("Dry Run - No changes were made:"))
                else:
                    self.stdout.write(self.style.SUCCESS("Executed Changes:"))

                for change in executed_changes:
                    self.stdout.write(change)

                if dry_run:
                    # Rollback the transaction
                    raise Exception("Dry run complete. Rolling back.")

        except Exception as e:
            if dry_run:
                self.stdout.write(self.style.WARNING("Dry run completed. No changes were made."))
                logger.info("Dry run completed. No changes were made.")
            else:
                logger.exception("An error occurred while executing changes.")
                self.stderr.write(self.style.ERROR("An error occurred. Changes have been rolled back."))
                raise e
