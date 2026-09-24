"""Actual available spreads from the displayed chain, labeled by frozen analysis.

No strategy is rerun here. No quotes, trades, or clocks are cached here.
One-minute history timestamps label bar starts; their data are available one
minute later. Button-click and refresh times never renew analysis freshness.
"""
from __future__ import annotations

from datetime import time
import math

import pandas as pd
import streamlit as st

EASTERN = "America/New_York"
REGULAR_SESSION_END = time(16, 0)


TITLE = "Available Trades From Current Option Chain"
REFRESH_MESSAGE = "Refresh analysis above before showing available trades."
EMPTY_MESSAGE = "Nothing available at this time."
SYMBOL_PREFERENCE = ("XSP", "QQQ", "SPY")
MAX_AGE = pd.Timedelta(minutes=60)


def _stamp(value):
    if value is None:
        return None
    try:
        result = pd.Timestamp(value)
        if pd.isna(result):
            return None
        return result.tz_localize(EASTERN) if result.tzinfo is None else result.tz_convert(EASTERN)
    except (TypeError, ValueError):
        return None


def _date(value):
    result = _stamp(value)
    return result.date() if result is not None else None


def _clock(day, value):
    return _stamp(f"{day} {value}") if day is not None and value else None


def _completed_at(frame):
    if frame is None or frame.empty or "timestamp_et" not in frame:
        return None
    result = _stamp(frame["timestamp_et"].max())
    return result + pd.Timedelta(minutes=1) if result is not None else None


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def number(value):
    return f"{float(value):.8f}".rstrip("0").rstrip(".")


def _time_text(value):
    stamp = _stamp(value)
    return stamp.strftime("%I:%M %p").lstrip("0") if stamp is not None else "unavailable"


def _age_text(age):
    if age is None:
        return "unavailable"
    seconds = int(age.total_seconds())
    if seconds < 0:
        return f"future by {_age_text(-age)}"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    for value, label in ((hours, "hour"), (minutes, "minute"), (seconds, "second")):
        if value:
            parts.append(f"{value} {label}{'' if value == 1 else 's'}")
    return " ".join(parts) or "0 minutes"


