from unittest.mock import patch

from django.test import override_settings
from google.auth.exceptions import TransportError

from accounts.tests.base import AccountsAPITestCase
from accounts.tests.helpers import (
    GOOGLE_URL,
    LIST_URL,
    LOGIN_URL,
    VERIFY_GOOGLE_TOKEN as VERIFY,
    auth,
    google_claims,
    item,
    register,
    shopping_list,
)


@override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client-id")
class GoogleLoginTests(AccountsAPITestCase):
    def test_a_valid_google_token_creates_an_account_and_returns_a_token(self):
        with patch(VERIFY, return_value=google_claims("Anna@Example.com")) as verify:
            response = self.client.post(GOOGLE_URL, {"id_token": "google-jwt"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "anna@example.com")
        self.assertTrue(response.data["token"])
        self.assertEqual(verify.call_args.args[0], "google-jwt")
        self.assertEqual(verify.call_args.args[2], "test-client-id")

    def test_signing_in_again_reuses_the_same_account(self):
        with patch(VERIFY, return_value=google_claims()):
            first = self.client.post(GOOGLE_URL, {"id_token": "google-jwt"}, format="json")
            second = self.client.post(GOOGLE_URL, {"id_token": "google-jwt"}, format="json")

        self.assertEqual(first.data["token"], second.data["token"])

    def test_the_guest_list_is_migrated_on_the_first_google_login(self):
        guest = shopping_list(items=[item("Milch", quantity=2)], preferred_brands=["NÖM"])

        with patch(VERIFY, return_value=google_claims()):
            response = self.client.post(
                GOOGLE_URL, {"id_token": "google-jwt", "guest_list": guest}, format="json"
            )

        self.assertEqual(response.data["shopping_list"], guest)
        stored = self.client.get(LIST_URL, **auth(response.data["token"]))
        self.assertEqual(stored.data, guest)

    def test_a_token_google_rejects_is_refused(self):
        with patch(VERIFY, side_effect=ValueError("Wrong audience")):
            response = self.client.post(GOOGLE_URL, {"id_token": "forged"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(register(self.client).status_code, 201)  # no account was created

    def test_google_being_unreachable_reports_the_service_as_unavailable(self):
        with patch(VERIFY, side_effect=TransportError("no route to Google")):
            response = self.client.post(GOOGLE_URL, {"id_token": "google-jwt"}, format="json")

        self.assertEqual(response.status_code, 503)

    def test_an_unverified_google_email_is_refused(self):
        with patch(VERIFY, return_value=google_claims(email_verified=False)):
            response = self.client.post(GOOGLE_URL, {"id_token": "google-jwt"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(register(self.client).status_code, 201)  # no account was created

    def test_google_never_takes_over_an_account_registered_with_a_password(self):
        # Emails are not verified at password registration, so linking by email
        # would let anyone pre-register a victim's address and inherit their account.
        register(self.client)

        with patch(VERIFY, return_value=google_claims()):
            response = self.client.post(GOOGLE_URL, {"id_token": "google-jwt"}, format="json")

        self.assertEqual(response.status_code, 409)

    def test_a_google_account_cannot_be_entered_with_a_password(self):
        with patch(VERIFY, return_value=google_claims()):
            self.client.post(GOOGLE_URL, {"id_token": "google-jwt"}, format="json")

        login = self.client.post(LOGIN_URL, {"email": "anna@example.com", "password": "any-password-at-all"})
        registration = register(self.client)

        self.assertEqual(login.status_code, 400)
        self.assertEqual(registration.status_code, 400)

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="")
    def test_google_login_is_unavailable_when_no_client_id_is_configured(self):
        response = self.client.post(GOOGLE_URL, {"id_token": "google-jwt"}, format="json")

        self.assertEqual(response.status_code, 503)
