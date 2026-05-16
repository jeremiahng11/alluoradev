from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0001_initial'),
        ('videos', '0002_video_min_tier'),
    ]

    operations = [
        migrations.AddField(
            model_name='video',
            name='category',
            field=models.ForeignKey(
                blank=True,
                help_text='Cross-app taxonomy shared with articles. Optional.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='videos',
                to='content.contentcategory',
            ),
        ),
    ]
