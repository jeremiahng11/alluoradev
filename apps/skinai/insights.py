"""Single source of truth for Skin AI insight copy.

`compute(analysis)` returns three strings:

  - summary  — one-line italic quote on the result hero (overall band)
  - headline — title of the recommendation card (lowest-scoring category)
  - body     — recommendation paragraph; **bold** markers are kept raw,
                Flutter parses them into TextSpans, the admin template
                renders them as <strong> via `body_html` instead

These are exposed on the SkinAnalysisSerializer as `insight_summary`,
`insight_headline`, `insight_body` so the Flutter result screen reads
them straight from the analyze / history JSON. The admin scan-detail
view calls compute() directly and renders body_html.
"""
import re
from typing import Mapping


_HEADLINES = {
    'hydration_score': 'How to hydrate',
    'pores_score': 'How to refine pores',
    'wrinkles_score': 'How to soften lines',
    'redness_score': 'How to calm redness',
    'spots_score': 'How to brighten',
    'pigmentation_score': 'How to even out tone',
    'acne_score': 'How to clear breakouts',
    'dark_circles_score': 'How to lift dark circles',
    'eyebags_score': 'How to reduce puffiness',
    'white_spots_score': 'How to soften white spots',
}

_BODIES = {
    'hydration_score': (
        'Focus on **a hydrating serum + occlusive moisturiser**. '
        'Drink more water, cut hot showers, and a sheet mask 2× a week '
        'will visibly plump the skin within 1–2 weeks.'
    ),
    'pores_score': (
        'Focus on **a gentle BHA exfoliant**, 2–3× a week. A weekly '
        'clay mask refines visible pores; avoid heavy oils on the t-zone.'
    ),
    'wrinkles_score': (
        'Focus on **retinol at night + daily SPF 50+**. Sunscreen is '
        'the single biggest factor — consistency beats intensity here.'
    ),
    'redness_score': (
        'Focus on **barrier repair**: niacinamide + centella, no '
        'fragrances, lukewarm water. Pause harsh actives for 1–2 weeks.'
    ),
    'spots_score': (
        'Focus on **pigmentation lightening** with vitamin C in the '
        'morning and daily SPF 50+. Expect visible fading in 4–6 weeks.'
    ),
    'pigmentation_score': (
        'Focus on **vitamin C + niacinamide in the morning**, with '
        'daily SPF 50+. Patchy tone responds best to consistency over '
        '6–8 weeks; avoid lemon juice and other DIY actives.'
    ),
    'acne_score': (
        'Focus on **salicylic acid (BHA) 2–3× a week** plus a non-'
        'comedogenic moisturiser. Spot-treat active breakouts with '
        'benzoyl peroxide; resist picking — that\'s what scars.'
    ),
    'dark_circles_score': (
        'Focus on **caffeine eye cream + sleep + hydration**. '
        'Pigment-driven circles also respond to vitamin C; structural '
        'shadows need a dermatologist for fillers.'
    ),
    'eyebags_score': (
        'Focus on **cool compress + reducing salt and alcohol**. '
        'Persistent puffiness is often genetic; an eye cream with '
        'caffeine and peptides helps daily appearance.'
    ),
    'white_spots_score': (
        'Focus on **gentle exfoliation + daily SPF 50+**. Milia (small '
        'white bumps) clear with patience or a quick in-office '
        'extraction; broader pigment shifts need a dermatologist read.'
    ),
}

_DEFAULT_HEADLINE = 'Keep glowing'
_DEFAULT_BODY = (
    'Everything is reading in the healthy band — keep your routine '
    'consistent and re-scan in 4 weeks to track progress.'
)


def _lowest_category(scores: Mapping[str, int]) -> str:
    """Pick the lowest-scoring category from the full set (original 5
    plus the 5 extended findings). Skips missing fields so a dropped
    key can't mask a "0 — needs care" reading."""
    keys = (
        'hydration_score', 'pores_score', 'wrinkles_score',
        'redness_score', 'spots_score',
        'pigmentation_score', 'acne_score',
        'dark_circles_score', 'eyebags_score', 'white_spots_score',
    )
    present = [(k, scores[k]) for k in keys if isinstance(scores.get(k), int)]
    if not present:
        return ''
    present.sort(key=lambda kv: kv[1])
    return present[0][0]


