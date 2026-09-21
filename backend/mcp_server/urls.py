from django.urls import include, path
from oauth2_provider import views as oauth2_views
from oauth2_provider.urls import metadata_urlpatterns

from mcp_server.login import ConsentLoginView
from mcp_server.views import McpView

# Only what the authorization-code flow needs. django-oauth-toolkit's own URLconf also ships
# application/token management screens (any signed-in user could register OAuth clients there),
# dynamic client registration and the device flow: none of that is exposed.
authorization_server = [
    *metadata_urlpatterns,
    path("oauth/authorize/", oauth2_views.AuthorizationView.as_view(), name="authorize"),
    path("oauth/token/", oauth2_views.TokenView.as_view(), name="token"),
    path("oauth/revoke_token/", oauth2_views.RevokeTokenView.as_view(), name="revoke-token"),
]

urlpatterns = [
    path("", include((authorization_server, "oauth2_provider"))),
    path("accounts/login/", ConsentLoginView.as_view(), name="oauth-login"),
    path("mcp/", McpView.as_view(), name="mcp"),
]
