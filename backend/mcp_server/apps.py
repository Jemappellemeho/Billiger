from django.apps import AppConfig
from django.db.models.signals import post_migrate


class McpServerConfig(AppConfig):
    name = "mcp_server"

    def ready(self):
        from mcp_server.clients import ensure_clients

        # The clients are configuration, not user data: every migrate leaves them in place.
        post_migrate.connect(ensure_clients, sender=self, dispatch_uid="mcp_server.ensure_clients")
