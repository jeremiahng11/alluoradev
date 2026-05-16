from django.db import migrations


class Migration(migrations.Migration):
    """The admin no longer soft-deletes scans — the dashboard does a real
    delete instead, so the hidden_from_admin column is dead weight. Drop
    it. The user-side hidden_from_user stays — the mobile app still
    soft-deletes from the user's own history."""

    dependencies = [
        ('skinai', '0002_two_sided_soft_delete'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='skinanalysis',
            name='hidden_from_admin',
        ),
    ]
