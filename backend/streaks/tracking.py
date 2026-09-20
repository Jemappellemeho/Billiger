"""Streak & savings tracking (Ticket 13).

A *completed cart comparison* is one successful run of `POST /api/compare/` by
a signed-in account (see `record_comparison`, called from the comparison view).
Its savings are those of the full multi-store split — the best plan the
comparison found — measured against both the most expensive offer and the
regular (non-sale) price, exactly like the comparison response itself.

Weeks are Monday-to-Sunday in `settings.TIME_ZONE` (Vienna). Each account
keeps one comparison per week (the latest one wins; see `WeeklyComparison`).

The streak is the number of weeks with a completed comparison. A missed week
*pauses* the streak instead of resetting it: the value stays where it was, the
status reports `paused`, and the next completed comparison simply continues
the count.

    none    no comparison completed yet
    active  this week's comparison is done
    pending last week's is done, this week's is still open (streak is safe)
    paused  at least one whole week went by without a comparison
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from streaks.models import WeeklyComparison

CENTS = Decimal("0.01")


def week_start(moment=None):
    """The Monday (a `date`) of the week `moment` falls into, in local time."""
    local_date = timezone.localtime(moment or timezone.now()).date()
    return local_date - timedelta(days=local_date.weekday())


def record_comparison(user, comparison):
    """Counts `comparison` (the result of search.comparison.compare_cart) as this
    week's completed comparison for `user`. Comparisons without any purchasable
    item have nothing to compare and are not recorded."""
    lines = comparison["full_split"]["assignment"]
    if not lines:
        return None

    items = [_item_entry(line) for line in lines]
    row, _ = WeeklyComparison.objects.update_or_create(
        user=user,
        week_start=week_start(),
        defaults={
            "savings_vs_most_expensive": _euros(sum(i["savings_vs_most_expensive"] for i in items)),
            "savings_vs_regular": _euros(sum(i["savings_vs_regular"] for i in items)),
            "items": items,
        },
    )
    return row


def summary(user):
    """Everything the home hero, the assistant and the history need, in one document."""
    current_week = week_start()
    rows = list(WeeklyComparison.objects.filter(user=user).order_by("week_start"))
    by_week = {row.week_start: row for row in rows}

    return {
        "current_week": current_week.isoformat(),
        "streak": _streak(rows, current_week),
        "this_week": _week_detail(by_week[current_week]) if current_week in by_week else None,
        "total_savings": {
            "vs_most_expensive": float(sum((r.savings_vs_most_expensive for r in rows), Decimal(0))),
            "vs_regular": float(sum((r.savings_vs_regular for r in rows), Decimal(0))),
        },
        "history": _history(rows, by_week, current_week),
    }


def _streak(rows, current_week):
    if not rows:
        return {"weeks": 0, "status": "none", "missed_weeks": 0, "last_completed_week": None}

    last_week = rows[-1].week_start
    weeks_since = (current_week - last_week).days // 7
    if weeks_since <= 0:
        status = "active"
    elif weeks_since == 1:
        status = "pending"
    else:
        status = "paused"
    return {
        "weeks": len(rows),
        "status": status,
        "missed_weeks": max(weeks_since - 1, 0),
        "last_completed_week": last_week.isoformat(),
    }


def _history(rows, by_week, current_week):
    """Every week from the first completed comparison up to now, gaps included."""
    if not rows:
        return []
    history, week = [], rows[0].week_start
    while week <= current_week:
        row = by_week.get(week)
        history.append({"week_start": week.isoformat(), "completed": row is not None, **_week_detail(row)})
        week += timedelta(weeks=1)
    return history


def _week_detail(row):
    """Savings plus what contributed to them, largest contribution first."""
    if row is None:
        return {"savings_vs_most_expensive": 0, "savings_vs_regular": 0, "stores": [], "items": []}

    per_store = defaultdict(float)
    for item in row.items:
        per_store[item["advertiser"]] += item["savings_vs_most_expensive"]
    stores = [
        {"advertiser": advertiser, "savings_vs_most_expensive": round(savings, 2)}
        for advertiser, savings in per_store.items()
        if savings > 0
    ]
    items = [i for i in row.items if i["savings_vs_most_expensive"] > 0]
    return {
        "savings_vs_most_expensive": float(row.savings_vs_most_expensive),
        "savings_vs_regular": float(row.savings_vs_regular),
        "stores": sorted(stores, key=lambda s: -s["savings_vs_most_expensive"]),
        "items": sorted(items, key=lambda i: -i["savings_vs_most_expensive"]),
    }


def _item_entry(line):
    regular = max(line["savings_vs_regular"] or 0, 0)
    return {
        "name": line["name"],
        "brand": line["brand"],
        "advertiser": line["advertiser"],
        "savings_vs_most_expensive": max(line["savings_vs_most_expensive"], 0),
        "savings_vs_regular": regular,
        "on_sale": regular > 0,
    }


def _euros(amount):
    return Decimal(str(round(amount, 2))).quantize(CENTS)
