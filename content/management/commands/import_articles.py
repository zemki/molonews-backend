from datetime import datetime, time, date
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.utils.timezone import is_naive, make_aware, localtime, timedelta
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
from content.models import Article, Source, Tag, Area, Organization, EventV4, Event_Occurrence
from content.parsers import get_parser_function
import ml.news_article_tagging  as ml
import sys
import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from icalendar import Calendar, Event as iCalEvent

IMAGE_MIN_SIZE = 150

logger = getLogger(__name__)


def html_article_exists(title, source):
    """
    Check if an article with the same title, date, and source already exists.

    Args:
        title (str): Title of the article.
        source (Source): The source of the article.

    Returns:
        bool: True if a duplicate exists, False otherwise.
    """
    # Check for an article with the same title, date, and source
    return Article.objects.filter(title=title, source=source).exists()



def parse_ics_for_events(ics_content, base_url):
    try:
        cal = Calendar.from_ical(ics_content)
    except Exception as e:
        logger.error(f"Error parsing .ics content: {str(e)}")
        return []

    events = []
    for component in cal.walk():
        if component.name == "VEVENT":
            try:
                title = component.get("summary")
                start_datetime = component.get("dtstart").dt
                end_datetime = component.get("dtend").dt
                location = component.get("location", "")
                description = component.get("description", "")

                if title and start_datetime and end_datetime:
                    events.append({
                        "title": title,
                        "start_datetime": start_datetime,
                        "end_datetime": end_datetime,
                        "location": location,
                        "description": description,
                    })
            except Exception as e:
                logger.error(f"Error parsing event in .ics file: {str(e)}")
                continue
    return events

def parse_html_for_articles(html_content, base_url):
    try:
        soup = BeautifulSoup(html_content, 'lxml')
    except Exception as e:
        logger.error(f"Error parsing HTML content with BeautifulSoup: {str(e)}")
        return []

    articles = []

    # Nur nach relevanten Artikel-Divs suchen
    for article in soup.find_all("div", class_="CurrentPressReleases-release is-Active"):
        try:
            # Datum extrahieren
            date_tag = article.find("div", class_="CurrentPressReleases-releaseDate")
            title_tag = article.find("h3", class_="Headline")
            content_tag = article.find("div", class_="CurrentPressReleases-releasePreviewText")
            image_tag = article.find("img")
            link_tag = article.find("a", href=True)

            # Artikel nur speichern, wenn die essentiellen Informationen vorliegen
            if date_tag and title_tag and content_tag:
                date_value = date_tag.get_text(strip=True)
                title = title_tag.get_text(strip=True)
                content = content_tag.get_text(strip=True)

                # Entfernen von Datum und Titel aus dem Inhalt
                content = content.replace(date_value, "").replace(title, "").strip()

                # Bild-URL und Artikel-Link umwandeln
                image_url = urljoin(base_url, image_tag["src"]) if image_tag and image_tag.get("src") else None
                article_url = urljoin(base_url, link_tag["href"]) if link_tag else None

                # Überprüfung der Inhaltslänge und Hinzufügen des Artikels
                if 30 < len(content) < 1500:
                    articles.append({
                        "date": date_value,
                        "title": title,
                        "summary": content,
                        "image_url": image_url,
                        "article_url": article_url
                    })
                else:
                    pass
            else:
                pass

        except Exception as e:
            continue  # Weiter mit dem nächsten Artikel bei Fehler

    # invert the articles list to get the latest articles first
    articles = articles[::-1]
    return articles


# for debugging
def _save(entry):
    with open("entry.json", "w") as f:
        json.dump(entry, f, indent=2)


def get_baseurl(url):
    """
    This function takes a URL as an input and returns the base URL.
    It uses the urlparse function from the urllib.parse module to parse the URL into its components.
    It then formats and returns the base URL, which consists of the scheme (e.g., http, https) and the network location (netloc).

    Parameters:
    url (str): The URL to parse.

    Returns:
    str: The base URL.
    """
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
    """
    Diese Funktion nimmt einen Link als Eingabe und versucht, das OpenGraph-Bild des Links zu extrahieren.
    Wenn das Bild existiert und die Mindestgröße erfüllt, wird das Bild zurückgegeben.
    Bei einem Fehler während des Prozesses wird None zurückgegeben.

    Parameter:
    link (str): Der Link der Webseite, von der das OpenGraph-Bild extrahiert werden soll.

    Rückgabe:
    str: Der Link zum OpenGraph-Bild, wenn es existiert und die Mindestgröße erfüllt. Andernfalls None.
    """
    try:
        og_infos = OpenGraph(link, ["og:image"])
        if og_infos.image and image_has_min_size(og_infos.image):
            return og_infos.image
    except:
        return None
    return


