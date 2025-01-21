from django.core.management.base import BaseCommand
from django.utils.timezone import localtime
from lxml import etree
from logging import getLogger
import traceback
import json
from urllib.parse import urlparse
from PIL import Image
from io import BytesIO
import requests
import feedparser
from webpreview import InvalidURL, OpenGraph, URLUnreachable
from dateutil.parser import parse as parse_datetime
from content.models import Article, Source, Tag, Area, Organization
from content.parsers import get_parser_function
import ml.news_article_tagging  as ml

IMAGE_MIN_SIZE = 150

logger = getLogger(__name__)

# for debugging
def _save(entry):
    with open("entry.json", "w") as f:
        json.dump(entry, f, indent=2)


def get_baseurl(url):
    parsed_link = urlparse(url)
    return "{}://{}".format(parsed_link.scheme, parsed_link.netloc)


def get_image_infos(image_url):
    response = requests.get(image_url)
    if not response.status_code == 200:
        return
    image = Image.open(BytesIO(response.content))
    return image


def image_has_min_size(image_url):
    image_infos = get_image_infos(image_url)
    if (
        image_infos
        and image_infos.width >= IMAGE_MIN_SIZE
        and image_infos.height >= IMAGE_MIN_SIZE
    ):
        return True
    return False


def get_og_image(link):
    try:
        og_infos = OpenGraph(link, ["og:image"])
        if og_infos.image and image_has_min_size(og_infos.image):
            return og_infos.image
    except (InvalidURL, URLUnreachable):
        return
    return


def normalize_image_url(image_url, base_url):
    if image_url.startswith("/"):
        return "{}{}".format(base_url, image_url)
    else:
        return image_url


def get_image_url(entry, default_image_url=None):

    if hasattr(entry, "force_default_image") and entry.force_default_image:
        return default_image_url

    article_link = entry.link
    base_url = get_baseurl(article_link)

    og_image = get_og_image(article_link)
    if og_image:
        return og_image

    if hasattr(entry, "image_url") and entry.image_url:
        image = entry.image_url
        image_url = normalize_image_url(image, base_url)
        if image_has_min_size(image_url):
            return image_url
    for media_content in entry.get("media_content", []):
        if hasattr(media_content, "type") and media_content["type"].startswith(
            "image/"
        ):
            image = media_content["url"]
            image_url = normalize_image_url(image, base_url)
            if image_has_min_size(image_url):
                return image_url
    return default_image_url


def get_image(image_url, default_image):
    image = None
    if not image_url:
        image = default_image
    return image


def add_date(entry):
    if "date" in entry:
        entry.date = parse_datetime(entry.date)
    else:
        entry.date = localtime()


def _get_article(entry):
    article = None
    if hasattr(entry, "foreign_id") and entry.foreign_id:
        try:
            article = Article.objects.get(foreign_id=entry.foreign_id)
        except Article.DoesNotExist:
            pass
    if not article:
        article = Article.objects.get(link=entry.link)
    return article


def article_exists(entry):
    try:
        _get_article(entry)
        return True
    except Article.DoesNotExist:
        return False


def depublicate_article(entry):
    article = _get_article(entry)
    article.delete()


def has_title(entry):
    try:
        if entry.title:
            return True
    except AttributeError:
        return False


def write_article(entry_parsed, source, tagging_engine):
    """Create new article

    Args:
        entry_parsed (feedparser.entry): parsed feedparser entry
        source (source): article source

    Returns:
        None
    """
    _image = None
    _image_detail = None
    _image_url = get_image_url(entry_parsed)

    entry_class = Article

    entry_class.area

    #replace parts of the default text inside the article
    entry_parsed_summary = entry_parsed.summary
    entry_parsed_summary = entry_parsed_summary.replace(" erschien zuerst auf Lüne-Blog", "")


    article = entry_class.objects.create(
        title=entry_parsed.title,
        abstract=entry_parsed_summary,
        link=entry_parsed.link,
        date=getattr(entry_parsed, "statedate", None) or getattr(entry_parsed, 'date'),
        moddate=getattr(entry_parsed, "moddate", None) or localtime(),
        source=source,
        image_url=_image_url,
        image=getattr(entry_parsed, "image_square", None) or _image,
        image_detail=_image_detail,
        image_source=getattr(entry_parsed, "image_source", None),
        published=source.default_published,
        foreign_id=getattr(entry_parsed, "foreign_id", None),
        up_for_review=True,
    )

    #https://docs.djangoproject.com/en/4.2/topics/db/examples/many_to_many/

    all_tags = Tag.objects.all().values()
    automatically_detected_tags = tagging_engine.tag_news_article(entry_parsed.title, entry_parsed.summary)

    # add the automatically detected tags to the list of tags of the article
    for auto_tag in automatically_detected_tags:
        for tag in all_tags:
            if tag['name'] == auto_tag:
                article.tags.add(tag['id'])

    # add the areas of the source to the area of the article
    all_areas = Area.objects.all().values()
    source_areas = source.area.all().values() 

    for source_area in source_areas:
        for area in all_areas:
            if area['name'] == source_area['name']:
                article.area.add(area['id'])


    # TODO add start_date / end_date if it can be parsed in case of an event
    #article.tags.set(source.default_tags.all())


