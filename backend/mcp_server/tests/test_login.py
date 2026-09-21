from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from google.auth.exceptions import TransportError

from accounts.tests.helpers import VERIFY_GOOGLE_TOKEN as VERIFY, google_claims
from mcp_server.tests.helpers import LOGIN_URL, PASSWORD, McpTestCase


class ConsentLoginTests(McpTestCase):
    def test_an_account_signs_in_with_its_api_credentials_and_lands_where_it_was_going(self):
        response = self.sign_in(next="/oauth/authorize/?client_id=billiger-claude")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/oauth/authorize/?client_id=billiger-claude")

    def test_the_email_is_matched_case_insensitively_like_at_registration(self):
        self.assertEqual(self.sign_in(email="  Anna@Example.com ").status_code, 302)

    def test_a_wrong_password_is_refused(self):
        response = self.sign_in(password="wrong")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_redirect_to_another_site_is_ignored(self):
        response = self.sign_in(next="https://evil.example/")
        self.assertNotIn("evil.example", response["Location"])

    def test_sign_in_attempts_are_throttled_like_the_api_login(self):
        for _ in range(10):
            self.sign_in(password="wrong")

        response = self.sign_in()

        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_form_is_shown_in_german(self):
        response = self.client.get(LOGIN_URL)
        self.assertContains(response, "Anmelden")


NEXT = "/oauth/authorize/?client_id=billiger-claude"


@override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client-id")
class ConsentGoogleLoginTests(McpTestCase):
    def setUp(self):
        super().setUp()
        # Anna registered with Google: an account without a password.
        self.user.set_unusable_password()
        self.user.save()

    def sign_in_with_google(self, claims=None, **extra):
        with patch(VERIFY, return_value=claims or google_claims()) as verify:
            response = self.client.post(LOGIN_URL, {"google_credential": "google-jwt", **extra})
        self.verify = verify
        return response

    def test_a_google_account_signs_in_and_lands_where_it_was_going(self):
        response = self.sign_in_with_google(next=NEXT)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], NEXT)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
        self.assertEqual(self.verify.call_args.args[0], "google-jwt")
        self.assertEqual(self.verify.call_args.args[2], "test-client-id")

    def test_the_email_is_matched_case_insensitively(self):
        response = self.sign_in_with_google(google_claims("Anna@Example.com"))
        self.assertEqual(response.status_code, 302)

    def test_an_account_with_a_password_is_not_linked_silently(self):
        self.user.set_password(PASSWORD)
        self.user.save()

        response = self.sign_in_with_google()

        self.assertContains(response, "bereits ein Konto mit Passwort")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_an_unknown_email_does_not_create_an_account_and_points_to_the_app(self):
        response = self.sign_in_with_google(google_claims("new@example.com"))

        self.assertContains(response, "noch kein Billiger-Konto")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(get_user_model().objects.filter(username="new@example.com").exists())

    def test_a_deactivated_account_is_refused(self):
        self.user.is_active = False
        self.user.save()

        response = self.sign_in_with_google()

        self.assertContains(response, "deaktiviert")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_token_google_rejects_is_shown_as_an_error_without_a_session(self):
        with patch(VERIFY, side_effect=ValueError("Wrong audience")):
            response = self.client.post(LOGIN_URL, {"google_credential": "forged", "next": NEXT})

        self.assertContains(response, "Ungültiges Google-Token")
        self.assertContains(response, NEXT.replace("&", "&amp;"))  # the way on is kept for a retry
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_an_unverified_google_email_is_refused(self):
        response = self.sign_in_with_google(google_claims(email_verified=False))

        self.assertContains(response, "nicht verifiziert")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_an_unreachable_google_is_shown_as_an_error(self):
        with patch(VERIFY, side_effect=TransportError("offline")):
            response = self.client.post(LOGIN_URL, {"google_credential": "google-jwt"})

        self.assertContains(response, "nicht erreichbar")
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="")
    def test_without_a_client_id_google_sign_in_is_refused_and_the_button_is_hidden(self):
        attempt = self.client.post(LOGIN_URL, {"google_credential": "google-jwt"})
        page = self.client.get(LOGIN_URL)

        self.assertContains(attempt, "nicht konfiguriert")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotContains(page, "accounts.google.com")
        self.assertContains(page, "Passwort")

    def test_the_button_is_offered_with_the_configured_client_id(self):
        page = self.client.get(LOGIN_URL)

        self.assertContains(page, "Mit Google anmelden")
        self.assertContains(page, "test-client-id")

    def test_google_sign_in_attempts_are_throttled_like_the_password_login(self):
        for _ in range(10):
            self.sign_in_with_google(google_claims(email_verified=False))

        response = self.sign_in_with_google()

        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_google_and_password_sign_in_share_one_throttle(self):
        for _ in range(10):
            self.sign_in(password="wrong")

        self.assertEqual(self.sign_in_with_google().status_code, 429)

    def test_the_page_lets_googles_sign_in_popup_reach_back_to_it(self):
        response = self.client.get(LOGIN_URL)
        self.assertEqual(response["Cross-Origin-Opener-Policy"], "same-origin-allow-popups")

    def test_a_redirect_to_another_site_is_ignored(self):
        response = self.sign_in_with_google(next="https://evil.example/")

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example", response["Location"])
