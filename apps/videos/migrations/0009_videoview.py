"""VideoView — one watch session per row, used for the admin stats
dashboard (total views, completion rate, drop-off curves)."""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0008_video_is_reel'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VideoView',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID')),
                ('seconds_watched', models.PositiveIntegerField(default=0)),
                ('completed', models.BooleanField(default=False)),
                ('is_reel', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=models.deletion.SET_NULL,
                    related_name='video_views',
                    to=settings.AUTH_USER_MODEL)),
                ('video', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='view_events',
                    to='videos.video')),
            ],
            options={
                'ordering': ('-created_at',),
                'indexes': [
                    models.Index(
                        fields=['video', '-created_at'],
                        name='videos_view_video_i_a1b2c3_idx'),
                    models.Index(
                        fields=['is_reel', '-created_at'],
                        name='videos_view_isreel_d4e5f6_idx'),
                    models.Index(
                        fields=['user', '-created_at'],
                        name='videos_view_user_i_g7h8i9_idx'),
                ],
            },
        ),
    ]
