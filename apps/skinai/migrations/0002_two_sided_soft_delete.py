from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('skinai', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='skinanalysis',
            name='hidden_from_user',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='skinanalysis',
            name='hidden_from_admin',
            field=models.BooleanField(default=False),
        ),
    ]
