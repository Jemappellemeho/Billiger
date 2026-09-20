from django.core.cache import cache
from rest_framework.test import APITestCase


class AccountsAPITestCase(APITestCase):
    """Clears the cache so the auth throttle counters don't leak between tests."""

    def setUp(self):
        super().setUp()
        cache.clear()
