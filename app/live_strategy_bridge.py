"""Adapt completed live assessments to the shared summary and quote comparison.

Only Analyze calls this module. Chain refreshes never recalculate a strategy or
change its original data timestamp, anchor, or strike reference.
"""
import pandas as pd
import streamlit as st

from available_trades import capture_trade_analysis
from rare_fingerprint import add_daily_indicators, active_fingerprint_state, assess_rare, RULES
from strategy_summary import build_strategy_summary

RARE_HISTORY_MESSAGE = "Cannot get enough data. Refer to the historical application."


def evaluate_rare_history(symbol, daily, trade_date, review, foundational, metrics, today_gate, next_gate):
    prior = daily.loc[daily.index.date < trade_date].copy() if not daily.empty else daily
    import pandas_market_calendars as calendars
    expected = calendars.get_calendar("NYSE").valid_days(
        pd.Timestamp(trade_date) - pd.Timedelta(days=150), pd.Timestamp(trade_date) - pd.Timedelta(days=1)
    )[-61:]
    if prior.empty or len(expected) < 61 or not set(expected.date).issubset(set(prior.index.date)):
        return {"result": "DAILY HISTORY UNAVAILABLE", "description": RARE_HISTORY_MESSAGE,
                "fingerprint": {"ready": False}, "conditions": [], "strike": None,
                "history_days": len(prior), "history_note": "Needs the latest 61 completed trading sessions without missing daily bars."}
    state = active_fingerprint_state(add_daily_indicators(prior), trade_date,
                                     RULES[symbol]["rare"]["maximum_age"]) if not prior.empty else {"ready": False}
    if not state.get("ready"):
        return {"result": "DAILY HISTORY UNAVAILABLE", "description": RARE_HISTORY_MESSAGE,
                "fingerprint": state, "conditions": [], "strike": None, "history_days": len(prior)}
    if not foundational or not metrics or not review:
        return {"result": "NOT ACTIVE", "description": "Requires a completed Golden checkpoint at or after 11:00 AM.",
                "fingerprint": state, "conditions": [], "strike": None, "history_days": len(prior)}
    result = assess_rare(symbol, review, foundational, metrics, today_gate, next_gate, state)
    result["history_days"] = len(prior)
    return result


def completed_analysis_snapshot(payload):
    """Preserve each strategy's own as-of; never use the download/click time."""
    symbol, session = payload["symbol"], payload["trade_date"]
    cutoff = pd.Timestamp(payload["analysis_cutoff"]).tz_convert("America/New_York")
    day = payload["day_1m"]
    visible = day[day.timestamp_et < cutoff].copy()
    visible["timestamp_et"] = visible.timestamp_et.dt.tz_convert("America/New_York")
    expected = pd.date_range(pd.Timestamp(f"{session} 09:30", tz="America/New_York"),
                             cutoff, freq="min", inclusive="left")
    complete = bool(len(expected) and pd.DatetimeIndex(visible.timestamp_et).equals(expected))
    assessment = None
    foundational = payload.get("foundational")
    if foundational:
        combined = []
        for side in ("call", "put"):
            choices = [(name, mode) for name, mode in foundational["modes"].items() if mode["status"] == "ENTER"]
            chosen = min(choices, key=lambda item: item[1]["distance"], default=None)
            combined.append({"result": "ENTER" if chosen else foundational["result"],
                             "tier": chosen[0] if chosen else None,
                             "strike": chosen[1][f"{side}_strike"] if chosen else None})
        directional = dict(payload.get("directional") or {})
        directional.update(symbol=symbol, trade_date=session, active=bool(directional.get("candidates")))
        assessment = {"symbol": symbol, "trade_date": session, "next_trading_date": payload["next_trading_date"],
                      "combined": {"rows": combined}, "next_day": payload.get("next_day") or {},
                      "rare": payload.get("rare") or {}, "directional_distance": directional}
    golden = dict(payload.get("result") or {})
    if golden.get("ready"):
        golden_cutoff = payload["golden_cutoff"]
        golden["visible"] = day[day.timestamp_et < golden_cutoff].copy()
    snapshot = {"ready": complete, "inputs": {"symbol": symbol, "selected_date": session},
                "checkpoint_result": {"visible": visible if complete else None},
                "result": golden, "assessment": assessment,
                "daily_price_forecast": payload["daily_price_forecast"],
                "market_movement": payload["movement"], "morning_recheck": payload.get("morning_recheck")}
    snapshot["trade_analysis"] = capture_trade_analysis(snapshot, day)
    # All operating foundational tiers are valid references, not only the
    # closest tier selected for the combined summary.
    if assessment and golden.get("ready"):
        stamp = golden["visible"].timestamp_et.max() + pd.Timedelta(minutes=1)
        references = snapshot["trade_analysis"]["references"]
        names = {ref["strategy"] for ref in references}
        for side in ("CALL", "PUT"):
            for name, mode in foundational["modes"].items():
                label = f"Foundational Golden Filter {side.title()} ({name})"
                if mode["status"] == "ENTER" and label not in names:
                    references.append({"strategy": label, "side": side,
                                       "strike": mode[f"{side.lower()}_strike"],
                                       "as_of": stamp.isoformat(), "expiration_date": str(session)})
    return snapshot


