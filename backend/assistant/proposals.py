"""The proposal lifecycle (Ticket 15): the assistant proposes, the user decides.

    create  — what a chat turn's `propose_*` tool does: store a pending proposal with its full diff
    revise  — the user's "Ändern": replace the proposed state, get a fresh diff
    accept  — the user's "Übernehmen": the only place anything is applied
    reject  — the user's "Verwerfen"

`create` and `revise` never touch the account's data; `accept` refuses proposals that
were already decided or whose base state has moved on since.
"""
from django.db import transaction
from django.utils import timezone

from assistant.changes import CHANGES, ProposalInvalid
from assistant.models import Proposal

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
    return Proposal.objects.create(
        user=user, kind=kind, base=base, proposed=proposed, diff=_diff_against(change, base, proposed)
    )


def revise(proposal, data):
    """Replaces the proposed state with the user's edit; the diff is recomputed against the current state."""
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
