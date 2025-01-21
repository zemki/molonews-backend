from logging import getLogger

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.conf import settings
from pyfcm import FCMNotification

from content.models import AppUser, Article, Source

logger = getLogger("push_notifications")


def query_push_articles():
    articles = Article.objects.filter(push_notification_queued=True)
    return articles


def push_messages(push_queue):

    logger.info("Processing messages")
    if not settings.FCM_API_KEY:
        logger.error("No firebase api key! Aborting")
        return

    push_service = FCMNotification(api_key=settings.FCM_API_KEY)

    for article in push_queue:
        _do_push = all(
            [
                article.push_notification_sent is False,
                article.push_notification_queued is True,
            ]
        )

        # prevent sending more than once
        article.push_notification_sent = True
        article.push_notification_queued = False
        article.save()

        if not _do_push:
            continue

        logger.debug(
            "Article {} is marked as is_hot and was saved prior to sending push notifications.".format(
                article.id
            )
        )

        push_type = article.source.organization.type
        _filter = {"push_{}".format(push_type): True}
        firebase_users = AppUser.objects.filter(**_filter).exclude(firebase_token=None)
        # dedupe and 'validate' firebase id's
        registration_ids = list(
            set(
                [
                    user.firebase_token.strip()
                    for user in firebase_users
                    if (user.firebase_token and len(user.firebase_token) > 25)
                ]
            )
        )

        valid_ids = push_service.clean_registration_ids(registration_ids)

        logger.debug(
            "Not pushing to invalid id's: {}".format(
                [id for id in registration_ids if id not in valid_ids]
            )
        )

        logger.debug("Pushing to firebase ids:")
        logger.debug(valid_ids)

        message_title = article.title
        # strip html tags
        message_body = BeautifulSoup(article.abstract, "lxml").text

        data = {"article_id": article.id}

        result = push_service.notify_multiple_devices(
            registration_ids=valid_ids,
            message_title=message_title,
            message_body=message_body,
            data_message=data,
        )
        logger.debug("Push result:")
        logger.debug(result)


def run():
    push_queue = query_push_articles()
    if push_queue:
        push_messages(push_queue)
    else:
        logger.info("No messages")


class Command(BaseCommand):
    help = "Imports new articles"

    def handle(self, *args, **options):
        logger.info("Starting push message run")
        run()
        logger.info("Done")


if __name__ == "__main__":
    c = Command()
    c.run_from_argv(["", ""])
