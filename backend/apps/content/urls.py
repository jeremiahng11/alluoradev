from rest_framework.routers import DefaultRouter
from .views import ContentCategoryViewSet, ArticleViewSet

router = DefaultRouter()
router.register('categories', ContentCategoryViewSet, basename='content-category')
router.register('articles', ArticleViewSet, basename='article')

urlpatterns = router.urls