def capture_trade_analysis(snapshot, day):
    """Freeze provenance once, when Analyze actually finishes, never on refresh.

    The checkpoint, Golden review, forecast, and Directional reference can use
    different bars. Retain each clock instead of relabeling all of them with
    the latest checkpoint. Prior-day strikes are references, not today's age.
    """
    inputs = snapshot["inputs"]
    symbol = inputs["symbol"]
    session = _date(inputs["selected_date"])
    checkpoint = snapshot["checkpoint_result"]
    as_of = _completed_at(checkpoint.get("visible"))
    context = {
        "symbol": symbol, "session": str(session),
        "as_of": as_of.isoformat() if as_of is not None else None,
        "outcome_only": bool(snapshot.get("is_end_of_day_checkpoint")),
        "references": [],
    }
    if context["outcome_only"]:
        return context

    def add(name, side, strike, data_time, expiration=None, **details):
        stamp = _stamp(data_time)
        if not _finite(strike) or stamp is None:
            return
        context["references"].append({
            "strategy": name, "side": side, "strike": float(strike),
            "as_of": stamp.isoformat(), "expiration_date": str(expiration or session),
            **details,
        })

    forecast = snapshot.get("daily_price_forecast") or {}
    if (forecast.get("available") and forecast.get("headline_gate", {}).get("clear")
            and forecast.get("symbol") == symbol and _date(forecast.get("date")) == session):
        last = _stamp(forecast.get("last_candle"))
        forecast_time = last + pd.Timedelta(minutes=1) if last is not None else None
        # Use the same 90/95 references already included in the existing summary.
        for level in ("90", "95"):
            band = forecast.get("ranges", {}).get(level, {})
            for side in ("CALL", "PUT"):
                add(f"Daily Price Boundary Strategy ({level}%)", side,
                    band.get(f"{side.lower()}_strike"), forecast_time)

    movement = snapshot.get("market_movement") or {}
    if (movement.get("active") and movement.get("symbol") == symbol
            and _date(movement.get("trade_date")) == session
            and all(gate.get("passed") for gate in movement.get("gates", []))):
        # The parent review clock belongs to these exact-time signals. It is
        # deliberately not the latest forecast clock or the chain clock.
        signal_time = _clock(session, movement.get("review_time_et"))
        for item in movement.get("primary_results", {}).values():
            for side, key, rounding in (("CALL", "upper_boundary", math.ceil),
                                        ("PUT", "lower_boundary", math.floor)):
                if _finite(item.get(key)):
                    add(f"Market Movement Strategy ({item['target_label']}; {item['rule_id']})",
                        side, rounding(item[key]), signal_time,
                        movement_signal_time=signal_time.isoformat() if signal_time is not None else None,
                        anchor_price=item.get("anchor_price"), anchor_type=item.get("anchor_type"),
                        lower_boundary=item.get("lower_boundary"), upper_boundary=item.get("upper_boundary"))

    assessment = snapshot.get("assessment") or {}
    if assessment.get("symbol") == symbol and _date(assessment.get("trade_date")) == session:
        golden_time = _completed_at((snapshot.get("result") or {}).get("visible"))
        for side, item in zip(("CALL", "PUT"), assessment.get("combined", {}).get("rows", [])[:2]):
            if item.get("result") == "ENTER":
                add(f"Foundational Golden Filter {side.title()} ({item.get('tier')})",
                    side, item.get("strike"), golden_time)
        expiration = _date(assessment.get("next_trading_date"))
        if expiration is not None and expiration > session:
            for side, item in assessment.get("next_day", {}).get("sides", {}).items():
                if item.get("result") == "ENTER":
                    add(f"1DTE Strategy {side.title()} ({item.get('selected_tier')})",
                        side.upper(), item.get("strike"), golden_time, expiration)
            rare = assessment.get("rare", {})
            if rare.get("result") == "ENTER":
                add("Rare Golden Fingerprint", "PUT", rare.get("strike"), golden_time, expiration)

        directional = assessment.get("directional_distance") or {}
        if (directional.get("active") and directional.get("result", "").startswith("ELIGIBLE")
                and directional.get("symbol") == symbol
                and _date(directional.get("trade_date")) == session):
            # The existing Directional method reads the 11:00 bar's CLOSE.
            # Its data are therefore not available to an 11:00 chain; 11:01
            # is the earliest supporting as-of. Leave its calculation intact.
            bars = day[day["timestamp_et"].dt.time == time(11, 0)]
            directional_time = _completed_at(bars)
            for item in directional.get("candidates", []):
                add(f"Directional Distance ({item['label']})", directional.get("option_side"),
                    item.get("short_strike"), directional_time,
                    anchor_price=directional.get("market_open"), anchor_type="FIXED_OPEN")

    recheck = snapshot.get("morning_recheck") or {}
    prior = _date(recheck.get("previous_date"))
    opportunity = recheck.get("opportunity") or {}
    if (recheck.get("ready") and prior is not None and prior < session
            and _date(recheck.get("inputs", {}).get("selected_date")) == session
            and opportunity.get("symbol") == symbol and opportunity.get("active")
            and opportunity.get("result", "").startswith("ELIGIBLE")):
        for item in opportunity.get("candidates", []):
            add(f"Prior-Day 1DTE Strike Check ({item['label']})", opportunity.get("option_side"),
                item.get("short_strike"), as_of, session,
                reference_date=str(prior), anchor_price=opportunity.get("market_open"),
                anchor_type="PRIOR_SESSION_OPEN")
    return context


