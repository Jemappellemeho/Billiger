from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.http import HttpResponse, HttpResponseRedirect
from rest_framework.throttling import SimpleRateThrottle

from accounts import google


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

    Only reached when an external LLM client sends a user here to authorize it. Accounts created
    with Google have no password, so the page offers Google sign-in next to the password form.
    """

    template_name = "registration/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        # Google's sign-in popup hands its credential back through window.opener, which Django's
        # default `same-origin` policy severs; SecurityMiddleware leaves a header already set alone.
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["google_client_id"] = settings.GOOGLE_OAUTH_CLIENT_ID
        return context

    def post(self, request, *args, **kwargs):
        if not _LoginThrottle().allow_request(request, self):
            return HttpResponse("Zu viele Anmeldeversuche. Bitte warte kurz.", status=429)
        if "google_credential" in request.POST:
            return self._sign_in_with_google(request, request.POST["google_credential"])
        return super().post(request, *args, **kwargs)

    def _sign_in_with_google(self, request, credential):
        try:
            email = google.verified_email(credential)
        except (google.GoogleLoginUnavailable, google.InvalidGoogleToken) as exc:
            return self._google_error(request, str(exc))

        # Unlike the API's Google login this never creates an account: registering through another
        # party's client is not what a consent screen is for.
        user = get_user_model().objects.filter(username=email).first()
        if user is None:
            return self._google_error(
                request, "Für diese E-Mail gibt es noch kein Billiger-Konto. Registriere dich zuerst in der Billiger-App."
            )
        if user.has_usable_password():
            # Emails aren't verified at password registration, so silently linking would let a
            # pre-registered attacker inherit this login (same rule as the API, Ticket 12).
            return self._google_error(
                request,
                "Für diese E-Mail existiert bereits ein Konto mit Passwort. Melde dich mit E-Mail und Passwort an.",
            )
        if not user.is_active:
            return self._google_error(request, "Dieses Konto ist deaktiviert.")

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return HttpResponseRedirect(self.get_success_url())

    def _google_error(self, request, message):
        form = self.get_form_class()(request=request)
        return self.render_to_response(self.get_context_data(form=form, google_error=message))
