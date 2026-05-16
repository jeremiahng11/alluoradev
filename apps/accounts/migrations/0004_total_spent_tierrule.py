"""Add AppUser.total_spent + AppUser.spending_synced_at, plus the
TierRule table that drives automatic tier upgrades from spending."""
from decimal import Decimal
from django.db import migrations, models


def seed_tier_rules(apps, schema_editor):
    """Seed the four production tiers. Defaults match the pricing the
    user described: Gold at $1000, Platinum at $5000 (the high-spender
    tier), Titanium invite-only. Silver is the entry tier ($0)."""
    TierRule = apps.get_model('accounts', 'TierRule')
    defaults = [
        ('Silver', Decimal('0'), False),
        ('Gold', Decimal('1000'), False),
        ('Platinum', Decimal('5000'), False),
        ('Titanium', Decimal('0'), True),
    ]
    for tier, min_spent, invite in defaults:
        TierRule.objects.update_or_create(
            tier=tier,
            defaults={
                'min_spent': min_spent,
                'is_invite_only': invite,
            },
        )


def unseed(apps, schema_editor):
    apps.get_model('accounts', 'TierRule').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_welcome_bonus_granted'),
    ]

    operations = [
        migrations.AddField(
            model_name='appuser',
            name='total_spent',
            field=models.DecimalField(
                max_digits=12, decimal_places=2, default=Decimal('0'),
                help_text='Lifetime WooCommerce spend in store currency.',
            ),
        ),
        migrations.AddField(
            model_name='appuser',
            name='spending_synced_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.CreateModel(
            name='TierRule',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID')),
                ('tier', models.CharField(
                    max_length=24, unique=True,
                    help_text='One of Silver / Gold / Platinum / Titanium.')),
                ('min_spent', models.DecimalField(
                    max_digits=12, decimal_places=2,
                    default=Decimal('0'),
                    help_text='Minimum lifetime WooCommerce spend (store '
                              'currency) required to qualify. Ignored if '
                              'invite-only.')),
                ('is_invite_only', models.BooleanField(
                    default=False,
                    help_text="When true, this tier ignores spending — "
                              "admins must assign it manually. The app's "
                              "card screen also displays a custom label "
                              "(e.g. 'INVITE ONLY' for Titanium) instead "
                              "of '<TIER> MEMBER'.")),
            ],
            options={
                'ordering': ('min_spent',),
            },
        ),
        migrations.RunPython(seed_tier_rules, unseed),
    ]
