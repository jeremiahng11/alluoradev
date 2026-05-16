from django.db import migrations, models


class Migration(migrations.Migration):
    """Flip Video.is_published default from False to True so admin-uploaded
    videos go live as soon as Bunny processing completes, instead of
    needing a follow-up edit. Existing rows are not changed — only the
    default for newly-inserted rows."""

    dependencies = [
        ('videos', '0004_video_publish_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='video',
            name='is_published',
            field=models.BooleanField(
                default=True,
                help_text='Visible to the app once Bunny processing is done. '
                          'Untick to hide a video from users without deleting it.',
            ),
        ),
    ]
