from bs4 import BeautifulSoup
from datetime import datetime
from locale import LC_TIME, setlocale
from logging import getLogger
from django.utils.timezone import get_current_timezone, make_aware, is_aware


def _cook(entry_string, parser='lxml'):
    """Create a bs object to parse a feed entry string.

    Args:
        entry_string (str): entry as string

    Returns:
        BeautfulSoup object
    """
    return BeautifulSoup(entry_string, features=parser)


def sanitize_title(title):
    """ Shorten title if necessary

    Args:
        title (str): title string

    Returns:
        sanitized title
    """
    if len(title) > 300:
        return title[0:297] + '...'
    return title


def sanitize_link(link):
    """Remove extra 'https://*' from a link

    Args:
        link (str): link to sanitize

    Returns:
        sanitized link
    """
    if link.startswith("https"):
        link = 'https:{}'.format(link.split("https")[-1].lstrip(":"))
    return link


def sanitize_attribute(attribute_name, sanitize_function, target_object):
    """Sanitize an attribute of an object with a given function.

    Args:
        attribute_name (str): name of targe attribute
        sanitize_function (def): target function
        target_object (object): target entry object

    Returns:
        object with sanitized attribute
    """
    if hasattr(target_object, attribute_name) and getattr(target_object, attribute_name):
        setattr(target_object, attribute_name, sanitize_function(getattr(target_object, attribute_name)))
    return target_object


def sanitize_attributes(entry, attributes):
    """Sanitize all given attributes on an entry object.

      Args:
          entry (object): article entry from feed
          attributes (dict): dict of attributes to be sanitized including sanitize method

      Returns:
        sanitized entry object
      """
    for attribute, sanitize_method in attributes.items():
        entry = sanitize_attribute(attribute, sanitize_method, entry)
    return entry


def parse_date(date_string, scheme="%a %b %d %H:%M:%S %Z %Y"):
    """Parse a time string.

    Args:
        date_string (str): timestring

    Returns:
        timezone aware dateime or None
    """
    if not date_string:
        return None

    _locale = setlocale(LC_TIME)
    try:
        setlocale(LC_TIME, "C")
        _date = datetime.strptime(date_string, scheme)
    finally:
        setlocale(LC_TIME, _locale)
    if is_aware(_date):
        return _date
    return make_aware(_date, get_current_timezone())


def _taz(entry):
    soup = _cook(entry.description)
    entry.title = entry.title.strip(': ')
    if soup.img:
        entry.image_url = soup.img.attrs['src']
    entry.summary = soup.body.text
    return entry


def _weser(entry):
    soup = _cook(entry.summary)
    entry.summary = soup.p.text
    return entry


def _bremen_de(entry):
    soup = _cook(entry.summary, parser='html.parser')
    entry.summary = soup.text
    attributes = {
        "link": sanitize_link, "image_url": sanitize_link,
    }
    entry = sanitize_attributes(entry, attributes)
    return entry


def _generic(entry):
    soup = _cook(entry.summary, parser='html.parser')
    entry.summary = soup.text
    attributes = {
        "link": sanitize_link, "image_url": sanitize_link, "title": sanitize_title
    }
    entry = sanitize_attributes(entry, attributes)
    return entry


def _rss_events(entry):
    # TODO refine
    soup = _cook(entry.summary, parser='html.parser')
    entry.summary = soup.text
    attributes = {
        "link": sanitize_link, "image_url": sanitize_link,
    }
    entry = sanitize_attributes(entry, attributes)
    entry.event = True
    return entry


def _hochschule(entry):
    entry["summary"] = entry.title
    return entry


def _buergerschaft(entry):
    """Parser for Bremische Bürgerschaft Feed

    Args:
        entry (object): entry from bremische buergerschaft feed

    Returns:
        parsed entry object
    """
    # adapt link url (see Ticket 124)
    entry.link = entry.link + '&noMobile=1'
    return entry


def _buten_un_binnen(entry):
    """Buten un Binnen Feedparser.

    Args:
        entry (object): entry from bremische buergerschaft feed

    Returns:
        parsed entry object
    """
    
    entry.depublicated = False
    _depublicated = getattr(entry, 'deleted', False)
    if _depublicated and _depublicated != 'false':
        entry.depublicated = True
    entry.foreign_id = entry.id
    entry.image_source = entry['source'].get('title', None)
    entry.moddate = parse_date(getattr(entry, 'moddate', None))
    entry.statedate = parse_date(getattr(entry, 'statedate', None))
    return entry


def _regional_nachrichten(entry):
    """Regional Nachrichten Feedparser
        Dummy parser to force usage of default image

    Args:
        entry (object): entry from bremische buergerschaft feed

    Returns:
        parsed entry object
    """
    entry = _generic(entry)
    setattr(entry, 'force_default_image', True)
    return entry


def _weserkurier(entry):
    """Weserkurier Feedparser

    Args:
        entry (object): entry from feed

    Returns:
        parsed entry object
    """
    entry = _generic(entry)
    entry["published"] = parse_date(entry['published'], scheme="%a, %d %b %Y %H:%M:%S %z")
    entry["moddate"] = parse_date(entry['moddate'], scheme="%a, %d %b %Y %H:%M:%S %z")
    entry.statedate = parse_date(getattr(entry, 'statedate', None))
    return entry


parsers = {
    'taz': {
        'description': 'TAZ Parser',
        'func': _taz,
    },
    'weser': {
        'description': 'Weser Report Parser',
        'func': _weser,
    },
    'bremen.de': {
        'description': 'Bremen.de Parser',
        'func': _bremen_de,
    },
    'buergerschaft': {
        'description': 'Bremische Bürgerschaft Parser',
        'func': _buergerschaft,
    },
    'generic': {
        'description': 'Generic html Parser',
        'func': _generic,
    },
    'events': {
      'description': 'Parse to events',
      'func': _rss_events,
    },
    'hochschule': {
        'description': 'Hochschule Parser',
        'func': _hochschule,
    },
    'ButenUnBinnen': {
        'description': 'Buten un Binnen',
        'func': _buten_un_binnen,
    },
    'RegionalNachrichten': {
        'description': 'Regional-Nachrichten',
        'func': _regional_nachrichten,
    },
    'Weserkurier': {
        'description': 'Weserkurier',
        'func': _weserkurier,
    }
}


def get_parser_function(parser_name):
    """Get a bs parser function by parser name

    Args:
        parser_name (str): name of custom parser, defaults to "generic"

    Returns:
        parser or None
    """
    if parser_name:
        parser = parsers.get(parser_name, None)
        if parser:
            return parser["func"]
    return parsers["generic"]["func"]
