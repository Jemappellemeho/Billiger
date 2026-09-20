from unittest import TestCase

from search.comparison import compare_cart, select_matching_group


def _offer(advertiser, price, old_price=None):
    return {"advertiser": advertiser, "price": price, "old_price": old_price}


def _item(name, offers, brand=None, quantity=1):
    return {"name": name, "brand": brand, "quantity": quantity, "offers": offers}


class SelectMatchingGroupTests(TestCase):
    def test_prefers_group_with_matching_brand(self):
        groups = [
            {"brand": "Ferrero", "name": "Kinder Schokolade"},
            {"brand": "Nutella", "name": "Nuss Nougat Creme"},
        ]

        selected = select_matching_group(groups, "Nutella", "Nutella")

        self.assertEqual(selected["brand"], "Nutella")

    def test_falls_back_to_best_name_similarity_without_brand(self):
        groups = [
            {"brand": "Markenlos", "name": "Erdnussbutter"},
            {"brand": "Markenlos", "name": "Nutella Nuss Nougat Creme"},
        ]

        selected = select_matching_group(groups, "Nutella", None)

        self.assertEqual(selected["name"], "Nutella Nuss Nougat Creme")

    def test_empty_groups_returns_none(self):
        self.assertIsNone(select_matching_group([], "Nutella", "Nutella"))


class CompareCartSingleStoreTests(TestCase):
    def test_picks_cheapest_store_that_covers_every_item(self):
        items = [
            _item("Milch", [_offer("HOFER", 1.09), _offer("LIDL", 1.19), _offer("SPAR", 1.29)]),
            _item("Nutella", [_offer("HOFER", 4.99), _offer("LIDL", 5.29), _offer("SPAR", 5.59)]),
        ]

        result = compare_cart(items)

        self.assertEqual(result["single_store"]["advertiser"], "HOFER")
        self.assertAlmostEqual(result["single_store"]["total"], 1.09 + 4.99)

    def test_store_missing_an_item_is_excluded_from_single_store_candidates(self):
        items = [
            _item("Milch", [_offer("HOFER", 1.09), _offer("LIDL", 1.19)]),
            _item("Nutella", [_offer("LIDL", 5.29)]),  # not at HOFER
        ]

        result = compare_cart(items)

        self.assertEqual(result["single_store"]["advertiser"], "LIDL")
        totals_by_advertiser = {s["advertiser"]: s for s in result["store_totals"]}
        self.assertFalse(totals_by_advertiser["HOFER"]["covers_all_items"])
        self.assertEqual(totals_by_advertiser["HOFER"]["missing_items"], ["Nutella"])
        self.assertIsNone(totals_by_advertiser["HOFER"]["total"])

    def test_no_store_covers_everything_single_store_is_none(self):
        items = [
            _item("Milch", [_offer("HOFER", 1.09)]),
            _item("Nutella", [_offer("LIDL", 5.29)]),
        ]

        result = compare_cart(items)

        self.assertIsNone(result["single_store"])

    def test_quantity_scales_the_line_price_and_store_total(self):
        items = [_item("Milch", [_offer("HOFER", 1.00)], quantity=3)]

        result = compare_cart(items)

        self.assertEqual(result["single_store"]["total"], 3.00)
        self.assertEqual(result["single_store"]["items"][0]["price"], 3.00)


class CompareCartFullSplitTests(TestCase):
    def test_full_split_takes_the_per_product_minimum_across_all_stores(self):
        items = [
            _item("Milch", [_offer("HOFER", 1.09), _offer("LIDL", 1.19), _offer("PENNY", 1.15)]),
            _item("Nutella", [_offer("HOFER", 4.99), _offer("LIDL", 5.29), _offer("PENNY", 4.79)]),
        ]

        result = compare_cart(items)

        assignment_by_name = {line["name"]: line for line in result["full_split"]["assignment"]}
        self.assertEqual(assignment_by_name["Milch"]["advertiser"], "HOFER")
        self.assertEqual(assignment_by_name["Nutella"]["advertiser"], "PENNY")
        self.assertAlmostEqual(result["full_split"]["total"], 1.09 + 4.79)

    def test_savings_are_reported_vs_most_expensive_and_vs_regular_price(self):
        items = [_item("Nutella", [_offer("HOFER", 4.99, old_price=6.99), _offer("LIDL", 5.29)])]

        result = compare_cart(items)

        line = result["full_split"]["assignment"][0]
        self.assertEqual(line["advertiser"], "HOFER")
        self.assertAlmostEqual(line["savings_vs_most_expensive"], 5.29 - 4.99)
        self.assertAlmostEqual(line["savings_vs_regular"], 6.99 - 4.99)

    def test_missing_regular_price_reports_none_not_zero(self):
        items = [_item("Nutella", [_offer("HOFER", 4.99, old_price=None)])]

        result = compare_cart(items)

        self.assertIsNone(result["full_split"]["assignment"][0]["savings_vs_regular"])

    def test_items_with_no_offers_are_reported_as_unavailable_and_excluded(self):
        items = [
            _item("Milch", [_offer("HOFER", 1.09)]),
            _item("Einhornstaub", []),
        ]

        result = compare_cart(items)

        self.assertEqual(result["unavailable_items"], ["Einhornstaub"])
        names_in_split = {line["name"] for line in result["full_split"]["assignment"]}
        self.assertNotIn("Einhornstaub", names_in_split)


