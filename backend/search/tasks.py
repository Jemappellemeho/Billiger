"""Weekly refresh of Marktguru offer data (Ticket 09).

Re-runs the same fetch/normalization pipeline as the on-demand search
endpoint (Ticket 08) — MarktguruClient.search -> group_offers ->
apply_anchor_overrides — once per anchor product, so that anchor price data
does not stay permanently dependent on a user happening to search for it.

Marktguru is a reverse-engineered, unofficial API that can break without
warning (see .scratch/billiger/research/01-marktguru-api-produktdaten.md).
A failure fetching one anchor is logged and skipped rather than raised, so a
single broken anchor does not crash the whole run, and that anchor's last
successfully cached snapshot stays in place and usable.
"""
import logging

from celery import shared_task
from django.conf import settings

from search.anchor_products import ANCHOR_PRODUCTS, anchor_id_for_offer_group, apply_anchor_overrides
from search.marktguru_client import MarktguruClient
from search.matching import group_offers
from search.models import AnchorOfferSnapshot

logger = logging.getLogger(__name__)

# MVP scope is Wien — a single representative postcode is enough to refresh
# anchor products' current offers regardless of which user later looks them up.
VIENNA_ZIP_CODE = "1010"


@shared_task
def refresh_offers():
    client = _marktguru_client()
    refreshed = 0
    failed = 0

    for anchor in ANCHOR_PRODUCTS:
        query = anchor["name_aliases"][0]
        try:
            raw_offers = client.search(query, zip_code=VIENNA_ZIP_CODE)
            groups = apply_anchor_overrides(group_offers(raw_offers))
        except Exception:
            logger.exception("Weekly offer refresh failed for anchor '%s'", anchor["id"])
            failed += 1
            continue

        matched_group = next(
            (g for g in groups if anchor_id_for_offer_group(g) == anchor["id"]), None
        )
        if matched_group is None:
            continue

        AnchorOfferSnapshot.objects.update_or_create(
            anchor_id=anchor["id"], defaults={"data": matched_group}
        )
        refreshed += 1

    return {"refreshed": refreshed, "failed": failed}


def _marktguru_client():
    return MarktguruClient(
        api_key=getattr(settings, "MARKTGURU_API_KEY", None),
        client_key=getattr(settings, "MARKTGURU_CLIENT_KEY", None),
    )
