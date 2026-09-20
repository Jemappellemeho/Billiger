from datetime import timedelta

from accounts.tests.base import AccountsAPITestCase
from accounts.tests.helpers import LIST_URL, auth, item, shopping_list
from assistant.tests.helpers import CHAT_URL, assistant_llm, call_tool, chat, say
from search.marktguru_client import MarktguruClient
from search.tests.test_cart_comparison_view import _fake_session_get, _raw_offer, _response
from streaks.tests.helpers import WEEK_1, WEEK_2, WEEK_4, clock, compare, sign_up, streak_summary


class ChatEndpointTests(AccountsAPITestCase):
    def test_chat_requires_a_signed_in_account(self):
        response = self.client.post(CHAT_URL, {"message": "Hallo"}, format="json")

        self.assertEqual(response.status_code, 401)

    def test_plain_answer_is_returned_as_the_reply(self):
        token = sign_up(self.client)

        with assistant_llm(say("Servus! Wie kann ich helfen?")) as llm:
            response = chat(self.client, token, "Hallo")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["reply"], "Servus! Wie kann ich helfen?")
        self.assertEqual(body["actions"], [])
        self.assertEqual(body["user_message"], {"role": "user", "content": "Hallo", "input": "text"})
        self.assertEqual(llm.requests[0]["messages"], [{"role": "user", "content": "Hallo"}])


class ShoppingListActionTests(AccountsAPITestCase):
    def _save_list(self, token, *items, **preferences):
        response = self.client.put(
            LIST_URL, shopping_list(items, **preferences), format="json", **auth(token)
        )
        self.assertEqual(response.status_code, 200)

    def test_shows_the_accounts_current_list_without_any_confirmation_step(self):
        token = sign_up(self.client)
        self._save_list(
            token,
            item("Milch", brand="Ja! Natürlich", quantity=2, category="Molkerei"),
            item("Nutella", favorite=True),
            preferred_brands=["Ja! Natürlich"],
        )
        expected = self.client.get(LIST_URL, **auth(token)).json()

        with assistant_llm(call_tool("get_shopping_list"), say("Auf deiner Liste: Milch und Nutella.")) as llm:
            response = chat(self.client, token, "Was steht auf meiner Einkaufsliste?")

        body = response.json()
        self.assertEqual(body["reply"], "Auf deiner Liste: Milch und Nutella.")
        self.assertEqual(body["actions"], [{"tool": "get_shopping_list", "input": {}, "result": expected}])
        self.assertEqual(
            llm.tool_results(1),
            [{"type": "tool_result", "tool_use_id": "toolu_1", "content": expected}],
        )
        self.assertIn("get_shopping_list", [tool["name"] for tool in llm.requests[0]["tools"]])

    def test_an_empty_account_has_an_empty_list(self):
        token = sign_up(self.client)

        with assistant_llm(call_tool("get_shopping_list"), say("Deine Liste ist leer.")) as llm:
            chat(self.client, token, "Meine Liste?")

        self.assertEqual(llm.tool_results(1)[0]["content"]["items"], [])

    def test_never_shows_another_accounts_list(self):
        anna = sign_up(self.client, "anna@example.com")
        ben = sign_up(self.client, "ben@example.com")
        self._save_list(anna, item("Milch"))

        with assistant_llm(call_tool("get_shopping_list"), say("Leer.")) as llm:
            chat(self.client, ben, "Meine Liste?")

        self.assertEqual(llm.tool_results(1)[0]["content"]["items"], [])


