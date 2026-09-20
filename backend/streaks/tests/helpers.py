from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from accounts.tests.helpers import auth, register
from search.tests.test_cart_comparison_view import _fake_session_get

STREAK_URL = "/api/streak/"
COMPARE_URL = "/api/compare/"

VIENNA = ZoneInfo("Europe/Vienna")

# Mondays in a row (Vienna calendar weeks start on Monday).
WEEK_1 = datetime(2026, 9, 7, 12, 0, tzinfo=VIENNA)
WEEK_2 = datetime(2026, 9, 14, 12, 0, tzinfo=VIENNA)
WEEK_3 = datetime(2026, 9, 21, 12, 0, tzinfo=VIENNA)
WEEK_4 = datetime(2026, 9, 28, 12, 0, tzinfo=VIENNA)
WEEK_5 = datetime(2026, 10, 5, 12, 0, tzinfo=VIENNA)

MILCH_AND_NUTELLA = [{"name": "Milch"}, {"name": "Nutella"}]


@contextmanager
def clock(moment):
    """Pins "now" for both the streak logic and model timestamps."""
    with patch("django.utils.timezone.now", return_value=moment):
        yield


def sign_up(client, email="anna@example.com"):
    return register(client, email=email).data["token"]


def compare(client, token=None, items=MILCH_AND_NUTELLA, moment=WEEK_1, marktguru=_fake_session_get):
    """Runs a cart comparison (Marktguru stubbed) at `moment`, optionally signed in."""
    extra = auth(token) if token else {}
    with clock(moment), patch("requests.Session.get", side_effect=marktguru):
        return client.post(
            COMPARE_URL, {"items": items, "zip_code": "1010"}, format="json", **extra
        )


def streak_summary(client, token, moment=WEEK_1):
    with clock(moment):
        return client.get(STREAK_URL, **auth(token))