def _summary_for(overall: int) -> str:
    if overall >= 75:
        return '"Bright, balanced — your routine is working."'
    if overall >= 50:
        return '"Healthy base — a few targeted upgrades will lift it."'
    return '"A reset moment — gentle hydration and SPF will help."'


def _md_bold_to_html(text: str) -> str:
    """Convert **bold** → <strong>bold</strong> after escaping the text.
    Used by the admin template to render the body emphasis the same
    way the in-app result does, without trusting raw HTML."""
    from django.utils.html import escape
    escaped = escape(text)
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)


_CONCERN_TO_KEY = {
    'hydration': 'hydration_score',
    'aging': 'wrinkles_score',
    'acne': 'acne_score',
    'brightening': 'spots_score',
    'sensitivity': 'redness_score',
    'pigmentation': 'pigmentation_score',
    'dark_circles': 'dark_circles_score',
    'eyebags': 'eyebags_score',
    'white_spots': 'white_spots_score',
    'pores': 'pores_score',
}


def derive_skin_type(scores: Mapping[str, int]) -> str:
    """Quick four-bucket skin-type guess. Not clinical — a coarse
    classification useful as a chip on the result screen.

    Heuristics:
      sensitive — redness < 50 (irritation reading dominates)
      oily      — (hydration < 55 AND pores < 60) OR acne < 55
                  (high sebum proxy, optionally confirmed by active
                  breakouts)
      dry       — hydration < 55 (matte / flat without the pores signal)
      combination — anything else, default
    """
    # Explicit None check instead of `or default` so a real 0 score
    # (worst case for that metric) doesn't get silently rewritten as
    # the missing-data fallback. Previous version collapsed acne=0
    # into 100, which masked severe breakouts.
    def _val(key, missing):
        v = scores.get(key)
        return v if isinstance(v, int) else missing

    redness = _val('redness_score', 100)
    hydration = _val('hydration_score', 100)
    pores = _val('pores_score', 100)
    acne = _val('acne_score', 100)
    if redness < 50:
        return 'sensitive'
    if (hydration < 55 and pores < 60) or acne < 55:
        return 'oily'
    if hydration < 55:
        return 'dry'
    return 'combination'


_SKIN_TYPE_LABELS = {
    'oily': 'Oily',
    'dry': 'Dry',
    'combination': 'Combination',
    'sensitive': 'Sensitive',
}


def skin_type_label(slug: str) -> str:
    return _SKIN_TYPE_LABELS.get(slug, '')


# ─── Detailed per-category descriptions ───────────────────────────
#
# Each category gets a 3-tuple per band:
#   (label, what-it-measures sentence, what-yours-says-by-band dict)
# Bands are 'great' (>=75), 'good' (50-74), 'watch' (30-49),
# 'concern' (<30). Copy is intentionally short (1-2 sentences each)
# so it reads on a phone without burying the user.
_DETAIL_CATEGORIES = (
    'hydration_score', 'pores_score', 'wrinkles_score', 'redness_score',
    'spots_score', 'pigmentation_score', 'acne_score',
    'dark_circles_score', 'eyebags_score', 'white_spots_score',
)

_DETAIL_LABELS = {
    'hydration_score': 'Hydration',
    'pores_score': 'Pores',
    'wrinkles_score': 'Fine lines & wrinkles',
    'redness_score': 'Redness',
    'spots_score': 'Spots',
    'pigmentation_score': 'Pigmentation',
    'acne_score': 'Acne & breakouts',
    'dark_circles_score': 'Dark circles',
    'eyebags_score': 'Eyebag puffiness',
    'white_spots_score': 'White spots',
}

_DETAIL_MEASURES = {
    'hydration_score':
        'How much moisture your skin appears to hold. Looks at light '
        'distribution to estimate matte-vs-plump skin.',
    'pores_score':
        'Visible pore size and texture across the t-zone, estimated '
        'from high-frequency detail in your photo.',
    'wrinkles_score':
        'Fine lines and creases, estimated from edge density on a '
        'softened version of your image.',
    'redness_score':
        'Overall warmth in your skin tone — proxy for irritation, '
        'inflammation, or rosacea-like flushing.',
    'spots_score':
        'Small, dense unevenness in skin lightness — freckles, '
        'tiny dark spots, mild blemishes.',
    'pigmentation_score':
        'Larger patches of uneven tone — sun damage, melasma, or '
        'post-inflammatory pigmentation.',
    'acne_score':
        'Active red blemishes (papules, pustules) detected through '
        'a colour mask. May also pick up lipstick or nostril shadow.',
    'dark_circles_score':
        'Darkness gradient between your upper face and the under-eye '
        'area. A directional proxy without eye-region detection.',
    'eyebags_score':
        'Vertical shadowing under the eyes — lower face contour '
        'changes that read as puffiness.',
    'white_spots_score':
        'Small bright outliers — milia (tiny white bumps), shiny '
        't-zone reflections, or hyperpigmentation lighter than '
        'surrounding skin.',
}

