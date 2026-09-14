from unittest import TestCase

from search.matching import group_offers


def _offer(
    offer_id,
    product_id,
    product_name,
    brand_name,
    advertiser_name,
    price,
    old_price=None,
    reference_price=None,
    unit_short_name=None,
    volume=None,
    quantity=None,
    description=None,
    categories=None,
):
    return {
        "id": offer_id,
        "price": price,
        "oldPrice": old_price,
        "referencePrice": reference_price,
        "description": description,
        "product": {"id": product_id, "name": product_name, "description": None},
        "brand": {"id": 1, "name": brand_name},
        "categories": categories or [],
        "advertisers": [{"id": 1, "name": advertiser_name}],
        "unit": {"id": 1, "name": unit_short_name, "shortName": unit_short_name}
        if unit_short_name
        else None,
        "volume": volume,
        "quantity": quantity,
    }


class GroupOffersSameProductTests(TestCase):
    def test_same_brand_name_and_quantity_across_retailers_are_grouped(self):
        offers = [
            _offer(
                3388876, 23457, "Nutella", "Nutella", "BILLA", 5.59,
                old_price=6.99, reference_price=7.45, unit_short_name="kg", volume=0.75,
            ),
            _offer(
                3384937, 23457, "Nutella", "Nutella", "PENNY", 4.99,
                old_price=5.99, reference_price=7.45, unit_short_name="kg", volume=0.75,
            ),
        ]

        groups = group_offers(offers)

        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual({o["advertiser"] for o in group["offers"]}, {"BILLA", "PENNY"})
        self.assertEqual(group["cheapest"]["advertiser"], "PENNY")
        self.assertEqual(group["cheapest"]["price"], 4.99)

    def test_normalized_quantity_is_converted_to_a_common_base_unit(self):
        offers = [
            _offer(1, 1, "Milch", "Ja! Natürlich", "SPAR", 1.19, unit_short_name="l", volume=1.0),
            _offer(2, 1, "Milch", "Ja! Natürlich", "EUROSPAR", 1.15, unit_short_name="l", volume=1.0),
        ]

        groups = group_offers(offers)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["normalized_quantity"], {"amount": 1000.0, "unit": "ml"})

    def test_extracts_category_names_onto_the_group(self):
        offers = [
            _offer(
                1, 1, "Nutella", "Nutella", "BILLA", 5.59, unit_short_name="kg", volume=0.75,
                categories=[{"id": 10, "name": "Schokoaufstrich"}],
            ),
        ]

        groups = group_offers(offers)

        self.assertEqual(groups[0]["categories"], ["Schokoaufstrich"])

    def test_same_brand_name_and_quantity_but_different_product_id_are_still_grouped(self):
        # product.id is only a weak prefilter (see module docstring) — Marktguru
        # does not guarantee it agrees across retailers for the identical product,
        # so brand+name+quantity equality must win even across different product.id.
        offers = [
            _offer(1, 111, "Nutella", "Nutella", "BILLA", 5.59, unit_short_name="kg", volume=0.75),
            _offer(2, 222, "Nutella", "Nutella", "PENNY", 4.99, unit_short_name="kg", volume=0.75),
        ]

        groups = group_offers(offers)

        self.assertEqual(len(groups), 1)
        self.assertEqual({o["advertiser"] for o in groups[0]["offers"]}, {"BILLA", "PENNY"})


class GroupOffersCrossProductGuardTests(TestCase):
    """Regression coverage for the Coca-Cola counterexample from the research doc:
    Marktguru reuses product.id=21896 across different volumes and even different
    brands within a mixed pack — product.id alone must never decide equality.
    """

    def test_same_product_id_but_different_volume_is_not_merged(self):
        offers = [
            _offer(1, 21896, "Cola", "Coca-Cola", "EUROSPAR", 0.59, unit_short_name="l", volume=0.33),
            _offer(2, 21896, "Cola", "Coca-Cola", "EUROSPAR", 1.99, unit_short_name="l", volume=2.0),
        ]

        groups = group_offers(offers)

        self.assertEqual(len(groups), 2)

    def test_same_product_id_but_different_brand_is_not_merged(self):
        offers = [
            _offer(1, 21896, "Fanta, Sprite, Mezzo Mix", "Fanta", "ADEG", 2.49, unit_short_name="l", volume=1.5),
            _offer(2, 21896, "Cola", "Coca-Cola", "EUROSPAR", 1.99, unit_short_name="l", volume=1.5),
        ]

        groups = group_offers(offers)

        self.assertEqual(len(groups), 2)

    def test_different_product_id_and_different_details_are_not_merged(self):
        offers = [
            _offer(1, 1, "Nutella", "Nutella", "BILLA", 5.59, unit_short_name="kg", volume=0.75),
            _offer(2, 2, "Red Bull", "Red Bull", "BILLA", 1.99, unit_short_name="l", volume=0.25),
        ]

        groups = group_offers(offers)

        self.assertEqual(len(groups), 2)
