"""Videos API.

Public endpoints (no auth):
  GET  /api/v1/videos/                    list published videos
  GET  /api/v1/videos/{id}/               video detail (HLS URL, thumbnail)
  GET  /api/v1/videos/collections/        list collections

Admin-only endpoints (dashboard staff):
  POST /api/v1/videos/admin/create/       create Bunny video object + DB row
  POST /api/v1/videos/admin/{id}/presign/ get TUS upload signature
  POST /api/v1/videos/admin/{id}/sync/    pull status from Bunny
"""
from rest_framework import serializers, viewsets, generics, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Video, VideoCollection
from . import bunny


# --------------------------------------------------------------------------- 
# Permissions
# ---------------------------------------------------------------------------

class IsDashboardAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and
            getattr(request.user, 'is_dashboard_admin', False)
        )


# --------------------------------------------------------------------------- 
# Serializers — public-facing
# ---------------------------------------------------------------------------

class VideoCollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoCollection
        fields = ('id', 'name', 'slug', 'sort_order')


class VideoSerializer(serializers.ModelSerializer):
    hls_url = serializers.CharField(read_only=True)
    thumbnail_url = serializers.CharField(read_only=True)
    collection_name = serializers.CharField(source='collection.name', read_only=True)

    class Meta:
        model = Video
        fields = (
            'id', 'title', 'description', 'collection', 'collection_name',
            'duration_seconds', 'width', 'height',
            'is_featured', 'hls_url', 'thumbnail_url', 'created_at',
        )


# --------------------------------------------------------------------------- 
# Public viewsets
# ---------------------------------------------------------------------------

class VideoCollectionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VideoCollection.objects.all()
    serializer_class = VideoCollectionSerializer
    permission_classes = [permissions.AllowAny]


class VideoViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = VideoSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ('collection', 'is_featured')

    def get_queryset(self):
        return Video.objects.filter(
            is_published=True,
            status=Video.STATUS_READY,
        ).select_related('collection')


# --------------------------------------------------------------------------- 
# Admin endpoints — used by the dashboard upload UI
# ---------------------------------------------------------------------------

class CreateVideoRequestSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    collection_id = serializers.IntegerField(required=False, allow_null=True)


class AdminCreateVideoView(generics.GenericAPIView):
    """Step 1: dashboard calls this to mint a Bunny video GUID + DB row.
    Returns the new Video record. Then call /presign/ next."""
    permission_classes = [IsDashboardAdmin]
    serializer_class = CreateVideoRequestSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        title = serializer.validated_data['title']
        description = serializer.validated_data.get('description', '')
        collection_id = serializer.validated_data.get('collection_id')

        if not bunny.is_configured():
            return Response(
                {'detail': 'Bunny Stream is not configured.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            bunny_resp = bunny.create_video(title)
        except bunny.BunnyStreamError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        video = Video.objects.create(
            title=title,
            description=description,
            bunny_video_guid=bunny_resp['guid'],
            collection_id=collection_id,
            status=Video.STATUS_CREATED,
        )
        return Response(VideoSerializer(video).data, status=status.HTTP_201_CREATED)


class AdminPresignView(generics.GenericAPIView):
    """Step 2: get TUS upload headers for the given video. Client uses these
    to upload bytes directly to Bunny."""
    permission_classes = [IsDashboardAdmin]

    def post(self, request, pk):
        try:
            video = Video.objects.get(pk=pk)
        except Video.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            data = bunny.make_presigned_upload(video.bunny_video_guid)
        except bunny.BunnyStreamError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        video.status = Video.STATUS_UPLOADING
        video.save(update_fields=['status'])
        return Response(data)


class AdminSyncStatusView(generics.GenericAPIView):
    """Step 3 (poll): pull status + metadata from Bunny.
    Once Bunny reports status=4 (ready) we update our row."""
    permission_classes = [IsDashboardAdmin]

    BUNNY_STATUS_MAP = {
        0: Video.STATUS_CREATED,
        1: Video.STATUS_UPLOADING,
        2: Video.STATUS_PROCESSING,
        3: Video.STATUS_PROCESSING,
        4: Video.STATUS_READY,
        5: Video.STATUS_FAILED,
        6: Video.STATUS_FAILED,
    }

    def post(self, request, pk):
        try:
            video = Video.objects.get(pk=pk)
        except Video.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            bunny_data = bunny.get_video(video.bunny_video_guid)
        except bunny.BunnyStreamError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        bunny_status = bunny_data.get('status', 0)
        new_status = self.BUNNY_STATUS_MAP.get(bunny_status, video.status)
        update_fields = ['status']

        if new_status != video.status:
            video.status = new_status

        if bunny_data.get('length'):
            video.duration_seconds = int(bunny_data['length'])
            update_fields.append('duration_seconds')
        if bunny_data.get('width'):
            video.width = bunny_data['width']
            update_fields.append('width')
        if bunny_data.get('height'):
            video.height = bunny_data['height']
            update_fields.append('height')

        video.save(update_fields=update_fields)
        return Response(VideoSerializer(video).data)
