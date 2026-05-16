"""Add VideoView.session_id + a partial-unique constraint on
(video, session_id) so repeated track POSTs from the same client
session update one row instead of inflating the view count."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0009_videoview'),
    ]

    operations = [
        migrations.AddField(
            model_name='videoview',
            name='session_id',
            field=models.CharField(
                blank=True, default='', max_length=64,
                help_text='Client-generated UUID per watch session. Used '
                          'to dedupe repeated track POSTs from one '
                          'session.',
            ),
        ),
        migrations.AddConstraint(
            model_name='videoview',
            constraint=models.UniqueConstraint(
                condition=models.Q(session_id__gt=''),
                fields=('video', 'session_id'),
                name='videoview_unique_session',
            ),
        ),
    ]
