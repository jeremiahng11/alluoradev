from django.urls import path

from . import views

app_name = 'skinai'

urlpatterns = [
    path('analyze/', views.AnalyzeView.as_view(), name='analyze'),
    path('history/', views.HistoryView.as_view(), name='history'),
    path('quota/', views.QuotaView.as_view(), name='quota'),
    # User-managed routine tracker.
    path('routine/', views.RoutineProductListCreateView.as_view(),
         name='routine-list'),
    path('routine/<int:pk>/',
         views.RoutineProductDetailView.as_view(), name='routine-detail'),
    # Daily check-in: lightweight free scan, 1/day, no insights/recs.
    path('check-in/', views.CheckInView.as_view(), name='check-in'),
    path('check-ins/', views.CheckInsListView.as_view(),
         name='check-ins-list'),
    path('check-ins/<int:pk>/thumb/',
         views.CheckInThumbView.as_view(), name='check-in-thumb'),
    # Auth-gated thumbnail (owner or dashboard admin). Replaces
    # public /media/skinai/thumbs/... access for face images.
    path('<int:pk>/thumb/',
         views.ThumbnailView.as_view(), name='thumb'),
    # Product recommendations for an analysis. Owner-only — pulls
    # matching items from the WC catalog tagged by recommendations.py.
    path('<int:pk>/recommendations/',
         views.RecommendationsView.as_view(), name='recommendations'),
    path('<int:pk>/', views.DeleteAnalysisView.as_view(), name='delete'),
    path('health/', views.HealthView.as_view(), name='health'),
    path('deps/', views.DepsHealthView.as_view(), name='deps'),
    path('selftest/', views.SelfTestView.as_view(), name='selftest'),
]
