import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from assistant.agent import run_assistant
from assistant.llm import LLMError, LLMNotConfigured, llm_from_django_settings
from assistant.serializers import ChatRequestSerializer
from assistant.tools import ToolContext, zip_code_resolver

logger = logging.getLogger(__name__)


class ChatView(APIView):
    """POST /api/assistant/chat/ {message, input?, history?, zip_code|lat+lon?}

    One turn of the built-in assistant. Needs an account (guest mode has no
    server-side access point). Text and voice share this one endpoint: a
    voice message is just a transcript with `input: "voice"`.

    The location is only used by the tools that need prices (price query,
    cart comparison); the client sends its current one with every turn.
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
            }
        )
