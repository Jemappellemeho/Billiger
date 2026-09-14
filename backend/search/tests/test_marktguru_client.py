import json
from unittest import TestCase
from unittest.mock import Mock

from search.marktguru_client import MarktguruClient

HOMEPAGE_HTML = """
<html><body>
<script type="application/json">{"config": {"apiKey": "test-api-key", "clientKey": "test-client-key"}}</script>
</body></html>
"""

SEARCH_RESPONSE = {
    "totalResults": 2,
    "results": [
        {
            "id": 3388876,
            "price": 5.59,
            "oldPrice": 6.99,
            "referencePrice": 7.45,
            "description": "750 g Glas",
            "product": {"id": 23457, "name": "Nutella", "description": None},
            "brand": {"id": 1, "name": "Nutella"},
            "categories": [{"id": 10, "name": "Schokoaufstrich"}],
            "advertisers": [{"id": 5, "name": "BILLA"}],
            "unit": {"id": 1, "name": "Kilogramm", "shortName": "kg"},
            "volume": 0.75,
            "quantity": None,
        },
        {
            "id": 3384937,
            "price": 4.99,
            "oldPrice": 5.99,
            "referencePrice": 7.45,
            "description": "750 g Glas",
            "product": {"id": 23457, "name": "Nutella", "description": None},
            "brand": {"id": 1, "name": "Nutella"},
            "categories": [{"id": 10, "name": "Schokoaufstrich"}],
            "advertisers": [{"id": 6, "name": "PENNY"}],
            "unit": {"id": 1, "name": "Kilogramm", "shortName": "kg"},
            "volume": 0.75,
            "quantity": None,
        },
    ],
}


def _make_response(status_code=200, text=None, json_body=None):
    resp = Mock()
    resp.status_code = status_code
    if text is not None:
        resp.text = text
    if json_body is not None:
        resp.json.return_value = json_body

    def raise_for_status():
        if status_code >= 400:
            raise Exception(f"HTTP {status_code}")

    resp.raise_for_status.side_effect = raise_for_status
    return resp


class MarktguruClientSearchTests(TestCase):
    def _client_with_session(self):
        session = Mock()

        def get(url, params=None, headers=None, timeout=None):
            if url == MarktguruClient.HOMEPAGE_URL:
                return _make_response(text=HOMEPAGE_HTML)
            if url == MarktguruClient.API_URL:
                self.captured_params = params
                self.captured_headers = headers
                return _make_response(json_body=SEARCH_RESPONSE)
            raise AssertionError(f"unexpected URL requested: {url}")

        session.get.side_effect = get
        return MarktguruClient(session=session)

    def test_search_returns_raw_offers_from_api(self):
        client = self._client_with_session()

        offers = client.search("Nutella", zip_code="1010")

        self.assertEqual(len(offers), 2)
        self.assertEqual(offers[0]["advertisers"][0]["name"], "BILLA")
        self.assertEqual(offers[1]["advertisers"][0]["name"], "PENNY")

    def test_search_sends_query_and_zip_code_as_params(self):
        client = self._client_with_session()

        client.search("Nutella", zip_code="1010")

        self.assertEqual(self.captured_params["q"], "Nutella")
        self.assertEqual(self.captured_params["zipCode"], "1010")
        self.assertEqual(self.captured_params["as"], "web")

    def test_search_authenticates_using_credentials_scraped_from_homepage(self):
        client = self._client_with_session()

        client.search("Nutella", zip_code="1010")

        self.assertEqual(self.captured_headers["x-apikey"], "test-api-key")
        self.assertEqual(self.captured_headers["x-clientkey"], "test-client-key")

    def test_search_reuses_cached_credentials_across_calls(self):
        client = self._client_with_session()

        client.search("Nutella", zip_code="1010")
        client.search("Red Bull", zip_code="1010")

        homepage_calls = [
            call
            for call in client.session.get.call_args_list
            if call.args[0] == MarktguruClient.HOMEPAGE_URL
        ]
        self.assertEqual(len(homepage_calls), 1)

    def test_credentials_can_be_overridden_via_constructor_without_scraping(self):
        session = Mock()

        def get(url, params=None, headers=None, timeout=None):
            if url == MarktguruClient.API_URL:
                self.captured_headers = headers
                return _make_response(json_body=SEARCH_RESPONSE)
            raise AssertionError("homepage should not be scraped when credentials are given")

        session.get.side_effect = get
        client = MarktguruClient(
            session=session, api_key="fixed-api-key", client_key="fixed-client-key"
        )

        client.search("Nutella", zip_code="1010")

        self.assertEqual(self.captured_headers["x-apikey"], "fixed-api-key")
        self.assertEqual(self.captured_headers["x-clientkey"], "fixed-client-key")
