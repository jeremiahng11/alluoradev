"""Add TierRule.card_label_subtitle so admins can edit the per-tier
text rendered under the tier name on the app's membership card."""
from django.db import migrations, models


def seed_card_labels(apps, schema_editor):
    """Default subtitles match what the app was hardcoding before:
    VIP MEMBER for Platinum, INVITE ONLY for Titanium, blank for
    Silver / Gold (which fall back to 'MEMBER' on the card)."""
    TierRule = apps.get_model('accounts', 'TierRule')
    defaults = {
        'Platinum': 'VIP MEMBER',
        'Titanium': 'INVITE ONLY',
    }
    for tier, label in defaults.items():
        TierRule.objects.filter(tier=tier).update(card_label_subtitle=label)


def unseed(apps, schema_editor):
    apps.get_model('accounts', 'TierRule').objects.update(card_label_subtitle='')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_total_spent_tierrule'),
    ]

    operations = [
        migrations.AddField(
            model_name='tierrule',
            name='card_label_subtitle',
            field=models.CharField(
                blank=True, default='', max_length=64,
                help_text="Subtitle shown under the tier name on the "
                          "membership card in the app (e.g. 'VIP "
                          "MEMBER', 'INVITE ONLY'). Leave empty to "
                          "show the default 'MEMBER'.",
            ),
        ),
        migrations.RunPython(seed_card_labels, unseed),
    ]