_DETAIL_BAND_BY_SCORE = {
    'great': {  # >= 75
        'hydration_score':
            'Your skin reads plump and balanced. Routine’s working — keep it.',
        'pores_score':
            'Pores are refined and texture is smooth.',
        'wrinkles_score':
            'Very few visible fine lines for your age band.',
        'redness_score':
            'Calm, even tone — no obvious irritation.',
        'spots_score':
            'Skin reads clear of small spots and freckles.',
        'pigmentation_score':
            'Even, uniform tone across your face.',
        'acne_score':
            'No active breakouts detected.',
        'dark_circles_score':
            'No noticeable shadowing under your eyes.',
        'eyebags_score':
            'Under-eye contour reads smooth.',
        'white_spots_score':
            'No bright outliers — skin tone is consistent.',
    },
    'good': {  # 50–74
        'hydration_score':
            'Healthy hydration with mild dryness in places. '
            'A daily moisturiser would push this up.',
        'pores_score':
            'Pores are visible in places but well within normal. '
            'A weekly BHA exfoliant would refine them.',
        'wrinkles_score':
            'Some fine lines starting to show. Daily SPF + a '
            'retinol introduction would slow them.',
        'redness_score':
            'A little warmth in your tone — typical for combination '
            'skin. Niacinamide helps.',
        'spots_score':
            'A few small spots. Vitamin C in the morning would '
            'fade them over 4–6 weeks.',
        'pigmentation_score':
            'Some patchiness. Targeted brightening serums help; '
            'consistency over weeks matters more than intensity.',
        'acne_score':
            'A breakout or two visible. A salicylic-acid spot '
            'treatment usually clears these.',
        'dark_circles_score':
            'Slight under-eye darkness. Caffeine eye cream + '
            'better sleep typically lifts pigment-driven circles.',
        'eyebags_score':
            'Mild puffiness. Cool compress + reducing salt the '
            'night before usually helps.',
        'white_spots_score':
            'A couple of small bright spots — most likely milia '
            'or a shiny t-zone, both harmless.',
    },
    'watch': {  # 30–49
        'hydration_score':
            'Skin reads dehydrated. Hyaluronic-acid serum + a '
            'richer moisturiser; cut hot showers and increase water.',
        'pores_score':
            'Pores are noticeably enlarged. BHA 2–3× weekly + a '
            'clay mask once a week refines them over time.',
        'wrinkles_score':
            'Fine lines are showing. Daily SPF 50+ is non-negotiable; '
            'add a retinol at night, low-strength to start.',
        'redness_score':
            'Skin is reading inflamed. Pause harsh actives, stick to '
            'fragrance-free, and add niacinamide + centella.',
        'spots_score':
            'Several small spots. Combine vitamin C (AM) with '
            'gentle exfoliation and daily SPF for a 6–8 week reset.',
        'pigmentation_score':
            'Visible uneven tone. Layered brightening (vitamin C + '
            'niacinamide) plus daily SPF; expect change in 6–8 weeks.',
        'acne_score':
            'Active breakouts present. Salicylic acid 2–3× a week, '
            'spot-treat with benzoyl peroxide, don’t pick.',
        'dark_circles_score':
            'Noticeable dark circles. Combine sleep + caffeine eye '
            'cream + vitamin C; structural shadows may need a derm.',
        'eyebags_score':
            'Puffiness reads strong. Eye cream with caffeine + '
            'peptides; cold compress in the morning helps acutely.',
        'white_spots_score':
            'Several bright outliers. If they’re raised white '
            'bumps, gentle exfoliation; persistent ones can be '
            'extracted by a dermatologist.',
    },
    'concern': {  # < 30
        'hydration_score':
            'Skin reads severely dehydrated. Multi-step layering '
            '(toner → essence → serum → cream) and a sheet mask '
            '2–3× a week. See a dermatologist if it persists.',
        'pores_score':
            'Pores read very enlarged. BHA + retinol routine; '
            'clay mask 2× a week; in-clinic treatments accelerate.',
        'wrinkles_score':
            'Significant lines. Sunscreen + retinoid + peptide '
            'serum. In-clinic treatments (e.g. microneedling) speed it.',
        'redness_score':
            'Strong inflammation reading. Strip the routine to a '
            'gentle cleanser + barrier cream for 2 weeks; if not '
            'better, see a derm to rule out rosacea.',
        'spots_score':
            'Skin reads blotchy. Layered brightening protocol + '
            'professional consult if patches don’t respond.',
        'pigmentation_score':
            'Strong patchy pigmentation. A derm can recommend '
            'tranexamic acid or in-clinic peels for faster results.',
        'acne_score':
            'Significant breakouts. Don’t pick. Consider seeing '
            'a dermatologist for prescription topicals or oral options.',
        'dark_circles_score':
            'Very dark under-eye reading. Could be pigment, '
            'hollowness, or vasculature. A derm consult is the '
            'fastest path to the right fix.',
        'eyebags_score':
            'Strong puffiness. If it’s persistent, lifestyle '
            '(sleep, sodium) helps short term; structural bags '
            'may need cosmetic treatment.',
        'white_spots_score':
            'Many bright outliers. If they’re raised milia or '
            'persistent depigmentation, see a dermatologist for '
            'extraction or diagnosis.',
    },
}


