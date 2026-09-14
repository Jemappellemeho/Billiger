from unittest import TestCase
from unittest.mock import Mock

from search.location import InvalidLocation, LocationResolver

NOMINATIM_RESPONSE = {
    "address": {
        "postcode": "1010",
        "city": "Wien",
        "country": "Österreich",
    }
}


def _make_response(json_body):
    resp = Mock()
    resp.raise_for_status.side_effect = lambda: None
    resp.json.return_value = json_body
    return resp


class LocationResolverZipCodeTests(TestCase):
    def test_explicit_zip_code_is_returned_as_is(self):
        resolver = LocationResolver(session=Mock())

        zip_code = resolver.resolve(zip_code="1010")

        self.assertEqual(zip_code, "1010")

    def test_malformed_zip_code_is_rejected(self):
        resolver = LocationResolver(session=Mock())

        with self.assertRaises(InvalidLocation):
            resolver.resolve(zip_code="abc")

    def test_zip_code_takes_precedence_over_gps_when_both_given(self):
        session = Mock()
        resolver = LocationResolver(session=session)

        zip_code = resolver.resolve(zip_code="1010", lat=48.2, lon=16.3)

        self.assertEqual(zip_code, "1010")
        session.get.assert_not_called()


class LocationResolverGPSTests(TestCase):
    def test_gps_coordinates_are_reverse_geocoded_to_a_zip_code(self):
        session = Mock()
        session.get.return_value = _make_response(NOMINATIM_RESPONSE)
        resolver = LocationResolver(session=session)

        zip_code = resolver.resolve(lat=48.2082, lon=16.3738)

        self.assertEqual(zip_code, "1010")
        called_url = session.get.call_args.args[0]
        self.assertEqual(called_url, LocationResolver.REVERSE_GEOCODE_URL)
        called_params = session.get.call_args.kwargs["params"]
        self.assertEqual(called_params["lat"], 48.2082)
        self.assertEqual(called_params["lon"], 16.3738)

    def test_sends_identifying_user_agent_per_nominatim_usage_policy(self):
        session = Mock()
        session.get.return_value = _make_response(NOMINATIM_RESPONSE)
        resolver = LocationResolver(session=session)

        resolver.resolve(lat=48.2082, lon=16.3738)

        headers = session.get.call_args.kwargs["headers"]
        self.assertIn("User-Agent", headers)

    def test_missing_postcode_in_geocoder_response_raises(self):
        session = Mock()
        session.get.return_value = _make_response({"address": {"city": "Wien"}})
        resolver = LocationResolver(session=session)

        with self.assertRaises(InvalidLocation):
            resolver.resolve(lat=48.2082, lon=16.3738)

    def test_no_location_information_at_all_raises(self):
        resolver = LocationResolver(session=Mock())

        with self.assertRaises(InvalidLocation):
            resolver.resolve()
