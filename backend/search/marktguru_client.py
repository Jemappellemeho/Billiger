"""Client for the unofficial Marktguru AT offers API.

Marktguru does not publish this API; there is no API-key signup flow.
The web frontend at marktguru.at embeds a short-lived apiKey/clientKey
pair in a JSON <script> blob on the homepage, which is how every known
open-source client (see .scratch/billiger/research/01-marktguru-api-produktdaten.md)
authenticates. We scrape that blob once per process and cache it, with
an explicit override for callers (e.g. Django settings) who already
know a working key pair.
"""
import json
import re
from html.parser import HTMLParser

import requests
from django.conf import settings


class CredentialsUnavailable(Exception):
    """Raised when apiKey/clientKey could not be found on the homepage."""


class _JSONScriptExtractor(HTMLParser):
    """Collects the text content of every <script type="application/json"> tag."""

    def __init__(self):
        super().__init__()
        self._in_json_script = False
        self.blobs = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script" and dict(attrs).get("type") == "application/json":
            self._in_json_script = True

    def handle_endtag(self, tag):
        if tag.lower() == "script":
            self._in_json_script = False

    def handle_data(self, data):
        if self._in_json_script:
            self.blobs.append(data)


def _find_key(obj, *names):
    """Recursively search a parsed JSON structure for the first of `names`."""
    lowered = {name.lower() for name in names}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in lowered and isinstance(value, str):
                return value
        for value in obj.values():
            found = _find_key(value, *names)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_key(item, *names)
            if found is not None:
                return found
    return None


class MarktguruClient:
    HOMEPAGE_URL = "https://www.marktguru.at"
    API_URL = "https://api.marktguru.at/api/v1/offers/search"

    def __init__(self, session=None, api_key=None, client_key=None, timeout=10):
        self.session = session or requests.Session()
        self.timeout = timeout
        self._api_key = api_key
        self._client_key = client_key

    def search(self, query, zip_code, limit=30, offset=0):
        """Return the raw `results` list from the Marktguru offers search API."""
        api_key, client_key = self._get_credentials()
        response = self.session.get(
            self.API_URL,
            params={
                "as": "web",
                "q": query,
                "zipCode": zip_code,
                "limit": limit,
                "offset": offset,
            },
            headers={
                "x-apikey": api_key,
                "x-clientkey": client_key,
                "Accept": "application/json",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def _get_credentials(self):
        if self._api_key and self._client_key:
            return self._api_key, self._client_key

        api_key, client_key = self._scrape_credentials()
        self._api_key, self._client_key = api_key, client_key
        return api_key, client_key

    def _scrape_credentials(self):
        response = self.session.get(self.HOMEPAGE_URL, timeout=self.timeout)
        response.raise_for_status()

        extractor = _JSONScriptExtractor()
        extractor.feed(response.text)

        for blob in extractor.blobs:
            try:
                parsed = json.loads(blob)
            except json.JSONDecodeError:
                continue
            api_key = _find_key(parsed, "apiKey")
            client_key = _find_key(parsed, "clientKey")
            if api_key and client_key:
                return api_key, client_key

        raise CredentialsUnavailable(
            "Could not find apiKey/clientKey in the marktguru.at homepage — "
            "the site markup may have changed."
        )


def client_from_django_settings():
    return MarktguruClient(
        api_key=getattr(settings, "MARKTGURU_API_KEY", None),
        client_key=getattr(settings, "MARKTGURU_CLIENT_KEY", None),
    )
