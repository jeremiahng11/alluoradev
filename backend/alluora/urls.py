"""URL routing for the Alluora platform."""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),

    # Custom admin dashboard (NOT django admin)
    path('dashboard/', include('apps.dashboard.urls')),

    # Keep django admin available at /django-admin/ for emergency use only.
    path('django-admin/', admin.site.urls),

    # API
    path('api/v1/', include([
        path('accounts/', include('apps.accounts.urls')),
        path('content/', include('apps.content.urls')),
        path('videos/', include('apps.videos.urls')),
        path('rewards/', include('apps.rewards.urls')),
        path('quiz/', include('apps.quiz.urls')),
    ])),

    # API schema + Swagger UI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
