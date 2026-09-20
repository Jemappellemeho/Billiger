from django.contrib.auth import get_user_model
from accounts.tests.base import AccountsAPITestCase

LOGIN_URL = "/api/auth/login/"
LOGOUT_URL = "/api/auth/logout/"


class LoginTests(AccountsAPITestCase):
    def setUp(self):
        super().setUp()
        get_user_model().objects.create_user(
            username="anna@example.com", email="anna@example.com", password="correct-horse-battery"
        )

    def test_logging_in_with_the_right_credentials_returns_a_token(self):
        response = self.client.post(
            LOGIN_URL, {"email": "Anna@Example.com", "password": "correct-horse-battery"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "anna@example.com")
        self.assertTrue(response.data["token"])

    def test_a_wrong_password_and_an_unknown_email_get_the_same_rejection(self):
        wrong_password = self.client.post(
            LOGIN_URL, {"email": "anna@example.com", "password": "wrong-password"}
        )
        unknown_email = self.client.post(
            LOGIN_URL, {"email": "nobody@example.com", "password": "correct-horse-battery"}
        )

        self.assertEqual(wrong_password.status_code, 400)
        self.assertEqual(unknown_email.status_code, 400)
        self.assertEqual(wrong_password.data, unknown_email.data)

    def test_logging_out_revokes_the_token(self):
        token = self.client.post(
            LOGIN_URL, {"email": "anna@example.com", "password": "correct-horse-battery"}
        ).data["token"]

        first = self.client.post(LOGOUT_URL, HTTP_AUTHORIZATION=f"Token {token}")
        second = self.client.post(LOGOUT_URL, HTTP_AUTHORIZATION=f"Token {token}")

        self.assertEqual(first.status_code, 204)
        self.assertEqual(second.status_code, 401)

    def test_logging_out_without_a_token_is_rejected(self):
        self.assertEqual(self.client.post(LOGOUT_URL).status_code, 401)

    def test_repeated_failed_logins_are_throttled(self):
        statuses = [
            self.client.post(
                LOGIN_URL, {"email": "anna@example.com", "password": "wrong-password"}
            ).status_code
            for _ in range(12)
        ]

        self.assertEqual(statuses[0], 400)
        self.assertEqual(statuses[-1], 429)
