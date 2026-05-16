"""Add VideoLike + VideoComment models and Video.comments_enabled."""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0005_video_is_published_default_true'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='video',
            name='comments_enabled',
            field=models.BooleanField(
                default=True,
                help_text='If unticked, the app hides the comment field and '
                          'posting a comment returns 403. Existing comments '
                          'are preserved.',
            ),
        ),
        migrations.CreateModel(
            name='VideoLike',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='video_likes',
                    to=settings.AUTH_USER_MODEL)),
                ('video', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='likes',
                    to='videos.video')),
            ],
            options={
                'unique_together': {('user', 'video')},
                'indexes': [models.Index(
                    fields=['video', '-created_at'],
                    name='videos_vide_video_i_e35f5b_idx')],
            },
        ),
        migrations.CreateModel(
            name='VideoComment',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID')),
                ('body', models.TextField(max_length=2000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='video_comments',
                    to=settings.AUTH_USER_MODEL)),
                ('video', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='comments',
                    to='videos.video')),
            ],
            options={
                'ordering': ('-created_at',),
                'indexes': [models.Index(
                    fields=['video', '-created_at'],
                    name='videos_vide_video_i_b9d6a8_idx')],
            },
        ),
    ]
