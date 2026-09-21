"""The assistant's three write actions (Ticket 15), through the HTTP contract.

Every write action follows one pattern: the model can only *propose* (a chat
turn stores a pending proposal with the full diff and changes nothing); the
user then accepts, edits or rejects it through the proposal endpoints, and
only accepting commits.
"""
from accounts.tests.base import AccountsAPITestCase
from accounts.tests.helpers import LIST_URL, auth, item, shopping_list
from assistant.tests.helpers import PROPOSALS_URL, decide, propose, proposal_url, revise
from streaks.tests.helpers import sign_up

REJECTED_MESSAGE = "Verworfen — keine Änderung vorgenommen."


class ProposalTestCase(AccountsAPITestCase):
    def setUp(self):
        super().setUp()
        self.token = sign_up(self.client)

    def save_list(self, *items, token=None, **preferences):
        response = self.client.put(
            LIST_URL, shopping_list(items, **preferences), format="json", **auth(token or self.token)
        )
        self.assertEqual(response.status_code, 200)

    def current_list(self, token=None):
        return self.client.get(LIST_URL, **auth(token or self.token)).json()

    def proposal_of(self, response):
        self.assertEqual(response.status_code, 200)
        [proposal] = response.json()["proposals"]
        return proposal


class ShoppingListProposalTests(ProposalTestCase):
    def setUp(self):
        super().setUp()
        self.save_list(
            item("Milch", quantity=1, category="Molkerei", favorite=True),
            item("Nutella", brand="Ferrero"),
            preferred_brands=["Ja! Natürlich"],
        )
        self.before = self.current_list()

    def propose_new_state(self):
        # Butter is new, Nutella is gone, Milch goes from 1 to 3.
        return propose(
            self.client,
            self.token,
            "propose_shopping_list_change",
            {"items": [{"name": "Milch", "quantity": 3}, {"name": "Butter", "quantity": 2}]},
        )

    def test_proposes_the_whole_new_list_as_one_combined_diff_and_changes_nothing_yet(self):
        response, llm = self.propose_new_state()

        proposal = self.proposal_of(response)
        self.assertEqual(proposal["kind"], "shopping_list")
        self.assertEqual(proposal["status"], "pending")
        diff = proposal["diff"]
        self.assertEqual([entry["name"] for entry in diff["added"]], ["Butter"])
        self.assertEqual(diff["added"][0]["quantity"], 2)
        self.assertEqual([entry["name"] for entry in diff["removed"]], ["Nutella"])
        self.assertEqual(
            diff["changed"],
            [{"id": "milch", "name": "Milch", "brand": None, "changes": {"quantity": {"before": 1, "after": 3}}}],
        )
        self.assertEqual(
            [entry["name"] for entry in proposal["proposed"]["items"]], ["Milch", "Butter"]
        )
        # Nothing is applied before the user decides.
        self.assertEqual(self.current_list(), self.before)
        # The model sees the diff, so it can describe it, and is told to wait for the decision.
        [result] = llm.tool_results(1)
        self.assertNotIn("is_error", result)
        self.assertEqual(result["content"]["proposal"]["diff"], diff)
        self.assertEqual(response.json()["actions"][0]["tool"], "propose_shopping_list_change")

    def test_existing_items_keep_their_category_and_favorite_flag(self):
        response, _ = self.propose_new_state()

        milch = next(entry for entry in self.proposal_of(response)["proposed"]["items"] if entry["name"] == "Milch")

        self.assertEqual(milch["category"], "Molkerei")
        self.assertTrue(milch["favorite"])

    def test_accepting_commits_the_new_list_and_confirms(self):
        proposal = self.proposal_of(self.propose_new_state()[0])

        response = decide(self.client, self.token, proposal["id"], "accept")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["message"], "✅ Einkaufsliste aktualisiert.")
        self.assertEqual(body["proposal"]["status"], "accepted")
        saved = self.current_list()
        self.assertEqual(body["shopping_list"], saved)
        self.assertEqual([(i["name"], i["quantity"]) for i in saved["items"]], [("Milch", 3), ("Butter", 2)])
        self.assertEqual(saved["preferences"], self.before["preferences"])
        self.assertTrue(saved["items"][0]["favorite"])

    def test_rejecting_leaves_the_list_untouched_and_says_so(self):
        proposal = self.proposal_of(self.propose_new_state()[0])

        response = decide(self.client, self.token, proposal["id"], "reject")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], REJECTED_MESSAGE)
        self.assertEqual(response.json()["proposal"]["status"], "rejected")
        self.assertEqual(self.current_list(), self.before)

    def test_editing_shows_a_fresh_diff_and_only_the_edited_version_is_committed(self):
        proposal = self.proposal_of(self.propose_new_state()[0])

        edited = revise(
            self.client, self.token, proposal["id"], {"items": [{"name": "Milch", "quantity": 3}]}
        )

        self.assertEqual(edited.status_code, 200)
        revised = edited.json()["proposal"]
        self.assertEqual(revised["id"], proposal["id"])
        self.assertEqual(revised["status"], "pending")
        self.assertEqual(revised["diff"]["added"], [])
        self.assertEqual([entry["name"] for entry in revised["diff"]["removed"]], ["Nutella"])
        self.assertEqual(self.current_list(), self.before)

        decide(self.client, self.token, proposal["id"], "accept")

        self.assertEqual([(i["name"], i["quantity"]) for i in self.current_list()["items"]], [("Milch", 3)])

    def test_an_edit_that_changes_nothing_is_refused(self):
        proposal = self.proposal_of(self.propose_new_state()[0])

        response = revise(
            self.client, self.token, proposal["id"],
            {"items": [{"name": "Milch", "quantity": 1}, {"name": "Nutella", "brand": "Ferrero"}]},
        )

        self.assertEqual(response.status_code, 400)

    def test_a_decided_proposal_cannot_be_decided_again(self):
        proposal = self.proposal_of(self.propose_new_state()[0])
        decide(self.client, self.token, proposal["id"], "reject")

        again = decide(self.client, self.token, proposal["id"], "accept")

        self.assertEqual(again.status_code, 409)
        self.assertEqual(self.current_list(), self.before)
        self.assertEqual(revise(self.client, self.token, proposal["id"], {"items": []}).status_code, 409)

    def test_a_list_that_changed_since_the_proposal_is_not_overwritten(self):
        proposal = self.proposal_of(self.propose_new_state()[0])
        self.save_list(item("Milch"), item("Brot"))  # e.g. edited on another device
        edited_elsewhere = self.current_list()

        response = decide(self.client, self.token, proposal["id"], "accept")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.current_list(), edited_elsewhere)

    def test_a_proposal_that_changes_nothing_is_reported_to_the_model_instead(self):
        response, llm = propose(
            self.client,
            self.token,
            "propose_shopping_list_change",
            {"items": [{"name": "Milch", "quantity": 1}, {"name": "Nutella", "brand": "Ferrero"}]},
        )

        self.assertEqual(response.json()["proposals"], [])
        [result] = llm.tool_results(1)
        self.assertTrue(result["is_error"])

    def test_invalid_lists_are_reported_to_the_model_not_stored(self):
        for bad in (
            {"items": [{"name": "Milch", "quantity": 0}]},
            {"items": [{"name": "Milch"}, {"name": "milch"}]},  # the same product twice
            {"items": [{"quantity": 2}]},
            {},
        ):
            with self.subTest(bad=bad):
                response, llm = propose(self.client, self.token, "propose_shopping_list_change", bad)

                self.assertEqual(response.json()["proposals"], [])
                self.assertTrue(llm.tool_results(1)[0]["is_error"])

    def test_the_new_list_may_be_empty(self):
        response, _ = propose(self.client, self.token, "propose_shopping_list_change", {"items": []})

        proposal = self.proposal_of(response)
        self.assertEqual(len(proposal["diff"]["removed"]), 2)

    def test_another_account_can_neither_see_nor_decide_the_proposal(self):
        proposal = self.proposal_of(self.propose_new_state()[0])
        ben = sign_up(self.client, "ben@example.com")

        for action in ("accept", "reject"):
            self.assertEqual(decide(self.client, ben, proposal["id"], action).status_code, 404)
        self.assertEqual(revise(self.client, ben, proposal["id"], {"items": []}).status_code, 404)
        self.assertEqual(self.current_list(), self.before)

    def test_deciding_needs_an_account(self):
        proposal = self.proposal_of(self.propose_new_state()[0])

        response = self.client.post(proposal_url(proposal["id"], "accept/"), format="json")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.current_list(), self.before)

    def test_proposals_only_come_from_the_assistant_never_from_the_client(self):
        response = self.client.post(
            PROPOSALS_URL, {"kind": "shopping_list", "items": []}, format="json", **auth(self.token)
        )

        self.assertEqual(response.status_code, 404)


