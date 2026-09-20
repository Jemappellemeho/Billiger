from django.contrib.auth import get_user_model
from accounts.tests.base import AccountsAPITestCase

REGISTER_URL = "/api/auth/register/"


class RegisterTests(AccountsAPITestCase):
    def test_registering_with_email_and_password_returns_a_token_for_the_new_account(self):
        response = self.client.post(
            REGISTER_URL, {"email": "Anna@Example.com", "password": "correct-horse-battery"}
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["email"], "anna@example.com")
        self.assertTrue(response.data["token"])
        self.assertTrue(get_user_model().objects.filter(username="anna@example.com").exists())

    def test_registering_an_already_used_email_is_rejected_regardless_of_case(self):
        self.client.post(
            REGISTER_URL, {"email": "anna@example.com", "password": "correct-horse-battery"}
        )

        response = self.client.post(
            REGISTER_URL, {"email": "ANNA@example.com", "password": "another-good-password"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_a_weak_password_is_rejected(self):
        response = self.client.post(REGISTER_URL, {"email": "anna@example.com", "password": "12345"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)

    def test_an_invalid_email_is_rejected(self):
        response = self.client.post(
            REGISTER_URL, {"email": "not-an-email", "password": "correct-horse-battery"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)
