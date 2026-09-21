from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from rest_framework.throttling import SimpleRateThrottle


class _LoginThrottle(SimpleRateThrottle):
    """The API's brute-force guard for sign-in (`auth`, per client IP), applied to this login form too."""

    scope = "auth"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class EmailAuthenticationForm(AuthenticationForm):
    """Accounts are identified by their lowercased email, stored as the username."""

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class ConsentLoginView(LoginView):
    """Sign-in for the OAuth consent screen: the one place the API's accounts get a browser session.

    Only reached when an external LLM client sends a user here to authorize it.
    """

    template_name = "registration/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        if not _LoginThrottle().allow_request(request, self):
            return HttpResponse("Zu viele Anmeldeversuche. Bitte warte kurz.", status=429)
        return super().post(request, *args, **kwargs)
