from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='appuser',
            name='card_number_prefix',
            field=models.CharField(
                blank=True,
                help_text='8-digit prefix; combined with last 4 of wp_user_id to form the visible membership card number.',
                max_length=8,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name='appuser',
            name='tier',
            field=models.CharField(
                choices=[
                    ('Silver', 'Silver'),
                    ('Gold', 'Gold'),
                    ('Platinum', 'Platinum'),
                    ('Titanium', 'Titanium'),
                ],
                default='Silver',
                help_text='Membership tier — managed on Django, not WordPress.',
                max_length=24,
            ),
        ),
    ]