def build_available_trades(snapshot, chain, symbol, trade_date, enabled_widths=(1.,), now_et=None):
    """Evaluate only this newly displayed chain; return a fresh result every call."""
    chain = chain or {}
    session = _date(trade_date)
    context = (snapshot or {}).get("trade_analysis") or {}
    analysis_time = _stamp(context.get("as_of"))
    now = _stamp(now_et) if now_et is not None else pd.Timestamp.now(tz=EASTERN)
    chain_time = _stamp(chain.get("as_of"))
    age = now - analysis_time if analysis_time is not None else None
    result = {
        "status": "refresh", "message": REFRESH_MESSAGE, "reason": "",
        "symbol": symbol, "session": str(session), "underlying_price": chain.get("underlying_price"),
        "analysis_time": analysis_time, "chain_time": chain_time, "age": age, "evaluated_at": now,
        "rows": [], "references": [], "excluded_references": [],
    }
    if symbol not in SYMBOL_PREFERENCE:
        return {**result, "status": "unsupported_symbol", "message": "This section applies to XSP, QQQ, and SPY only."}
    inputs = (snapshot or {}).get("inputs") or {}
    if (not (snapshot or {}).get("ready") or context.get("symbol") != symbol
            or inputs.get("symbol") != symbol or _date(inputs.get("selected_date")) != session
            or _date(context.get("session")) != session or analysis_time is None
            or analysis_time.date() != session or now.date() != session):
        return {**result, "reason": "A completed analysis with matching symbol, session, and market-data timestamp is required."}
    if age < pd.Timedelta(0) or age > MAX_AGE:
        return {**result, "reason": "Analysis must be 0–60 minutes old, inclusive, at the current Eastern market time."}
    if chain_time is None:
        return {**result, "status": "no_chain", "message": EMPTY_MESSAGE,
                "reason": "No current chain snapshot is loaded."}
    if chain_time.date() != session or chain_time > now or analysis_time > chain_time:
        return {**result, "reason": "Analysis and the loaded chain must belong to this session; analysis cannot come after the chain snapshot."}
    if context.get("outcome_only") or not time(9, 30) <= now.time() < REGULAR_SESSION_END:
        return {**result, "status": "no_candidates", "message": EMPTY_MESSAGE,
                "reason": "Outside the regular-session entry window."}

    for reference in context.get("references", []):
        data_time = _stamp(reference.get("as_of"))
        reference_age = now - data_time if data_time is not None else None
        if (data_time is None or data_time.date() != session or data_time > chain_time or reference_age < pd.Timedelta(0)
                or reference_age > MAX_AGE):
            result["excluded_references"].append({**reference, "age": reference_age})
        else:
            result["references"].append({**reference, "age": reference_age})
    if chain.get("status") != "ok":
        return {**result, "status": "no_chain" if chain.get("status") == "no_data" else "no_candidates",
                "message": EMPTY_MESSAGE, "reason": chain.get("message") or "No current chain spreads are available."}
    price = chain.get("underlying_price")
    if not _finite(price) or float(price) <= 0:
        return {**result, "status": "no_chain", "message": EMPTY_MESSAGE,
                "reason": "The chain's exact-time underlying price is unavailable."}
    price = float(price)
    widths = {float(width) for width in enabled_widths if _finite(width) and 1 <= float(width) <= 9 and float(width).is_integer()}
    for quote in chain.get("rows", []):
        fields = ("short_strike", "long_strike", "width", "short_bid", "short_ask", "long_bid", "long_ask")
        if not all(_finite(quote.get(key)) for key in fields):
            continue
        side, expiration = quote.get("type"), _date(quote.get("expiration_date"))
        short, long, width = (float(quote[key]) for key in fields[:3])
        if (side not in ("CALL", "PUT") or width not in widths
                or _stamp(quote.get("time")) != chain_time
                or expiration is None or expiration < session
                or quote.get("symbol") != symbol
                or not quote.get("sell_contract_id") or not quote.get("buy_contract_id")):
            continue
        distance = short - price if side == "CALL" else price - short
        actual_width = long - short if side == "CALL" else short - long
        credit = round(float(quote["short_bid"]) - float(quote["long_ask"]), 4)
        if (distance <= 0 or not math.isclose(actual_width, width, abs_tol=1e-8)
                or float(quote["short_bid"]) <= 0 or float(quote["long_ask"]) <= 0 or credit <= 0
                or float(quote["long_bid"]) < 0 or float(quote["short_ask"]) < float(quote["short_bid"])
                or float(quote["long_ask"]) < float(quote["long_bid"])):
            continue
        references = [ref for ref in result["references"]
                      if ref["side"] == side and _date(ref["expiration_date"]) == expiration]
        comparisons = []
        for ref in references:
            inside = ref["strike"] - short if side == "CALL" else short - ref["strike"]
            comparisons.append({**ref, "inside_points": max(0., round(inside, 8)),
                                "supports": inside <= 1e-8})
        supporters = [ref for ref in comparisons if ref["supports"]]
        comparison = min(comparisons, key=lambda ref: (
            not ref["strategy"].startswith("Market Movement Strategy"),
            abs(ref["strike"] - short), ref["strategy"]), default=None)
        if supporters:
            label = "; ".join(ref["strategy"] for ref in supporters)
        elif comparison is not None:
            difference = comparison["inside_points"]
            label = (f"{number(difference)} {'point' if difference == 1 else 'points'} closer to price than the "
                     f"{comparison['strategy']} suggested strike — no strategy support.")
        else:
            label = ("No strategy support — no fresh, eligible strategy reference "
                     "for this side and expiration.")
        result["rows"].append({
            "symbol": symbol, "underlying_price": price, "side": side,
            "expiration_date": str(expiration), "dte": quote["expiration"],
            "sell_strike": short, "buy_strike": long, "width": width,
            "credit": credit, "credit_per_width": credit / width,
            "distance_from_price": round(distance, 8), "supported": bool(supporters),
            "support_label": label, "supporting_strategies": [ref["strategy"] for ref in supporters],
            "comparison": comparison, "comparisons": comparisons,
            "analysis_time": analysis_time, "chain_time": chain_time, "age": age,
            # Contract identity and both quoted legs come exclusively from the
            # scanner's matched symbol/type/expiration group, never a target.
            "sell_contract": {"id": quote["sell_contract_id"], "quote_time": quote.get("short_quote_time"), "symbol": symbol, "type": side, "expiration": str(expiration),
                              "strike": short, "bid": float(quote["short_bid"]),
                              "ask": float(quote["short_ask"]), "time": quote["time"]},
            "buy_contract": {"id": quote["buy_contract_id"], "quote_time": quote.get("long_quote_time"), "symbol": symbol, "type": side, "expiration": str(expiration),
                             "strike": long, "bid": float(quote["long_bid"]),
                             "ask": float(quote["long_ask"]), "time": quote["time"]},
        })
    result["rows"].sort(key=lambda row: (
        not row["supported"], SYMBOL_PREFERENCE.index(row["symbol"]), row["width"],
        row["dte"], row["side"], -row["distance_from_price"], -row["credit"],
    ))
    return {**result, "status": "ok" if result["rows"] else "no_candidates",
            "message": "" if result["rows"] else EMPTY_MESSAGE}