class SavingsStreakActionTests(AccountsAPITestCase):
    def _ask_for_streak(self, token, moment):
        with assistant_llm(call_tool("get_savings_streak"), say("Läuft!")) as llm, clock(moment):
            response = chat(self.client, token, "Wie steht's um meine Ersparnis?")
        self.assertEqual(response.status_code, 200)
        return llm, response.json()

    def test_shows_this_weeks_savings_and_streak_without_confirmation(self):
        token = sign_up(self.client)
        compare(self.client, token, moment=WEEK_1)
        expected = streak_summary(self.client, token, moment=WEEK_1).json()

        llm, body = self._ask_for_streak(token, WEEK_1)

        result = llm.tool_results(1)[0]["content"]
        self.assertEqual(result["streak"], {
            "weeks": 1, "status": "active", "missed_weeks": 0, "last_completed_week": "2026-09-07",
        })
        # Milch: LIDL 0.99 vs HOFER 1.09; Nutella: HOFER 4.99 (was 6.99) vs LIDL 5.29.
        self.assertEqual(result["this_week"]["savings_vs_most_expensive"], 0.40)
        self.assertEqual(result["this_week"]["savings_vs_regular"], 2.00)
        self.assertEqual(result["this_week"], expected["this_week"])
        self.assertEqual(result["total_savings"], expected["total_savings"])
        self.assertEqual(result["history"], expected["history"])
        self.assertEqual(body["reply"], "Läuft!")
        self.assertEqual(body["actions"][0]["tool"], "get_savings_streak")

    def test_a_missed_week_pauses_the_streak_and_reports_the_last_standing(self):
        token = sign_up(self.client)
        compare(self.client, token, moment=WEEK_1)
        compare(self.client, token, moment=WEEK_2)

        llm, _ = self._ask_for_streak(token, WEEK_4)

        result = llm.tool_results(1)[0]["content"]
        self.assertEqual(result["streak"]["status"], "paused")
        self.assertEqual(result["streak"]["weeks"], 2)
        self.assertEqual(result["streak"]["missed_weeks"], 1)  # WEEK_3; WEEK_4 is still open
        self.assertEqual(result["streak"]["last_completed_week"], "2026-09-14")
        self.assertIsNone(result["this_week"])

    def test_a_new_account_has_no_streak_yet(self):
        token = sign_up(self.client)

        llm, _ = self._ask_for_streak(token, WEEK_1)

        result = llm.tool_results(1)[0]["content"]
        self.assertEqual(result["streak"]["status"], "none")
        self.assertEqual(result["history"], [])

    def test_long_histories_are_cut_to_the_latest_weeks_and_say_so(self):
        token = sign_up(self.client)
        for week in range(14):
            compare(self.client, token, moment=WEEK_1 + timedelta(weeks=week))
        last_week = WEEK_1 + timedelta(weeks=13)
        full_history = streak_summary(self.client, token, moment=last_week).json()["history"]

        llm, _ = self._ask_for_streak(token, last_week)

        result = llm.tool_results(1)[0]["content"]
        self.assertEqual(result["streak"]["weeks"], 14)
        self.assertEqual(result["history"], full_history[-12:])
        self.assertEqual(result["history_omitted_weeks"], 2)


def _many_products(url, params=None, headers=None, timeout=None):
    if url == MarktguruClient.API_URL:
        names = ["Butter", "Kaffee", "Nudeln", "Reis", "Honig", "Senf", "Tee"]
        offers = [_raw_offer(i, 900 + i, name, "Marke", "HOFER", 1.0 + i) for i, name in enumerate(names)]
        return _response(json_body={"results": offers})
    return _fake_session_get(url, params=params, headers=headers, timeout=timeout)


def _marktguru_down(url, params=None, headers=None, timeout=None):
    if url == MarktguruClient.API_URL:
        raise ConnectionError("Marktguru is down")
    return _fake_session_get(url, params=params, headers=headers, timeout=timeout)


