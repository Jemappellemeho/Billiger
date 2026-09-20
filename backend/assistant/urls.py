from django.urls import path

from assistant.views import ChatView

urlpatterns = [
    path("assistant/chat/", ChatView.as_view(), name="assistant-chat"),
]
