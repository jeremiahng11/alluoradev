from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SkinAiTierConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tier', models.CharField(choices=[('none', 'Guest (anonymous)'), ('Silver', 'Silver'), ('Gold', 'Gold'), ('Platinum', 'Platinum'), ('Titanium', 'Titanium')], max_length=24, unique=True)),
                ('free_scans_per_period', models.PositiveIntegerField(default=0, help_text='Number of free scans inside one period. 0 = no free scans.')),
                ('period_unit', models.CharField(choices=[('day', 'Per day'), ('week', 'Per week'), ('month', 'Per month')], default='week', max_length=8)),
                ('coin_cost_per_scan', models.PositiveIntegerField(default=50, help_text='Glow Coins deducted for each scan past the free quota.')),
                ('unlimited_free', models.BooleanField(default=False, help_text='Overrides everything — scans are always free and unlimited (used for invitation-only Titanium tier).')),
            ],
            options={
                'verbose_name': 'Skin AI tier config',
                'verbose_name_plural': 'Skin AI tier configs',
                'ordering': ('tier',),
            },
        ),
        migrations.CreateModel(
            name='SkinAnalysis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('thumbnail', models.ImageField(blank=True, help_text='256x256 JPEG of the analysed face. Full-res original is deleted right after the analysis returns.', null=True, upload_to='skinai/thumbs/%Y/%m/')),
                ('skin_age', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('hydration_score', models.PositiveSmallIntegerField(default=0)),
                ('pores_score', models.PositiveSmallIntegerField(default=0)),
                ('wrinkles_score', models.PositiveSmallIntegerField(default=0)),
                ('redness_score', models.PositiveSmallIntegerField(default=0)),
                ('spots_score', models.PositiveSmallIntegerField(default=0)),
                ('overall_score', models.PositiveSmallIntegerField(default=0)),
                ('coin_cost', models.PositiveIntegerField(default=0)),
                ('raw_results', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='skin_analyses', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'Skin analyses',
                'ordering': ('-created_at',),
                'indexes': [models.Index(fields=['user', '-created_at'], name='skinai_skin_user_id_idx')],
            },
        ),
    ]
