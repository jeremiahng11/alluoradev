from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

import apps.content.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('content', '0003_rename_content_view_article_a1b2c3_idx_content_art_article_f9e4fb_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Ebook',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('slug', models.SlugField(blank=True, max_length=220, unique=True)),
                ('description', models.TextField(blank=True, help_text='Shown on the Library card + ebook detail sheet.')),
                ('author_name', models.CharField(blank=True, default='', help_text='Optional byline shown under the title.', max_length=120)),
                ('cover_image', models.ImageField(blank=True, null=True, upload_to='ebooks/covers/')),
                ('cover_image_url', models.URLField(blank=True, default='', help_text='External URL alternative to uploaded cover_image.')),
                ('pdf_file', models.FileField(help_text="PDF up to ~50 MB. Filename is hidden behind a random token subdir so it can't be enumerated.", upload_to=apps.content.models._ebook_pdf_upload_to)),
                ('pdf_size_bytes', models.PositiveBigIntegerField(default=0)),
                ('page_count', models.PositiveSmallIntegerField(default=0, help_text='Optional. Shown next to file size on the card.')),
                ('is_members_only', models.BooleanField(default=False, help_text='When true, only signed-in app users can download. Guests see a lock badge + join CTA.')),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('published', 'Published')], default='draft', max_length=12)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('download_count', models.PositiveIntegerField(default=0, help_text='Lifetime download count — incremented by the download endpoint. EbookDownload rows have the full audit trail.')),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ebooks', to='content.contentcategory')),
            ],
            options={
                'ordering': ('-published_at', '-created_at'),
                'indexes': [
                    models.Index(fields=['status', '-published_at'], name='content_ebo_status_5b6e3a_idx'),
                    models.Index(fields=['is_members_only'], name='content_ebo_is_memb_2d8c91_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='EbookDownload',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ebook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='download_events', to='content.ebook')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ebook_downloads', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at',),
                'indexes': [
                    models.Index(fields=['ebook', '-created_at'], name='content_ebo_ebook_i_71fd2a_idx'),
                    models.Index(fields=['user', '-created_at'], name='content_ebo_user_id_a4c9e3_idx'),
                ],
            },
        ),
    ]
