import logging

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from assistant import proposals
from assistant.agent import run_assistant
from assistant.changes import CHANGES, ProposalInvalid
from assistant.llm import LLMError, LLMNotConfigured, llm_from_django_settings
from assistant.models import Proposal
from assistant.serializers import ChatRequestSerializer
from assistant.tools import ToolContext, zip_code_resolver

logger = logging.getLogger(__name__)


class ChatView(APIView):
    """POST /api/assistant/chat/ {message, input?, history?, zip_code|lat+lon?}

    One turn of the built-in assistant. Needs an account (guest mode has no
    server-side access point). Text and voice share this one endpoint: a
    voice message is just a transcript with `input: "voice"`.

    The location is only used by the tools that need prices (price query,
    cart comparison) and to show the "before" of a location change; the
    client sends its current one with every turn.

    `proposals` lists the changes the assistant suggested this turn. They are
    only suggestions: each one waits for the user's decision on the proposal
    endpoints below.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assistant"

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            llm = llm_from_django_settings()
        except LLMNotConfigured:
            return Response({"detail": "Der Assistent ist nicht eingerichtet."}, status=503)

        tool_context = ToolContext(user=request.user, zip_code=zip_code_resolver(request.data))
        try:
            reply = run_assistant(llm, data.get("history", []), data["message"], tool_context)
        except LLMError:
            logger.exception("The assistant's language model request failed")
            return Response({"detail": "Der Assistent ist derzeit nicht erreichbar."}, status=502)

        return Response(
            {
                "user_message": {"role": "user", "content": data["message"], "input": data["input"]},
                "reply": reply.text,
                "actions": reply.actions,
                "proposals": reply.proposals,
            }
        )


class ProposalCollectionView(APIView):
    """The account's proposals as a collection (Ticket 16: how a channel without a chat turn proposes).

    POST /api/assistant/proposals/ {kind, ...fields}  a new pending proposal, exactly what a chat turn's
                                                       `propose_*` tool stores: kind is `shopping_list`,
                                                       `preferences` or `location`, the fields are that
                                                       tool's input → 201 {proposal} with the full diff
    GET  /api/assistant/proposals/                     the caller's proposals still waiting for a decision

    Creating one changes nothing: it waits for the user on the decision endpoints below.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        pending = Proposal.objects.filter(user=request.user, status=Proposal.Status.PENDING)
        pending = pending.order_by("-created_at", "-pk")
        return Response({"proposals": [proposals.serialize(proposal) for proposal in pending]})

    def post(self, request):
        data = request.data
        if not isinstance(data, dict):
            return Response({"detail": "Die Eingabe muss ein Objekt sein."}, status=400)
        kind = data.get("kind")
        if kind not in CHANGES:
            return Response({"detail": f"kind muss einer von diesen sein: {', '.join(CHANGES)}."}, status=400)

        fields = {key: value for key, value in data.items() if key != "kind"}
        try:
            # The location a proposal is made from lives in the client; a channel without one has no "before".
            proposal = proposals.create(request.user, kind, fields, current_zip_code=lambda: None)
        except ProposalInvalid as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"proposal": proposals.serialize(proposal)}, status=201)


class _ProposalEndpoint(APIView):
    """The user's reaction to one of the assistant's proposals (only the owner's; others get 404).

    PUT    /api/assistant/proposals/<id>/         "Ändern": the edited proposal (same shape as the
                                                   proposed state) → the proposal with a fresh diff
    POST   /api/assistant/proposals/<id>/accept/  "Übernehmen": applies it → {proposal, message, ...}
    POST   /api/assistant/proposals/<id>/reject/  "Verwerfen": drops it → {proposal, message}

    `accept` also returns what changed: the account's `shopping_list` for list and preference
    changes, the new `location` (`{zip_code}`) for a location change — that lives in the client.
    A proposal that was already decided, or whose list changed in the meantime, answers 409.
    """

    permission_classes = [IsAuthenticated]

    def _proposal(self, request, pk):
        return get_object_or_404(Proposal, pk=pk, user=request.user)


class ProposalView(_ProposalEndpoint):
    def put(self, request, pk):
        proposal = self._proposal(request, pk)
        try:
            revised = proposals.revise(proposal, request.data)
        except proposals.ProposalNotPending:
            return _already_decided()
        except ProposalInvalid as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"proposal": proposals.serialize(revised)})


class ProposalDecisionView(_ProposalEndpoint):
    """`decision` is `proposals.accept` or `proposals.reject`, passed in through `as_view`."""

    decision = None

    def post(self, request, pk):
        proposal = self._proposal(request, pk)
        try:
            decided, outcome = self.decision(proposal)
        except proposals.ProposalNotPending:
            return _already_decided()
        except proposals.ProposalStale:
            return Response(
                {"detail": "Die Daten haben sich seit dem Vorschlag geändert. Bitte lass dir einen neuen vorschlagen."},
                status=409,
            )
        return Response({"proposal": proposals.serialize(decided), **outcome})


def _already_decided():
    return Response({"detail": "Über diesen Vorschlag wurde schon entschieden."}, status=409)
