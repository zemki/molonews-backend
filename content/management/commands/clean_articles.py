from django.core.management.base import BaseCommand
from django.utils.timezone import localtime
from datetime import datetime, timedelta

import traceback
import json
from urllib.parse import urlparse
from PIL import Image
from io import BytesIO
import requests

import feedparser

from content.models import Article

DELETE_AFTER_DAYS = 30


def get_old_news_articles():
    current_date = datetime.now().date()
    oldest_date = current_date - timedelta(days=DELETE_AFTER_DAYS)
    return Article.objects.filter(type='news').filter(date__lte=oldest_date.strftime("%Y-%m-%d"))


def check_article_links(info, error):
    info("Checkin article links...")
    articles = Article.objects.all()
    for article in articles:
        if not article.link:
            # can't use an article without link
            article.delete()
            info("Deleting article without link")
            continue
        try:
            response = requests.get(article.link)
        except requests.RequestException as err:
            error("Error checking article {} : {}".format(article.link, err))
        if response.status_code == 404:
            info("Deleting unreachable article: {}".format(article.link))
            article.delete()


def clean_articles(info, warning, error, success):
    articles = get_old_news_articles()
    info("Checking for expired articles...")
    if articles:
        info("Expired articles found.")
        num_deleted = articles.delete()
        info("Deleted {} old articles.".format(num_deleted[0]))
    else:
        info("No expired articles found.")
    check_article_links(info, error)



class Command(BaseCommand):
    help = 'Remove old articles'


    def handle(self, *args, **options):
        write = self.stdout.write
        style = self.style
        info = lambda s: write(style.HTTP_INFO(s))
        warning = lambda s: write(style.WARNING(s))
        error = lambda s: write(style.ERROR(s))
        success = lambda s: write(style.SUCCESS(s))
        clean_articles(info, warning, error, success)
        success('Articles cleaned.')


if __name__ == '__main__':
    clean_articles()