def update_article(article, entry_parsed, source, article_date, moddate=None):
    """update an existing article

    Args:
        article (article): article object
        entry_parsed (feedparser.entry): parsed feedparser entry
        source (source): article source
        article_date (date): modification date

    Returns:
        None
    """

    _image_url = get_image_url(entry_parsed, source.default_image_url)
    article.title = entry_parsed.title
    article.link = entry_parsed.link
    article.abstract = entry_parsed.summary
    article.date = article_date
    article.moddate = moddate or localtime()
    article.image_url = _image_url
    article.image = getattr(entry_parsed, "image_square", article.image)
    article.image_detail = article.image_detail or None
    article.image_source = getattr(entry_parsed, "image_source", None)
    article.foreign_id = getattr(entry_parsed, "foreign_id", None)
    article.save()


def import_articles():
    """import articles from list of sources which is stored in the DB

    Args:
        None

    Returns:
        None
    """

    #for organization in Organization.objects.all():
    #    organization.area.set('3')
    #    organization.save

    xml_parser = etree.XMLParser(recover=True)
    tagging_engine = ml.MlTagging()
    counter = 0   # stores the amount of imported articles

    #go through List of Sources from DB and fetch articles
    for source in Source.objects.filter(type="rss", active=True):

        text = ""
        sanitized_text  = ""
        feed  = ""
        parser  = "" 
        s = "{} - {}".format(source.name, source.link)

        # get sourece data
        try:
            text = requests.get(source.link).text 
        except:
            logger.info("Error while getting html code of source " + s)
            continue
        
        # sanitize source data
        try:
            sanitized_text = etree.tostring(etree.fromstring(text.encode('utf-8'), parser=xml_parser))
        except:
            logger.error("Error while parsing to string")
            logger.error(s)
            logger.error(sanitized_text)
            continue
        
        # parse source data
        try:
            feed = feedparser.parse(sanitized_text)
        except:
            logger.error("Error while parsing sanitized_text")
            logger.error(s)
            logger.error(traceback.format_exc())
            continue

        # get parser function
        try:
            parser = get_parser_function(source.parser)
        except:
            logger.error("Error while getting parser function")
            logger.error(s)
            logger.error(traceback.format_exc())
            continue
 
   
        # iterate through all entries
        for entry in feed.entries:

            if not has_title(entry):
                #logger.info("Article has not title, skipping...")
                continue

            try:
                add_date(entry)
                if parser:
                    entry_parsed = parser(entry)
                else:
                    entry_parsed = entry
            except:
                logger.error("Error while parsing")
                logger.error(s)
                logger.error(traceback.format_exc())
            
            try:
                depublicated = getattr(entry_parsed, "depublicated", None)
                moddate = getattr(entry_parsed, "moddate", None)
                exists = article_exists(entry_parsed)
                summary = getattr(entry_parsed, "summary", None)
                summary = summary.strip()

                if summary.find('mehr...') > 8:
                   summary = summary.replace("mehr...", "")
                
                if len(summary) == 0:
                    summary = "mehr..."

                von_pos = summary.find("Von")
                dpa_pos = summary.find("dpa")

                if von_pos > -1 and dpa_pos > -1:
                    dpa_pos = dpa_pos + len("dpa")
                    summary = summary[dpa_pos:]

                setattr(entry_parsed, "summary", summary)

            except:
                logger.error("Error while parsing")
                logger.error(s)
                logger.error(traceback.format_exc())
            
            try:
                
                if exists or depublicated:
                    if exists and depublicated:
                        logger.info(f"deleting {entry_parsed.title} from db")
                        
                        depublicate_article(entry_parsed)
                    if exists and not depublicated and not moddate:
                        pass #logger.info("    skipped, already exists.")
                    if exists and not depublicated and moddate:
                        #logger.info("    article was modified, checking date")
                        article = _get_article(entry_parsed)
                        if (
                            moddate > article.date and moddate > article.moddate
                        ) or entry_parsed.link != article.link:
                            logger.info(f"updating {entry_parsed.title} ")
                            article_date = entry_parsed.statedate or moddate
                            update_article(
                                article,
                                entry_parsed,
                                source,
                                article_date,
                                moddate=moddate,
                            )
                        else:
                            pass#logger.info("    no need to update article")
                    if not exists and depublicated:
                        pass #logger.info("    skipped, article is depublicated.")
                    continue
                else:
                    write_article(entry_parsed, source, tagging_engine)
                    counter = counter + 1

            except:
                logger.error("Error while importing")
                logger.error(traceback.format_exc())

        source.import_date = localtime()
        source.save()

    logger.info (str(counter) + " Articles imported.")

class Command(BaseCommand):
    help = "Imports new articles"

    def handle(self, *args, **options):
        logger.info("Starting article import.")
        import_articles()
   

if __name__ == "__main__":
    c = Command()
    c.run_from_argv(["", ""])
