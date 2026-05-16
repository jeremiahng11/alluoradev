import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """User-managed routine tracker. One row per active or
    historical product the user is using on their skin. Powers the
    list view + future correlation against scan trends."""

    dependencies = [
        ('skinai', '0008_skincheckin'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SkinRoutineProduct',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID',
                )),
                ('name', models.CharField(max_length=120)),
                ('brand', models.CharField(blank=True, default='', max_length=80)),
                ('slot', models.CharField(
                    choices=[
                        ('am', 'Morning'),
                        ('pm', 'Evening'),
                        ('both', 'Morning + evening'),
                    ],
                    default='both', max_length=8,
                )),
                ('started_at', models.DateField(blank=True, null=True)),
                ('ended_at', models.DateField(
                    blank=True, null=True,
                    help_text='When set, the product is no longer '
                              'active. Kept for historical correlation '
                              'against past scans.',
                )),
                ('notes', models.CharField(blank=True, default='', max_length=240)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='skin_routine_products',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Skin routine product',
                'ordering': ('-started_at', '-created_at'),
                'indexes': [
                    models.Index(
                        fields=['user', '-created_at'],
                        name='skinai_skin_user_id_b97c44_idx',
                    ),
                ],
            },
        ),
    ]
