"""Add Video.is_reel — short-form 30-90s clips that feed the app's
Reel tab, separate from regular videos."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0007_drop_category_add_views'),
    ]

    operations = [
        migrations.AddField(
            model_name='video',
            name='is_reel',
            field=models.BooleanField(
                default=False,
                help_text='Short-form (30-90s). Reels are managed in the '
                          'Reel admin section, never have a collection, '
                          'and feed the Reel tab on the app. Regular '
                          'videos (is_reel=False) feed the Videos page.',
            ),
        ),
    ]
