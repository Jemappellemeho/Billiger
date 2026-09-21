import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from oauth2_provider.models import get_access_token_model
from oauth2_provider.settings import oauth2_settings


class Command(BaseCommand):
    help = (
        "Prints an MCP access token for an account, to try the MCP server by hand during development "
        "(a Personal Access Token in effect). Not an end-user flow: it is a command, not an endpoint, and "
        "refuses to run unless MCP_ALLOW_DEV_TOKENS=1."
    )

    def add_arguments(self, parser):
        parser.add_argument("email", help="The account the token acts as.")
        parser.add_argument(
            "--scope",
            default=" ".join(oauth2_settings.SCOPES),
            help="Space-separated scopes (default: all).",
        )
        parser.add_argument("--hours", type=int, default=8, help="Lifetime in hours (default: 8).")

    def handle(self, *args, email, scope, hours, **options):
        if not settings.MCP_ALLOW_DEV_TOKENS:
            raise CommandError("Developer tokens are only issued when MCP_ALLOW_DEV_TOKENS=1 is set.")

        unknown = set(scope.split()) - set(oauth2_settings.SCOPES)
        if unknown:
            raise CommandError(f"Unknown scope(s): {' '.join(sorted(unknown))}")
        user = get_user_model().objects.filter(username=email.strip().lower()).first()
        if user is None:
            raise CommandError(f"No account with the email {email}.")

        # An ordinary OAuth access token (same audience, same validation, same expiry) — just not
        # obtained through the authorization flow, so no client is attached.
        token = get_access_token_model().objects.create(
            user=user,
            token=secrets.token_urlsafe(32),
            scope=scope,
            expires=timezone.now() + timedelta(hours=hours),
            resource=[settings.MCP_RESOURCE_URL],
        )
        self.stdout.write(token.token)
