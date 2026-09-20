from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from streaks import tracking


class StreakView(APIView):
    """GET /api/streak/ — the signed-in account's streak, savings and weekly history."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(tracking.summary(request.user))
