from django.core.management.base import BaseCommand

from mcp_server.clients import ensure_clients


class Command(BaseCommand):
    help = "Creates or updates the pre-registered OAuth clients (Claude, and ChatGPT once its redirect URI is set)."

    def handle(self, *args, **options):
        for client_id in ensure_clients():
            self.stdout.write(f"OAuth client ready: {client_id}")
