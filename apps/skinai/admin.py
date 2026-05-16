from django.contrib import admin

from .models import SkinAiTierConfig, SkinAnalysis, SkinCheckIn


@admin.register(SkinAiTierConfig)
class SkinAiTierConfigAdmin(admin.ModelAdmin):
    list_display = (
        'tier', 'unlimited_free', 'free_scans_per_period', 'period_unit',
        'coin_cost_per_scan',
    )
    list_editable = (
        'unlimited_free', 'free_scans_per_period', 'period_unit',
        'coin_cost_per_scan',
    )


@admin.register(SkinAnalysis)
class SkinAnalysisAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'skin_age', 'overall_score', 'coin_cost', 'created_at',
    )
    list_filter = ('created_at',)
    search_fields = ('user__email', 'user__username')
    readonly_fields = (
        'user', 'thumbnail', 'skin_age', 'hydration_score', 'pores_score',
        'wrinkles_score', 'redness_score', 'spots_score', 'overall_score',
        'coin_cost', 'raw_results', 'created_at',
    )


@admin.register(SkinCheckIn)
class SkinCheckInAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'overall_score', 'skin_age', 'hydration_score',
        'redness_score', 'low_confidence', 'created_at',
    )
    list_filter = ('low_confidence', 'created_at')
    search_fields = ('user__email', 'user__username')
    readonly_fields = (
        'user', 'thumbnail', 'skin_age', 'overall_score',
        'hydration_score', 'redness_score', 'low_confidence',
        'pipeline_version', 'created_at',
    )
