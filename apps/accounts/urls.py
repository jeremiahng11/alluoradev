from django.urls import path
from .views import DeleteMeView, MeView, SkinProfileView, TierLadderView

urlpatterns = [
    path('me/', MeView.as_view(), name='accounts-me'),
    path('me/skin-profile/', SkinProfileView.as_view(),
         name='accounts-skin-profile'),
    path('me/delete/', DeleteMeView.as_view(), name='accounts-delete-me'),
    path('tiers/', TierLadderView.as_view(), name='accounts-tiers'),
]
