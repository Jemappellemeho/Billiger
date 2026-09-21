"""The proposal lifecycle (Ticket 15): the assistant proposes, the user decides.

    create  — what a chat turn's `propose_*` tool does: store a pending proposal with its full diff
    revise  — the user's "Ändern": replace the proposed state, get a fresh diff
    accept  — the user's "Übernehmen": the only place anything is applied
    reject  — the user's "Verwerfen"

`create` and `revise` never touch the account's data; `accept` refuses proposals that
were already decided or whose base state has moved on since.

An account holds at most `MAX_PENDING` open proposals (Ticket 19): whatever channel makes a new
one, the oldest open ones beyond that go `stale`, so the list in the app can't grow without bound.
"""
from django.db import transaction
from django.utils import timezone

from accounts import shopping_list
from assistant.changes import CHANGES, ProposalInvalid
from assistant.models import Proposal

MAX_PENDING = 20

REJECTED_MESSAGE = "Verworfen — keine Änderung vorgenommen."
NOTHING_TO_CHANGE = "Der Vorschlag entspricht dem aktuellen Stand — es gibt nichts zu ändern."


class ProposalNotPending(Exception):
    """The proposal was already decided (or went stale)."""


class ProposalStale(Exception):
    """What the proposal was made for has changed since; accepting it would overwrite newer changes."""


def _diff_against(change, base, proposed):
    diff = change.diff(base, proposed)
    if change.is_empty(diff):
        raise ProposalInvalid(NOTHING_TO_CHANGE)
    return diff


def create(user, kind, data, current_zip_code):
    """`current_zip_code()` is the caller's location (for the "before" of a location change); it may raise."""
    change = CHANGES[kind]
    proposed = change.parse(data, user)
    base = change.snapshot(user, current_zip_code)
    diff = _diff_against(change, base, proposed)
    with transaction.atomic():
        proposal = Proposal.objects.create(user=user, kind=kind, base=base, proposed=proposed, diff=diff)
        _retire_beyond_limit(user)
    return proposal


def _retire_beyond_limit(user):
    """Marks the account's oldest open proposals `stale` once it holds more than `MAX_PENDING`."""
    # Locked so a concurrent accept/reject can't decide one of them while it is being retired.
    open_proposals = Proposal.objects.select_for_update().filter(user=user, status=Proposal.Status.PENDING)
    overflow = list(open_proposals.order_by("-created_at", "-pk").values_list("pk", flat=True))[MAX_PENDING:]
    if overflow:
        Proposal.objects.filter(pk__in=overflow).update(status=Proposal.Status.STALE, decided_at=timezone.now())


def revise(proposal, data):
    """Replaces the proposed state with the user's edit; the diff is recomputed against the current state."""
    with transaction.atomic():
        # Locked so a concurrent accept/reject can't decide the proposal while it is being rewritten.
        proposal = Proposal.objects.select_for_update().get(pk=proposal.pk)
        _require_pending(proposal)
        change = CHANGES[proposal.kind]
        proposed = change.parse(data, proposal.user)
        # A location's "before" is the client's, not the server's: keep the one the proposal was made with.
        base = change.snapshot(proposal.user, lambda: proposal.base["zip_code"])
        proposal.base, proposal.proposed = base, proposed
        proposal.diff = _diff_against(change, base, proposed)
        proposal.save(update_fields=["base", "proposed", "diff"])
        return proposal


def accept(proposal):
    """Applies the proposal; returns what changed (e.g. the new list) plus the confirmation message."""
    with transaction.atomic():
        proposal = Proposal.objects.select_for_update().get(pk=proposal.pk)
        _require_pending(proposal)
        change = CHANGES[proposal.kind]
        shopping_list.lock(proposal.user)  # a concurrent list save can't slip between check and apply
        if not change.is_stale(proposal.user, proposal.base):
            result = change.apply(proposal.user, proposal.proposed)
            _decide(proposal, Proposal.Status.ACCEPTED)
            return proposal, {**result, "message": change.accepted_message(proposal.proposed)}
        _decide(proposal, Proposal.Status.STALE)
    raise ProposalStale()  # after the commit, so the stale mark stays


@transaction.atomic
def reject(proposal):
    proposal = Proposal.objects.select_for_update().get(pk=proposal.pk)
    _require_pending(proposal)
    _decide(proposal, Proposal.Status.REJECTED)
    return proposal, {"message": REJECTED_MESSAGE}


def _require_pending(proposal):
    if proposal.status != Proposal.Status.PENDING:
        raise ProposalNotPending()


def _decide(proposal, status):
    proposal.status = status
    proposal.decided_at = timezone.now()
    proposal.save(update_fields=["status", "decided_at"])


def serialize(proposal):
    return {
        "id": proposal.pk,
        "kind": proposal.kind,
        "status": proposal.status,
        "diff": proposal.diff,
        "proposed": proposal.proposed,
    }
