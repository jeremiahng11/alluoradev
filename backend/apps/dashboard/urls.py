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

    # Videos
    path('videos/', views.VideoListView.as_view(), name='videos'),
    path('videos/new/', views.VideoCreateView.as_view(), name='video-create'),
    path('videos/<int:pk>/', views.VideoEditView.as_view(), name='video-edit'),
    path('videos/<int:pk>/delete/', views.VideoDeleteView.as_view(), name='video-delete'),

    # Rewards
    path('rewards/', views.RewardsView.as_view(), name='rewards'),
    path('rewards/grant/', views.RewardsGrantView.as_view(), name='rewards-grant'),

    # Users
    path('users/', views.UserListView.as_view(), name='users'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),

    # Settings
    path('settings/', views.SettingsView.as_view(), name='settings'),
]