def render_available_trades(result):
    """Keep shared chain context above two readable, independently labeled tables."""
    import streamlit as st

    st.header(TITLE)
    st.caption(f"{result['symbol']} · {result['session']} · All times Eastern. "
               f"Analysis: {_time_text(result['analysis_time'])} | "
               f"Chain retrieved: {_time_text(result['chain_time'])} | Analysis age: {_age_text(result['age'])}")
    if result["status"] != "ok":
        if result["status"] == "refresh":
            st.warning(REFRESH_MESSAGE)
        else:
            st.info(result["message"])
            if (result["status"] in ("no_chain", "no_candidates") and result["age"] is not None
                    and pd.Timedelta(0) <= result["age"] <= MAX_AGE):
                st.caption("Fresh analysis is available, but no actual spreads meet the current chain settings.")
        if result.get("reason"):
            st.caption(result["reason"])
    else:
        st.caption(f"Underlying price used for every spread below: ${number(result['underlying_price'])}. "
                   "Quotes come from the displayed chain. Credit = short bid − long ask. "
                   "Only the selected spread width is included; within each side/expiration, "
                   "farther short strikes appear first, then higher credit for ties. "
                   "Analysis and chain timestamps above apply to every row. Age is measured against current Eastern time, not the chain refresh time.")
        for supported, title in ((True, "Strategy-supported available trades"), (False, "Available trades without strategy support")):
            rows = [row for row in result["rows"] if row["supported"] == supported]
            st.markdown(f"**{title}**")
            if not rows:
                st.caption("None at this chain time under the current settings.")
                continue
            table = []
            for row in rows:
                comparison = row["comparison"] or {}
                table.append({
                    "Sell contract": row["sell_contract"]["id"], "Buy contract": row["buy_contract"]["id"],
                    "Side": row["side"], "Expiration": f"{row['expiration_date']} · {row['dte']}",
                    "Sell strike": row["sell_strike"], "Buy strike": row["buy_strike"], "Width": row["width"],
                    "Credit": row["credit"], "Credit / width": row["credit_per_width"],
                    "Distance from price": row["distance_from_price"],
                    "Strategy support": row["support_label"],
                    "Suggested short (reference only)": comparison.get("strike"),
                    "Points inside suggested strike": comparison.get("inside_points"),
                    "Original Movement signal": "; ".join(dict.fromkeys(
                        _time_text(ref["movement_signal_time"]) for ref in row["comparisons"]
                        if ref.get("movement_signal_time"))) or "—",
                })
            frame = pd.DataFrame(table)
            styled = frame.style.format({"Sell strike": "{:g}", "Buy strike": "{:g}", "Width": "{:g}",
                                         "Credit": "{:.4f}", "Credit / width": "{:.8f}",
                                         "Distance from price": "{:.4f}", "Suggested short (reference only)": "{:g}",
                                         "Points inside suggested strike": "{:g}"}, na_rep="—")
            if not supported:
                st.markdown(":red[These are actual quoted spreads with no strategy support. Where a comparison reference exists, the red text gives its name and distance.]")
                styled = styled.set_properties(subset=["Strategy support"], **{"color": "#c62828"})
            st.dataframe(styled, hide_index=True, width="stretch")

    references = result.get("references", []) + result.get("excluded_references", [])
    if references and result["rows"]:
        with st.expander("Strategy reference times and original boundaries"):
            st.caption("These references retain their own data timestamps. A later unrelated analysis does not restart their age. "
                       "A prior-day reference date is separate from today's evaluation time.")
            table = []
            for ref in references:
                table.append({
                    "Strategy": ref["strategy"], "Side": ref["side"], "Suggested short": ref["strike"],
                    "Expiration": ref["expiration_date"], "Data as of (ET)": _time_text(ref["as_of"]),
                    "Age now": _age_text(ref.get("age")),
                    "Status": "Eligible reference" if ref in result["references"] else "Excluded — refresh required",
                    "Original Movement signal (ET)": _time_text(ref.get("movement_signal_time")),
                    "Anchor": ref.get("anchor_price"), "Anchor type": ref.get("anchor_type", ""),
                    "Original lower boundary": ref.get("lower_boundary"),
                    "Original upper boundary": ref.get("upper_boundary"),
                    "Prior reference date": ref.get("reference_date", ""),
                })
            st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")


