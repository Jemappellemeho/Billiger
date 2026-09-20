"""Warenkorb-Vergleich (Ticket 11): single-store total, full multi-store
per-product-minimum split, and the stepped "ladder" between them.

Ladder construction: rung 1 is the cheapest store that carries every item in
the list (a genuine one-stop trip, same number as `single_store`). Each
further rung greedily adds whichever additional store shrinks the running
total the most, by moving items to that store's price wherever it undercuts
the current assignment. Every rung only ever reassigns items to a *cheaper*
offer, so the total is monotonically non-increasing and the ladder converges
exactly onto the full per-product-minimum split once enough stores have been
added — it never disagrees with `full_split`. If no single store covers the
whole list, `single_store` is None and the ladder instead seeds from whatever
store minimizes the (partially-covered) running total, then expands the same
way; items not yet covered by any chosen store fall back to their own
cheapest offer, so the total stays defined at every rung.
"""
from difflib import SequenceMatcher

from search.matching import normalize_text


def select_matching_group(groups, name, brand):
    """Which matched offer group (see matching.group_offers) best represents
    a shopping-list item, preferring an exact/near brand match and otherwise
    falling back to name similarity."""
    if not groups:
        return None
    target_name = normalize_text(name)
    target_brand = normalize_text(brand) if brand else ""

    def score(group):
        name_score = SequenceMatcher(None, target_name, normalize_text(group.get("name"))).ratio()
        brand_score = 1 if target_brand and normalize_text(group.get("brand")) == target_brand else 0
        return (brand_score, name_score)

    return max(groups, key=score)


def compare_cart(items):
    """items: [{"name", "brand", "quantity", "offers": [{"advertiser","price","old_price"}]}]

    Items with no offers at all are reported separately as `unavailable_items`
    and excluded from every total below (there is nowhere to buy them right now).
    """
    available = [item for item in items if item["offers"]]
    unavailable = [item["name"] for item in items if not item["offers"]]

    all_advertisers = sorted({offer["advertiser"] for item in available for offer in item["offers"]})

    store_totals = [_store_total(item_list=available, advertiser=advertiser) for advertiser in all_advertisers]
    full_coverage = [s for s in store_totals if s["covers_all_items"]]
    cheapest_store = min(full_coverage, key=lambda s: s["total"]) if full_coverage else None

    single_store = None
    if cheapest_store is not None:
        single_store = {
            "advertiser": cheapest_store["advertiser"],
            "total": cheapest_store["total"],
            "items": _assignment_lines(available, {cheapest_store["advertiser"]}),
        }

    full_split_assignment = _assignment_lines(available, set(all_advertisers))
    full_split_total = round(sum(line["price"] for line in full_split_assignment), 2)

    ladder = _build_ladder(available, all_advertisers, single_store)

    return {
        "unavailable_items": unavailable,
        "store_totals": store_totals,
        "single_store": single_store,
        "full_split": {"total": full_split_total, "assignment": full_split_assignment},
        "ladder": ladder,
    }


def _store_total(item_list, advertiser):
    missing = [
        item["name"] for item in item_list if not any(o["advertiser"] == advertiser for o in item["offers"])
    ]
    if missing:
        return {"advertiser": advertiser, "covers_all_items": False, "total": None, "missing_items": missing}

    total = sum(
        min(o["price"] for o in item["offers"] if o["advertiser"] == advertiser) * item["quantity"]
        for item in item_list
    )
    return {"advertiser": advertiser, "covers_all_items": True, "total": round(total, 2), "missing_items": []}


def _pick_offer(item, chosen_advertisers):
    candidates = [o for o in item["offers"] if o["advertiser"] in chosen_advertisers]
    if candidates:
        return min(candidates, key=lambda o: o["price"])
    # Not (yet) covered by any chosen store on this rung — falls back to its
    # own cheapest offer so partial rungs still have a defined total.
    return min(item["offers"], key=lambda o: o["price"])


def _line(item, offer):
    line_price = round(offer["price"] * item["quantity"], 2)
    most_expensive = max(o["price"] for o in item["offers"]) * item["quantity"]
    old_price = offer.get("old_price")
    return {
        "name": item["name"],
        "brand": item["brand"],
        "quantity": item["quantity"],
        "advertiser": offer["advertiser"],
        "price": line_price,
        "savings_vs_most_expensive": round(most_expensive - line_price, 2),
        "savings_vs_regular": round(old_price * item["quantity"] - line_price, 2) if old_price is not None else None,
    }


def _assignment_lines(available, chosen_advertisers):
    return [_line(item, _pick_offer(item, chosen_advertisers)) for item in available]


def _assignment_total(available, chosen_advertisers):
    return round(sum(line["price"] for line in _assignment_lines(available, chosen_advertisers)), 2)


def _build_ladder(available, all_advertisers, single_store):
    if not available or not all_advertisers:
        return []

    if single_store is not None:
        chosen = [single_store["advertiser"]]
    else:
        chosen = [min(all_advertisers, key=lambda a: _assignment_total(available, {a}))]

    total = _assignment_total(available, set(chosen))
    rungs = [
        {
            "stops": 1,
            "stores": list(chosen),
            "total": total,
            "marginal_savings": 0.0,
            "assignment": _assignment_lines(available, set(chosen)),
        }
    ]

    remaining = [a for a in all_advertisers if a not in chosen]
    prev_total = total
    while remaining:
        best_candidate, best_total = None, prev_total
        for candidate in remaining:
            trial_total = _assignment_total(available, set(chosen) | {candidate})
            if trial_total < best_total - 1e-9:
                best_total, best_candidate = trial_total, candidate
        if best_candidate is None:
            break

        chosen.append(best_candidate)
        remaining.remove(best_candidate)
        marginal_savings = round(prev_total - best_total, 2)
        rungs.append(
            {
                "stops": len(chosen),
                "stores": list(chosen),
                "total": best_total,
                "marginal_savings": marginal_savings,
                "assignment": _assignment_lines(available, set(chosen)),
            }
        )
        prev_total = best_total

    return rungs