class CompareCartLadderTests(TestCase):
    def test_ladder_starts_at_the_single_store_baseline(self):
        items = [
            _item("Milch", [_offer("HOFER", 1.09), _offer("LIDL", 1.19)]),
            _item("Nutella", [_offer("HOFER", 4.99), _offer("LIDL", 4.79)]),
        ]

        result = compare_cart(items)

        first_rung = result["ladder"][0]
        self.assertEqual(first_rung["stops"], 1)
        self.assertEqual(first_rung["stores"], [result["single_store"]["advertiser"]])
        self.assertEqual(first_rung["total"], result["single_store"]["total"])

    def test_ladder_converges_to_the_full_split_total(self):
        items = [
            _item("Milch", [_offer("HOFER", 1.09), _offer("LIDL", 1.19), _offer("PENNY", 1.15)]),
            _item("Nutella", [_offer("HOFER", 4.99), _offer("LIDL", 5.29), _offer("PENNY", 4.79)]),
            _item("Red Bull", [_offer("HOFER", 5.99), _offer("LIDL", 6.49), _offer("PENNY", 6.29)]),
        ]

        result = compare_cart(items)

        last_rung = result["ladder"][-1]
        self.assertAlmostEqual(last_rung["total"], result["full_split"]["total"])

    def test_ladder_marginal_savings_are_non_negative_and_strictly_decrease_total(self):
        items = [
            _item("Milch", [_offer("HOFER", 1.09), _offer("LIDL", 1.19), _offer("PENNY", 1.15)]),
            _item("Nutella", [_offer("HOFER", 4.99), _offer("LIDL", 5.29), _offer("PENNY", 4.79)]),
            _item("Red Bull", [_offer("HOFER", 5.99), _offer("LIDL", 6.49), _offer("PENNY", 5.49)]),
        ]

        result = compare_cart(items)

        totals = [rung["total"] for rung in result["ladder"]]
        for earlier, later in zip(totals, totals[1:]):
            self.assertLessEqual(later, earlier)
        for rung in result["ladder"][1:]:
            self.assertGreaterEqual(rung["marginal_savings"], 0)

    def test_ladder_stops_growing_once_no_further_store_helps(self):
        # Every item is cheapest at the same single store, so a second store
        # never improves the total and the ladder should not add one.
        items = [
            _item("Milch", [_offer("HOFER", 1.09), _offer("LIDL", 1.19)]),
            _item("Nutella", [_offer("HOFER", 4.99), _offer("LIDL", 5.29)]),
        ]

        result = compare_cart(items)

        self.assertEqual(len(result["ladder"]), 1)

    def test_no_full_coverage_store_ladder_still_converges_to_full_split(self):
        items = [
            _item("Milch", [_offer("HOFER", 1.09)]),
            _item("Nutella", [_offer("LIDL", 5.29)]),
        ]

        result = compare_cart(items)

        self.assertIsNone(result["single_store"])
        self.assertGreater(len(result["ladder"]), 0)
        self.assertAlmostEqual(result["ladder"][-1]["total"], result["full_split"]["total"])

    def test_empty_cart_returns_empty_results_without_crashing(self):
        result = compare_cart([])

        self.assertIsNone(result["single_store"])
        self.assertEqual(result["full_split"]["total"], 0)
        self.assertEqual(result["full_split"]["assignment"], [])
        self.assertEqual(result["ladder"], [])
        self.assertEqual(result["store_totals"], [])
