"""Drop Video.category (videos don't share article categories) and add
Video.views which mirrors Bunny's per-video view counter."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0006_likes_comments'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='video',
            name='category',
        ),
        migrations.AddField(
            model_name='video',
            name='views',
            field=models.PositiveIntegerField(
                default=0,
                help_text='View count mirrored from Bunny on each metadata '
                          'sync.',
            ),
        ),
    ]
