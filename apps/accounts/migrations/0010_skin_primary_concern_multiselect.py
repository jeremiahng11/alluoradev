from django.db import migrations, models


class Migration(migrations.Migration):
    """skin_primary_concern is now a comma-separated multi-select rather
    than a single-choice CharField. Bump max_length and drop the
    choices constraint — the field stores any subset of the allowed
    slugs (validated at the API boundary, not by the DB)."""

    dependencies = [
        ('accounts', '0009_appuser_skin_profile'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appuser',
            name='skin_primary_concern',
            field=models.CharField(
                blank=True, default='', max_length=128,
                help_text=(
                    'Comma-separated concern slugs: any of '
                    'hydration, aging, acne, brightening, sensitivity'
                ),
            ),
        ),
    ]
