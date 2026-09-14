from unittest import TestCase

from search.anchor_products import apply_anchor_overrides
from search.matching import group_offers


def _offer(offer_id, product_id, product_name, brand_name, advertiser_name, price,
           unit_short_name=None, volume=None, quantity=None):
    return {
        "id": offer_id,
        "price": price,
        "oldPrice": None,
        "referencePrice": None,
        "description": None,
        "product": {"id": product_id, "name": product_name, "description": None},
        "brand": {"id": 1, "name": brand_name},
        "categories": [],
        "advertisers": [{"id": 1, "name": advertiser_name}],
        "unit": {"id": 1, "name": unit_short_name, "shortName": unit_short_name}
        if unit_short_name
        else None,
        "volume": volume,
        "quantity": quantity,
    }


class AnchorOverrideTests(TestCase):
    def test_anchor_mapping_merges_offers_the_fuzzy_matcher_would_keep_separate(self):
        # Slightly different brand/product name spelling across retailers for the
        # exact same anchor product (Nutella 750 g) — fuzzy matching alone keeps
        # these apart because the brand strings disagree.
        offers = [
            _offer(1, 23457, "Nutella Nuss-Nougat-Creme", "Ferrero", "BILLA", 5.59,
                   unit_short_name="kg", volume=0.75),
            _offer(2, 23457, "Nutella", "Nutella", "PENNY", 4.99,
                   unit_short_name="kg", volume=0.75),
        ]
        groups = group_offers(offers)
        self.assertEqual(len(groups), 2, "fuzzy matching alone should keep these separate")

        merged = apply_anchor_overrides(groups)

        self.assertEqual(len(merged), 1)
        self.assertEqual({o["advertiser"] for o in merged[0]["offers"]}, {"BILLA", "PENNY"})
        self.assertEqual(merged[0]["cheapest"]["advertiser"], "PENNY")

    def test_groups_with_no_anchor_match_pass_through_unchanged(self):
        offers = [_offer(1, 1, "Irgendein Produkt", "Irgendeine Marke", "SPAR", 1.99)]
        groups = group_offers(offers)

        merged = apply_anchor_overrides(groups)

        self.assertEqual(merged, groups)
