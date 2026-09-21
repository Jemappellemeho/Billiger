from accounts.tests.base import AccountsAPITestCase
from accounts.tests.helpers import LIST_URL, auth, item, shopping_list
from assistant.models import Proposal
from assistant.tests.helpers import PROPOSALS_URL, decide
from streaks.tests.helpers import sign_up


def create(client, token, body):
    return client.post(PROPOSALS_URL, body, format="json", **auth(token))


class CreateProposalTests(AccountsAPITestCase):
    """POST /api/assistant/proposals/ makes what a chat turn's propose tool makes (Ticket 16)."""

    def setUp(self):
        super().setUp()
        self.token = sign_up(self.client)
        self.client.put(LIST_URL, shopping_list([item("Milch")]), format="json", **auth(self.token))

    def stored_names(self):
        response = self.client.get(LIST_URL, **auth(self.token))
        return [row["name"] for row in response.json()["items"]]

    def test_a_list_proposal_comes_back_pending_with_its_full_diff_and_changes_nothing(self):
        response = create(
            self.client, self.token, {"kind": "shopping_list", "items": [{"name": "Milch"}, {"name": "Butter"}]}
        )

        self.assertEqual(response.status_code, 201)
        proposal = response.json()["proposal"]
        self.assertEqual(proposal["status"], "pending")
        self.assertEqual([row["name"] for row in proposal["diff"]["added"]], ["Butter"])
        self.assertEqual(self.stored_names(), ["Milch"])

    def test_it_is_accepted_over_the_decision_endpoints_like_any_proposal(self):
        created = create(self.client, self.token, {"kind": "shopping_list", "items": [{"name": "Butter"}]})

        response = decide(self.client, self.token, created.json()["proposal"]["id"], "accept")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stored_names(), ["Butter"])

    def test_preference_and_location_proposals_work_too(self):
        preferences = create(self.client, self.token, {"kind": "preferences", "excluded_stores": ["Lidl"]})
        location = create(self.client, self.token, {"kind": "location", "zip_code": "8010"})

        self.assertEqual(preferences.json()["proposal"]["diff"]["excluded_stores"]["added"], ["Lidl"])
        self.assertEqual(location.json()["proposal"]["diff"], {"before": None, "after": {"zip_code": "8010"}})

    def test_an_unknown_or_missing_kind_is_refused(self):
        for body in ({"kind": "password", "password": "x"}, {"items": []}, {"kind": None}):
            response = create(self.client, self.token, body)
            self.assertEqual(response.status_code, 400, body)
        self.assertEqual(Proposal.objects.count(), 0)

    def test_invalid_input_and_fields_of_another_kind_are_refused(self):
        for body in (
            {"kind": "location", "zip_code": "nope"},
            {"kind": "location", "zip_code": "8010", "email": "eve@example.com"},
            {"kind": "shopping_list", "items": "Milch"},
        ):
            response = create(self.client, self.token, body)
            self.assertEqual(response.status_code, 400, body)
            self.assertIn("detail", response.json())
        self.assertEqual(Proposal.objects.count(), 0)

    def test_a_change_that_changes_nothing_is_refused(self):
        response = create(self.client, self.token, {"kind": "shopping_list", "items": [{"name": "Milch"}]})
        self.assertEqual(response.status_code, 400)

    def test_it_needs_an_account(self):
        response = self.client.post(PROPOSALS_URL, {"kind": "location", "zip_code": "8010"}, format="json")
        self.assertEqual(response.status_code, 401)


class ListProposalsTests(AccountsAPITestCase):
    def test_only_the_callers_pending_proposals_are_listed(self):
        mine, theirs = sign_up(self.client), sign_up(self.client, "ben@example.com")
        kept = create(self.client, mine, {"kind": "location", "zip_code": "8010"}).json()["proposal"]["id"]
        dropped = create(self.client, mine, {"kind": "location", "zip_code": "4020"}).json()["proposal"]["id"]
        create(self.client, theirs, {"kind": "location", "zip_code": "6020"})
        decide(self.client, mine, dropped, "reject")

        response = self.client.get(PROPOSALS_URL, **auth(mine))

        self.assertEqual([proposal["id"] for proposal in response.json()["proposals"]], [kept])

    def test_it_needs_an_account(self):
        self.assertEqual(self.client.get(PROPOSALS_URL).status_code, 401)