class PreferencesProposalTests(ProposalTestCase):
    def setUp(self):
        super().setUp()
        self.save_list(
            item("Milch", favorite=True),
            item("Nutella", brand="Ferrero"),
            preferred_brands=["Ja! Natürlich"],
            excluded_stores=["Penny"],
        )
        self.before = self.current_list()

    def propose_changes(self):
        return propose(
            self.client,
            self.token,
            "propose_preferences_change",
            {
                "preferred_brands": ["Ja! Natürlich", "Ferrero"],
                "excluded_stores": [],
                "excluded_ingredients": ["Palmöl"],
                "favorite_items": ["Nutella"],  # Milch is no favorite any more
            },
        )

    def test_proposes_the_preference_changes_as_a_diff_and_changes_nothing_yet(self):
        response, llm = self.propose_changes()

        proposal = self.proposal_of(response)
        self.assertEqual(proposal["kind"], "preferences")
        self.assertEqual(proposal["status"], "pending")
        diff = proposal["diff"]
        self.assertEqual(diff["preferred_brands"], {"added": ["Ferrero"], "removed": []})
        self.assertEqual(diff["excluded_stores"], {"added": [], "removed": ["Penny"]})
        self.assertEqual(diff["excluded_ingredients"], {"added": ["Palmöl"], "removed": []})
        self.assertEqual([i["name"] for i in diff["favorites"]["added"]], ["Nutella"])
        self.assertEqual([i["name"] for i in diff["favorites"]["removed"]], ["Milch"])
        self.assertEqual(self.current_list(), self.before)
        self.assertNotIn("is_error", llm.tool_results(1)[0])

    def test_only_parts_that_actually_change_are_in_the_diff(self):
        response, _ = propose(
            self.client, self.token, "propose_preferences_change", {"excluded_stores": ["Penny", "Billa"]}
        )

        self.assertEqual(list(self.proposal_of(response)["diff"]), ["excluded_stores"])

    def test_accepting_commits_preferences_and_favorites_but_leaves_the_items_alone(self):
        proposal = self.proposal_of(self.propose_changes()[0])

        response = decide(self.client, self.token, proposal["id"], "accept")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "✅ Präferenzen aktualisiert.")
        saved = self.current_list()
        self.assertEqual(response.json()["shopping_list"], saved)
        self.assertEqual(
            saved["preferences"],
            {
                "preferred_brands": ["Ja! Natürlich", "Ferrero"],
                "excluded_ingredients": ["Palmöl"],
                "excluded_stores": [],
            },
        )
        self.assertEqual({i["name"]: i["favorite"] for i in saved["items"]}, {"Milch": False, "Nutella": True})
        self.assertEqual([(i["name"], i["quantity"]) for i in saved["items"]], [("Milch", 1), ("Nutella", 1)])

    def test_rejecting_changes_nothing(self):
        proposal = self.proposal_of(self.propose_changes()[0])

        response = decide(self.client, self.token, proposal["id"], "reject")

        self.assertEqual(response.json()["message"], REJECTED_MESSAGE)
        self.assertEqual(self.current_list(), self.before)

    def test_editing_revises_the_proposal(self):
        proposal = self.proposal_of(self.propose_changes()[0])

        edited = revise(self.client, self.token, proposal["id"], {"preferred_brands": ["Ferrero"]})

        self.assertEqual(edited.status_code, 200)
        self.assertEqual(
            edited.json()["proposal"]["diff"],
            {"preferred_brands": {"added": ["Ferrero"], "removed": ["Ja! Natürlich"]}},
        )
        decide(self.client, self.token, proposal["id"], "accept")
        self.assertEqual(self.current_list()["preferences"]["preferred_brands"], ["Ferrero"])

    def test_favorites_must_be_items_on_the_list(self):
        response, llm = propose(
            self.client, self.token, "propose_preferences_change", {"favorite_items": ["Butter"]}
        )

        self.assertEqual(response.json()["proposals"], [])
        self.assertTrue(llm.tool_results(1)[0]["is_error"])
        self.assertIn("Butter", llm.tool_results(1)[0]["content"]["error"])

    def test_a_proposal_without_any_change_is_reported_to_the_model(self):
        for empty in ({}, {"preferred_brands": ["Ja! Natürlich"]}):
            with self.subTest(empty=empty):
                response, llm = propose(self.client, self.token, "propose_preferences_change", empty)

                self.assertEqual(response.json()["proposals"], [])
                self.assertTrue(llm.tool_results(1)[0]["is_error"])

    def test_a_list_that_changed_since_the_proposal_is_not_overwritten(self):
        proposal = self.proposal_of(self.propose_changes()[0])
        self.save_list(item("Milch"), preferred_brands=["Andere"])
        edited_elsewhere = self.current_list()

        self.assertEqual(decide(self.client, self.token, proposal["id"], "accept").status_code, 409)
        self.assertEqual(self.current_list(), edited_elsewhere)


