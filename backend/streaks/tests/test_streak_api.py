from datetime import datetime, timedelta

from accounts.tests.base import AccountsAPITestCase
from search.marktguru_client import MarktguruClient
from search.tests.test_cart_comparison_view import _fake_session_get, _raw_offer, _response
from streaks.tests.helpers import (
    MILCH_AND_NUTELLA,
    STREAK_URL,
    VIENNA,
    WEEK_1,
    WEEK_2,
    WEEK_3,
    WEEK_4,
    WEEK_5,
    compare,
    sign_up,
    streak_summary,
)


def _with_butter_at_billa(url, params=None, headers=None, timeout=None):
    if url == MarktguruClient.API_URL and (params or {}).get("q") == "Butter":
        return _response(json_body={"results": [_raw_offer(9, 300, "Butter", "Kerrygold", "BILLA", 2.49)]})
    return _fake_session_get(url, params=params, headers=headers, timeout=timeout)


class CompletedComparisonTests(AccountsAPITestCase):
    def test_streak_requires_a_signed_in_account(self):
        response = self.client.get(STREAK_URL)

        self.assertEqual(response.status_code, 401)

    def test_new_account_starts_without_streak_or_savings(self):
        token = sign_up(self.client)

        body = streak_summary(self.client, token).json()

        self.assertEqual(body["streak"]["weeks"], 0)
        self.assertEqual(body["streak"]["status"], "none")
        self.assertIsNone(body["this_week"])
        self.assertEqual(body["total_savings"], {"vs_most_expensive": 0, "vs_regular": 0})
        self.assertEqual(body["history"], [])

    def test_signed_in_comparison_starts_this_weeks_streak(self):
        token = sign_up(self.client)

        self.assertEqual(compare(self.client, token, moment=WEEK_1).status_code, 200)
        body = streak_summary(self.client, token, moment=WEEK_1).json()

        self.assertEqual(body["streak"]["weeks"], 1)
        self.assertEqual(body["streak"]["status"], "active")
        # Milch: LIDL 0.99 vs HOFER 1.09; Nutella: HOFER 4.99 (was 6.99) vs LIDL 5.29.
        self.assertEqual(body["this_week"]["savings_vs_most_expensive"], 0.40)
        self.assertEqual(body["this_week"]["savings_vs_regular"], 2.00)

    def test_guest_comparison_is_not_tracked(self):
        token = sign_up(self.client)

        self.assertEqual(compare(self.client, token=None, moment=WEEK_1).status_code, 200)

        self.assertEqual(streak_summary(self.client, token, moment=WEEK_1).json()["streak"]["weeks"], 0)

    def test_comparison_response_is_unchanged_for_signed_in_users(self):
        token = sign_up(self.client)

        signed_in = compare(self.client, token, moment=WEEK_1).json()
        guest = compare(self.client, None, moment=WEEK_1).json()

        self.assertEqual(signed_in, guest)

    def test_comparison_without_any_purchasable_item_is_not_tracked(self):
        token = sign_up(self.client)

        response = compare(self.client, token, items=[{"name": "Unbekanntes Produkt"}], moment=WEEK_1)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(streak_summary(self.client, token, moment=WEEK_1).json()["streak"]["weeks"], 0)

    def test_repeating_a_comparison_in_the_same_week_counts_once(self):
        token = sign_up(self.client)

        compare(self.client, token, moment=WEEK_1)
        compare(self.client, token, moment=WEEK_1 + timedelta(days=2))
        body = streak_summary(self.client, token, moment=WEEK_1 + timedelta(days=3)).json()

        self.assertEqual(body["streak"]["weeks"], 1)
        self.assertEqual(body["this_week"]["savings_vs_most_expensive"], 0.40)
        self.assertEqual(body["total_savings"]["vs_most_expensive"], 0.40)

    def test_latest_comparison_of_the_week_replaces_the_earlier_one(self):
        token = sign_up(self.client)

        compare(self.client, token, items=MILCH_AND_NUTELLA, moment=WEEK_1)
        compare(self.client, token, items=[{"name": "Milch"}], moment=WEEK_1 + timedelta(days=1))
        body = streak_summary(self.client, token, moment=WEEK_1 + timedelta(days=2)).json()

        self.assertEqual(body["this_week"]["savings_vs_most_expensive"], 0.10)
        self.assertEqual(body["this_week"]["savings_vs_regular"], 0)

    def test_accounts_do_not_see_each_others_streaks(self):
        anna = sign_up(self.client, "anna@example.com")
        ben = sign_up(self.client, "ben@example.com")

        compare(self.client, anna, moment=WEEK_1)

        self.assertEqual(streak_summary(self.client, ben, moment=WEEK_1).json()["streak"]["weeks"], 0)
        self.assertEqual(streak_summary(self.client, anna, moment=WEEK_1).json()["streak"]["weeks"], 1)