class ProductPriceActionTests(AccountsAPITestCase):
    def _ask(self, token, *, query="Milch", marktguru=_fake_session_get, **location):
        turns = (call_tool("search_product_prices", {"query": query}), say("Am billigsten bei Lidl."))
        with assistant_llm(*turns, marktguru=marktguru) as llm:
            response = chat(self.client, token, "Wo ist Milch am billigsten?", **location)
        self.assertEqual(response.status_code, 200)
        return llm, response.json()

    def test_answers_a_price_question_directly_from_the_search(self):
        token = sign_up(self.client)

        llm, body = self._ask(token, zip_code="1010")

        result = llm.tool_results(1)[0]["content"]
        self.assertEqual(result["query"], "Milch")
        self.assertEqual(result["zip_code"], "1010")
        [milch] = result["results"]
        self.assertEqual(milch["cheapest"]["advertiser"], "LIDL")
        self.assertEqual(milch["cheapest"]["price"], 0.99)
        self.assertEqual(sorted(o["advertiser"] for o in milch["offers"]), ["HOFER", "LIDL"])
        self.assertEqual(body["reply"], "Am billigsten bei Lidl.")
        self.assertEqual(body["actions"][0]["input"], {"query": "Milch"})

    def test_matches_what_the_search_endpoint_returns(self):
        token = sign_up(self.client)

        with assistant_llm():
            api = self.client.get("/api/search/", {"q": "Nutella", "zip_code": "1010"}).json()
        llm, _ = self._ask(token, query="Nutella", zip_code="1010")

        self.assertEqual(llm.tool_results(1)[0]["content"]["results"], api["results"])

    def test_uses_gps_coordinates_when_there_is_no_plz(self):
        token = sign_up(self.client)

        llm, _ = self._ask(token, lat=48.2082, lon=16.3738)

        self.assertEqual(llm.tool_results(1)[0]["content"]["zip_code"], "1010")

    def test_without_any_location_the_model_is_told_to_ask_for_the_plz(self):
        token = sign_up(self.client)

        llm, body = self._ask(token)

        [result] = llm.tool_results(1)
        self.assertTrue(result["is_error"])
        self.assertIn("Postleitzahl", result["content"]["error"])
        self.assertEqual(body["reply"], "Am billigsten bei Lidl.")

    def test_an_invalid_plz_is_reported_to_the_model(self):
        token = sign_up(self.client)

        llm, _ = self._ask(token, zip_code="abc")

        [result] = llm.tool_results(1)
        self.assertTrue(result["is_error"])
        self.assertIn("abc", result["content"]["error"])

    def test_marktguru_being_down_is_reported_to_the_model_not_as_a_server_error(self):
        token = sign_up(self.client)

        llm, body = self._ask(token, zip_code="1010", marktguru=_marktguru_down)

        [result] = llm.tool_results(1)
        self.assertTrue(result["is_error"])
        self.assertIn("Marktguru", result["content"]["error"])
        self.assertEqual(body["reply"], "Am billigsten bei Lidl.")

    def test_a_blank_query_is_an_error_for_the_model(self):
        token = sign_up(self.client)

        llm, _ = self._ask(token, query="  ", zip_code="1010")

        self.assertTrue(llm.tool_results(1)[0]["is_error"])

    def test_only_the_first_few_products_are_handed_to_the_model(self):
        token = sign_up(self.client)

        llm, _ = self._ask(token, query="Frühstück", zip_code="1010", marktguru=_many_products)

        result = llm.tool_results(1)[0]["content"]
        self.assertEqual(len(result["results"]), 5)
        self.assertEqual(result["results_omitted"], 2)


