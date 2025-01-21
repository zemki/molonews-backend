from django.core.management.base import BaseCommand
from django.db import connection
from logging import getLogger

logger = getLogger(__name__)


def count_users():
    with connection.cursor() as cursor:
        cursor.execute("Insert into user_count (timestamp, count) values(NOW(), (select count(id) from content_appuser where location_latitude is not null and location_latitude > 0));")


class Command(BaseCommand):
    help = 'Aggregate statistics'

    def handle(self, *args, **options):
        logger.info('Starting article import.')
        count_users()
        logger.info('Articles imported.')


if __name__ == '__main__':
    command = Command()
    command.run_from_argv(['', ''])
