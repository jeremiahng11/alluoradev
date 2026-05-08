"""Editorial content for the Alluora app.

Articles, skincare tips, brand stories. Owned by Django, served to the
Flutter app via /api/v1/content/articles/. Edited via the dashboard.
"""
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