class LocationProposalTests(ProposalTestCase):
    def propose_graz(self, **extra):
        return propose(self.client, self.token, "propose_location_change", {"zip_code": "8010"}, **extra)

    def test_proposes_the_new_plz_for_confirmation(self):
        response, llm = self.propose_graz(zip_code="1010")

        proposal = self.proposal_of(response)
        self.assertEqual(proposal["kind"], "location")
        self.assertEqual(proposal["status"], "pending")
        self.assertEqual(
            proposal["diff"], {"before": {"zip_code": "1010"}, "after": {"zip_code": "8010"}}
        )
        self.assertNotIn("is_error", llm.tool_results(1)[0])

    def test_the_previous_location_may_be_unknown(self):
        proposal = self.proposal_of(self.propose_graz()[0])

        self.assertEqual(proposal["diff"], {"before": None, "after": {"zip_code": "8010"}})

    def test_accepting_hands_the_new_location_to_the_client_and_confirms(self):
        proposal = self.proposal_of(self.propose_graz(zip_code="1010")[0])
        self.save_list(item("Milch"))
        list_before = self.current_list()

        response = decide(self.client, self.token, proposal["id"], "accept")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["message"], "✅ Standort auf PLZ 8010 gesetzt.")
        self.assertEqual(body["location"], {"zip_code": "8010"})
        self.assertEqual(body["proposal"]["status"], "accepted")
        self.assertEqual(self.current_list(), list_before)

    def test_rejecting_hands_over_no_location(self):
        proposal = self.proposal_of(self.propose_graz(zip_code="1010")[0])

        response = decide(self.client, self.token, proposal["id"], "reject")

        self.assertEqual(response.json()["message"], REJECTED_MESSAGE)
        self.assertNotIn("location", response.json())
        self.assertEqual(response.json()["proposal"]["status"], "rejected")

    def test_editing_changes_the_proposed_plz(self):
        proposal = self.proposal_of(self.propose_graz(zip_code="1010")[0])

        edited = revise(self.client, self.token, proposal["id"], {"zip_code": "5020"})

        self.assertEqual(edited.status_code, 200)
        self.assertEqual(
            edited.json()["proposal"]["diff"],
            {"before": {"zip_code": "1010"}, "after": {"zip_code": "5020"}},
        )
        accepted = decide(self.client, self.token, proposal["id"], "accept")
        self.assertEqual(accepted.json()["location"], {"zip_code": "5020"})

    def test_an_invalid_or_unchanged_plz_is_reported_to_the_model(self):
        for tool_input, extra in (
            ({"zip_code": "Graz"}, {}),
            ({"zip_code": "80100"}, {}),
            ({}, {}),
            ({"zip_code": "1010"}, {"zip_code": "1010"}),  # already there
        ):
            with self.subTest(tool_input=tool_input, extra=extra):
                response, llm = propose(
                    self.client, self.token, "propose_location_change", tool_input, **extra
                )

                self.assertEqual(response.json()["proposals"], [])
                self.assertTrue(llm.tool_results(1)[0]["is_error"])
