from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase

from search.marktguru_client import MarktguruClient
from search.models import AnchorOfferSnapshot
from search.tasks import refresh_offers

HOMEPAGE_HTML = (
    '<script type="application/json">'
    '{"apiKey": "test-api-key", "clientKey": "test-client-key"}'
    "</script>"
)


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


NUTELLA_OFFERS = [
    _offer(1, 23457, "Nutella", "Nutella", "BILLA", 5.59, unit_short_name="kg", volume=0.75),
    _offer(2, 23457, "Nutella", "Ferrero", "PENNY", 4.99, unit_short_name="kg", volume=0.75),
]

COLA_OFFERS = [
    _offer(3, 999, "Coca Cola", "Coca Cola", "SPAR", 1.99, unit_short_name="l", volume=1.5),
]

# A can that does not match the red-bull-250ml anchor's expected 250 ml quantity.
RED_BULL_WRONG_SIZE_OFFERS = [
    _offer(4, 111, "Red Bull Energy Drink", "Red Bull", "HOFER", 3.49,
           unit_short_name="ml", volume=None, quantity=500),
]


def _response(json_body=None, text=None):
    resp = Mock()
    resp.raise_for_status.side_effect = lambda: None
    if json_body is not None:
        resp.json.return_value = json_body
    if text is not None:
        resp.text = text
    return resp


def _fake_session_get(results_by_query, failing_queries=()):
    def _get(url, params=None, headers=None, timeout=None):
        if url == MarktguruClient.HOMEPAGE_URL:
            return _response(text=HOMEPAGE_HTML)
        if url == MarktguruClient.API_URL:
            query = params["q"]
            if query in failing_queries:
                raise ConnectionError("marktguru down")
            return _response(json_body={"results": results_by_query.get(query, [])})
        raise AssertionError(f"unexpected URL requested in test: {url}")

    return _get


class RefreshOffersTaskTests(TestCase):
    @patch("requests.Session.get")
    def test_refreshes_matched_anchors_tolerates_one_failure_and_keeps_stale_data(self, mock_get):
        # Pre-existing snapshot from a previous successful run — must survive
        # this run's failure for the same anchor untouched.
        AnchorOfferSnapshot.objects.create(
            anchor_id="red-bull-250ml", data={"stale": True, "cheapest": {"price": 1.0}}
        )

        mock_get.side_effect = _fake_session_get(
            results_by_query={"nutella": NUTELLA_OFFERS, "cola": COLA_OFFERS},
            failing_queries={"red bull energy drink"},
        )

        result = refresh_offers()

        self.assertEqual(result, {"refreshed": 2, "failed": 1})

        nutella = AnchorOfferSnapshot.objects.get(anchor_id="nutella-750g")
        self.assertEqual({o["advertiser"] for o in nutella.data["offers"]}, {"BILLA", "PENNY"})
        self.assertEqual(nutella.data["cheapest"]["advertiser"], "PENNY")

        cola = AnchorOfferSnapshot.objects.get(anchor_id="cola-1-5l")
        self.assertEqual(cola.data["cheapest"]["advertiser"], "SPAR")

        # Untouched by the failed red-bull-250ml fetch.
        stale = AnchorOfferSnapshot.objects.get(anchor_id="red-bull-250ml")
        self.assertEqual(stale.data, {"stale": True, "cheapest": {"price": 1.0}})

    @patch("requests.Session.get")
    def test_offers_that_do_not_match_the_anchor_are_not_cached(self, mock_get):
        mock_get.side_effect = _fake_session_get(
            results_by_query={"red bull energy drink": RED_BULL_WRONG_SIZE_OFFERS},
            failing_queries={"nutella", "cola"},
        )

        result = refresh_offers()

        self.assertEqual(result, {"refreshed": 0, "failed": 2})
        self.assertFalse(AnchorOfferSnapshot.objects.filter(anchor_id="red-bull-250ml").exists())

    @patch("requests.Session.get", side_effect=ConnectionError("marktguru down"))
    def test_total_marktguru_outage_does_not_raise(self, mock_get):
        result = refresh_offers()

        self.assertEqual(result, {"refreshed": 0, "failed": 3})
        self.assertEqual(AnchorOfferSnapshot.objects.count(), 0)


class WeeklyBeatScheduleTests(TestCase):
    def test_weekly_refresh_is_registered_on_the_celery_beat_schedule(self):
        entry = settings.CELERY_BEAT_SCHEDULE["weekly-offer-refresh"]

        self.assertEqual(entry["task"], "search.tasks.refresh_offers")