def render_added_strategy_sections(payload):
    st.subheader("Rare Golden Fingerprint")
    rare = payload["rare"]
    if rare["description"] == RARE_HISTORY_MESSAGE:
        st.info(RARE_HISTORY_MESSAGE)
    elif rare["result"] == "ENTER":
        st.success("ENTER")
        st.write(rare["description"])
        st.metric("1DTE PUT short-strike reference", f"{rare['strike']:g}")
    else:
        st.info(f"{rare['result']} — {rare['description']}")
    with st.expander("Rare Golden Fingerprint history and conditions"):
        st.caption(f"Completed daily sessions returned: {rare.get('history_days', 0)}. Today's daily candle is excluded.")
        state = rare.get("fingerprint", {})
        if state.get("signal_date"):
            st.write(f"Original signal: {state['signal_date']} | Age: {state['age']} sessions | Original boundary: {state['signal_boundary']:g}")
        if rare.get("conditions"):
            st.dataframe([{"Condition": row["label"], "Value": str(row.get("value")),
                           "Threshold": str(row.get("threshold", "—")),
                           "Result": "PASS" if row["passed"] else "FAIL"} for row in rare["conditions"]],
                         hide_index=True, width="stretch")
        if rare.get("history_note"):
            st.caption(rare["history_note"])

    st.subheader("Prior-Day 1DTE Strike Check")
    recheck = payload.get("morning_recheck") or {}
    if not recheck.get("ready"):
        st.info(recheck.get("message", "Runs at the 9:40 AM checkpoint using the previous trading session's directional references."))
    else:
        opportunity = recheck["opportunity"]
        st.caption(f"Original reference date: {recheck['previous_date']} · Today's evaluation: {payload['trade_date']} at 9:40 AM ET. "
                   "The prior 1DTE reference is compared with today's 0DTE contracts on the Options Opportunity Board.")
        st.write(f"**{opportunity['result']}** — {opportunity['reason']}")
        st.dataframe([{"Side": opportunity["option_side"], "Tier": row["label"],
                       "Prior-day short-strike reference": row["short_strike"],
                       "Prior 9:30 open": opportunity["market_open"]} for row in opportunity["candidates"]],
                     hide_index=True, width="stretch")

    st.subheader("Combined Best Entry Summary")
    snapshot = payload["analysis_snapshot"]
    visible = payload["day_1m"][payload["day_1m"].timestamp_et < payload["analysis_cutoff"]]
    price = float(visible.iloc[-1].close) if not visible.empty else None
    rows = build_strategy_summary(snapshot.get("assessment"), payload["movement"], payload["daily_price_forecast"],
                                  checkpoint_price=price, golden_review=payload.get("golden_review_label"))
    if recheck.get("ready"):
        opportunity = recheck["opportunity"]
        for item in opportunity["candidates"]:
            side = opportunity["option_side"].lower()
            otm = price is not None and (item["short_strike"] > price if side == "call" else item["short_strike"] < price)
            rows.append({"strategy": "Prior-Day 1DTE Strike Check", "expiry": "0DTE", "call_strike": None,
                         "put_strike": None, f"{side}_strike": item["short_strike"] if otm else None,
                         "status": opportunity["result"] if otm else "NO OTM REFERENCE",
                         "basis": f"{item['label']}; original reference {recheck['previous_date']}; evaluated today at 9:40 AM"})
    else:
        rows.append({"strategy": "Prior-Day 1DTE Strike Check", "expiry": "0DTE", "call_strike": None,
                     "put_strike": None, "status": "NOT ACTIVE", "basis": recheck.get("message", "9:40 AM only")})
    # If no Golden checkpoint is ready, retain the more specific Rare data state.
    for row in rows:
        if row["strategy"] == "Rare Golden Fingerprint":
            row.update(status=rare["result"], basis=rare["description"])
    st.caption("Strategy strike references only. Actual quoted spreads are on the Options Opportunity Board; a reference does not establish contract availability.")
    st.dataframe(pd.DataFrame(rows).rename(columns={"strategy": "Strategy", "expiry": "Expiration", "call_strike": "CALL reference",
                     "put_strike": "PUT reference", "status": "Result", "basis": "Reason / reference"}), hide_index=True, width="stretch")
