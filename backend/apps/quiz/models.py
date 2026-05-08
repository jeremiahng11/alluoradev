"""Skin quiz: questions, options, user submissions, computed result types.

Architecture:
  - Quiz (e.g. "Skin Type Finder")
  - Question with multiple Options
  - Each Option carries a `weights` JSON of `{result_type_slug: score}`
  - Submission stores chosen option ids + the computed primary result type
"""
from django.conf import settings
from django.db import models


class Quiz(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    intro = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)
        verbose_name_plural = 'Quizzes'

    def __str__(self):
        return self.name


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.CharField(max_length=300)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('quiz', 'sort_order')

    def __str__(self):
        return f'Q{self.sort_order}: {self.text[:60]}'


class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=200)
    weights = models.JSONField(
        default=dict,
        help_text='{ "oily": 1, "dry": 0, "combination": 2 }',
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('question', 'sort_order')

    def __str__(self):
        return self.text


class ResultType(models.Model):
    """A possible outcome — e.g. 'Oily', 'Dry', 'Combination', 'Sensitive'."""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='result_types')
    slug = models.SlugField(max_length=80)
    name = models.CharField(max_length=120)
    summary = models.TextField(blank=True)
    long_description = models.TextField(blank=True)
    image_url = models.URLField(blank=True, default='')

    class Meta:
        unique_together = (('quiz', 'slug'),)
        ordering = ('quiz', 'name')

    def __str__(self):
        return f'{self.quiz.name} → {self.name}'


class Submission(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='quiz_submissions',
    )
    quiz = models.ForeignKey(Quiz, on_delete=models.PROTECT, related_name='submissions')
    selected_options = models.ManyToManyField(Option, related_name='+')
    primary_result = models.ForeignKey(
        ResultType, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    score_breakdown = models.JSONField(
        default=dict,
        help_text='Final score per result_type slug.',
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-submitted_at',)

    def __str__(self):
        return f'{self.user} → {self.quiz.name} → {self.primary_result}'
