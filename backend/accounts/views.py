from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts import google, shopping_list
from accounts.serializers import (
    GoogleLoginSerializer,
    LoginSerializer,
    RegisterSerializer,
    ShoppingListSerializer,
)


def _session_response(user, guest_list, status=200):
    """Token + the account's list, with any guest-mode list migrated in first."""
    token, _ = Token.objects.get_or_create(user=user)
    return Response(
        {
            "token": token.key,
            "email": user.email,
            "shopping_list": shopping_list.migrate_guest_list(user, guest_list),
        },
        status=status,
    )


class AuthEndpoint(APIView):
    """Public sign-in endpoints: no credentials required, but throttled against brute force."""

    authentication_classes = []
    permission_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class RegisterView(AuthEndpoint):
    """POST /api/auth/register/ {email, password}"""

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = get_user_model().objects.create_user(
                username=serializer.validated_data["email"],
                email=serializer.validated_data["email"],
                password=serializer.validated_data["password"],
            )
            return _session_response(user, serializer.validated_data.get("guest_list"), status=201)


class LoginView(AuthEndpoint):
    """POST /api/auth/login/ {email, password}"""

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            username=serializer.validated_data["email"].strip().lower(),
            password=serializer.validated_data["password"],
        )
        if user is None:
            # Same answer for unknown email and wrong password: no account enumeration.
            return Response({"detail": "E-Mail oder Passwort ist falsch."}, status=400)
        return _session_response(user, serializer.validated_data.get("guest_list"))


class GoogleLoginView(AuthEndpoint):
    """POST /api/auth/google/ {id_token} — sign in or register with a Google ID token."""

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            email = google.verified_email(serializer.validated_data["id_token"])
        except google.GoogleLoginUnavailable as exc:
            return Response({"detail": str(exc)}, status=503)
        except google.InvalidGoogleToken as exc:
            return Response({"detail": str(exc)}, status=400)

        with transaction.atomic():
            user, created = get_user_model().objects.get_or_create(
                username=email, defaults={"email": email}
            )
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            elif user.has_usable_password():
                # Emails aren't verified at password registration, so silently
                # linking would let a pre-registered attacker inherit this login.
                return Response(
                    {"detail": "Für diese E-Mail existiert bereits ein Konto mit Passwort."},
                    status=409,
                )
            return _session_response(user, serializer.validated_data.get("guest_list"))


class LogoutView(APIView):
    """POST /api/auth/logout/ — revokes the account's token (signs out every device)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.auth.delete()
        return Response(status=204)


class ShoppingListView(APIView):
    """GET/PUT /api/shopping-list/ — the signed-in account's list + preferences."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(shopping_list.load(request.user))

    def put(self, request):
        serializer = ShoppingListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(shopping_list.save(request.user, serializer.data))