class CartComparisonActionTests(AccountsAPITestCase):
    def setUp(self):
        super().setUp()
        self.token = sign_up(self.client)

    def _save_list(self, *items):
        self.client.put(LIST_URL, shopping_list(items), format="json", **auth(self.token))

    def _ask(self, marktguru=_fake_session_get, **location):
        turns = (call_tool("compare_shopping_list"), say("Bei Hofer bist du am günstigsten."))
        with assistant_llm(*turns, marktguru=marktguru) as llm:
            response = chat(self.client, self.token, "Vergleich meinen Warenkorb", **location)
        self.assertEqual(response.status_code, 200)
        return llm, response.json()

    def test_summarises_cheapest_single_store_full_split_and_ladder(self):
        self._save_list(item("Milch"), item("Nutella"))

        llm, body = self._ask(zip_code="1010")

        result = llm.tool_results(1)[0]["content"]
        # Milch: LIDL 0.99 vs HOFER 1.09; Nutella: HOFER 4.99 (was 6.99) vs LIDL 5.29.
        self.assertEqual(result["single_store"]["advertiser"], "HOFER")
        self.assertAlmostEqual(result["single_store"]["total"], 1.09 + 4.99)
        self.assertAlmostEqual(result["full_split"]["total"], 0.99 + 4.99)
        stores_by_item = {line["name"]: line["advertiser"] for line in result["full_split"]["assignment"]}
        self.assertEqual(stores_by_item, {"Milch": "LIDL", "Nutella": "HOFER"})
        self.assertEqual([rung["stops"] for rung in result["ladder"]], [1, 2])
        self.assertAlmostEqual(result["ladder"][1]["marginal_savings"], 0.10)
        self.assertEqual(result["ladder"][-1]["total"], result["full_split"]["total"])
        self.assertEqual(result["unavailable_items"], [])
        self.assertEqual(body["reply"], "Bei Hofer bist du am günstigsten.")
        self.assertEqual(body["actions"][0]["tool"], "compare_shopping_list")

    def test_agrees_with_the_compare_endpoint(self):
        self._save_list(item("Milch", quantity=3), item("Nutella"))

        with assistant_llm():
            api = self.client.post(
                "/api/compare/",
                {"items": [{"name": "Milch", "quantity": 3}, {"name": "Nutella"}], "zip_code": "1010"},
                format="json",
            ).json()
        llm, _ = self._ask(zip_code="1010")

        result = llm.tool_results(1)[0]["content"]
        self.assertEqual(result["single_store"], api["single_store"])
        self.assertEqual(result["full_split"], api["full_split"])
        self.assertEqual(result["store_totals"], api["store_totals"])
        self.assertEqual(result["unavailable_items"], api["unavailable_items"])
        self.assertEqual(
            result["ladder"],
            [{k: rung[k] for k in ("stops", "stores", "total", "marginal_savings")} for rung in api["ladder"]],
        )

    def test_items_without_offers_are_reported_as_unavailable(self):
        self._save_list(item("Milch"), item("Einhornstaub"))

        llm, _ = self._ask(zip_code="1010")

        self.assertEqual(llm.tool_results(1)[0]["content"]["unavailable_items"], ["Einhornstaub"])

    def test_stop_count_questions_are_pointed_at_the_slider_instead_of_new_state(self):
        self._save_list(item("Milch"), item("Nutella"))

        llm, _ = self._ask(zip_code="1010")

        self.assertIn("Regler", llm.tool_results(1)[0]["content"]["hinweis"])

    def test_looking_at_the_comparison_does_not_count_toward_the_streak(self):
        self._save_list(item("Milch"), item("Nutella"))

        with clock(WEEK_1):
            self._ask(zip_code="1010")

        self.assertEqual(streak_summary(self.client, self.token, moment=WEEK_1).json()["streak"]["weeks"], 0)

    def test_an_empty_list_has_nothing_to_compare(self):
        llm, _ = self._ask(zip_code="1010")

        [result] = llm.tool_results(1)
        self.assertTrue(result["is_error"])
        self.assertIn("leer", result["content"]["error"])

    def test_without_any_location_the_model_is_told_to_ask_for_the_plz(self):
        self._save_list(item("Milch"))

        llm, _ = self._ask()

        [result] = llm.tool_results(1)
        self.assertTrue(result["is_error"])
        self.assertIn("Postleitzahl", result["content"]["error"])

    def test_marktguru_being_down_is_reported_to_the_model(self):
        self._save_list(item("Milch"))

        llm, _ = self._ask(zip_code="1010", marktguru=_marktguru_down)

        [result] = llm.tool_results(1)
        self.assertTrue(result["is_error"])
        self.assertIn("Marktguru", result["content"]["error"])
