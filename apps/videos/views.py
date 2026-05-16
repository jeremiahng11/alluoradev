"""Videos API.

Public endpoints:
  GET  /api/v1/videos/                          list published videos
  GET  /api/v1/videos/{id}/                     video detail (HLS URL, thumbnail)
  GET  /api/v1/videos/collections/              list collections
  GET  /api/v1/videos/{id}/comments/            list comments on a video
  POST /api/v1/videos/{id}/comments/            add a comment (auth required)
  POST /api/v1/videos/{id}/like/                toggle like (auth required)
  DELETE /api/v1/videos/{id}/comments/{cid}/    delete a comment
                                                (auth: owner OR dashboard admin)

Admin-only endpoints (dashboard staff):
  POST /api/v1/videos/admin/create/             create Bunny video object + DB row
  POST /api/v1/videos/admin/{id}/presign/       get TUS upload signature
  POST /api/v1/videos/admin/{id}/sync/          pull status from Bunny
"""
from rest_framework import serializers, viewsets, generics, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Count, Exists, F, OuterRef
from django_filters.rest_framework import DjangoFilterBackend

from .models import Video, VideoCollection, VideoLike, VideoComment, VideoView
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
    mp4_url = serializers.CharField(read_only=True)
    thumbnail_url = serializers.CharField(read_only=True)
    collection_name = serializers.CharField(source='collection.name', read_only=True)

    # Annotated by VideoViewSet.get_queryset; default to 0/false on bare
    # serialization paths (e.g. AdminCreateVideoView.post returning a
    # freshly-created row that wasn't pulled through the annotated qs).
    like_count = serializers.IntegerField(read_only=True, default=0)
    comment_count = serializers.IntegerField(read_only=True, default=0)
    liked_by_me = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Video
        fields = (
            'id', 'title', 'description',
            'collection', 'collection_name',
            'duration_seconds', 'width', 'height', 'views',
            'is_featured', 'is_reel',
            'min_tier', 'hls_url', 'mp4_url', 'thumbnail_url',
            'comments_enabled',
            'like_count', 'comment_count', 'liked_by_me',
            'created_at',
        )


class VideoCommentSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    user_name = serializers.SerializerMethodField()
    user_avatar = serializers.SerializerMethodField()

    class Meta:
        model = VideoComment
        fields = ('id', 'body', 'created_at',
                  'user_id', 'user_name', 'user_avatar')
        read_only_fields = ('id', 'created_at',
                            'user_id', 'user_name', 'user_avatar')

    def get_user_name(self, obj):
        u = obj.user
        full = f'{u.first_name} {u.last_name}'.strip()
        return full or u.username or u.email.split('@')[0]

    def get_user_avatar(self, obj):
        return getattr(obj.user, 'avatar_url', '') or ''

    def validate_body(self, value):
        v = (value or '').strip()
        if not v:
            raise serializers.ValidationError("Comment can't be empty.")
        return v


# ---------------------------------------------------------------------------
# Public viewsets
# ---------------------------------------------------------------------------

class VideoCollectionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VideoCollection.objects.all()
    serializer_class = VideoCollectionSerializer
    permission_classes = [permissions.AllowAny]


