from django.urls import path

from assistant import proposals
from assistant.views import ChatView, ProposalDecisionView, ProposalView

urlpatterns = [
    path("assistant/chat/", ChatView.as_view(), name="assistant-chat"),
    path("assistant/proposals/<int:pk>/", ProposalView.as_view(), name="assistant-proposal"),
    path(
        "assistant/proposals/<int:pk>/accept/",
        ProposalDecisionView.as_view(decision=proposals.accept),
        name="assistant-proposal-accept",
    ),
    path(
        "assistant/proposals/<int:pk>/reject/",
        ProposalDecisionView.as_view(decision=proposals.reject),
        name="assistant-proposal-reject",
    ),
]
