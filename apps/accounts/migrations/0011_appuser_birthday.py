from django.db import migrations, models


class Migration(migrations.Migration):
    """Optional birthday on AppUser. The Skin AI insight engine uses
    it to compare the DeepFace-estimated skin age against the user's
    real age — "your skin reads N years older/younger than you" — and
    tailor the recommendation copy accordingly. Nullable; the engine
    falls back to skin_age-only language when unset."""

    dependencies = [
        ('accounts', '0010_skin_primary_concern_multiselect'),
    ]

    operations = [
        migrations.AddField(
            model_name='appuser',
            name='birthday',
            field=models.DateField(blank=True, null=True),
        ),
    ]