def normalize_image_url(image_url, base_url):
    if image_url.startswith("/"):
        return "{}{}".format(base_url, image_url)
    else:
        return image_url


def extract_image_from_content_encoded(entry):
    """
    Extrahiere das erste Bild aus dem content:encoded-Element des RSS-Feeds.
    """
    if 'content' in entry:
        # Parse the content:encoded field using BeautifulSoup
        for content_item in entry['content']:
            if 'value' in content_item:
                soup = BeautifulSoup(content_item['value'], 'html.parser')
                
                # Find the first image tag in the parsed HTML
                img_tag = soup.find('img')
                if img_tag and 'src' in img_tag.attrs:
                    # Return the image URL from the 'src' attribute
                    return img_tag['src']
    
    # Return None if no image found
    return None

def get_image_url(entry, default_image_url=None):
    """
    Holt die URL des Bildes aus verschiedenen möglichen Feldern des RSS-Feeds.
    """
    if hasattr(entry, "force_default_image") and entry.force_default_image:
        return default_image_url
    
    if hasattr(entry, "image_url") and entry.image_url:
        return entry.image_url # Return the image URL if it exists

    if hasattr(entry, "links"):
        for link in entry.links:
            if link.get("rel") == "enclosure" and link.get("type", "").startswith("image/"):
                image_url = link["href"]
                if image_has_min_size(image_url):  # Check if the image meets the size requirement
                    return image_url

    article_link = entry.link
    base_url = get_baseurl(article_link)

    # Try OpenGraph image
    og_image = get_og_image(article_link)
    if og_image:
        return og_image

    # Check if entry has an image_url
    if hasattr(entry, "image_url") and entry.image_url:
        image = entry.image_url
        image_url = normalize_image_url(image, base_url)
        if image_has_min_size(image_url):
            return image_url

    # Check for media content
    for media_content in entry.get("media_content", []):
        if hasattr(media_content, "type") and media_content["type"].startswith("image/"):
            image = media_content["url"]
            image_url = normalize_image_url(image, base_url)
            if image_has_min_size(image_url):
                return image_url

    # Check for images in content:encoded
    content_encoded_image = extract_image_from_content_encoded(entry)
    if content_encoded_image:
        image_url = normalize_image_url(content_encoded_image, base_url)
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
        try:
            article = Article.objects.get(link=entry.link)
        except Article.DoesNotExist:
            pass
        except Article.MultipleObjectsReturned:
            logger.error("getting article error" + entry.link)
    return article



def article_exists(entry):
    article = None
    if hasattr(entry, "foreign_id") and entry.foreign_id:
        try:
            article = Article.objects.get(foreign_id=entry.foreign_id)
        except Article.DoesNotExist:
            pass
    if hasattr(entry, "link") and entry.link and not article:
        try: 
            article = Article.objects.get(link=entry.link)
        except:
            pass
    if hasattr(entry, "title") and entry.title and not article: 
       try:
           article = Article.objects.filter(title=entry.title).first()
       except:
           pass
   
    if not article:
        return False
    
    return True


def depublicate_article(entry):
    article = _get_article(entry)
    article.delete()


def has_title(entry):
    try:
        if entry.title:
            return True
    except AttributeError:
        return False

