from django.db import migrations, models


class Migration(migrations.Migration):
    """Store the hi-res original photo alongside the thumbnail so the
    admin dashboard can show the full image when reviewing a scan. The
    original is never exposed via /media/ — it streams through an auth-
    gated view (dashboard:skin-ai-analysis-original)."""

    dependencies = [
        ('skinai', '0003_drop_hidden_from_admin'),
    ]

    operations = [
        migrations.AddField(
            model_name='skinanalysis',
            name='original_photo',
            field=models.ImageField(
                blank=True, null=True,
                upload_to='skinai/originals/%Y/%m/',
                help_text=(
                    'Hi-res JPEG of the analysed face (already capped to '
                    '1600px on the long side by the Flutter app). EXIF '
                    'rotation is baked in. Streamed only through the '
                    'admin dashboard — never returned by the mobile API.'
                ),
            ),
        ),
    ]
