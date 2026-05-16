"""Editorial content for the Alluora app.

Articles, skincare tips, brand stories. Owned by Django, served to the
Flutter app via /api/v1/content/articles/. Edited via the dashboard.
"""
import secrets

from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils import timezone


class ContentCategory(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('sort_order', 'name')
        verbose_name_plural = 'Content categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Article(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_CHOICES = (
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PUBLISHED, 'Published'),
    )

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    summary = models.CharField(max_length=300, blank=True)
    body = models.TextField(help_text='Markdown allowed.')
    category = models.ForeignKey(
        ContentCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles',
    )
    cover_image = models.ImageField(upload_to='articles/covers/', blank=True, null=True)
    cover_image_url = models.URLField(
        blank=True, default='',
        help_text='External URL alternative to uploaded cover_image.',
    )

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    author = models.ForeignKey(
        'accounts.AppUser', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='authored_articles',
    )

    # Featured flag — surfaces on the app home screen.
    is_featured = models.BooleanField(default=False)

    class Meta:
        ordering = ('-published_at', '-created_at')
        indexes = [
            models.Index(fields=['status', '-published_at']),
            models.Index(fields=['is_featured']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200]
            slug = base
            counter = 1
            while Article.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{counter}'
                counter += 1
            self.slug = slug

        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def cover(self) -> str:
        if self.cover_image:
            return self.cover_image.url
        return self.cover_image_url


def _ebook_pdf_upload_to(instance, filename):
    """Place uploaded PDFs under a per-ebook random subdir so the URL
    can't be enumerated by guessing the slug. We still gate the
    members-only ones server-side, but this stops a casual leak of one
    URL from being a directory listing for the whole library."""
    token = secrets.token_urlsafe(12)
    safe_name = filename.rsplit('/', 1)[-1][-80:] or 'ebook.pdf'
    return f'ebooks/pdfs/{token}/{safe_name}'


class Ebook(models.Model):
    """Downloadable PDF surfaced on the app's Library screen.

    Free ebooks are downloadable by anyone (guests + members). Ones
    flagged `is_members_only=True` only return a download URL to
    authenticated users; the list response shows the lock badge to
    guests. Enforcement also runs on the download view itself so a
    guessed URL still 403s.
    """
    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_CHOICES = (
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PUBLISHED, 'Published'),
    )

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(
        blank=True,
        help_text='Shown on the Library card + ebook detail sheet.',
    )
    author_name = models.CharField(
        max_length=120, blank=True, default='',
        help_text='Optional byline shown under the title.',
    )

    category = models.ForeignKey(
        ContentCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ebooks',
    )

    cover_image = models.ImageField(
        upload_to='ebooks/covers/', blank=True, null=True,
    )
    cover_image_url = models.URLField(
        blank=True, default='',
        help_text='External URL alternative to uploaded cover_image.',
    )
    pdf_file = models.FileField(
        upload_to=_ebook_pdf_upload_to,
        help_text='PDF up to ~50 MB. Filename is hidden behind a random '
                  'token subdir so it can\'t be enumerated.',
    )
    pdf_size_bytes = models.PositiveBigIntegerField(default=0)
    page_count = models.PositiveSmallIntegerField(
        default=0,
        help_text='Optional. Shown next to file size on the card.',
    )

    is_members_only = models.BooleanField(
        default=False,
        help_text='When true, only signed-in app users can download. '
                  'Guests see a lock badge + join CTA.',
    )

    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    download_count = models.PositiveIntegerField(
        default=0,
        help_text='Lifetime download count — incremented by the download '
                  'endpoint. EbookDownload rows have the full audit trail.',
    )

    class Meta:
        ordering = ('-published_at', '-created_at')
        indexes = [
            models.Index(fields=['status', '-published_at']),
            models.Index(fields=['is_members_only']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200]
            slug = base
            counter = 1
            while Ebook.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{counter}'
                counter += 1
            self.slug = slug

        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()

        # Stamp the size off the file when it's first attached / replaced.
        if self.pdf_file and (not self.pdf_size_bytes or 'pdf_file' in
                              (kwargs.get('update_fields') or [])):
            try:
                self.pdf_size_bytes = self.pdf_file.size
            except (FileNotFoundError, ValueError, OSError):
                pass

        super().save(*args, **kwargs)

    @property
    def cover(self) -> str:
        if self.cover_image:
            return self.cover_image.url
        return self.cover_image_url


class EbookDownload(models.Model):
    """One download (or download attempt) of an ebook.

    Aggregated by the dashboard for "most downloaded" lists; per-row
    audit lets us spot abuse (e.g. a single user grinding through every
    PDF in 30 seconds).
    """
    ebook = models.ForeignKey(
        Ebook, on_delete=models.CASCADE, related_name='download_events',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='ebook_downloads',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['ebook', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]


class ArticleView(models.Model):
    """One read-through (or open) of an article from the app.

    Recorded by the article detail screen. Each open is a row; we
    aggregate in the stats dashboard for total views, unique
    readers, and per-day trend.
    """
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='view_events',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='article_views',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['article', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]
