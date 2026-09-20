from django.urls import path

from streaks.views import StreakView

urlpatterns = [
    path("streak/", StreakView.as_view(), name="streak"),
]
