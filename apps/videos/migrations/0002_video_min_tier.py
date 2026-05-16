from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='video',
            name='min_tier',
            field=models.CharField(
                choices=[
                    ('none', 'Public (everyone, including guests)'),
                    ('Silver', 'Silver members and up'),
                    ('Gold', 'Gold members and up'),
                    ('Platinum', 'Platinum members and up'),
                    ('Titanium', 'Titanium members only'),
                ],
                default='none',
                help_text='Lowest tier that can watch this video. Guests = none.',
                max_length=16,
            ),
        ),
    ]
