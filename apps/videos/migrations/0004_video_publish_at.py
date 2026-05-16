from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0003_video_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='video',
            name='publish_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Optional. If set in the future, the video stays '
                          'hidden from the app until this moment, then '
                          'auto-appears.',
                null=True,
            ),
        ),
    ]
