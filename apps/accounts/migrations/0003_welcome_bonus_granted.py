from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_card_number_prefix_and_tier'),
    ]

    operations = [
        migrations.AddField(
            model_name='appuser',
            name='welcome_bonus_granted',
            field=models.BooleanField(
                default=False,
                help_text='True once the 500-point Silver welcome bonus has been '
                          'pushed to the WP rewards plugin via the bridge.',
            ),
        ),
    ]
