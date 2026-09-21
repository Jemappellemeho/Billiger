from mcp_server.tests.helpers import PASSWORD, McpTestCase

LOGIN_URL = "/accounts/login/"


class ConsentLoginTests(McpTestCase):
    def sign_in(self, email="anna@example.com", password=PASSWORD, **extra):
        return self.client.post(LOGIN_URL, {"username": email, "password": password, **extra})

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
