from django.db import migrations, models


def backfill_main_admin(apps, schema_editor):
    """Promote the earliest existing dashboard admin to is_main_admin
    so existing deploys aren't left without an 'owner' account. If
    multiple dashboard admins exist (unlikely on first migration but
    possible), the one with the lowest date_joined wins.

    Idempotent: if any user already has is_main_admin=True we leave
    things alone — operator may have set it manually.
    """
    User = apps.get_model('accounts', 'AppUser')
    if User.objects.filter(is_main_admin=True).exists():
        return
    first_admin = (
        User.objects
        .filter(is_dashboard_admin=True)
        .order_by('date_joined', 'id')
        .first()
    )
    if first_admin:
        first_admin.is_main_admin = True
        first_admin.save(update_fields=['is_main_admin'])


def unset_main_admin(apps, schema_editor):
    """Reverse migration — drop the flag from any user that has it."""
    User = apps.get_model('accounts', 'AppUser')
    User.objects.filter(is_main_admin=True).update(is_main_admin=False)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_appuser_birthday'),
    ]

    operations = [
        migrations.AddField(
            model_name='appuser',
            name='is_main_admin',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Owner account — invisible to other dashboard admins '
                    'and protected from being demoted/deleted by them.'
                ),
            ),
        ),
        migrations.RunPython(backfill_main_admin, unset_main_admin),
    ]