def chain_from_board_rows(board_rows, symbol, retrieved_at):
    """Reuse exact matched contract identities/quotes from the displayed board."""
    rows = [row for row in board_rows if row.get("Symbol") == symbol]
    stamp = _stamp(retrieved_at)
    session = stamp.date() if stamp is not None else None
    result = {"status": "ok" if rows else "no_data", "as_of": retrieved_at,
              "underlying_price": rows[0].get("Current") if rows else None, "rows": []}
    expiration_labels = {}
    for row in rows:
        expiration = _date(row.get("Expiration"))
        if session is None or expiration is None or expiration < session:
            continue
        if expiration not in expiration_labels:
            import pandas_market_calendars as calendars
            sessions = calendars.get_calendar("NYSE").valid_days(session, expiration)
            expiration_labels[expiration] = f"{max(0, len(sessions) - 1)}DTE"
        result["rows"].append({
            "symbol": row["Symbol"], "type": "PUT" if row["Side"] == "Put Credit" else "CALL",
            "expiration_date": str(expiration), "expiration": expiration_labels[expiration], "time": retrieved_at,
            "short_strike": row["Short Strike"], "long_strike": row["Long Strike"], "width": row["Width"],
            "short_bid": row["Short Bid"], "short_ask": row["Short Ask"],
            "long_bid": row["Long Bid"], "long_ask": row["Long Ask"],
            "sell_contract_id": row["Short Symbol"], "buy_contract_id": row["Long Symbol"],
            "short_quote_time": row.get("_Short Quote Time"), "long_quote_time": row.get("_Long Quote Time"),
        })
    return result


@st.fragment(run_every="30s")
def render_live_available_trades(snapshot, board_rows, symbol, retrieved_at, enabled_widths):
    # Only this bottom display reruns on the timer. It does not fetch quotes or
    # rerun analysis, and expired results are replaced rather than cached.
    now = pd.Timestamp.now(tz=EASTERN)
    chain = chain_from_board_rows(board_rows, symbol, retrieved_at)
    result = build_available_trades(snapshot, chain, symbol, now.date(), enabled_widths, now)
    render_available_trades(result)
    if result["rows"]:
        import streamlit as st
        with st.expander("Actual contracts and source quote times"):
            st.caption("Snapshot retrieval and provider quote-update times are distinct. Every credit below uses the displayed sell bid minus buy ask.")
            st.dataframe([{"Sell contract": row["sell_contract"]["id"], "Sell bid": row["sell_contract"]["bid"],
                           "Sell quote time (ET)": str(_stamp(row["sell_contract"]["quote_time"]) or "Not supplied"),
                           "Buy contract": row["buy_contract"]["id"], "Buy ask": row["buy_contract"]["ask"],
                           "Buy quote time (ET)": str(_stamp(row["buy_contract"]["quote_time"]) or "Not supplied"),
                           "Quoted credit": row["credit"]} for row in result["rows"]], hide_index=True, width="stretch")
