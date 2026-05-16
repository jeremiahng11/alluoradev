"""Video records — metadata for content uploaded to Bunny Stream.

The actual video bytes live on Bunny. We store the GUID + display metadata.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class VideoCollection(models.Model):
    """Optional grouping (e.g. 'Skin Quiz Tutorials', 'Brand Stories')."""
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('sort_order', 'name')

    def __str__(self):
        return self.name


class Video(models.Model):
    STATUS_CREATED = 'created'      # Video object created in Bunny, no upload yet
    STATUS_UPLOADING = 'uploading'
    STATUS_PROCESSING = 'processing'
    STATUS_READY = 'ready'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_CREATED, 'Created'),
        (STATUS_UPLOADING, 'Uploading'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_READY, 'Ready'),
        (STATUS_FAILED, 'Failed'),
    )

    # Minimum membership tier required to play this video. `none` = visible
    # to guests AND every member tier. Higher tiers stack: Gold members
    # see Silver+Gold videos; Platinum sees Silver+Gold+Platinum; etc.
    TIER_NONE = 'none'
    TIER_SILVER = 'Silver'
    TIER_GOLD = 'Gold'
    TIER_PLATINUM = 'Platinum'
    TIER_TITANIUM = 'Titanium'
    MIN_TIER_CHOICES = (
        (TIER_NONE, 'Public (everyone, including guests)'),
        (TIER_SILVER, 'Silver members and up'),
        (TIER_GOLD, 'Gold members and up'),
        (TIER_PLATINUM, 'Platinum members and up'),
        (TIER_TITANIUM, 'Titanium members only'),
    )
    # Numeric ranks for filtering — higher number = more exclusive.
    TIER_RANKS = {
        TIER_NONE: 0,
        TIER_SILVER: 1,
        TIER_GOLD: 2,
        TIER_PLATINUM: 3,
        TIER_TITANIUM: 4,
    }

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    bunny_video_guid = models.CharField(
        max_length=64, unique=True,
        help_text='GUID returned by Bunny Stream Create Video.',
    )
    collection = models.ForeignKey(
        VideoCollection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='videos',
    )

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_CREATED)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    views = models.PositiveIntegerField(
        default=0,
        help_text='View count mirrored from Bunny on each metadata sync.',
    )
    is_published = models.BooleanField(
        default=True,
        help_text='Visible to the app once Bunny processing is done. '
                  'Untick to hide a video from users without deleting it.',
    )
    is_featured = models.BooleanField(default=False)
    is_reel = models.BooleanField(
        default=False,
        help_text='Short-form (20-90s). Reels are managed in the Reel admin '
                  'section, never have a collection, and feed the Reel tab '
                  'on the app. Regular videos (is_reel=False) feed the '
                  'Videos page.',
    )
    comments_enabled = models.BooleanField(
        default=True,
        help_text='If unticked, the app hides the comment field and posting '
                  'a comment returns 403. Existing comments are preserved.',
    )
    min_tier = models.CharField(
        max_length=16, choices=MIN_TIER_CHOICES, default=TIER_NONE,
        help_text='Lowest tier that can watch this video. Guests = none.',
    )
    publish_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Optional. If set in the future, the video stays hidden '
                  'from the app until this moment, then auto-appears.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['is_published', '-created_at']),
            models.Index(fields=['is_featured']),
        ]

    def __str__(self):
        return self.title

    @property
    def min_tier_rank(self) -> int:
        return self.TIER_RANKS.get(self.min_tier, 0)

    @property
    def hls_url(self) -> str:
        from .bunny import hls_url
        return hls_url(self.bunny_video_guid)

    @property
    def thumbnail_url(self) -> str:
        from .bunny import thumbnail_url
        return thumbnail_url(self.bunny_video_guid)

    @property
    def mp4_url(self) -> str:
        from .bunny import mp4_url
        return mp4_url(self.bunny_video_guid)


class VideoLike(models.Model):
    """A user's like on a video. The (user, video) pair is unique — a
    second POST from the same user toggles it off via DELETE-on-conflict
    in the view."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='video_likes',
    )
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name='likes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (('user', 'video'),)
        indexes = [models.Index(fields=['video', '-created_at'])]


class VideoComment(models.Model):
    """A user comment on a video. Admins can soft-delete via the
    dashboard; we hard-delete here since we don't need an audit trail."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='video_comments',
    )
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [models.Index(fields=['video', '-created_at'])]

    def __str__(self):
        return f'{self.user_id} on {self.video_id}'


class VideoView(models.Model):
    """One watch session for a video or reel.

    The app generates a `session_id` (UUID) once per watch session and
    sends it with every track POST. The server upserts on
    (video, session_id), so multiple POSTs from the same session
    (open, threshold-cross, close) update one row instead of inflating
    the view count. Subsequent POSTs only update seconds_watched and
    completed; only the *first* POST of a session bumps Video.views.

    `is_reel` is denormalised onto each row so dashboard aggregations
    can split video vs reel without a join. `completed` flips to True
    once seconds_watched >= 95% of the source duration (computed by
    the track endpoint, not the client).
    """
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name='view_events',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='video_views',
    )
    session_id = models.CharField(
        max_length=64, blank=True, default='',
        help_text='Client-generated UUID per watch session. Used to '
                  'dedupe repeated track POSTs from one session.',
    )
    seconds_watched = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    is_reel = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        constraints = [
            # session_id is unique per video when set. Empty string is
            # allowed multiple times (legacy rows / clients that don't
            # send a session_id will just append).
            models.UniqueConstraint(
                fields=['video', 'session_id'],
                condition=models.Q(session_id__gt=''),
                name='videoview_unique_session',
            ),
        ]
        indexes = [
            models.Index(fields=['video', '-created_at']),
            models.Index(fields=['is_reel', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]
