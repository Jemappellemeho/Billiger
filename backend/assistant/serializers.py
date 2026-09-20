from rest_framework import serializers

MAX_MESSAGE_LENGTH = 2000
MAX_HISTORY_MESSAGES = 40
INPUT_MODES = ("text", "voice")


class HistoryMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(max_length=4000)


class ChatRequestSerializer(serializers.Serializer):
    """`message` is the new user turn; `input` says how it was entered.

    A voice message arrives already transcribed (the browser does the
    speech-to-text) and is handled exactly like typed text — `input` only
    lets the client label the bubble.
    """

    message = serializers.CharField(max_length=MAX_MESSAGE_LENGTH)
    input = serializers.ChoiceField(choices=INPUT_MODES, default="text")
    history = HistoryMessageSerializer(many=True, required=False, max_length=MAX_HISTORY_MESSAGES)

    def validate_history(self, history):
        if history and history[0]["role"] != "user":
            raise serializers.ValidationError("Der Verlauf muss mit einer Nutzer-Nachricht beginnen.")
        return history
