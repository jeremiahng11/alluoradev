from django.apps import AppConfig


class SkinaiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.skinai'
    verbose_name = 'Skin AI'

    def ready(self):
        # Heavy ML deps (TensorFlow, DeepFace) are imported lazily on
        # first analysis. We deliberately do NOT pre-warm here — Django
        # startup must stay fast for healthchecks. The first analyser
        # request pays a one-time ~5-10s cost while DeepFace loads;
        # subsequent calls reuse the in-process cache.
        pass
