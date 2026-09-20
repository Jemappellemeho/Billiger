from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class OptionalTokenAuthentication(TokenAuthentication):
    """Recognises signed-in callers, but treats a stale or revoked token as a guest.

    For endpoints that work without an account and only add something extra
    when signed in (e.g. the cart comparison counting toward the streak): a
    token that is no longer valid must not turn a guest-capable request into a 401.
    """

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            return None
