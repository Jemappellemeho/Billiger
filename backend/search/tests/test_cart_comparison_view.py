from unittest.mock import Mock, patch

from rest_framework.test import APITestCase

from search.marktguru_client import MarktguruClient

HOMEPAGE_HTML = (
    '<script type="application/json">'
    '{"apiKey": "test-api-key", "clientKey": "test-client-key"}'
    "</script>"
)


def _raw_offer(offer_id, product_id, name, brand, advertiser, price, old_price=None):
    return {
        "id": offer_id,
        "price": price,
        "oldPrice": old_price,
        "referencePrice": None,
        "description": None,
        "product": {"id": product_id, "name": name, "description": None},
        "brand": {"id": 1, "name": brand},
        "categories": [],
        "advertisers": [{"id": 1, "name": advertiser}],
        "unit": {"id": 1, "name": "Liter", "shortName": "l"},
        "volume": 1.0,
        "quantity": None,
    }


MILCH_RESULTS = {
    "results": [
        _raw_offer(1, 100, "Milch", "Ja! Natürlich", "HOFER", 1.09),
        _raw_offer(2, 100, "Milch", "Ja! Natürlich", "LIDL", 0.99),
    ]
}

NUTELLA_RESULTS = {
    "results": [
        _raw_offer(3, 200, "Nutella", "Nutella", "HOFER", 4.99, old_price=6.99),
        _raw_offer(4, 200, "Nutella", "Nutella", "LIDL", 5.29),
    ]
}

NOMINATIM_RESPONSE = {"address": {"postcode": "1010", "city": "Wien"}}


def _response(json_body=None, text=None):
    resp = Mock()
    resp.raise_for_status.side_effect = lambda: None
    if json_body is not None:
        resp.json.return_value = json_body
    if text is not None:
        resp.text = text
    return resp


def _fake_session_get(url, params=None, headers=None, timeout=None):
    if url == MarktguruClient.HOMEPAGE_URL:
        return _response(text=HOMEPAGE_HTML)
    if url == MarktguruClient.API_URL:
        query = (params or {}).get("q")
        if query == "Milch":
            return _response(json_body=MILCH_RESULTS)
        if query == "Nutella":
            return _response(json_body=NUTELLA_RESULTS)
        return _response(json_body={"results": []})
    if "nominatim" in url:
        return _response(json_body=NOMINATIM_RESPONSE)
    raise AssertionError(f"unexpected URL requested in test: {url}")


class CartComparisonEndpointTests(APITestCase):
    @patch("requests.Session.get", side_effect=_fake_session_get)
    def test_returns_single_store_full_split_and_ladder(self, mock_get):
        response = self.client.post(
            "/api/compare/",
            {"items": [{"name": "Milch"}, {"name": "Nutella"}], "zip_code": "1010"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["zip_code"], "1010")

        self.assertEqual(body["single_store"]["advertiser"], "HOFER")
        self.assertAlmostEqual(body["single_store"]["total"], 1.09 + 4.99)

        full_split_by_name = {line["name"]: line for line in body["full_split"]["assignment"]}
        self.assertEqual(full_split_by_name["Milch"]["advertiser"], "LIDL")
        self.assertEqual(full_split_by_name["Nutella"]["advertiser"], "HOFER")
        self.assertAlmostEqual(body["full_split"]["total"], 0.99 + 4.99)

        self.assertEqual(body["ladder"][0]["stops"], 1)
        self.assertEqual(body["ladder"][-1]["total"], body["full_split"]["total"])

        nutella_line = full_split_by_name["Nutella"]
        self.assertAlmostEqual(nutella_line["savings_vs_regular"], 6.99 - 4.99)
        self.assertAlmostEqual(nutella_line["savings_vs_most_expensive"], 5.29 - 4.99)

    @patch("requests.Session.get", side_effect=_fake_session_get)
    def test_quantity_is_applied_to_totals(self, mock_get):
        response = self.client.post(
            "/api/compare/",
            {"items": [{"name": "Milch", "quantity": 4}], "zip_code": "1010"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertAlmostEqual(body["single_store"]["total"], 0.99 * 4)

    @patch("requests.Session.get", side_effect=_fake_session_get)
    def test_item_with_no_offers_is_reported_as_unavailable(self, mock_get):
        response = self.client.post(
            "/api/compare/",
            {"items": [{"name": "Milch"}, {"name": "Einhornstaub"}], "zip_code": "1010"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["unavailable_items"], ["Einhornstaub"])

    def test_missing_items_returns_400(self):
        response = self.client.post("/api/compare/", {"zip_code": "1010"}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_empty_items_list_returns_400(self):
        response = self.client.post("/api/compare/", {"items": [], "zip_code": "1010"}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_item_without_name_returns_400(self):
        response = self.client.post(
            "/api/compare/", {"items": [{"name": ""}], "zip_code": "1010"}, format="json"
        )

        self.assertEqual(response.status_code, 400)

    def test_non_positive_quantity_returns_400(self):
        response = self.client.post(
            "/api/compare/",
            {"items": [{"name": "Milch", "quantity": 0}], "zip_code": "1010"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_missing_location_returns_400(self):
        response = self.client.post("/api/compare/", {"items": [{"name": "Milch"}]}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_malformed_zip_code_returns_400(self):
        response = self.client.post(
            "/api/compare/",
            {"items": [{"name": "Milch"}], "zip_code": "notaplz"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    @patch("requests.Session.get", side_effect=_fake_session_get)
    def test_gps_coordinates_reverse_geocode_then_compare(self, mock_get):
        response = self.client.post(
            "/api/compare/",
            {"items": [{"name": "Milch"}], "lat": "48.2082", "lon": "16.3738"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["zip_code"], "1010")

    @patch("requests.Session.get", side_effect=ConnectionError("boom"))
    def test_marktguru_outage_returns_502_not_a_crash(self, mock_get):
        response = self.client.post(
            "/api/compare/",
            {"items": [{"name": "Milch"}], "zip_code": "1010"},
            format="json",
        )

        self.assertEqual(response.status_code, 502)
