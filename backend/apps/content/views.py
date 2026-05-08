"""Content API for the mobile app."""
from django.utils import timezone
from rest_framework import serializers, viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import ContentCategory, Article


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