class StreakOverTimeTests(AccountsAPITestCase):
    def test_comparisons_in_consecutive_weeks_extend_the_streak_and_add_up_savings(self):
        token = sign_up(self.client)

        for week in (WEEK_1, WEEK_2, WEEK_3):
            compare(self.client, token, moment=week)
        body = streak_summary(self.client, token, moment=WEEK_3).json()

        self.assertEqual(body["streak"]["weeks"], 3)
        self.assertEqual(body["streak"]["status"], "active")
        self.assertEqual(body["total_savings"]["vs_most_expensive"], 1.20)
        self.assertEqual(body["total_savings"]["vs_regular"], 6.00)

    def test_streak_stays_safe_while_this_weeks_comparison_is_still_open(self):
        token = sign_up(self.client)

        compare(self.client, token, moment=WEEK_1)
        body = streak_summary(self.client, token, moment=WEEK_2).json()

        self.assertEqual(body["streak"]["weeks"], 1)
        self.assertEqual(body["streak"]["status"], "pending")
        self.assertEqual(body["streak"]["missed_weeks"], 0)
        self.assertIsNone(body["this_week"])

    def test_a_missed_week_pauses_the_streak_instead_of_resetting_it(self):
        token = sign_up(self.client)
        for week in (WEEK_1, WEEK_2, WEEK_3):
            compare(self.client, token, moment=week)

        # WEEK_4 passes without a comparison; we look at the summary in WEEK_5.
        body = streak_summary(self.client, token, moment=WEEK_5).json()

        self.assertEqual(body["streak"]["weeks"], 3)
        self.assertEqual(body["streak"]["status"], "paused")
        self.assertEqual(body["streak"]["missed_weeks"], 1)
        self.assertEqual(body["streak"]["last_completed_week"], "2026-09-21")
        self.assertIsNone(body["this_week"])
        # Nothing already saved is lost either.
        self.assertEqual(body["total_savings"]["vs_most_expensive"], 1.20)

    def test_a_paused_streak_continues_with_the_next_comparison(self):
        token = sign_up(self.client)
        for week in (WEEK_1, WEEK_2, WEEK_3):
            compare(self.client, token, moment=week)

        compare(self.client, token, moment=WEEK_5)
        body = streak_summary(self.client, token, moment=WEEK_5).json()

        self.assertEqual(body["streak"]["weeks"], 4)
        self.assertEqual(body["streak"]["status"], "active")
        self.assertEqual(body["streak"]["missed_weeks"], 0)

    def test_weeks_run_monday_to_sunday_in_vienna_time(self):
        token = sign_up(self.client)
        sunday_night = datetime(2026, 9, 13, 23, 30, tzinfo=VIENNA)  # still WEEK_1's week
        monday_morning = datetime(2026, 9, 14, 0, 30, tzinfo=VIENNA)  # WEEK_2

        compare(self.client, token, moment=sunday_night)
        compare(self.client, token, moment=monday_morning)
        body = streak_summary(self.client, token, moment=monday_morning).json()

        self.assertEqual(body["streak"]["weeks"], 2)
        self.assertEqual([week["week_start"] for week in body["history"]], ["2026-09-07", "2026-09-14"])

    def test_history_lists_every_week_including_missed_ones(self):
        token = sign_up(self.client)
        compare(self.client, token, moment=WEEK_1)
        compare(self.client, token, moment=WEEK_3)

        history = streak_summary(self.client, token, moment=WEEK_4).json()["history"]

        self.assertEqual(
            [(week["week_start"], week["completed"]) for week in history],
            [("2026-09-07", True), ("2026-09-14", False), ("2026-09-21", True), ("2026-09-28", False)],
        )
        missed = history[1]
        self.assertEqual(missed["savings_vs_most_expensive"], 0)
        self.assertEqual(missed["stores"], [])
        self.assertEqual(history[0]["savings_vs_most_expensive"], 0.40)


class SavingsBreakdownTests(AccountsAPITestCase):
    def test_summary_names_the_stores_and_products_behind_the_savings(self):
        token = sign_up(self.client)

        compare(self.client, token, moment=WEEK_1)
        this_week = streak_summary(self.client, token, moment=WEEK_1).json()["this_week"]

        # Largest contribution first: Nutella at HOFER (0.30, on sale) before Milch at LIDL (0.10).
        self.assertEqual(
            this_week["stores"],
            [
                {"advertiser": "HOFER", "savings_vs_most_expensive": 0.30},
                {"advertiser": "LIDL", "savings_vs_most_expensive": 0.10},
            ],
        )
        self.assertEqual(
            [
                (i["name"], i["advertiser"], i["savings_vs_most_expensive"], i["on_sale"])
                for i in this_week["items"]
            ],
            [("Nutella", "HOFER", 0.30, True), ("Milch", "LIDL", 0.10, False)],
        )
        self.assertEqual(this_week["items"][0]["savings_vs_regular"], 2.00)

    def test_products_that_saved_nothing_are_left_out_of_the_breakdown(self):
        token = sign_up(self.client)

        # Butter is only on offer at BILLA, so it cannot save anything against itself.
        compare(
            self.client,
            token,
            items=[{"name": "Milch"}, {"name": "Butter"}],
            moment=WEEK_1,
            marktguru=_with_butter_at_billa,
        )
        this_week = streak_summary(self.client, token, moment=WEEK_1).json()["this_week"]

        self.assertEqual([i["name"] for i in this_week["items"]], ["Milch"])
        self.assertEqual([s["advertiser"] for s in this_week["stores"]], ["LIDL"])
