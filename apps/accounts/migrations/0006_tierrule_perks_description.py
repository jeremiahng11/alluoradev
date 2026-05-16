"""Add TierRule.perks_description (admin-editable bullet list of
benefits per tier, shown in the app's tier-ladder section)."""
from django.db import migrations, models


def seed_perks(apps, schema_editor):
    """Sensible defaults — the admin can edit these on the dashboard
    Membership page."""
    TierRule = apps.get_model('accounts', 'TierRule')
    defaults = {
        'Silver': (
            'Welcome bonus of 500 glow coins\n'
            'Member-only content and tutorials\n'
            'Birthday glow gift'
        ),
        'Gold': (
            'Everything in Silver\n'
            'Free standard shipping\n'
            'Early access to new launches\n'
            '5% birthday discount'
        ),
        'Platinum': (
            'Everything in Gold\n'
            'Free express shipping\n'
            '10% birthday discount\n'
            'Invites to exclusive events\n'
            'Priority customer support'
        ),
        'Titanium': (
            'Everything in Platinum\n'
            'Personal concierge service\n'
            'Custom skincare consultations\n'
            '15% off all purchases\n'
            'Invitation-only experiences'
        ),
    }
    for tier, perks in defaults.items():
        TierRule.objects.filter(tier=tier).update(perks_description=perks)


def unseed(apps, schema_editor):
    apps.get_model('accounts', 'TierRule').objects.update(perks_description='')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_tierrule_card_label_subtitle'),
    ]

    operations = [
        migrations.AddField(
            model_name='tierrule',
            name='perks_description',
            field=models.TextField(
                blank=True, default='',
                help_text="Member benefits for this tier — shown in the "
                          "app's tier ladder. One perk per line works "
                          "best; the app renders bullet points.",
            ),
        ),
        migrations.RunPython(seed_perks, unseed),
    ]
