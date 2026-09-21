from unittest.mock import patch

from rest_framework.authtoken.models import Token

from accounts.tests.base import AccountsAPITestCase
from accounts.tests.helpers import LIST_URL, auth, item, shopping_list
from assistant.models import Proposal
from assistant.tests.helpers import PROPOSALS_URL, assistant_llm, chat, decide, propose, say
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


class ProposalThrottleTests(AccountsAPITestCase):
    """Creating proposals is throttled per account (Ticket 19), so a runaway client can't flood the app."""

    def location_proposal(self, token, zip_code="8010"):
        return create(self.client, token, {"kind": "location", "zip_code": zip_code})

    def test_creating_proposals_is_rate_limited_with_a_german_message(self):
        token = sign_up(self.client)

        statuses = [self.location_proposal(token).status_code for _ in range(21)]
        blocked = self.location_proposal(token)

        self.assertEqual(statuses[:20], [201] * 20)
        self.assertEqual(statuses[20], 429)
        self.assertIn("Zu viele Vorschläge", blocked.json()["detail"])

    def test_the_limit_is_per_account(self):
        busy, other = sign_up(self.client), sign_up(self.client, "ben@example.com")
        for _ in range(21):
            self.location_proposal(busy)

        self.assertEqual(self.location_proposal(busy).status_code, 429)
        self.assertEqual(self.location_proposal(other).status_code, 201)

    def test_listing_and_deciding_are_not_throttled_by_it(self):
        token = sign_up(self.client)
        ids = [self.location_proposal(token).json()["proposal"]["id"] for _ in range(20)]
        self.assertEqual(self.location_proposal(token).status_code, 429)

        self.assertEqual(self.client.get(PROPOSALS_URL, **auth(token)).status_code, 200)
        self.assertEqual(decide(self.client, token, ids[0], "reject").status_code, 200)

    def test_the_limit_is_separate_from_the_chat_limit(self):
        token = sign_up(self.client)
        for _ in range(21):
            self.location_proposal(token)

        with assistant_llm(say("Hi")):
            self.assertEqual(chat(self.client, token).status_code, 200)


class PendingProposalLimitTests(AccountsAPITestCase):
    """An account holds at most `MAX_PENDING` open proposals: a new one retires the oldest (Ticket 19)."""

    LIMIT = 3

    def setUp(self):
        super().setUp()
        patcher = patch("assistant.proposals.MAX_PENDING", self.LIMIT)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.token = sign_up(self.client)

    def open_ids(self, token):
        response = self.client.get(PROPOSALS_URL, **auth(token))
        return [proposal["id"] for proposal in response.json()["proposals"]]

    def location_proposals(self, count, token=None):
        return [
            create(self.client, token or self.token, {"kind": "location", "zip_code": f"80{n:02d}"}).json()["proposal"]["id"]
            for n in range(count)
        ]

    def test_up_to_the_limit_nothing_is_retired(self):
        ids = self.location_proposals(self.LIMIT)

        self.assertEqual(self.open_ids(self.token), ids[::-1])
        self.assertFalse(Proposal.objects.filter(status=Proposal.Status.STALE).exists())

    def test_one_more_retires_the_oldest_and_the_list_keeps_the_newest(self):
        ids = self.location_proposals(self.LIMIT + 2)

        self.assertEqual(self.open_ids(self.token), ids[2:][::-1])
        retired = Proposal.objects.filter(pk__in=ids[:2])
        self.assertEqual({proposal.status for proposal in retired}, {Proposal.Status.STALE})
        self.assertTrue(all(proposal.decided_at for proposal in retired))

    def test_a_retired_proposal_can_no_longer_be_decided(self):
        oldest, *_ = self.location_proposals(self.LIMIT + 1)

        self.assertEqual(decide(self.client, self.token, oldest, "accept").status_code, 409)
        self.assertEqual(decide(self.client, self.token, oldest, "reject").status_code, 409)

    def test_decided_proposals_do_not_count_toward_the_limit(self):
        ids = self.location_proposals(self.LIMIT)
        decide(self.client, self.token, ids[0], "reject")

        newest = self.location_proposals(1)

        self.assertEqual(self.open_ids(self.token), newest + ids[1:][::-1])
        self.assertEqual(Proposal.objects.get(pk=ids[1]).status, Proposal.Status.PENDING)

    def test_it_only_retires_the_accounts_own_proposals(self):
        other = sign_up(self.client, "ben@example.com")
        theirs = self.location_proposals(self.LIMIT, token=other)

        self.location_proposals(self.LIMIT + 2)

        self.assertEqual(self.open_ids(other), theirs[::-1])

    def test_the_list_shows_at_most_the_limit_even_for_rows_older_than_the_cap(self):
        user = Token.objects.get(key=self.token).user
        ids = [
            Proposal.objects.create(user=user, kind="location", base=None, proposed={}, diff={}).pk
            for _ in range(self.LIMIT + 2)
        ]

        self.assertEqual(self.open_ids(self.token), ids[2:][::-1])

    def test_proposals_from_a_chat_turn_count_too(self):
        chat_proposals = []
        for n in range(self.LIMIT):
            response, _ = propose(self.client, self.token, "propose_location_change", {"zip_code": f"80{n:02d}"})
            chat_proposals.append(response.json()["proposals"][0]["id"])

        self.location_proposals(1)

        self.assertNotIn(chat_proposals[0], self.open_ids(self.token))
        self.assertEqual(len(self.open_ids(self.token)), self.LIMIT)


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