def compute_age_comparison(skin_age, real_age) -> dict:
    """Compare DeepFace's skin_age estimate against the user's real
    age (computed from birthday on AppUser). Returns a dict the UI
    renders as a small banner near the score.

      {
        'available':   bool,   # both ages known
        'skin_age':    int|None,
        'real_age':    int|None,
        'delta_years': int,    # skin_age - real_age (positive = older)
        'severity':    'positive' | 'neutral' | 'mild' | 'concern',
        'headline':    short label, e.g. "5 years younger"
        'message':     1-sentence explanation
      }

    If either age is missing the dict is returned with available=False
    and the rest blank — the UI hides the banner.
    """
    if not isinstance(skin_age, int) or not isinstance(real_age, int):
        return {
            'available': False,
            'skin_age': skin_age if isinstance(skin_age, int) else None,
            'real_age': real_age if isinstance(real_age, int) else None,
            'delta_years': 0,
            'severity': 'neutral',
            'headline': '',
            'message': '',
        }

    delta = skin_age - real_age
    abs_delta = abs(delta)

    if delta <= -5:
        severity = 'positive'
        headline = f'{abs_delta} years younger'
        message = (
            f"Your skin reads about {abs_delta} years younger than you "
            "actually are. Whatever you're doing, keep doing it — "
            "consistency on SPF + hydration is what compounds over time."
        )
    elif delta >= 8:
        severity = 'concern'
        headline = f'{delta} years older'
        message = (
            f"Your skin reads about {delta} years older than your real "
            f"age of {real_age}. Daily SPF 50+ is the highest-leverage "
            'fix, paired with a retinol/peptide routine at night and '
            'a hydrating serum in the morning.'
        )
    elif delta >= 4:
        severity = 'mild'
        headline = f'{delta} years older'
        message = (
            f"Your skin reads about {delta} years older than your real "
            f"age of {real_age}. Sunscreen consistency is the biggest "
            'lever; a gentle retinol introduction speeds it up over '
            '8–12 weeks.'
        )
    else:
        severity = 'neutral'
        if delta == 0:
            headline = 'On track for your age'
        elif delta < 0:
            headline = f'{abs_delta} years younger'
        else:
            headline = f'{delta} years older'
        message = (
            f"Your skin reads close to your real age ({real_age}). "
            'Your routine is roughly in step with your biology — keep '
            'up the SPF + hydration baseline and add targeted actives '
            'as concerns appear.'
        )

    return {
        'available': True,
        'skin_age': skin_age,
        'real_age': real_age,
        'delta_years': delta,
        'severity': severity,
        'headline': headline,
        'message': message,
    }


def _band_for(score: int) -> str:
    if score >= 75:
        return 'great'
    if score >= 50:
        return 'good'
    if score >= 30:
        return 'watch'
    return 'concern'


