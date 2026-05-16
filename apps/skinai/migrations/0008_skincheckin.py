import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Daily check-in model. Lightweight progress snapshot —
    overall_score + skin_age + thumbnail only. 1/day per user,
    capped at 90 records. Doesn't share the SkinAnalysis 6-cap or
    the Glow Coin economics."""

    dependencies = [
        ('skinai', '0007_skinanalysis_pipeline_version'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SkinCheckIn',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID',
                )),
                ('thumbnail', models.ImageField(
                    blank=True, null=True,
                    upload_to='skinai/checkins/%Y/%m/',
                    help_text='256x256 face crop. Same encode as '
                              'SkinAnalysis.thumbnail.',
                )),
                ('skin_age', models.PositiveSmallIntegerField(
                    blank=True, null=True,
                )),
                ('overall_score', models.PositiveSmallIntegerField(default=0)),
                ('hydration_score', models.PositiveSmallIntegerField(default=0)),
                ('redness_score', models.PositiveSmallIntegerField(default=0)),
                ('low_confidence', models.BooleanField(default=False)),
                ('pipeline_version', models.PositiveSmallIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='skin_check_ins',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Skin check-in',
                'verbose_name_plural': 'Skin check-ins',
                'ordering': ('-created_at',),
                'indexes': [
                    models.Index(
                        fields=['user', '-created_at'],
                        name='skinai_skin_user_id_06fd6c_idx',
                    ),
                ],
            },
        ),
    ]
