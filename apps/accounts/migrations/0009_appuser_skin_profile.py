from django.db import migrations, models


class Migration(migrations.Migration):
    """Two skin-AI personalisation fields on AppUser, captured by the
    in-app onboarding sheet on first scan attempt:
      - skin_sex            — used for sex-aware scoring tweaks
      - skin_primary_concern — used to weight insight copy
    Both default to '' so existing users get a clean blank state and
    the bottom sheet fires for them on their next visit to /skin-ai."""

    dependencies = [
        ('accounts', '0008_alter_alluorasessiontoken_id_alter_tierrule_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='appuser',
            name='skin_sex',
            field=models.CharField(
                blank=True, default='', max_length=12,
                choices=[
                    ('', 'Not set'),
                    ('female', 'Female'),
                    ('male', 'Male'),
                    ('other', 'Prefer not to say'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='appuser',
            name='skin_primary_concern',
            field=models.CharField(
                blank=True, default='', max_length=24,
                choices=[
                    ('', 'Not set'),
                    ('hydration', 'Hydration'),
                    ('aging', 'Anti-aging'),
                    ('acne', 'Acne / breakouts'),
                    ('brightening', 'Brightening'),
                    ('sensitivity', 'Sensitivity / redness'),
                ],
            ),
        ),
    ]
