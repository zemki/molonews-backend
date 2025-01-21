from django.utils.translation import gettext_lazy as _

ORGANIZATION_TYPE_CHOICES = (
    ('news', 'News'),
    ('official', 'Offiziell'),
    ('collective', 'Kollektiv'),
)

V1_ORGANIZATION_TYPE_CHOICES = (
    ("collectives", "Kollektive"),
    ("news", "News"),
)

ARTICLE_TYPE_CHOICES = (
    ('news', 'News'),
    ('event', 'Event')
)

FEEDBACK_CONTACT_TYPE_CHOICES = (
    ('app_feedback', 'App Feedback'),
    ('info_news_feedback', 'Info und News Feedback')
)

RECURRING_EVENT_CHOICES = [
    (0, _("single event")),
    (1, _("regular interval")),
    (2, _("irregular interval")),
]
