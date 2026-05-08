from django.urls import path
from .views import QuizDetailView, QuizSubmitView, MySubmissionsView

urlpatterns = [
    path('submissions/', MySubmissionsView.as_view(), name='quiz-submissions'),
    path('<slug:slug>/', QuizDetailView.as_view(), name='quiz-detail'),
    path('<slug:slug>/submit/', QuizSubmitView.as_view(), name='quiz-submit'),
]
