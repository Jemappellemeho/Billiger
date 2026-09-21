"""Calls Billiger's own REST endpoints on behalf of an account, without a network hop.

The MCP tools are wrappers over the REST API: they go through the very same views (permissions,
validation, side effects) that the app and the built-in assistant use, never around them. The
request is authenticated as the token's account, so a tool can reach nothing that account's
own API session couldn't — and only the endpoints named in `mcp_server.tools` at all.
"""
import json
from dataclasses import dataclass
from typing import Any

from django.urls import resolve, reverse
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.utils.encoders import JSONEncoder


@dataclass
class RestResponse:
    status: int
    data: Any

    @property
    def ok(self):
        return 200 <= self.status < 300


def call_rest(user, method, url_name, *, params=None, body=None):
    """Runs `method` against the endpoint named `url_name`; `params` is the query string, `body` the JSON body."""
    path = reverse(url_name)
    match = resolve(path)
    factory = APIRequestFactory()
    if method == "GET":
        request = factory.get(path, {key: value for key, value in (params or {}).items() if value is not None})
    else:
        request = factory.generic(method, path, json.dumps(body or {}), content_type="application/json")
    force_authenticate(request, user=user)
    response = match.func(request, *match.args, **match.kwargs)
    # Through the JSON encoder the REST API itself uses, so what a tool returns is what the endpoint serves.
    return RestResponse(response.status_code, json.loads(json.dumps(response.data, cls=JSONEncoder)))
