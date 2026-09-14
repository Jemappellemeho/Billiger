from unittest.mock import Mock, patch

from rest_framework.test import APITestCase

from search.marktguru_client import MarktguruClient

HOMEPAGE_HTML = (
    '<script type="application/json">'
    '{"apiKey": "test-api-key", "clientKey": "test-client-key"}'
    "</script>"
)

NUTELLA_RESULTS = {
    "totalResults": 2,
    "results": [
        {
            "id": 1,
            "price": 5.59,
            "oldPrice": 6.99,
            "referencePrice": 7.45,
            "description": "750 g Glas",
            "product": {"id": 23457, "name": "Nutella", "description": None},
            "brand": {"id": 1, "name": "Nutella"},
            "categories": [],
            "advertisers": [{"id": 1, "name": "BILLA"}],
            "unit": {"id": 1, "name": "Kilogramm", "shortName": "kg"},
            "volume": 0.75,
            "quantity": None,
        },
        {
            "id": 2,
            "price": 4.99,
            "oldPrice": 5.99,
            "referencePrice": 7.45,
            "description": "750 g Glas",
            "product": {"id": 23457, "name": "Nutella", "description": None},
            "brand": {"id": 1, "name": "Nutella"},
            "categories": [],
            "advertisers": [{"id": 2, "name": "PENNY"}],
            "unit": {"id": 1, "name": "Kilogramm", "shortName": "kg"},
            "volume": 0.75,
            "quantity": None,
        },
    ],
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
        return _response(json_body=NUTELLA_RESULTS)
    if "nominatim" in url:
        return _response(json_body=NOMINATIM_RESPONSE)
    raise AssertionError(f"unexpected URL requested in test: {url}")


class ProductSearchEndpointTests(APITestCase):
    @patch("requests.Session.get", side_effect=_fake_session_get)
    def test_search_with_zip_code_returns_matched_products_with_cheapest_store(self, mock_get):
        response = self.client.get("/api/search/", {"q": "Nutella", "zip_code": "1010"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["zip_code"], "1010")
        self.assertEqual(len(body["results"]), 1)
        group = body["results"][0]
        self.assertEqual({o["advertiser"] for o in group["offers"]}, {"BILLA", "PENNY"})
        self.assertEqual(group["cheapest"]["advertiser"], "PENNY")
        self.assertEqual(group["cheapest"]["price"], 4.99)

    @patch("requests.Session.get", side_effect=_fake_session_get)
    def test_search_with_gps_coordinates_reverse_geocodes_then_searches(self, mock_get):
        response = self.client.get(
            "/api/search/", {"q": "Nutella", "lat": "48.2082", "lon": "16.3738"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["zip_code"], "1010")

    def test_missing_query_returns_400(self):
        response = self.client.get("/api/search/", {"zip_code": "1010"})

        self.assertEqual(response.status_code, 400)

    def test_missing_location_returns_400(self):
        response = self.client.get("/api/search/", {"q": "Nutella"})

        self.assertEqual(response.status_code, 400)

    def test_malformed_zip_code_returns_400(self):
        response = self.client.get("/api/search/", {"q": "Nutella", "zip_code": "notaplz"})

        self.assertEqual(response.status_code, 400)

    def test_non_numeric_gps_coordinates_return_400_not_a_crash(self):
        response = self.client.get(
            "/api/search/", {"q": "Nutella", "lat": "not-a-number", "lon": "also-not"}
        )

        self.assertEqual(response.status_code, 400)

    @patch("requests.Session.get", side_effect=ConnectionError("boom"))
    def test_marktguru_outage_returns_502_not_a_crash(self, mock_get):
        response = self.client.get("/api/search/", {"q": "Nutella", "zip_code": "1010"})

        self.assertEqual(response.status_code, 502)