def compute_details(analysis) -> list[dict]:
    """Return a list of detailed per-category breakdowns for the
    in-app and admin "Detailed analysis" section. Each item:

      {
        'key':           score field name,
        'label':         display label,
        'score':         0-100,
        'band':          'great' | 'good' | 'watch' | 'concern',
        'what_it_is':    one-sentence description of the metric,
        'what_yours_says': band-specific 1-2 sentence interpretation,
      }

    Categories are returned in the same order as _DETAIL_CATEGORIES.
    Rows scored under pipeline_version 1 only had the original 5
    metrics; the extended findings are filtered out so legacy rows
    don't render "Needs care" placeholders for categories they were
    never actually scored on.
    """
    pipeline_v = getattr(analysis, 'pipeline_version', 1) or 1
    if pipeline_v < 2:
        eligible_keys = (
            'hydration_score', 'pores_score', 'wrinkles_score',
            'redness_score', 'spots_score',
        )
    else:
        eligible_keys = _DETAIL_CATEGORIES
    out = []
    for key in eligible_keys:
        score = getattr(analysis, key, None)
        if not isinstance(score, int):
            continue
        band = _band_for(score)
        out.append({
            'key': key,
            'label': _DETAIL_LABELS.get(key, key),
            'score': score,
            'band': band,
            'what_it_is': _DETAIL_MEASURES.get(key, ''),
            'what_yours_says':
                _DETAIL_BAND_BY_SCORE[band].get(key, ''),
        })
    return out


def compute(analysis, primary_concern: str = '') -> dict:
    """Build the trio of strings shown on the in-app result screen,
    plus an HTML-rendered body and a derived skin_type slug.

    Args:
      analysis:        SkinAnalysis instance.
      primary_concern: comma-separated concern slugs from the user's
                       skin profile, any of 'hydration' / 'aging' /
                       'acne' / 'brightening' / 'sensitivity'. When
                       set, the recommendation targets the WORST-
                       scoring of the user's stated concerns. If
                       another category outside the user's set is
                       >15 points worse than the picked concern, the
                       worse one wins (they'd want to know).

    Returns:
        {
          'summary':    str,  # one-line italic quote next to the score
          'headline':   str,  # "How to hydrate" / etc.
          'body':       str,  # raw markdown-style copy with **bold**
          'body_html':  str,  # body with **bold** rendered as <strong>
          'skin_type':  str,  # 'oily' | 'dry' | 'combination' | 'sensitive'
          'skin_type_label': str,  # human-readable form
        }
    """
    scores = {
        'hydration_score': analysis.hydration_score,
        'pores_score': analysis.pores_score,
        'wrinkles_score': analysis.wrinkles_score,
        'redness_score': analysis.redness_score,
        'spots_score': analysis.spots_score,
        'pigmentation_score': getattr(analysis, 'pigmentation_score', 0),
        'acne_score': getattr(analysis, 'acne_score', 0),
        'dark_circles_score': getattr(analysis, 'dark_circles_score', 0),
        'eyebags_score': getattr(analysis, 'eyebags_score', 0),
        'white_spots_score': getattr(analysis, 'white_spots_score', 0),
    }

    # Pick the worst-scoring category among the user's stated concerns.
    concern_keys = [
        _CONCERN_TO_KEY[s.strip()]
        for s in (primary_concern or '').split(',')
        if s.strip() in _CONCERN_TO_KEY
    ]
    actual_lowest = _lowest_category(scores)
    chosen = actual_lowest
    if concern_keys:
        scored = [(k, scores[k]) for k in concern_keys
                  if isinstance(scores.get(k), int)]
        if scored:
            scored.sort(key=lambda kv: kv[1])
            target_key, target_score = scored[0]
            worst_score = scores.get(actual_lowest)
            # Honour the worst stated concern unless something outside
            # the user's set is meaningfully worse.
            if (isinstance(worst_score, int)
                    and target_score - worst_score > 15):
                chosen = actual_lowest
            else:
                chosen = target_key

    body = _BODIES.get(chosen, _DEFAULT_BODY)
    skin_type = derive_skin_type(scores)
    real_age = getattr(getattr(analysis, 'user', None), 'age_years', None)
    age_comparison = compute_age_comparison(analysis.skin_age, real_age)
    return {
        'summary': _summary_for(analysis.overall_score),
        'headline': _HEADLINES.get(chosen, _DEFAULT_HEADLINE),
        'body': body,
        'body_html': _md_bold_to_html(body),
        'skin_type': skin_type,
        'skin_type_label': skin_type_label(skin_type),
        'age_comparison': age_comparison,
    }