class VideoViewSet(viewsets.ReadOnlyModelViewSet):
    """Public read-only video catalogue.

    Tier-gated: guests (anonymous) only see videos with `min_tier='none'`.
    Authenticated members see every video at or below their tier
    (Silver=1, Gold=2, Platinum=3, Titanium=4).
    """
    serializer_class = VideoSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ('collection', 'is_featured', 'is_reel', 'min_tier')

    def get_queryset(self):
        from django.db.models import Q
        from django.utils import timezone
        qs = Video.objects.filter(
            is_published=True,
            status=Video.STATUS_READY,
        ).filter(
            Q(publish_at__isnull=True) | Q(publish_at__lte=timezone.now())
        ).select_related('collection')

        # Annotate counts + per-user liked flag so the Reel doesn't need
        # N+1 round trips for like/comment metadata.
        qs = qs.annotate(
            like_count=Count('likes', distinct=True),
            comment_count=Count('comments', distinct=True),
        )
        user = self.request.user
        if user.is_authenticated:
            qs = qs.annotate(
                liked_by_me=Exists(
                    VideoLike.objects.filter(video=OuterRef('pk'), user=user)
                )
            )

        # Tier filter.
        viewer_rank = 0
        if user.is_authenticated:
            viewer_rank = Video.TIER_RANKS.get(
                getattr(user, 'tier', Video.TIER_SILVER),
                Video.TIER_RANKS[Video.TIER_SILVER],
            )
        allowed_tiers = [
            tier for tier, rank in Video.TIER_RANKS.items() if rank <= viewer_rank
        ]
        return qs.filter(min_tier__in=allowed_tiers)

    # ─────────────────────────────────────────────────────────────────
    # Likes
    # ─────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────
    # View tracking
    # ─────────────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'],
            permission_classes=[permissions.AllowAny])
    def track(self, request, pk=None):
        """Record a watch session for this video.

        Called by the app:
          - Long-form videos: once on tap-to-play (seconds_watched=0),
            again on player close with the cumulative total.
          - Reels: once when the user crosses the 5-second threshold,
            again on scroll-away with the final total.

        Body: `{session_id: str, seconds_watched: int, completed?: bool}`

        session_id is a UUID the client generates ONCE per watch
        session. Multiple POSTs sharing the same session_id upsert
        one VideoView row — only the first POST bumps the public view
        counter. Without dedup, a Reel that fires "5s threshold" +
        "scroll-away" + "dispose" would otherwise count as 3 views.
        """
        video = self.get_object()
        try:
            secs = int(request.data.get('seconds_watched', 0) or 0)
        except (TypeError, ValueError):
            secs = 0
        secs = max(0, secs)
        # Server computes `completed` from duration so the client
        # can't game the metric — completed iff watched >= 95% of
        # the source duration (or the client explicitly says so AND
        # we have no duration to check against).
        completed = bool(request.data.get('completed', False))
        if video.duration_seconds:
            completed = secs >= max(1, int(video.duration_seconds * 0.95))

        session_id = (request.data.get('session_id') or '').strip()[:64]
        user = request.user if request.user.is_authenticated else None

        created = False
        if session_id:
            # Upsert by (video, session_id). Only the first POST in a
            # session creates a row + bumps the counter; later POSTs
            # update seconds_watched/completed only.
            existing = VideoView.objects.filter(
                video=video, session_id=session_id,
            ).first()
            if existing:
                # Don't let seconds_watched go down (e.g. on a stray
                # late POST after a fresh re-entry); only forward.
                if secs > existing.seconds_watched:
                    existing.seconds_watched = secs
                if completed:
                    existing.completed = True
                # Backfill user if the session started as a guest and
                # the user signed in mid-session.
                if existing.user_id is None and user is not None:
                    existing.user = user
                existing.save(update_fields=[
                    'seconds_watched', 'completed', 'user', 'updated_at',
                ])
            else:
                VideoView.objects.create(
                    video=video,
                    user=user,
                    session_id=session_id,
                    seconds_watched=secs,
                    completed=completed,
                    is_reel=video.is_reel,
                )
                created = True
        else:
            # Legacy clients without session_id — still create one row
            # per POST. Newer app builds always send a session_id.
            VideoView.objects.create(
                video=video,
                user=user,
                seconds_watched=secs,
                completed=completed,
                is_reel=video.is_reel,
            )
            created = True

        if created:
            Video.objects.filter(pk=video.pk).update(views=F('views') + 1)

        return Response({
            'tracked': True,
            'counted': created,
            'view_count': video.view_events.count(),
        })

    @action(detail=True, methods=['post'],
            permission_classes=[permissions.IsAuthenticated])
    def like(self, request, pk=None):
        """Toggle like state for the current user on this video.
        Returns the new state and updated count."""
        video = self.get_object()
        existing = VideoLike.objects.filter(video=video, user=request.user).first()
        if existing:
            existing.delete()
            liked = False
        else:
            VideoLike.objects.create(video=video, user=request.user)
            liked = True
        return Response({
            'liked': liked,
            'like_count': VideoLike.objects.filter(video=video).count(),
        })

    # ─────────────────────────────────────────────────────────────────
    # Comments
    # ─────────────────────────────────────────────────────────────────

    @action(detail=True, methods=['get', 'post'],
            permission_classes=[permissions.AllowAny])
    def comments(self, request, pk=None):
        video = self.get_object()
        if request.method == 'GET':
            qs = (video.comments
                  .select_related('user')
                  .order_by('-created_at')[:200])
            return Response(VideoCommentSerializer(qs, many=True).data)

        # POST — create
        if not request.user.is_authenticated:
            return Response({'detail': 'Sign in to comment.'},
                            status=status.HTTP_401_UNAUTHORIZED)
        if not video.comments_enabled:
            return Response({'detail': 'Comments are turned off for this video.'},
                            status=status.HTTP_403_FORBIDDEN)
        serializer = VideoCommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = VideoComment.objects.create(
            video=video,
            user=request.user,
            body=serializer.validated_data['body'],
        )
        return Response(VideoCommentSerializer(comment).data,
                        status=status.HTTP_201_CREATED)


