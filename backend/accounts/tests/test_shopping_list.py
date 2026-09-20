from accounts.tests.base import AccountsAPITestCase
from accounts.tests.helpers import LIST_URL, auth, item, register, shopping_list


class ShoppingListStorageTests(AccountsAPITestCase):
    def setUp(self):
        super().setUp()
        self.token = register(self.client).data["token"]

    def test_the_list_requires_an_account(self):
        self.assertEqual(self.client.get(LIST_URL).status_code, 401)
        self.assertEqual(self.client.put(LIST_URL, shopping_list(), format="json").status_code, 401)

    def test_a_new_account_starts_with_an_empty_list(self):
        response = self.client.get(LIST_URL, **auth(self.token))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, shopping_list())

    def test_a_saved_list_is_returned_unchanged(self):
        saved = shopping_list(
            items=[item("Milch", brand="NÖM", quantity=2, favorite=True, category="Molkerei")],
            preferred_brands=["NÖM"],
            excluded_ingredients=["Palmöl"],
            excluded_stores=["Lidl"],
        )

        put = self.client.put(LIST_URL, saved, format="json", **auth(self.token))
        got = self.client.get(LIST_URL, **auth(self.token))

        self.assertEqual(put.status_code, 200)
        self.assertEqual(got.data, saved)

    def test_saving_replaces_the_previous_list(self):
        self.client.put(LIST_URL, shopping_list(items=[item("Milch")]), format="json", **auth(self.token))
        self.client.put(LIST_URL, shopping_list(items=[item("Brot")]), format="json", **auth(self.token))

        got = self.client.get(LIST_URL, **auth(self.token))

        self.assertEqual([entry["name"] for entry in got.data["items"]], ["Brot"])

    def test_lists_are_private_to_their_account(self):
        self.client.put(LIST_URL, shopping_list(items=[item("Milch")]), format="json", **auth(self.token))
        other_token = register(self.client, email="ben@example.com").data["token"]

        got = self.client.get(LIST_URL, **auth(other_token))

        self.assertEqual(got.data, shopping_list())

    def test_an_invalid_list_is_rejected_and_the_stored_list_is_kept(self):
        self.client.put(LIST_URL, shopping_list(items=[item("Milch")]), format="json", **auth(self.token))

        zero_quantity = shopping_list(items=[item("Brot", quantity=0)])
        duplicate_ids = shopping_list(items=[item("Brot"), item("Brot")])
        missing_preferences = {"items": []}

        for invalid in (zero_quantity, duplicate_ids, missing_preferences):
            response = self.client.put(LIST_URL, invalid, format="json", **auth(self.token))
            self.assertEqual(response.status_code, 400)

        got = self.client.get(LIST_URL, **auth(self.token))
        self.assertEqual([entry["name"] for entry in got.data["items"]], ["Milch"])
