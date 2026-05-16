from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('', views.HomeView.as_view(), name='home'),

    # Content
    path('articles/', views.ArticleListView.as_view(), name='articles'),
    path('articles/new/', views.ArticleCreateView.as_view(), name='article-create'),
    path('articles/<int:pk>/', views.ArticleEditView.as_view(), name='article-edit'),
    path('articles/<int:pk>/delete/', views.ArticleDeleteView.as_view(), name='article-delete'),

    # Library — downloadable ebooks (PDFs), with optional members-only gate
    path('ebooks/', views.EbookListView.as_view(), name='ebooks'),
    path('ebooks/new/', views.EbookCreateView.as_view(), name='ebook-create'),
    path('ebooks/<int:pk>/', views.EbookEditView.as_view(), name='ebook-edit'),
    path('ebooks/<int:pk>/delete/', views.EbookDeleteView.as_view(), name='ebook-delete'),

    # Content categories (taxonomy for articles)
    path('categories/', views.CategoryListView.as_view(), name='categories'),
    path('categories/new/', views.CategoryCreateView.as_view(), name='category-create'),
    path('categories/<int:pk>/', views.CategoryEditView.as_view(), name='category-edit'),
    path('categories/<int:pk>/delete/', views.CategoryDeleteView.as_view(), name='category-delete'),
    # JSON endpoint used by the article form's inline "+ New category" widget.
    path('categories/api/create/', views.CategoryApiCreateView.as_view(), name='category-api-create'),

    # Videos (long-form, with collections)
    path('videos/', views.VideoListView.as_view(), name='videos'),
    path('videos/new/', views.VideoCreateView.as_view(), name='video-create'),
    path('videos/<int:pk>/', views.VideoEditView.as_view(), name='video-edit'),
    path('videos/<int:pk>/delete/', views.VideoDeleteView.as_view(), name='video-delete'),
    path('videos/<int:video_id>/comments/<int:comment_id>/delete/',
         views.VideoCommentDeleteAdminView.as_view(), name='video-comment-delete'),

    # Reels (short-form, 20-90s, no collection)
    path('reels/', views.ReelListView.as_view(), name='reels'),
    path('reels/new/', views.ReelCreateView.as_view(), name='reel-create'),
    path('reels/<int:pk>/', views.ReelEditView.as_view(), name='reel-edit'),
    path('reels/<int:pk>/delete/', views.ReelDeleteView.as_view(), name='reel-delete'),

    # Video collections (taxonomy for videos)
    path('collections/', views.CollectionListView.as_view(), name='collections'),
    path('collections/new/', views.CollectionCreateView.as_view(), name='collection-create'),
    path('collections/<int:pk>/', views.CollectionEditView.as_view(), name='collection-edit'),
    path('collections/<int:pk>/delete/', views.CollectionDeleteView.as_view(), name='collection-delete'),

    # Rewards
    path('rewards/', views.RewardsView.as_view(), name='rewards'),
    path('rewards/grant/', views.RewardsGrantView.as_view(), name='rewards-grant'),

    # Membership — tier overview + cards directory
    path('membership/', views.MembershipView.as_view(), name='membership'),
    path('membership/tier-rules/',
         views.TierRuleUpdateView.as_view(), name='tier-rule-update'),
    path('membership/sync-all/',
         views.MembershipSyncAllView.as_view(), name='membership-sync-all'),

    # Users
    path('users/', views.UserListView.as_view(), name='users'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
    path('users/<int:pk>/tier/', views.UserTierUpdateView.as_view(), name='user-tier-update'),
    path('users/<int:pk>/sync-spending/',
         views.UserSpendingSyncView.as_view(), name='user-sync-spending'),

    # Stats / analytics
    path('stats/', views.StatsView.as_view(), name='stats'),

    # Settings
    path('settings/', views.SettingsView.as_view(), name='settings'),

    # Skin AI tier rules now live inside the Settings page; only the
    # update POST handler remains as its own URL.
    path('skin-ai/settings/update/',
         views.SkinAiSettingsUpdateView.as_view(),
         name='skin-ai-settings-update'),
    # Bust the WC product cache used by the recommendation engine.
    path('skin-ai/clear-products-cache/',
         views.SkinAiClearProductsCacheView.as_view(),
         name='skin-ai-clear-products-cache'),
    # Force-recompute the dormant tier-averages aggregation.
    path('skin-ai/refresh-tier-averages/',
         views.SkinAiRefreshTierAvgView.as_view(),
         name='skin-ai-refresh-tier-averages'),

    # Skin AI — admin browser of user scans (read + hard delete)
    path('skin-ai/users/',
         views.SkinAiUsersView.as_view(), name='skin-ai-users'),
    path('skin-ai/users/<int:pk>/',
         views.SkinAiUserDetailView.as_view(), name='skin-ai-user-detail'),
    path('skin-ai/users/<int:pk>/bulk-delete/',
         views.SkinAiUserBulkDeleteView.as_view(),
         name='skin-ai-user-bulk-delete'),
    path('skin-ai/results/<int:pk>/',
         views.SkinAiAnalysisDetailView.as_view(),
         name='skin-ai-analysis-detail'),
    path('skin-ai/results/<int:pk>/original/',
         views.SkinAiAnalysisOriginalView.as_view(),
         name='skin-ai-analysis-original'),
    path('skin-ai/results/<int:pk>/delete/',
         views.SkinAiAnalysisDeleteView.as_view(),
         name='skin-ai-analysis-delete'),
]