def query_gpt_server(prompt):
    """
    Sendet eine POST-Anfrage an den Server.

    Parameter:
    url (str): Die URL des Servers, an den die Anfrage gesendet werden soll.
    prompt (str): Der Prompt, der an den Server gesendet werden soll.

    Rückgabe:
    Response: Das Response-Objekt, das von der Anfrage zurückgegeben wird.
    """
    url = "https://gpt.molo.news:8000/v1/completions"
    data = {
                "prompt": prompt,
                "max_tokens": 100,
                "temperature": 0.28,
                "top_p": 0.1,
                "top_k": 40,
                "prompt_batch_size": 128,
                "repeat_penality": 1.18,
                "repeat_last_n": 64,
                "prompt_template": "\n### Instruction:\nParaphrase and Expand the text below.\n### Text:\n%1\n### Response:\n"
            }
    try:
        response = requests.post(url, json=data)
        jsonResponse = response.json()
        response_content = jsonResponse['choices'][0]['text']
    except:
        response_content = "error response"
    return response_content


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

    if getattr(entry_parsed, 'published', None):
        date_value = getattr(entry_parsed, 'published')
    elif getattr(entry_parsed, 'pubDate', None):
        date_value = getattr(entry_parsed, 'pubDate')
    elif getattr(entry_parsed, 'date', None):
        date_value = getattr(entry_parsed, 'date')
    elif getattr(entry_parsed, 'updated', None):
        date_value = getattr(entry_parsed, 'updated')
    else:
        date_value = timezone.now()

   # Only parse date_value if it's a string
    if isinstance(date_value, str):
        date_value = parse_datetime(date_value)

    # if date is later than now, set it to now
    if date_value > timezone.now():
        date_value = timezone.now()

    # Make date_value timezone-aware if it's naive
    if isinstance(date_value, datetime) and timezone.is_naive(date_value):
        date_value = timezone.make_aware(date_value)
    # write out the content of entry_parsed into the log but convert it into a string first

    article = entry_class.objects.create(
        title=correct_encoding(entry_parsed.title, source),
        abstract=correct_encoding(entry_parsed_summary, source),
        link=entry_parsed.link,
        date=date_value,
        moddate=date_value,
        source=source,
        image_url=_image_url,
        image=getattr(entry_parsed, "image_square", None) or _image,
        image_detail=_image_detail,
        image_source=getattr(entry_parsed, "image_source", None),
        published=source.default_published,
        foreign_id=getattr(entry_parsed, "foreign_id", None),
        up_for_review=True,
    )

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

    article_area = None

    for source_area in source_areas:
        for area in all_areas:
            if area['name'] == source_area['name']:
                article.area.add(area['id'])
                article_area = source_area['name']

  # get the info if the article is related to the area of the source using the GPT model
    
    # create the prompt for the query
    # prompt = "Hat der folgende Artikel einen Bezug zu " + article_area + "? " 
    # prompt += entry_parsed.title.replace("?", "").replace("\n", "").replace(";", "").replace("\t", "")
    # prompt += ". " + entry_parsed_summary.replace("?", "").replace("\n", "").replace(";", "").replace("\t", "")
    # prompt += ". Bitte antworte mit ja oder nein. "
    # prompt = prompt.replace("  ", " ").replace("..",".")  

    # send the promt to the server and request the response
    # result = query_gpt_server(prompt=prompt)

    # write the prompt into a file
    # f = open("/home/molonews/molonews/promptresult.txt", "a")
    # f.write(prompt + "\n")
    # f.write(result + "\n\n")
    # f.close()

    # write the prompt into a file
    # f = open("/home/molonews/molonews/prompt.txt", "a")
    # f.write(prompt + "\n")
    # f.close()
    
    # if the response is yes, then publish the article
    # if the response is no, then do not publish the article

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

    # check if article is none
    if article is None:
        # ToDo: log error
        # logger.error("Cannot update article: article is None")
        return
    
    # Check if entry_parsed is None and log an error if it is
    if entry_parsed is None:
        logger.error("Cannot update article: entry_parsed is None")
        return

    # Ensure entry_parsed has the necessary attributes
    if not hasattr(entry_parsed, 'title'):
        logger.error("Cannot update article: entry_parsed has no title")
        return

    _image_url = get_image_url(entry_parsed, source.default_image_url)

    changes = []  # List to track changes

    # Compare title
    if article.title != entry_parsed.title:
        changes.append(f"Title changed from '{article.title}' to '{entry_parsed.title}'")
        article.title = entry_parsed.title

    # Compare link
    if article.link != entry_parsed.link:
        changes.append(f"Link changed from '{article.link}' to '{entry_parsed.link}'")
        article.link = entry_parsed.link

    # Compare summary
    if article.abstract != entry_parsed.summary:
        changes.append(f"Summary changed from '{article.abstract}' to '{entry_parsed.summary}'")
        article.abstract = entry_parsed.summary

    # Compare date
    if article.date != article_date:
        changes.append(f"Date changed from '{article.date}' to '{article_date}'")
        article.date = article_date

    # Compare moddate
    if article.moddate != moddate:
        changes.append(f"Modification date changed from '{article.moddate}' to '{moddate}'")
        article.moddate = moddate or localtime()

    # Compare image_url
    _image_url = get_image_url(entry_parsed, source.default_image_url)
    if article.image_url != _image_url:
        changes.append(f"Image URL changed from '{article.image_url}' to '{_image_url}'")
        article.image_url = _image_url

    # Compare image
    if article.image != getattr(entry_parsed, "image_square", article.image):
        changes.append("Image content has changed.")
        article.image = getattr(entry_parsed, "image_square", article.image)

    # Compare image source
    if article.image_source != getattr(entry_parsed, "image_source", None):
        changes.append(f"Image source changed from '{article.image_source}' to '{getattr(entry_parsed, 'image_source', None)}'")
        article.image_source = getattr(entry_parsed, "image_source", None)

    # Log changes if any
    if changes:
        logger.info(f"Updating article '{article.title}' with the following changes: {', '.join(changes)}")
        article.save()
    else:
        pass

