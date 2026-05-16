"""Seed three sample articles (and a couple of categories) for the
dashboard. Idempotent — re-runs are no-ops on already-seeded slugs.

Usage:
    python manage.py seed_sample_articles
    railway run python manage.py seed_sample_articles
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.content.models import Article, ContentCategory


SAMPLE_CATEGORIES = [
    {'name': 'Skincare', 'sort_order': 1},
    {'name': 'Wellness', 'sort_order': 2},
    {'name': 'Glow Tips', 'sort_order': 3},
]


SAMPLE_ARTICLES = [
    {
        'slug': 'sample-the-five-step-evening-ritual',
        'title': 'The five-step evening ritual that resets your skin',
        'category': 'Skincare',
        'summary': 'A short, repeatable nightly routine you can stick to even on the busiest days.',
        'is_featured': True,
        'body': """\
Your evening ritual is the single highest-leverage thing you can do for your skin. Here's the version we recommend to every new Alluora member.

## 1. Double cleanse
Start with an oil-based cleanser to lift makeup and SPF, then follow with a gentle gel or cream cleanser to clear out everything underneath. Skipping this on busy days is the most common reason routines stall.

## 2. Hydrating mist
Before the rest of your routine, mist your skin so the products that follow have something to bind to. Damp skin absorbs serums far better than dry skin.

## 3. Treatment serum
Pick **one** active per night — retinol *or* exfoliating acid *or* vitamin C — and stay consistent for at least four weeks before judging whether it's working.

## 4. Moisturiser
Lock everything in with a moisturiser matched to your skin type. Oily skin: gel. Combination: lotion. Dry: cream.

## 5. Sleep with intention
The last step isn't a product. Sleep on a clean pillowcase, in a cool room, ideally with a humidifier running. Most "skin transformations" are really just better sleep paying you compound interest.
""",
    },
    {
        'slug': 'sample-glow-foods',
        'title': 'Six foods that quietly transform your glow',
        'category': 'Wellness',
        'summary': 'Skincare from the inside out — what to eat more of when your routine plateaus.',
        'is_featured': False,
        'body': """\
Topicals do a lot, but they can't do everything. When clients tell us they've hit a plateau, the next conversation is almost always about food.

### 1. Wild salmon
Omega-3s reduce inflammation and visibly calm redness within a few weeks of regular eating.

### 2. Avocado
Healthy fats help skin retain moisture — particularly useful in air-conditioned offices and dry climates.

### 3. Berries
Anthocyanins are protective antioxidants. Blueberries, blackberries, raspberries — frozen counts.

### 4. Sweet potato
Beta-carotene converts to vitamin A in the body, supporting cell turnover.

### 5. Walnuts
A small handful covers your daily omega-3 needs if you don't eat fish.

### 6. Dark chocolate
70%+ cacao, in moderation. The flavanols are real; the sugar in milk chocolate cancels them out.

You don't need all six every day — just rotate. Think of food as the slow track and serums as the fast track. The slow track is what's still there in five years.
""",
    },
    {
        'slug': 'sample-sleep-and-skin',
        'title': 'Why your skin care actually starts with sleep',
        'category': 'Glow Tips',
        'summary': 'The one habit that does more for your face than any serum on the market.',
        'is_featured': True,
        'body': """\
If we could only recommend one thing to a new member, it wouldn't be a product. It would be sleep.

## What happens overnight
Skin enters its repair phase between roughly 10pm and 2am. Cell turnover roughly doubles, blood flow to the face increases, and growth hormone — the body's repair signal — peaks. Cut this window short and the rest of your routine has less to work with.

## Three small changes
- **Pillowcase**: silk or satin reduces friction lines and helps your products stay on your face instead of soaking into cotton.
- **Temperature**: 18–20°C (65–68°F) is the sweet spot. Warmer and you sleep lighter.
- **Last screen**: a 30-minute buffer before bed makes a measurable difference to how quickly you fall asleep.

## What to track
For one week, write down the time you went to bed and how your skin looked the next morning. The pattern is usually obvious by day five.

Sleep is the part of skincare nobody sells you, because nobody profits from it. That's exactly why it works.
""",
    },
]


class Command(BaseCommand):
    help = 'Seed three sample articles + a few categories for the dashboard.'

    def handle(self, *args, **options):
        # Categories first so articles can FK to them.
        cats = {}
        for cat in SAMPLE_CATEGORIES:
            obj, created = ContentCategory.objects.get_or_create(
                name=cat['name'],
                defaults={'sort_order': cat['sort_order']},
            )
            cats[cat['name']] = obj
            verb = 'created' if created else 'kept existing'
            self.stdout.write(f'  category: {cat["name"]} ({verb})')

        inserted = 0
        skipped = 0
        for art in SAMPLE_ARTICLES:
            obj, created = Article.objects.get_or_create(
                slug=art['slug'],
                defaults={
                    'title': art['title'],
                    'summary': art['summary'],
                    'body': art['body'],
                    'category': cats.get(art['category']),
                    'is_featured': art['is_featured'],
                    'status': Article.STATUS_PUBLISHED,
                    'published_at': timezone.now(),
                },
            )
            if created:
                inserted += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  article: "{art["title"]}" (created)'
                ))
            else:
                skipped += 1
                self.stdout.write(
                    f'  article: "{art["title"]}" (already exists, skipped)'
                )

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. inserted={inserted} skipped={skipped}'
        ))
