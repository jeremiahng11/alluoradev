"""Video records — metadata for content uploaded to Bunny Stream.

The actual video bytes live on Bunny. We store the GUID + display metadata.
"""
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
    is_published = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)

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
    def hls_url(self) -> str:
        from .bunny import hls_url
        return hls_url(self.bunny_video_guid)

    @property
    def thumbnail_url(self) -> str:
        from .bunny import thumbnail_url
        return thumbnail_url(self.bunny_video_guid)
