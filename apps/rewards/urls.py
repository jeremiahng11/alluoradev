from django.urls import path
from .views import BalanceView, HistoryView

urlpatterns = [
    path('balance/', BalanceView.as_view(), name='rewards-balance'),
    path('history/', HistoryView.as_view(), name='rewards-history'),
]
