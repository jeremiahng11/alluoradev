"""Content API for the mobile app."""
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.utils import timezone
from rest_framework import serializers, viewsets, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import ContentCategory, Article, ArticleView, Ebook, EbookDownload


class ContentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentCategory
        fields = ('id', 'name', 'slug', 'sort_order')


class ArticleListSerializer(serializers.ModelSerializer):
    cover = serializers.CharField(read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    author_name = serializers.CharField(source='author.display_name_or_email', read_only=True)

    class Meta:
        model = Article
        fields = (
            'id', 'title', 'slug', 'summary', 'cover',
            'category', 'category_name', 'author_name',
            'is_featured', 'published_at',
        )


class ArticleDetailSerializer(ArticleListSerializer):
    class Meta(ArticleListSerializer.Meta):
        fields = ArticleListSerializer.Meta.fields + ('body',)


class ContentCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ContentCategory.objects.all()
    serializer_class = ContentCategorySerializer
    permission_classes = [permissions.AllowAny]


class ArticleViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ('category', 'is_featured')
    search_fields = ('title', 'summary')
    ordering_fields = ('published_at', 'created_at')
    lookup_field = 'slug'

    def get_queryset(self):
        return Article.objects.filter(
            status=Article.STATUS_PUBLISHED,
            published_at__lte=timezone.now(),
        ).select_related('category', 'author')

    def get_serializer_class(self):
        if self.action == 'list':
            return ArticleListSerializer
        return ArticleDetailSerializer

    @action(detail=True, methods=['post'],
            permission_classes=[permissions.AllowAny])
    def track(self, request, slug=None):
        """Record one article open. Called by the app's article detail
        screen on mount. Guests count too."""
        article = self.get_object()
        ArticleView.objects.create(
            article=article,
            user=request.user if request.user.is_authenticated else None,
        )
        return Response({
            'tracked': True,
            'view_count': article.view_events.count(),
        })


class EbookListSerializer(serializers.ModelSerializer):
    cover = serializers.CharField(read_only=True)
    category_name = serializers.CharField(
        source='category.name', read_only=True, default=None,
    )
    download_url = serializers.SerializerMethodField()
    locked = serializers.SerializerMethodField()

    class Meta:
        model = Ebook
        fields = (
            'id', 'title', 'slug', 'description', 'author_name', 'cover',
            'category', 'category_name',
            'is_members_only', 'locked',
            'pdf_size_bytes', 'page_count',
            'download_url', 'download_count',
            'published_at',
        )

    def get_download_url(self, obj: Ebook):
        """Absolute URL to the gated download endpoint, OR None when
        the caller isn't allowed to download this ebook. Mobile uses
        the null signal to show the lock badge + join CTA."""
        request = self.context.get('request')
        if obj.is_members_only and (
            not request or not request.user.is_authenticated
        ):
            return None
        if not request:
            return None
        return request.build_absolute_uri(
            f'/api/v1/content/ebooks/{obj.slug}/download/'
        )

    def get_locked(self, obj: Ebook) -> bool:
        request = self.context.get('request')
        if not obj.is_members_only:
            return False
        return not (request and request.user.is_authenticated)


class EbookViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ebook browser. Guests see everything but only get a
    download_url for free ebooks (members-only show locked=True).

    The actual file download lives at /ebooks/<slug>/download/ — that
    view re-checks auth so a guessed URL can't bypass the lock.
    """
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter,
                       filters.OrderingFilter]
    filterset_fields = ('category', 'is_members_only')
    search_fields = ('title', 'description', 'author_name')
    ordering_fields = ('published_at', 'created_at', 'download_count')
    lookup_field = 'slug'
    serializer_class = EbookListSerializer

    def get_queryset(self):
        return Ebook.objects.filter(
            status=Ebook.STATUS_PUBLISHED,
            published_at__lte=timezone.now(),
        ).select_related('category')

    @action(detail=True, methods=['get'],
            permission_classes=[permissions.AllowAny],
            url_path='download')
    def download(self, request, slug=None):
        """Stream the PDF. Guests are 403'd on members-only ebooks.
        Increments download_count + drops an EbookDownload row for
        audit / per-ebook leaderboards."""
        ebook = self.get_object()
        if ebook.is_members_only and not request.user.is_authenticated:
            return HttpResponseForbidden(
                'This ebook is for members only. Sign in to download.'
            )
        if not ebook.pdf_file:
            raise Http404('No file attached to this ebook.')
        try:
            fh = ebook.pdf_file.open('rb')
        except FileNotFoundError:
            raise Http404('Ebook file is missing on disk.')

        EbookDownload.objects.create(
            ebook=ebook,
            user=request.user if request.user.is_authenticated else None,
        )
        # F() expression so concurrent downloads don't trample each other.
        from django.db.models import F
        Ebook.objects.filter(pk=ebook.pk).update(
            download_count=F('download_count') + 1,
        )

        filename = ebook.pdf_file.name.rsplit('/', 1)[-1]
        response = FileResponse(
            fh, content_type='application/pdf', as_attachment=False,
            filename=filename,
        )
        # Encourage the OS to open it inline (system PDF viewer) rather
        # than always pushing a download. `url_launcher` on the Flutter
        # side passes the URL to the OS viewer either way.
        response['Content-Disposition'] = (
            f'inline; filename="{filename}"'
        )
        return response