def correct_encoding(text, source):
    
    try:
        if source == "Lüne Blog Quelle":
            return text.encode('latin-1').decode('utf-8')
    except:
        pass
    
    return text

def import_articles():
    """import articles from list of sources which is stored in the DB

    Args:
        None

    Returns:
        None
    """
    
    xml_parser = etree.XMLParser(recover=True)
    tagging_engine = ml.MlTagging()
    counter = 0   # stores the amount of imported articles

    for source in Source.objects.filter(type="ics", active=True):
        logger.error ("Importing ICS source: " + source.name)
        try:
                # get response
                response = requests.get(source.link)
                # Handle .ics file parsing and event creation
                events = parse_ics_for_events(response.content, base_url=source.link)
                
                for event_data in events:
                    title = event_data["title"]
                    start_datetime = event_data["start_datetime"]
                    end_datetime = event_data["end_datetime"]

                     # Handle `datetime.date` objects
                    if isinstance(start_datetime, date) and not isinstance(start_datetime, datetime):
                        # Convert to `datetime` at midnight
                        start_datetime = datetime.combine(start_datetime, time.min)

                    if isinstance(end_datetime, date) and not isinstance(end_datetime, datetime):
                        end_datetime = datetime.combine(end_datetime, time.min)

                    # Check if the datetime is naive
                    if is_naive(start_datetime):
                        # Make it timezone-aware using the system timezone
                        start_datetime = make_aware(start_datetime)
                    else:
                        # Normalize the aware datetime to Django's current timezone
                        start_datetime = localtime(start_datetime)

                    if is_naive(end_datetime):
                        # Make it timezone-aware using the system timezone
                        end_datetime = make_aware(end_datetime)
                    else:
                        # Normalize the aware datetime to Django's current timezone
                        end_datetime = localtime(end_datetime)

                    #end_datetime = timezone.make_aware(event_data["end_datetime"])
                    location = event_data["location"]
                    description = event_data["description"]

                    # check if starte_datetime in past then skip
                    if start_datetime < timezone.now():
                        continue

                    # Check for duplicate event
                    if EventV4.objects.filter(title=title, source=source, start_date=start_datetime).exists():
                        continue  # Skip if duplicate exists
                    
                    event = EventV4.objects.create(
                        title=title,
                        content=description,
                        start_date=start_datetime,
                        moddate=timezone.now(),
                        source=source,
                        event_location=location,
                        published=source.default_published
                    )

                    # Create event occurrences
                    Event_Occurrence.objects.create(
                        event=event,
                        start_datetime=start_datetime,
                        end_datetime=end_datetime
                    )

                    # Add areas and tags
                    for area in source.area.all():
                        event.area.add(area)
                    for tag in source.default_tags.all():
                        event.tags.add(tag)
                    # check if no tags are set and set the default tags
                    if not event.tags.all():
                        for tag in Tag.objects.filter(id=30):
                            event.tags.add(tag)
                   
                    counter += 1
        except Exception as e:
            logger.error(f"Error processing .ics source {source.name}: {str(e)}")
            continue


    #go through List of Sources from DB and fetch articles
    for source in Source.objects.filter(type="rss", active=True):

        #continue  # Skip RSS sources for now
        
        if 'hansestadt-lueneburg.de' in source.link:
            try:
                response = requests.get(source.link)
                response.encoding = 'utf-8'
                articles = parse_html_for_articles(response.text, base_url=source.link)

                for article_data in articles:
                    # Assuming article_data["date"] contains the date in German format, like '11.12.2024' (DD.MM.YYYY)
                    date_value = parse_datetime(article_data["date"], dayfirst=True)
                    if timezone.is_naive(date_value):
                        date_value = timezone.make_aware(date_value)

                    article_entry = {
                        "title": article_data["title"],
                        "summary": article_data["summary"],
                        "link": article_data["article_url"] or source.link,  # Nutzt article_url falls verfügbar
                        "image_url": article_data["image_url"],  # Neu: Bild-URL verwenden
                        "moddate": date_value,
                        "date": date_value,
                    }

                     # Check for duplicates
                    if html_article_exists(article_entry["title"], source):
                        continue  # Skip if duplicate exists

                    # Convert dictionary to object-like structure
                    entry_object = DictToObject(article_entry)
                    
                    # Pass entry_object to write_article
                    write_article(entry_object, source, tagging_engine)
                    counter += 1

            except Exception as e:
                logger.error(f"Error processing hansestadt-lueneburg.de source: {str(e)}")
            continue

        text = ""
        sanitized_text  = ""
        feed  = ""
        parser  = "" 
        s = "{} - {}".format(source.name, source.link)

        # Get source data
        try:
            response = requests.get(source.link)
            response.encoding = 'utf-8'  # Setze die Kodierung explizit auf UTF-8
            text = response.text
        except Exception as e:
            logger.info(f"Error while getting HTML code of source {s}: {str(e)}")
            continue
        
        # Sanitize source data
        try:
            sanitized_text = etree.tostring(
                etree.fromstring(text.encode('utf-8'), parser=xml_parser)
            )
        except Exception as e:
            # logger.error(f"Error while parsing to string for source {s}: {str(e)}")
            # Log the problematic text for debugging
            # logger.error(f"Problematic feed content: {text[:500]}...")  # Log first 500 chars
            # logger.error(sanitized_text)
            continue
        
        # Parse source data
        try:
            feed = feedparser.parse(sanitized_text)

        except Exception as e:
            logger.error(f"Error while parsing sanitized_text for source {s}: {str(e)}")
            logger.error(traceback.format_exc())
            continue

        # Get parser function
        try:
            parser = get_parser_function(source.parser)
        except Exception as e:
            logger.error(f"Error while getting parser function for source {s}: {str(e)}")
            logger.error(traceback.format_exc())
            continue
 
        # iterate through all entries
        for entry in feed.entries:

            if not has_title(entry):
                #logger.info("Article has not title, skipping...")
                continue

            try:
                #add_date(entry)
                if parser:
                    entry_parsed = parser(entry)
                else:
                    entry_parsed = entry

                # Check if entry_parsed is None
                if entry_parsed is None:
                    logger.error(f"Error: Parsed entry is None for feed entry {entry}")
                    continue

            except Exception as e:
                # ToDo: log error
                # logger.error(f"Error while parsing entry: {str(e)}")
                # logger.error(traceback.format_exc())
                continue
            
            try:
                depublicated = getattr(entry_parsed, "depublicated", None)
                moddate = getattr(entry_parsed, "moddate", None)
                exists = article_exists(entry_parsed)
                summary = getattr(entry_parsed, "summary", None)
                
                if summary:
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
                else:
                    # Handle missing summary case, assign a default value
                    # logger.warning(f"Article {entry_parsed.title} has no summary, assigning default value.")
                    summary = "No summary available"
                    setattr(entry_parsed, "summary", summary)

            except Exception as e:
                logger.error(f"Error while processing entry: {str(e)}")
                logger.error(traceback.format_exc())
                continue
            
            try:
                if exists or depublicated:
                    if exists and depublicated:
                        logger.info(f"deleting {entry_parsed.title} from db")
                        depublicate_article(entry_parsed)
                    if exists and not depublicated and not moddate:
                        pass #logger.info("    skipped, already exists.")
                    if exists and not depublicated and moddate:
                        
                        article = _get_article(entry_parsed)
                        article_date = entry_parsed.statedate or moddate
                        update_article(article, entry_parsed, source, article_date, moddate=moddate)
                    continue
                else:
                    write_article(entry_parsed, source, tagging_engine)
                    counter += 1

            except Exception as e:
                logger.error(f"Error while handling article existence: {str(e)}")
                logger.error(traceback.format_exc())
                continue

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


class DictToObject:
    def __init__(self, dictionary):
        # Store the dictionary internally
        self._dict = dictionary
        for key, value in dictionary.items():
            setattr(self, key, value)

    def get(self, key, default=None):
        return getattr(self, key, default)

    # Add dictionary-like methods
    def items(self):
        return self._dict.items()

    def keys(self):
        return self._dict.keys()

    def values(self):
        return self._dict.values()

    def __iter__(self):
        # Allows iteration over keys, just like a dictionary
        return iter(self._dict)

    def __contains__(self, item):
        # Allows use of `in` keyword to check for keys
        return item in self._dict
    
    def __getitem__(self, key):
        # Allows getting values using square brackets
        return getattr(self, key, None)
    
    def __setitem__(self, key, value):
        # Allows setting values using square brackets
        setattr(self, key, value)
    
    def to_string(self):
        return str(self._dict)