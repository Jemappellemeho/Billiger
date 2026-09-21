from django.conf import settings
from django.db import models


class Proposal(models.Model):
    """A change the assistant suggested and the user has yet to decide on (Ticket 15).

    The model can only create these (a chat turn stores one with its full
    diff, and so does an MCP client through the proposals endpoint, Ticket 16);
    applying happens solely through the user's "accept". `base` is
    what the diff was computed against, so a proposal made for a state that
    has since moved on is refused instead of overwriting newer changes.
    """

    class Kind(models.TextChoices):
        SHOPPING_LIST = "shopping_list"
        PREFERENCES = "preferences"
        LOCATION = "location"

    class Status(models.TextChoices):
        PENDING = "pending"
        ACCEPTED = "accepted"
        REJECTED = "rejected"
        # No longer decidable: the state it was made for changed first, or newer proposals pushed it
        # out of the account's `MAX_PENDING` open ones.
        STALE = "stale"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assistant_proposals"
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    base = models.JSONField(null=True)
    proposed = models.JSONField()
    diff = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True)

    def __str__(self):
        return f"Proposal({self.pk}, {self.kind}, {self.status})"
