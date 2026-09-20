from django.conf import settings
from google.auth.exceptions import TransportError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


class GoogleLoginUnavailable(Exception):
    """Google login is not configured, or Google could not be reached."""


class InvalidGoogleToken(Exception):
    """The ID token failed verification or carries no verified email."""


def verified_email(token):
    """Verify a Google ID token (signature, expiry, audience) and return its lowercased email."""
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    if not client_id:
        raise GoogleLoginUnavailable("Google-Login ist nicht konfiguriert.")

    try:
        claims = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
    except TransportError as exc:
        raise GoogleLoginUnavailable("Google ist derzeit nicht erreichbar.") from exc
    except ValueError as exc:
        raise InvalidGoogleToken("Ungültiges Google-Token.") from exc

    email = claims.get("email")
    if not email or not claims.get("email_verified"):
        raise InvalidGoogleToken("Die Google-E-Mail ist nicht verifiziert.")
    return email.strip().lower()
