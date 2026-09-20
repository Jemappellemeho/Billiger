from django.contrib.auth import get_user_model

from accounts.tests.base import AccountsAPITestCase
from accounts.tests.helpers import LIST_URL, LOGIN_URL, auth, item, register, shopping_list


class GuestListMigrationTests(AccountsAPITestCase):
    def test_registering_with_a_guest_list_stores_it_on_the_new_account(self):
        guest = shopping_list(
            items=[item("Milch", brand="NÖM", quantity=2), item("Brot", favorite=True)],
            preferred_brands=["NÖM"],
            excluded_stores=["Lidl"],
        )

        response = register(self.client, guest_list=guest)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["shopping_list"], guest)
        stored = self.client.get(LIST_URL, **auth(response.data["token"]))
        self.assertEqual(stored.data, guest)

    def test_registering_without_a_guest_list_returns_an_empty_list(self):
        response = register(self.client)

        self.assertEqual(response.data["shopping_list"], shopping_list())

    def test_logging_in_merges_the_guest_list_into_the_stored_list(self):
        token = register(self.client).data["token"]
        stored = shopping_list(
            items=[
                item("Milch", quantity=1, category=None),
                item("Butter", quantity=3),
            ],
            preferred_brands=["NÖM"],
        )
        self.client.put(LIST_URL, stored, format="json", **auth(token))
        guest = shopping_list(
            items=[
                item("Milch", quantity=4, favorite=True, category="Molkerei"),
                item("Brot"),
            ],
            preferred_brands=["NÖM", "Ja! Natürlich"],
            excluded_ingredients=["Palmöl"],
        )

        response = self.client.post(
            LOGIN_URL,
            {"email": "anna@example.com", "password": "correct-horse-battery", "guest_list": guest},
            format="json",
        )

        merged = response.data["shopping_list"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            merged["items"],
            [
                item("Milch", quantity=4, favorite=True, category="Molkerei"),
                item("Butter", quantity=3),
                item("Brot"),
            ],
        )
        self.assertEqual(merged["preferences"]["preferred_brands"], ["NÖM", "Ja! Natürlich"])
        self.assertEqual(merged["preferences"]["excluded_ingredients"], ["Palmöl"])
        self.assertEqual(self.client.get(LIST_URL, **auth(token)).data, merged)

    def test_migrating_the_same_guest_list_twice_changes_nothing(self):
        register(self.client)
        guest = shopping_list(items=[item("Milch", quantity=2)], preferred_brands=["NÖM"])
        credentials = {
            "email": "anna@example.com",
            "password": "correct-horse-battery",
            "guest_list": guest,
        }

        first = self.client.post(LOGIN_URL, credentials, format="json")
        second = self.client.post(LOGIN_URL, credentials, format="json")

        self.assertEqual(first.data["shopping_list"], second.data["shopping_list"])
        self.assertEqual(second.data["shopping_list"]["items"][0]["quantity"], 2)

    def test_logging_in_without_a_guest_list_returns_the_stored_list(self):
        token = register(self.client).data["token"]
        stored = shopping_list(items=[item("Milch")])
        self.client.put(LIST_URL, stored, format="json", **auth(token))

        response = self.client.post(
            LOGIN_URL, {"email": "anna@example.com", "password": "correct-horse-battery"}
        )

        self.assertEqual(response.data["shopping_list"], stored)

    def test_an_invalid_guest_list_rejects_the_whole_registration(self):
        invalid = shopping_list(items=[item("Milch", quantity=0)])

        response = register(self.client, guest_list=invalid)

        self.assertEqual(response.status_code, 400)
        self.assertIn("guest_list", response.data)
        self.assertFalse(get_user_model().objects.filter(username="anna@example.com").exists())

    def test_a_failed_login_does_not_touch_the_stored_list(self):
        token = register(self.client).data["token"]
        self.client.put(LIST_URL, shopping_list(items=[item("Milch")]), format="json", **auth(token))

        self.client.post(
            LOGIN_URL,
            {
                "email": "anna@example.com",
                "password": "wrong-password",
                "guest_list": shopping_list(items=[item("Brot")]),
            },
            format="json",
        )

        stored = self.client.get(LIST_URL, **auth(token))
        self.assertEqual([entry["name"] for entry in stored.data["items"]], ["Milch"])
