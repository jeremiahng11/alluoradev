from django.db import migrations, models


class Migration(migrations.Migration):
    """Five additional skin-analysis fields surfaced in the in-app
    result screen and admin scan detail. All compute as CV proxies in
    apps/skinai/pipeline (no face landmark detection yet — see the
    docstring on each block in analyse() for accuracy notes)."""

    dependencies = [
        ('skinai', '0005_skinanalysis_low_confidence'),
    ]

    operations = [
        migrations.AddField(
            model_name='skinanalysis', name='pigmentation_score',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='skinanalysis', name='acne_score',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='skinanalysis', name='dark_circles_score',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='skinanalysis', name='eyebags_score',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='skinanalysis', name='white_spots_score',
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
