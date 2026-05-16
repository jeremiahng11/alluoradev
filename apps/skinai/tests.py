"""Unit tests for apps.skinai.insights.

Targets the pure-logic functions — no DB rows, no DeepFace, no WP
fetches. Catches the kinds of regressions we hit during iteration:
falsy-zero collapses, missing-category drift, band threshold drifts,
legacy-row rendering.

Run with:
    python manage.py test apps.skinai
"""
from datetime import date
from types import SimpleNamespace
from unittest import TestCase

from apps.skinai import insights


def _scan(**overrides):
    """Build a stand-in for a SkinAnalysis row without hitting the DB.
    Defaults to a clean current-pipeline scan with all 10 categories
    at 70. Tests that care about the version bump can override
    pipeline_version explicitly."""
    base = dict(
        hydration_score=70, pores_score=70, wrinkles_score=70,
        redness_score=70, spots_score=70,
        pigmentation_score=70, acne_score=70, dark_circles_score=70,
        eyebags_score=70, white_spots_score=70,
        overall_score=70, skin_age=30, pipeline_version=3,
        user=SimpleNamespace(skin_primary_concern='', age_years=30),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class DeriveSkinTypeTests(TestCase):
    """Regression tests for the falsy-zero bug — a real 0 acne score
    (worst breakouts) must NOT collapse into the missing-data 100
    fallback, which used to push severe-acne users into 'combination'
    instead of 'oily'."""

    def test_acne_zero_classifies_oily(self):
        scores = {
            'hydration_score': 80, 'pores_score': 80,
            'redness_score': 80, 'acne_score': 0,
        }
        self.assertEqual(insights.derive_skin_type(scores), 'oily')

    def test_low_redness_wins_sensitive(self):
        scores = {'hydration_score': 80, 'pores_score': 80,
                  'redness_score': 40, 'acne_score': 80}
        self.assertEqual(insights.derive_skin_type(scores), 'sensitive')

    def test_low_hydration_low_pores_is_oily(self):
        scores = {'hydration_score': 40, 'pores_score': 50,
                  'redness_score': 80, 'acne_score': 80}
        self.assertEqual(insights.derive_skin_type(scores), 'oily')

    def test_low_hydration_high_pores_is_dry(self):
        scores = {'hydration_score': 40, 'pores_score': 75,
                  'redness_score': 80, 'acne_score': 80}
        self.assertEqual(insights.derive_skin_type(scores), 'dry')

    def test_default_is_combination(self):
        scores = {'hydration_score': 80, 'pores_score': 80,
                  'redness_score': 80, 'acne_score': 80}
        self.assertEqual(insights.derive_skin_type(scores), 'combination')

    def test_missing_fields_default_safe(self):
        # Empty dict → no metric flagged → 'combination'. Critically
        # NOT 'sensitive' (which would happen if missing redness
        # rewrote as 0).
        self.assertEqual(insights.derive_skin_type({}), 'combination')


class AgeComparisonTests(TestCase):
    def test_unavailable_when_either_age_missing(self):
        out = insights.compute_age_comparison(None, 30)
        self.assertFalse(out['available'])
        out = insights.compute_age_comparison(30, None)
        self.assertFalse(out['available'])

    def test_younger_is_positive(self):
        out = insights.compute_age_comparison(25, 35)
        self.assertEqual(out['severity'], 'positive')
        self.assertEqual(out['delta_years'], -10)
        self.assertIn('younger', out['headline'])

    def test_within_neutral_band(self):
        out = insights.compute_age_comparison(33, 30)
        self.assertEqual(out['severity'], 'neutral')

    def test_four_to_seven_is_mild(self):
        out = insights.compute_age_comparison(36, 30)
        self.assertEqual(out['severity'], 'mild')

    def test_eight_plus_is_concern(self):
        out = insights.compute_age_comparison(40, 30)
        self.assertEqual(out['severity'], 'concern')


class ComputeDetailsTests(TestCase):
    def test_v2_or_newer_returns_all_ten_categories(self):
        # compute_details has a >= 2 cutoff, so v2 and v3 should
        # both return the full set.
        for v in (2, 3):
            details = insights.compute_details(_scan(pipeline_version=v))
            self.assertEqual(len(details), 10, f'v{v} returned {len(details)}')
            keys = {d['key'] for d in details}
            self.assertIn('pigmentation_score', keys)
            self.assertIn('white_spots_score', keys)

    def test_v1_clips_to_original_five(self):
        details = insights.compute_details(_scan(pipeline_version=1))
        self.assertEqual(len(details), 5)
        keys = {d['key'] for d in details}
        self.assertNotIn('pigmentation_score', keys)
        self.assertEqual(
            keys,
            {'hydration_score', 'pores_score', 'wrinkles_score',
             'redness_score', 'spots_score'},
        )

    def test_band_thresholds(self):
        # Spot-check the band boundaries in _band_for.
        d_great = insights.compute_details(
            _scan(hydration_score=80))[0]
        self.assertEqual(d_great['band'], 'great')
        d_good = insights.compute_details(
            _scan(hydration_score=60))[0]
        self.assertEqual(d_good['band'], 'good')
        d_watch = insights.compute_details(
            _scan(hydration_score=40))[0]
        self.assertEqual(d_watch['band'], 'watch')
        d_concern = insights.compute_details(
            _scan(hydration_score=20))[0]
        self.assertEqual(d_concern['band'], 'concern')


class ComputeTests(TestCase):
    """Smoke tests for compute(); the per-category text maps are
    hand-curated so we only check the structural pieces."""

    def test_returns_full_dict_shape(self):
        out = insights.compute(_scan())
        self.assertIn('summary', out)
        self.assertIn('headline', out)
        self.assertIn('body', out)
        self.assertIn('body_html', out)
        self.assertIn('skin_type', out)
        self.assertIn('skin_type_label', out)
        self.assertIn('age_comparison', out)

    def test_picks_lowest_concern_when_user_has_concerns(self):
        # User says they care about hydration + brightening; hydration
        # is lowest of the two, so the headline targets hydration.
        analysis = _scan(
            hydration_score=40, spots_score=70,
            wrinkles_score=80, redness_score=80,
            pores_score=80, acne_score=80,
        )
        out = insights.compute(analysis, primary_concern='hydration,brightening')
        self.assertEqual(out['headline'], 'How to hydrate')

    def test_outside_concern_wins_when_much_worse(self):
        # User picked aging, but wrinkles is 75 while spots is 30.
        # spots wins because it's >15 points worse.
        analysis = _scan(
            wrinkles_score=75, spots_score=30,
            hydration_score=70, redness_score=70,
            pores_score=70, acne_score=70,
        )
        out = insights.compute(analysis, primary_concern='aging')
        self.assertEqual(out['headline'], 'How to brighten')

    def test_md_bold_renders_as_strong(self):
        analysis = _scan(spots_score=30)
        out = insights.compute(analysis)
        # body has **bold** markers, body_html should have <strong>
        self.assertIn('**', out['body'])
        self.assertIn('<strong>', out['body_html'])
        self.assertNotIn('**', out['body_html'])

    def test_age_comparison_pulls_from_user(self):
        analysis = _scan(
            skin_age=40,
            user=SimpleNamespace(skin_primary_concern='', age_years=30),
        )
        out = insights.compute(analysis)
        self.assertTrue(out['age_comparison']['available'])
        self.assertEqual(out['age_comparison']['delta_years'], 10)
        self.assertEqual(out['age_comparison']['severity'], 'concern')


class LandmarksFallbackTests(TestCase):
    """Make sure the landmarks wrapper degrades to None instead of
    raising when mediapipe is missing or the image has no face.
    Pipeline relies on this to fall back to the center crop."""

    def test_none_image_returns_none(self):
        from apps.skinai import landmarks
        # Pass an obviously bogus shape — must not raise.
        import numpy as np
        garbage = np.zeros((10, 10, 3), dtype=np.uint8)
        result = landmarks.detect_regions(garbage)
        # Either None (no face) or a FaceRegions tuple — either way
        # callable, not an exception.
        self.assertTrue(result is None or hasattr(result, 'face_bbox'))


class SkinTypeLabelTests(TestCase):
    def test_known_slugs(self):
        self.assertEqual(insights.skin_type_label('oily'), 'Oily')
        self.assertEqual(insights.skin_type_label('dry'), 'Dry')
        self.assertEqual(
            insights.skin_type_label('combination'), 'Combination')
        self.assertEqual(insights.skin_type_label('sensitive'), 'Sensitive')

    def test_unknown_slug_returns_empty(self):
        self.assertEqual(insights.skin_type_label('mystery'), '')
