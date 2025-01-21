# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey has `on_delete` set to the desired behavior.
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission_id = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission_id'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class ContentAppuser(models.Model):
    device_id = models.CharField(unique=True, max_length=300)
    firebase_token = models.CharField(max_length=300, blank=True, null=True)
    ordering = models.CharField(max_length=100)
    push_collective = models.BooleanField()
    push_news = models.BooleanField()
    location_latitude = models.DecimalField(max_digits=22, decimal_places=16, blank=True, null=True)
    location_longitude = models.DecimalField(max_digits=22, decimal_places=16, blank=True, null=True)
    push_official = models.BooleanField(blank=True, null=True)
    filter_events_by_source = models.BooleanField()
    location_radius = models.DecimalField(max_digits=11, decimal_places=5, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'content_appuser'


class ContentAppuserArchivedArticles(models.Model):
    appuser = models.ForeignKey(ContentAppuser, models.DO_NOTHING)
    article = models.ForeignKey('ContentArticle', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_appuser_archived_articles'
        unique_together = (('appuser', 'article'),)


class ContentAppuserArchivedEvents(models.Model):
    appuser = models.ForeignKey(ContentAppuser, models.DO_NOTHING)
    event = models.ForeignKey('ContentEvent', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_appuser_archived_events'
        unique_together = (('appuser', 'event'),)


class ContentAppuserBookmarkedArticles(models.Model):
    appuser = models.ForeignKey(ContentAppuser, models.DO_NOTHING)
    article = models.ForeignKey('ContentArticle', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_appuser_bookmarked_articles'
        unique_together = (('appuser', 'article'),)


class ContentAppuserBookmarkedEvents(models.Model):
    appuser = models.ForeignKey(ContentAppuser, models.DO_NOTHING)
    event = models.ForeignKey('ContentEvent', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_appuser_bookmarked_events'
        unique_together = (('appuser', 'event'),)


class ContentAppuserDeselectedOrganization(models.Model):
    appuser = models.ForeignKey(ContentAppuser, models.DO_NOTHING)
    organization = models.ForeignKey('ContentOrganization', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_appuser_deselected_organization'
        unique_together = (('appuser', 'organization'),)


class ContentAppuserDeselectedOrganizationAllTags(models.Model):
    appuser = models.ForeignKey(ContentAppuser, models.DO_NOTHING)
    organization = models.ForeignKey('ContentOrganization', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_appuser_deselected_organization_all_tags'
        unique_together = (('appuser', 'organization'),)


class ContentAppuserOrganization(models.Model):
    appuser = models.ForeignKey(ContentAppuser, models.DO_NOTHING)
    organization = models.ForeignKey('ContentOrganization', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_appuser_organization'
        unique_together = (('appuser', 'organization'),)


class ContentAppuserOrganizationAllTags(models.Model):
    appuser = models.ForeignKey(ContentAppuser, models.DO_NOTHING)
    organization = models.ForeignKey('ContentOrganization', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_appuser_organization_all_tags'
        unique_together = (('appuser', 'organization'),)


class ContentAppuserTags(models.Model):
    appuser = models.ForeignKey(ContentAppuser, models.DO_NOTHING)
    tag = models.ForeignKey('ContentTag', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_appuser_tags'
        unique_together = (('appuser', 'tag'),)


class ContentArea(models.Model):
    area_name = models.CharField(max_length=100)
    area_latitude = models.DecimalField(max_digits=22, decimal_places=16, blank=True, null=True)
    area_longitude = models.DecimalField(max_digits=22, decimal_places=16, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'content_area'


class ContentArticle(models.Model):
    title = models.CharField(max_length=350)
    abstract = models.TextField(blank=True, null=True)
    content = models.TextField()
    date = models.DateTimeField()
    moddate = models.DateTimeField()
    link = models.CharField(unique=True, max_length=600, blank=True, null=True)
    foreign_id = models.CharField(unique=True, max_length=600, blank=True, null=True)
    image_url = models.CharField(max_length=1000, blank=True, null=True)
    image = models.CharField(max_length=100, blank=True, null=True)
    image_detail = models.CharField(max_length=100, blank=True, null=True)
    image_source = models.CharField(max_length=600, blank=True, null=True)
    address = models.CharField(max_length=300)
    source = models.ForeignKey('ContentSource', models.DO_NOTHING)
    published = models.BooleanField()
    reviewed = models.BooleanField()
    up_for_review = models.BooleanField()
    draft = models.BooleanField()
    is_hot = models.BooleanField()
    push_notification_sent = models.BooleanField()
    push_notification_queued = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'content_article'


class ContentArticleTags(models.Model):
    article = models.ForeignKey(ContentArticle, models.DO_NOTHING)
    tag = models.ForeignKey('ContentTag', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_article_tags'
        unique_together = (('article', 'tag'),)


class ContentCategory(models.Model):
    name = models.CharField(max_length=100)
    rank = models.IntegerField()
    description = models.TextField()
    title = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'content_category'


class ContentEvent(models.Model):
    title = models.CharField(max_length=300)
    content = models.TextField()
    date = models.DateTimeField()
    moddate = models.DateTimeField()
    link = models.CharField(unique=True, max_length=300, blank=True, null=True)
    foreign_id = models.CharField(unique=True, max_length=300, blank=True, null=True)
    image_url = models.CharField(max_length=300, blank=True, null=True)
    image = models.CharField(max_length=100, blank=True, null=True)
    image_source = models.CharField(max_length=200, blank=True, null=True)
    zip_code = models.IntegerField(blank=True, null=True)
    address = models.CharField(max_length=300)
    event_location = models.CharField(max_length=100, blank=True, null=True)
    source = models.ForeignKey('ContentSource', models.DO_NOTHING)
    published = models.BooleanField()
    event_date = models.DateTimeField()
    event_end_date = models.DateTimeField(blank=True, null=True)
    recurring_event_end_date = models.DateField(blank=True, null=True)
    is_child = models.BooleanField()
    reviewed = models.BooleanField()
    up_for_review = models.BooleanField()
    draft = models.BooleanField()
    recurring = models.IntegerField()
    recurrences = models.TextField(blank=True, null=True)
    auto_generated = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'content_event'


class ContentEventTags(models.Model):
    event = models.ForeignKey(ContentEvent, models.DO_NOTHING)
    tag = models.ForeignKey('ContentTag', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_event_tags'
        unique_together = (('event', 'tag'),)


class ContentEventchild(models.Model):
    event_date = models.DateTimeField()
    event_end_date = models.DateTimeField(blank=True, null=True)
    parent = models.ForeignKey(ContentEvent, models.DO_NOTHING)
    auto_generated = models.BooleanField()
    event = models.ForeignKey(ContentEvent, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'content_eventchild'


class ContentOrganization(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    address = models.TextField()
    type = models.CharField(max_length=10)
    image = models.CharField(max_length=100, blank=True, null=True)
    homepage = models.CharField(max_length=300, blank=True, null=True)
    title = models.CharField(max_length=100, blank=True, null=True)
    active = models.BooleanField()
    street = models.TextField()
    town = models.TextField()
    zip = models.TextField()

    class Meta:
        managed = False
        db_table = 'content_organization'


class ContentSource(models.Model):
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=100)
    active = models.BooleanField()
    parser = models.CharField(max_length=20, blank=True, null=True)
    link = models.CharField(max_length=300, blank=True, null=True)
    import_date = models.DateTimeField(blank=True, null=True)
    import_errors = models.TextField(blank=True, null=True)
    organization = models.ForeignKey(ContentOrganization, models.DO_NOTHING, blank=True, null=True)
    default_category = models.ForeignKey(ContentCategory, models.DO_NOTHING)
    default_published = models.BooleanField()
    default_image_url = models.CharField(max_length=300, blank=True, null=True)
    default_image = models.CharField(max_length=100, blank=True, null=True)
    default_image_detail = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'content_source'


class ContentSourceDefaultTags(models.Model):
    source = models.ForeignKey(ContentSource, models.DO_NOTHING)
    tag = models.ForeignKey('ContentTag', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_source_default_tags'
        unique_together = (('source', 'tag'),)


class ContentTag(models.Model):
    name = models.CharField(max_length=30)
    category = models.ForeignKey(ContentCategory, models.DO_NOTHING)
    color = models.CharField(max_length=10)

    class Meta:
        managed = False
        db_table = 'content_tag'


class ContentUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.BooleanField()
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.BooleanField()
    is_active = models.BooleanField()
    date_joined = models.DateTimeField()
    can_publish = models.BooleanField()
    can_modify_organization_info = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'content_user'


class ContentUserGroups(models.Model):
    user = models.ForeignKey(ContentUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_user_groups'
        unique_together = (('user', 'group'),)


class ContentUserSources(models.Model):
    user = models.ForeignKey(ContentUser, models.DO_NOTHING)
    source = models.ForeignKey(ContentSource, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_user_sources'
        unique_together = (('user', 'source'),)


class ContentUserUserPermissions(models.Model):
    user = models.ForeignKey(ContentUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'content_user_user_permissions'
        unique_together = (('user', 'permission'),)


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.SmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(ContentUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class JetBookmark(models.Model):
    url = models.CharField(max_length=200)
    title = models.CharField(max_length=255)
    user = models.IntegerField()
    date_add = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'jet_bookmark'


class JetPinnedapplication(models.Model):
    app_label = models.CharField(max_length=255)
    user = models.IntegerField()
    date_add = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'jet_pinnedapplication'


class RecurrenceDate(models.Model):
    mode = models.BooleanField()
    dt = models.DateTimeField()
    recurrence = models.ForeignKey('RecurrenceRecurrence', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'recurrence_date'


class RecurrenceParam(models.Model):
    param = models.CharField(max_length=16)
    value = models.IntegerField()
    index = models.IntegerField()
    rule = models.ForeignKey('RecurrenceRule', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'recurrence_param'


class RecurrenceRecurrence(models.Model):
    dtstart = models.DateTimeField(blank=True, null=True)
    dtend = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'recurrence_recurrence'


class RecurrenceRule(models.Model):
    mode = models.BooleanField()
    freq = models.IntegerField()
    interval = models.IntegerField()
    wkst = models.IntegerField(blank=True, null=True)
    count = models.IntegerField(blank=True, null=True)
    until = models.DateTimeField(blank=True, null=True)
    recurrence = models.ForeignKey(RecurrenceRecurrence, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'recurrence_rule'


class UserCount(models.Model):
    timestamp = models.DateTimeField()
    count = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'user_count'
