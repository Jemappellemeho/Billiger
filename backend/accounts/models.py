from django.conf import settings
from django.db import models


class ShoppingList(models.Model):
    """One account's shopping list + preferences, stored as a validated document.

    The document shape is defined by accounts.serializers.ShoppingListSerializer
    (the same shape the frontend keeps in guest mode). One document per account
    keeps the "replace on sync" and "merge on first login" operations atomic.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shopping_list"
    )
    data = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"ShoppingList({self.user_id})"
