"""URL routing for the Alluora platform."""
from django.contrib import admin
from django.conf import settings
from django.urls import path, include, re_path
from django.views.generic import RedirectView
from django.views.static import serve as static_serve
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
        path('skinai/', include('apps.skinai.urls')),
    ])),

    # API schema + Swagger UI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

# Serve MEDIA_URL in every environment, not just DEBUG. We can't use
# django.conf.urls.static.static() here because it's a no-op when
# DEBUG=False — it returns an empty url list. Wire the django.views.
# static.serve view directly so the route exists in production.
#
# This is the pragmatic option for ~50 KB JPEG thumbnails behind
# Railway's Gunicorn. If thumbnail volume grows or full-res storage is
# added, switch to S3/Bunny via django-storages (already in
# requirements.txt) and drop this route.
urlpatterns += [
    re_path(
        r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'),
        static_serve,
        {'document_root': settings.MEDIA_ROOT},
    ),
]
