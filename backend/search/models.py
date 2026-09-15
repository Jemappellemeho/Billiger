from django.db import models


class AnchorOfferSnapshot(models.Model):
    """Last successfully refreshed offer group for one anchor product.

    Populated by the weekly refresh task (search.tasks.refresh_offers). A
    failed refresh for an anchor simply skips writing here, so this row keeps
    the last known-good data usable instead of being wiped on a Marktguru
    outage.
    """

    anchor_id = models.CharField(max_length=100, unique=True)
    data = models.JSONField()
    refreshed_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.anchor_id
