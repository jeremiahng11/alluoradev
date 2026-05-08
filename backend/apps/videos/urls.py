from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    VideoViewSet, VideoCollectionViewSet,
    AdminCreateVideoView, AdminPresignView, AdminSyncStatusView,
)

router = DefaultRouter()
router.register('collections', VideoCollectionViewSet, basename='video-collection')
router.register('', VideoViewSet, basename='video')

urlpatterns = [
    path('admin/create/', AdminCreateVideoView.as_view(), name='video-admin-create'),
    path('admin/<int:pk>/presign/', AdminPresignView.as_view(), name='video-admin-presign'),
    path('admin/<int:pk>/sync/', AdminSyncStatusView.as_view(), name='video-admin-sync'),
] + router.urls