class VideoCommentDeleteView(APIView):
    """DELETE /videos/<video_id>/comments/<comment_id>/

    The comment owner OR a dashboard admin can delete a comment. The
    @action mechanism on VideoViewSet doesn't compose a sub-id into the
    URL, so this lives as a standalone view.
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, video_id, comment_id):
        try:
            comment = VideoComment.objects.get(pk=comment_id, video_id=video_id)
        except VideoComment.DoesNotExist:
            return Response({'detail': 'Not found.'},
                            status=status.HTTP_404_NOT_FOUND)
        is_owner = comment.user_id == request.user.id
        is_admin = getattr(request.user, 'is_dashboard_admin', False)
        if not (is_owner or is_admin):
            return Response({'detail': 'Forbidden.'},
                            status=status.HTTP_403_FORBIDDEN)
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Admin endpoints — used by the dashboard upload UI
# ---------------------------------------------------------------------------

class CreateVideoRequestSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    collection_id = serializers.IntegerField(required=False, allow_null=True)
    is_reel = serializers.BooleanField(required=False, default=False)
    min_tier = serializers.ChoiceField(
        choices=Video.MIN_TIER_CHOICES,
        required=False,
        default=Video.TIER_NONE,
    )
    publish_at = serializers.DateTimeField(required=False, allow_null=True)


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
        is_reel = serializer.validated_data.get('is_reel', False)
        min_tier = serializer.validated_data.get('min_tier', Video.TIER_NONE)

        if not bunny.is_configured():
            return Response(
                {'detail': 'Bunny Stream is not configured.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Route uploads to the right Bunny-side collection so the admin
        # has a clean split there too: long-form videos → 'Alluora',
        # short-form clips → 'Reels'. Best-effort — if Bunny rejects
        # the lookup we just upload into the default root collection.
        bunny_collection_id = bunny.get_or_create_collection(
            'Reels' if is_reel else 'Alluora'
        )

        try:
            bunny_resp = bunny.create_video(
                title, collection_id=bunny_collection_id,
            )
        except bunny.BunnyStreamError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        # Reels never have a collection — strip even if the client sent one.
        video = Video.objects.create(
            title=title,
            description=description,
            bunny_video_guid=bunny_resp['guid'],
            collection_id=None if is_reel else collection_id,
            is_reel=is_reel,
            min_tier=min_tier,
            publish_at=serializer.validated_data.get('publish_at'),
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
        # Don't mirror Bunny's `views` — see _sync_bunny_for_video for
        # why. VideoView.count() is the authoritative source.

        video.save(update_fields=update_fields)
        return Response(VideoSerializer(video).data)
