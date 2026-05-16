"""AlluoraSessionToken — one-token-per-user bearer auth so the app
can skip the WP /auth/me roundtrip after the first authenticated
request."""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_tierrule_perks_description'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AlluoraSessionToken',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID')),
                ('key', models.CharField(
                    max_length=64, unique=True, db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    on_delete=models.deletion.CASCADE,
                    related_name='alluora_token',
                    to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
