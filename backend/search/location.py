"""Resolves a Marktguru-compatible zip code from either an explicit PLZ or GPS coordinates.

Marktguru's search API only accepts a `zipCode`, not raw coordinates. The
map decision is "GPS automatic, PLZ manual fallback" — a browser only gives
us lat/lon, so GPS requests are reverse-geocoded to a postcode via the free
OpenStreetMap Nominatim API before ever reaching the Marktguru client.
"""
import re

import requests

_AT_ZIP_CODE_RE = re.compile(r"^\d{4}$")


class InvalidLocation(Exception):
    pass


class LocationResolver:
    REVERSE_GEOCODE_URL = "https://nominatim.openstreetmap.org/reverse"

    def __init__(self, session=None, timeout=10, user_agent="Billiger/0.1 (billiger app)"):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.user_agent = user_agent

    def resolve(self, zip_code=None, lat=None, lon=None):
        if zip_code is not None:
            return self._validate_zip_code(zip_code)
        if lat is not None and lon is not None:
            return self._reverse_geocode(lat, lon)
        raise InvalidLocation("Either zip_code or lat/lon must be provided.")

    def _validate_zip_code(self, zip_code):
        zip_code = str(zip_code).strip()
        if not _AT_ZIP_CODE_RE.match(zip_code):
            raise InvalidLocation(f"'{zip_code}' is not a valid 4-digit Austrian PLZ.")
        return zip_code

    def _reverse_geocode(self, lat, lon):
        response = self.session.get(
            self.REVERSE_GEOCODE_URL,
            params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1},
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
        )
        response.raise_for_status()
        postcode = response.json().get("address", {}).get("postcode")
        if not postcode:
            raise InvalidLocation("Reverse geocoding returned no postcode for this location.")
        return self._validate_zip_code(postcode)
