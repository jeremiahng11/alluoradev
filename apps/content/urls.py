from rest_framework.routers import DefaultRouter
from .views import ContentCategoryViewSet, ArticleViewSet, EbookViewSet

router = DefaultRouter()
router.register('categories', ContentCategoryViewSet, basename='content-category')
router.register('articles', ArticleViewSet, basename='article')
router.register('ebooks', EbookViewSet, basename='ebook')

urlpatterns = router.urls
