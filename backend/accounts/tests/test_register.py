from accounts.tests.base import AccountsAPITestCase
from accounts.tests.helpers import LOGIN_URL, register


class RegisterTests(AccountsAPITestCase):
    def test_registering_with_email_and_password_returns_a_token_for_the_new_account(self):
        response = register(self.client, email="Anna@Example.com")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["email"], "anna@example.com")
        self.assertTrue(response.data["token"])

    def test_the_new_account_can_log_in_with_the_chosen_password(self):
        register(self.client, email="anna@example.com", password="correct-horse-battery")

        login = self.client.post(
            LOGIN_URL, {"email": "anna@example.com", "password": "correct-horse-battery"}
        )

        self.assertEqual(login.status_code, 200)

    def test_registering_an_already_used_email_is_rejected_regardless_of_case(self):
        register(self.client, email="anna@example.com")

        response = register(self.client, email="ANNA@example.com", password="another-good-password")

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_a_weak_password_is_rejected(self):
        response = register(self.client, password="12345")

        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)

    def test_an_invalid_email_is_rejected(self):
        response = register(self.client, email="not-an-email")

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_an_email_longer_than_an_account_name_can_be_is_rejected(self):
        response = register(self.client, email="a" * 140 + "@example.com")

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)
