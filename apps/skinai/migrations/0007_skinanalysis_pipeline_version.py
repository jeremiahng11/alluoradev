from django.db import migrations, models


class Migration(migrations.Migration):
    """Versions the scoring pipeline so the in-app result + admin can
    render rows differently based on which set of metrics ran. Old
    rows default to 1 (original 5 categories); current pipeline writes
    2 (5 originals + 5 extended findings + face-ROI crop + sex-aware
    threshold tuning)."""

    dependencies = [
        ('skinai', '0006_skinanalysis_extended_findings'),
    ]

    operations = [
        migrations.AddField(
            model_name='skinanalysis',
            name='pipeline_version',
            field=models.PositiveSmallIntegerField(default=1),
        ),
    ]
