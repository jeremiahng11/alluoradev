"""ArticleView — one record per article open, drives the admin stats
dashboard's article metrics."""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ArticleView',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('article', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='view_events',
                    to='content.article')),
                ('user', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=models.deletion.SET_NULL,
                    related_name='article_views',
                    to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at',),
                'indexes': [
                    models.Index(
                        fields=['article', '-created_at'],
                        name='content_view_article_a1b2c3_idx'),
                    models.Index(
                        fields=['user', '-created_at'],
                        name='content_view_user_d4e5f6_idx'),
                ],
            },
        ),
    ]
