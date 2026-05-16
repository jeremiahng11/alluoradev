from django.db import migrations, models


class Migration(migrations.Migration):
    """Flag scans where DeepFace couldn't read a face age (skin_age
    None) so the result screen can show a "low confidence — retake in
    better light" banner instead of pretending the numbers are reliable."""

    dependencies = [
        ('skinai', '0004_skinanalysis_original_photo'),
    ]

    operations = [
        migrations.AddField(
            model_name='skinanalysis',
            name='low_confidence',
            field=models.BooleanField(default=False),
        ),
    ]
