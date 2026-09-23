"""Combine displayed references without changing any strategy or chain filter."""
from __future__ import annotations
import math


def build_strategy_summary(assessment, movement, forecast, checkpoint_price=None,
                           golden_review=None, end_of_day=False):
    rows = []

    def add(strategy, expiry="0DTE", call=None, put=None, status="", basis=""):
        # A previous strategy checkpoint can be overtaken by later prices.
        # Do not present its now-ATM/ITM reference as a new OTM entry.
        notes = []
        original_reference = call is not None or put is not None
        if checkpoint_price is not None:
            if call is not None and call <= checkpoint_price:
                call = None
                notes.append("Call reference is no longer OTM at the analysis price")
            if put is not None and put >= checkpoint_price:
                put = None
                notes.append("Put reference is no longer OTM at the analysis price")
        if original_reference and call is None and put is None:
            status = "NO OTM REFERENCE — " + status
        if end_of_day:
            status = "OUTCOME REVIEW / EARLIER REFERENCE — " + status
        rows.append({"strategy": strategy, "expiry": expiry, "call_strike": call,
                     "put_strike": put, "status": status,
                     "basis": "; ".join([basis, *notes]).strip("; ")})

    if forecast.get("available"):
        for level in ("90", "95"):
            band = forecast["ranges"][level]
            evidence = band["coverage"]
            add("Daily Price Boundary Strategy", call=band["call_strike"], put=band["put_strike"],
                status=forecast["status"],
                basis=f"{level}% target; both boundaries held {evidence['both_count']}/{evidence['days']} ({evidence['both_rate']:.1%}). Regular session only.")
    else:
        add("Daily Price Boundary Strategy", status=forecast.get("status", "UNAVAILABLE"), basis=forecast.get("reason", ""))

    signals = movement.get("primary_results", {})
    if signals:
        for item in signals.values():
            add("Market Movement Strategy", call=float(math.ceil(item["upper_boundary"])),
                put=float(math.floor(item["lower_boundary"])), status=movement["signal_status"],
                basis=f"{item['target_label']}; {item['rule_id']}")
    else:
        add("Market Movement Strategy", status=movement.get("signal_status", "UNAVAILABLE"), basis=movement.get("reason", ""))

    if assessment is None:
        reason = "Not active before 11:00 AM." if golden_review is None else f"The {golden_review} strategy checkpoint lacks required data."
        for name, expiry in (("Directional Distance", "0DTE"), ("Foundational Golden Filter Call", "0DTE"),
                             ("Foundational Golden Filter Put", "0DTE"), ("1DTE Strategy Call", "1DTE"),
                             ("1DTE Strategy Put", "1DTE"), ("Rare Golden Fingerprint", "1DTE")):
            add(name, expiry=expiry, status="NOT ACTIVE", basis=reason)
        return rows

    directional = assessment.get("directional_distance", {})
    if directional.get("candidates"):
        for item in directional["candidates"]:
            side = "call" if directional.get("option_side") == "CALL" else "put"
            add("Directional Distance", **{side: item["short_strike"]},
                status=directional["result"], basis=f"{item['label']}; {item['risk_level']}; original 11:00 reference")
    else:
        add("Directional Distance", status=directional.get("result", "UNAVAILABLE"), basis=directional.get("reason", ""))

    # Retain the existing closest-qualifying foundational selections exactly.
    original = assessment.get("combined", {}).get("rows", [])
    for i, side in enumerate(("call", "put")):
        item = original[i] if len(original) > i else {}
        add(f"Foundational Golden Filter {side.title()}", **{side: item.get("strike")},
            status=item.get("result", "UNAVAILABLE"), basis=f"{item.get('tier') or 'No qualifying tier'}; {golden_review}")
    for side in ("call", "put"):
        item = assessment.get("next_day", {}).get("sides", {}).get(side, {})
        add(f"1DTE Strategy {side.title()}", expiry="1DTE", **{side: item.get("strike")},
            status=item.get("result", "UNAVAILABLE"), basis=f"{item.get('selected_tier') or 'No qualifying tier'}; {golden_review}")
    rare = assessment.get("rare", {})
    add("Rare Golden Fingerprint", expiry="1DTE", put=rare.get("strike"),
        status=rare.get("result", "UNAVAILABLE"), basis=rare.get("description", ""))
    return rows
