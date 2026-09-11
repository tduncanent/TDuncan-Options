import asyncio
import math
import re
import time
from datetime import date, datetime, time as clock_time, timedelta
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import requests
import streamlit as st

from market_movement import (
    MOVEMENT_REVIEW_CLOCKS,
    MOVEMENT_REVIEW_OPTIONS,
    TARGET_FRESH,
    TARGET_LABELS,
    TARGET_OPEN,
    build_market_movement_assessment,
)


st.set_page_config(page_title="TDuncan & Co", layout="wide")

APP_PASSWORD = st.secrets["APP_PASSWORD"]

password = st.text_input(
    "Enter Password",
    type="password",
    key="app_password_input",
)

if password != APP_PASSWORD:
    st.stop()

st.markdown(
    """
    <style>
    div.stButton > button[kind="primary"] {
        background-color: #0057D9;
        color: white;
        border: 1px solid #0057D9;
        font-weight: 700;
    }

    div.stButton > button[kind="primary"]:hover {
        background-color: #0047B3;
        color: white;
        border: 1px solid #0047B3;
    }

    div.stButton > button[kind="primary"]:focus {
        background-color: #0057D9;
        color: white;
        border: 1px solid #0057D9;
        box-shadow: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default

        return float(value)

    except Exception:
        return default


# ==================================================
# LIVE TECHNICAL ENTRY CHECK — TASTYTRADE CANDLES
# ==================================================

EASTERN_ZONE = ZoneInfo("America/New_York")
LIVE_TECHNICAL_SYMBOLS = ["QQQ", "SPY", "XSP", "XND"]
LIVE_REVIEW_TIMES = {
    "11:00 AM": clock_time(11, 0),
    "1:00 PM": clock_time(13, 0),
    "2:15 PM": clock_time(14, 15),
}
LIVE_ANALYSIS_TIMES = dict(MOVEMENT_REVIEW_CLOCKS)

# This is the Foundational Golden Filter subset used by the Research Engine.
# Keeping it here makes the live page deployable as a single Streamlit file.
LIVE_FOUNDATIONAL_RULES = {
    "QQQ": {
        "standard_distance": 20.0,
        "preferred_distance": 25.0,
        "closer_distance": 15.0,
        "near_extreme_percent": 0.30,
        "11:00 AM": {"impulse": 3.20, "atr": 5.00, "churn": 11.90, "displacement": 4.00},
        "1:00 PM": {
            "impulse": 3.20,
            "atr": 5.00,
            "churn": 11.90,
            "displacement": 4.00,
            "persistent_trend": 15.00,
        },
        "2:15 PM": {
            "impulse": 3.20,
            "atr": 5.00,
            "churn": 11.90,
            "displacement": 4.00,
            "persistent_trend": 15.00,
        },
    },
    "SPY": {
        "standard_distance": 12.5,
        "preferred_distance": 15.0,
        "closer_distance": 10.0,
        "near_extreme_percent": 0.30,
        "11:00 AM": {"impulse": 3.25, "atr": 2.30, "churn": 6.00, "displacement": 2.00},
        "1:00 PM": {"impulse": 3.50, "atr": 3.10, "churn": 4.00, "displacement": 5.00},
        "2:15 PM": {"impulse": 2.25, "atr": 2.30, "churn": 3.00, "displacement": 10.00},
    },
    "XSP": {
        "standard_distance": 15.0,
        "preferred_distance": 16.0,
        "closer_distance": 10.0,
        "near_extreme_percent": 0.30,
        "11:00 AM": {
            "impulse": 3.30,
            "atr": 2.25,
            "churn": 7.75,
            "displacement": 4.25,
            "combined_activity_gate": True,
        },
        "1:00 PM": {
            "impulse": 3.20,
            "atr": 2.80,
            "churn": 5.25,
            "displacement": 4.00,
            "persistent_trend": 9.00,
        },
        "2:15 PM": {
            "impulse": 4.00,
            "atr": 2.60,
            "churn": 3.50,
            "displacement": 4.00,
            "persistent_trend": 9.00,
        },
    },
    "XND": {
        "standard_distance": 6.0,
        "preferred_distance": 7.0,
        "closer_distance": 5.0,
        "near_extreme_percent": 0.30,
        "11:00 AM": {"impulse": 1.25, "atr": 2.25, "churn": 1.00, "displacement": 4.50},
        "1:00 PM": {"impulse": 2.00, "atr": 1.25, "churn": 1.50, "displacement": 3.00},
        "2:15 PM": {"impulse": 1.75, "atr": 1.50, "churn": 1.50, "displacement": 3.50},
    },
}

LIVE_DIRECTIONAL_DISTANCE_RULES = {
    "XSP": {
        "closer_distance": 8.5,
        "preferred_distance": 11.5,
        "closer_history": "1 post-skip closing failure in the five-year test",
        "preferred_history": "0 post-skip closing failures in the five-year test",
        "product_note": "Cash-settled index option.",
    },
    "XND": {
        "closer_distance": 3.0,
        "preferred_distance": 5.0,
        "closer_history": "2 post-skip closing failures in the five-year test",
        "preferred_history": "0 post-skip closing failures in the five-year test",
        "product_note": "Cash-settled index option.",
    },
    "QQQ": {
        "closer_distance": 10.0,
        "preferred_distance": 12.5,
        "extra_cushion_distance": 15.0,
        "closer_history": "1 post-skip closing failure in the five-year test",
        "preferred_history": "0 post-skip closing failures in the five-year test",
        "extra_cushion_history": "0 post-skip closing failures in the five-year test",
        "product_note": "ETF option; distance does not eliminate assignment or broker-liquidation risk.",
    },
    "SPY": {
        "closer_distance": 10.0,
        "preferred_distance": 12.5,
        "extra_cushion_distance": 15.0,
        "closer_history": "2 post-skip closing failures in the five-year test",
        "preferred_history": "0 post-skip closing failures in the five-year test",
        "extra_cushion_history": "0 post-skip closing failures in the five-year test",
        "product_note": "ETF option; distance does not eliminate assignment or broker-liquidation risk.",
    },
}

LIVE_NEXT_DAY_RULES = {
    "QQQ": {
        "preferred_fallback": 25.0,
        "call": {
            "extra_close": {
                "distance": 9.0,
                "conditions": [
                    ("signed_move", "<=", -2.50, "QQQ is at least $2.50 below open"),
                    ("morning_range", "<=", 6.00, "Morning range is no more than $6"),
                ],
            },
            "regular_closer": {
                "distance": 14.0,
                "conditions": [
                    ("absolute_move", "<=", 3.00, "Absolute move from open is no more than $3"),
                    ("atr", "<=", 1.25, "15-minute ATR is no more than $1.25"),
                ],
            },
        },
        "put": {
            "extra_close": {
                "distance": 10.0,
                "conditions": [
                    ("signed_move", ">=", 1.50, "QQQ is at least $1.50 above open"),
                    ("atr", "<=", 1.25, "15-minute ATR is no more than $1.25"),
                ],
            },
            "regular_closer": {
                "distance": 15.0,
                "conditions": [
                    ("signed_move", ">=", 1.00, "QQQ is at least $1 above open"),
                    ("atr", "<=", 1.50, "15-minute ATR is no more than $1.50"),
                ],
            },
        },
    },
    "SPY": {
        "preferred_fallback": 15.0,
        "call": {
            "extra_close": {
                "distance": 6.0,
                "evidence": "121/121",
                "conditions": [
                    ("signed_move", "<=", -2.00, "SPY is at least $2 below open"),
                    ("atr", "<=", 1.50, "15-minute ATR is no more than $1.50"),
                ],
            },
            "regular_closer": {
                "distance": 13.0,
                "evidence": "1,430/1,430",
                "conditions": [
                    ("absolute_move", "<=", 3.00, "Absolute move from open is no more than $3"),
                    ("atr", "<=", 1.50, "15-minute ATR is no more than $1.50"),
                ],
            },
        },
        "put": {
            "extra_close": {
                "distance": 10.0,
                "evidence": "568/568",
                "conditions": [
                    ("signed_move", ">=", -0.50, "SPY is no more than $0.50 below open"),
                    ("morning_range", "<=", 2.00, "Morning range is no more than $2"),
                ],
            },
            "regular_closer": {
                "distance": 11.0,
                "evidence": "419/419",
                "conditions": [
                    ("signed_move", ">=", 0.50, "SPY is at least $0.50 above open"),
                    ("morning_range", "<=", 3.00, "Morning range is no more than $3"),
                ],
            },
        },
    },
    "XSP": {
        "preferred_fallback": None,
        "call": {
            "extra_close": {
                "distance": 6.0,
                "evidence": "SPY source: 121/121",
                "conditions": [
                    ("signed_move", "<=", -2.00, "XSP is at least $2 below open"),
                    ("atr", "<=", 1.50, "15-minute ATR is no more than $1.50"),
                ],
            },
            "regular_closer": {
                "distance": 14.0,
                "evidence": "799/799",
                "conditions": [
                    ("atr", "<=", 1.50, "15-minute ATR is no more than $1.50"),
                    ("morning_range", "<=", 6.00, "Morning range is no more than $6"),
                ],
            },
        },
        "put": {
            "extra_close": {
                "distance": 10.0,
                "evidence": "SPY source: 568/568",
                "conditions": [
                    ("signed_move", ">=", -0.50, "XSP is no more than $0.50 below open"),
                    ("morning_range", "<=", 2.00, "Morning range is no more than $2"),
                ],
            },
            "regular_closer": {
                "distance": 14.0,
                "evidence": "551/551",
                "conditions": [
                    ("atr", "<=", 2.00, "15-minute ATR is no more than $2"),
                    ("morning_range", "<=", 3.00, "Morning range is no more than $3"),
                ],
            },
        },
    },
    "XND": {
        "preferred_fallback": None,
        "call": {
            "extra_close": {
                "distance": 5.0,
                "conditions": [
                    ("signed_move", "<=", -1.025, "XND is at least 1.025 points below open"),
                    ("morning_range", "<=", 2.46, "Morning range is no more than 2.46 points"),
                ],
            },
            "regular_closer": {
                "distance": 6.0,
                "conditions": [
                    ("absolute_move", "<=", 1.23, "Absolute move from open is no more than 1.23 points"),
                    ("atr", "<=", 0.5125, "15-minute ATR is no more than 0.5125"),
                ],
            },
        },
        "put": {
            "extra_close": {
                "distance": 5.0,
                "conditions": [
                    ("signed_move", ">=", 0.615, "XND is at least 0.615 points above open"),
                    ("atr", "<=", 0.5125, "15-minute ATR is no more than 0.5125"),
                ],
            },
            "regular_closer": {
                "distance": 7.0,
                "conditions": [
                    ("signed_move", ">=", 0.41, "XND is at least 0.41 points above open"),
                    ("atr", "<=", 0.615, "15-minute ATR is no more than 0.615"),
                ],
            },
        },
    },
}

LIVE_FOUNDATIONAL_CLOSE_RULES = {
    "QQQ": {"operating": True, "risk_envelope_multiplier": 2.50},
    "SPY": {"operating": True, "maximum_1100_absolute_move": 4.0},
    "XSP": {"operating": True, "allowed_reviews": ("1:00 PM", "2:15 PM")},
    "XND": {"operating": False},
}

LIVE_HEADLINE_OPTIONS = (
    "Not reviewed",
    "Clear",
    "Monitor — entry allowed",
    "Wait — hold entry until next review",
    "Suggest skip",
)

LIVE_CHART_INTERVALS = {
    "1 Minute": "1min",
    "5 Minute": "5min",
    "15 Minute": "15min",
}

LIVE_FOMC_DATES = {
    pd.Timestamp(value).date()
    for value in [
        "2018-05-02", "2018-06-13", "2018-08-01", "2018-09-26", "2018-11-08", "2018-12-19",
        "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19", "2019-07-31", "2019-09-18",
        "2019-10-30", "2019-12-11", "2020-01-29", "2020-03-03", "2020-04-29", "2020-06-10",
        "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16", "2021-01-27", "2021-03-17",
        "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
        "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21",
        "2022-11-02", "2022-12-14", "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
        "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13", "2024-01-31", "2024-03-20",
        "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
        "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17",
        "2025-10-29", "2025-12-10", "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
        "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    ]
}


def default_live_review_label(now_et):
    return "9:40 AM"


def live_analysis_timestamp(trade_date, review_label):
    return datetime.combine(
        trade_date,
        LIVE_ANALYSIS_TIMES[review_label],
        tzinfo=EASTERN_ZONE,
    )


def applicable_live_golden_review(review_label):
    review_clock = LIVE_ANALYSIS_TIMES[review_label]
    applicable = [
        label
        for label, checkpoint_clock in LIVE_REVIEW_TIMES.items()
        if checkpoint_clock <= review_clock
    ]
    return applicable[-1] if applicable else None


def live_review_timestamp(trade_date, review_label):
    return datetime.combine(
        trade_date,
        LIVE_REVIEW_TIMES[review_label],
        tzinfo=EASTERN_ZONE,
    )


def format_live_clock(value, include_seconds=False):
    hour = value.strftime("%I").lstrip("0") or "0"
    minute_second = value.strftime(":%M:%S" if include_seconds else ":%M")
    return f"{hour}{minute_second} {value.strftime('%p %Z')}".strip()


def live_strike_text(value):
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):,.2f}".rstrip("0").rstrip(".")


def live_outward_strike(boundary, side, increment=1.0):
    scaled = float(boundary) / float(increment)
    if str(side).upper() == "CALL":
        strike = math.ceil(scaled - 1e-10) * increment
    else:
        strike = math.floor(scaled + 1e-10) * increment
    return round(float(strike), 8)


def live_strike_for_distance(market_open, distance, side):
    boundary = market_open + distance if str(side).upper() == "CALL" else market_open - distance
    return boundary, live_outward_strike(boundary, side)


def build_live_headline_gate(trade_date, status, review_label, holding_window=False):
    if trade_date in LIVE_FOMC_DATES:
        return {
            "clear": False,
            "pending": False,
            "waiting": False,
            "status": "BLOCKED",
            "reason": f"{trade_date} is an FOMC decision day.",
        }
    if status in {"Clear", "Monitor — entry allowed"}:
        monitored = status == "Monitor — entry allowed"
        return {
            "clear": True,
            "pending": False,
            "waiting": False,
            "status": "MONITOR" if monitored else "CLEAR",
            "reason": (
                "Headline conditions require monitoring, but entry remains allowed when the technical engine is clear."
                if monitored
                else "The separate headline review was marked clear."
            ),
        }
    if status == "Wait — hold entry until next review":
        if holding_window:
            decision = "DO NOT OPEN 1DTE — HOLDING-WINDOW RISK UNRESOLVED"
        elif review_label == "11:00 AM":
            decision = "WAIT UNTIL 1:00 PM"
        elif review_label == "1:00 PM":
            decision = "WAIT UNTIL 2:15 PM"
        else:
            decision = "SKIP THE DAY — HEADLINE RISK STILL UNRESOLVED"
        return {
            "clear": False,
            "pending": False,
            "waiting": True,
            "status": "WAIT",
            "decision": decision,
            "reason": "The headline-risk review remains unresolved.",
        }
    if status == "Suggest skip":
        return {
            "clear": False,
            "pending": False,
            "waiting": False,
            "status": "BLOCKED",
            "reason": "The separate headline review suggests skipping this opportunity.",
        }
    return {
        "clear": False,
        "pending": True,
        "waiting": False,
        "status": "REVIEW REQUIRED",
        "reason": "The separate headline-risk report has not been entered on this page.",
    }


def get_live_next_trading_date(available_dates, trade_date):
    later_dates = sorted({value for value in available_dates if value > trade_date})
    if later_dates:
        return later_dates[0]
    try:
        import pandas_market_calendars as market_calendars

        calendar = market_calendars.get_calendar("NYSE")
        schedule = calendar.schedule(
            start_date=trade_date + timedelta(days=1),
            end_date=trade_date + timedelta(days=14),
        )
        if not schedule.empty:
            return schedule.index[0].date()
    except Exception:
        pass
    candidate = trade_date + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def build_live_directional_opportunity(symbol, day_1m, today_gate, reviews, exact_eleven_ready=True):
    rules = LIVE_DIRECTIONAL_DISTANCE_RULES[symbol]
    base = {
        "product_note": rules["product_note"],
        "headline_gate": today_gate,
        "candidates": [],
    }
    if day_1m.empty:
        return {
            **base,
            "result": "UNAVAILABLE — NO SESSION DATA",
            "reason": "No one-minute session data are available.",
        }
    if not exact_eleven_ready:
        return {
            **base,
            "result": "UNAVAILABLE — 11:00 CANDLE STILL FORMING",
            "reason": "Run again at 11:01 AM Eastern so the exact 11:00 one-minute close is final.",
        }
    day = day_1m.sort_values("timestamp_et")
    market_open = float(day.iloc[0]["open"])
    clocks = day["timestamp_et"].dt.time
    exact_eleven = day[clocks == clock_time(11, 0)]
    if exact_eleven.empty:
        return {
            **base,
            "market_open": market_open,
            "result": "UNAVAILABLE — EXACT 11:00 PRICE MISSING",
            "reason": "This separate strategy requires the close of the exact 11:00 one-minute bar.",
        }
    review_price = float(exact_eleven.iloc[-1]["close"])
    signed_move = review_price - market_open
    eleven_review = reviews.get("11:00 AM", {})
    if not eleven_review or not eleven_review.get("ready"):
        foundational_context = "UNAVAILABLE"
    elif eleven_review.get("flagged"):
        foundational_context = "FLAGGED"
    else:
        foundational_context = "CLEAR"
    base.update(
        {
            "market_open": market_open,
            "review_price": review_price,
            "signed_move": signed_move,
            "absolute_move": abs(signed_move),
            "foundational_context": foundational_context,
        }
    )
    if math.isclose(signed_move, 0.0, abs_tol=1e-10):
        return {
            **base,
            "direction": "NO DIRECTION",
            "option_side": "NONE",
            "result": "NO TRADE — 11:00 PRICE TIED THE OPEN",
            "reason": "The exact 11:00 price did not establish a direction from the open.",
        }
    direction = "BULLISH" if signed_move > 0 else "BEARISH"
    option_side = "PUT" if direction == "BULLISH" else "CALL"
    candidate_specs = [
        ("CLOSER", "Higher risk", rules["closer_distance"], rules["closer_history"]),
        ("PREFERRED", "Preferred", rules["preferred_distance"], rules["preferred_history"]),
    ]
    if rules.get("extra_cushion_distance") is not None:
        candidate_specs.append(
            (
                "EXTRA CUSHION",
                "Further distance",
                rules["extra_cushion_distance"],
                rules["extra_cushion_history"],
            )
        )
    candidates = []
    for label, risk_level, distance, history_note in candidate_specs:
        boundary, strike = live_strike_for_distance(market_open, float(distance), option_side)
        candidates.append(
            {
                "label": label,
                "risk_level": risk_level,
                "distance_from_open": float(distance),
                "boundary": boundary,
                "short_strike": strike,
                "distance_from_1100_price": abs(strike - review_price),
                "history_note": history_note,
            }
        )
    if today_gate["clear"]:
        result = "ELIGIBLE — MONITOR" if today_gate["status"] == "MONITOR" else "ELIGIBLE"
        reason = "The headline gate permits review. Use the chart, contract credit, and risk preference for the final selection."
    elif today_gate.get("waiting"):
        result = "WAIT — HEADLINE RISK UNRESOLVED"
        reason = today_gate["reason"]
    elif today_gate.get("pending"):
        result = "NO TRADE — HEADLINE REVIEW REQUIRED"
        reason = today_gate["reason"]
    else:
        result = "NO TRADE — MARKET-WIDE GATE BLOCKED"
        reason = today_gate["reason"]
    return {
        **base,
        "direction": direction,
        "option_side": option_side,
        "candidates": candidates,
        "result": result,
        "reason": reason,
    }


def build_live_morning_metrics(day_15m, review_result):
    clocks = day_15m["timestamp_et"].dt.time
    morning = day_15m[(clocks >= clock_time(9, 30)) & (clocks < clock_time(11, 0))]
    market_open = float(review_result["market_open"])
    review_price = float(review_result["review_price"])
    signed_move = review_price - market_open
    morning_range = float(morning["high"].max() - morning["low"].min()) if not morning.empty else float("nan")
    return {
        "market_open": market_open,
        "review_price": review_price,
        "signed_move": signed_move,
        "absolute_move": abs(signed_move),
        "morning_range": morning_range,
        "atr": float(review_result["atr"]),
    }


def live_blocked_mode_status(foundational_result):
    if str(foundational_result).startswith("WAIT"):
        return "WAIT"
    if str(foundational_result).startswith("SKIP"):
        return "SKIP"
    return "DO NOT ENTER"


def evaluate_live_next_day_tier(tier, metrics):
    conditions = []
    for metric_name, operator, threshold, label in tier["conditions"]:
        value = float(metrics.get(metric_name, float("nan")))
        if operator == "<=":
            passed = bool(not math.isnan(value) and value <= float(threshold))
        else:
            passed = bool(not math.isnan(value) and value >= float(threshold))
        conditions.append(
            {
                "metric": metric_name,
                "label": label,
                "operator": operator,
                "threshold": float(threshold),
                "value": value,
                "passed": passed,
            }
        )
    return {
        "distance": float(tier["distance"]),
        "evidence": tier.get("evidence"),
        "passed": all(condition["passed"] for condition in conditions),
        "conditions": conditions,
    }


def build_live_foundational_assessment(symbol, review_label, current_result, reviews, today_gate):
    technical_clear = bool(current_result.get("ready")) and not bool(current_result.get("flagged"))
    if not technical_clear:
        overall = current_result.get("decision", "DO NOT ENTER")
        description = "The current Foundational technical review is flagged or unavailable."
    elif today_gate["clear"]:
        overall = "ENTER"
        description = "Foundational technical conditions and today's entered headline gate are clear."
    elif today_gate.get("waiting"):
        overall = today_gate.get("decision", "WAIT")
        description = today_gate["reason"]
    elif today_gate.get("pending"):
        overall = "DO NOT ENTER — HEADLINE REVIEW REQUIRED"
        description = today_gate["reason"]
    else:
        overall = "SKIP — HEADLINE OR EVENT RISK"
        description = today_gate["reason"]

    rules = LIVE_FOUNDATIONAL_RULES[symbol]
    modes = {}
    for mode, key in (("Standard", "standard_distance"), ("Preferred", "preferred_distance")):
        distance = float(rules[key])
        _, call_strike = live_strike_for_distance(current_result["market_open"], distance, "CALL")
        _, put_strike = live_strike_for_distance(current_result["market_open"], distance, "PUT")
        modes[mode] = {
            "status": "ENTER" if overall == "ENTER" else live_blocked_mode_status(overall),
            "distance": distance,
            "call_strike": call_strike,
            "put_strike": put_strike,
            "reason": description,
        }

    close_cfg = LIVE_FOUNDATIONAL_CLOSE_RULES[symbol]
    close_distance = float(rules["closer_distance"])
    _, close_call = live_strike_for_distance(current_result["market_open"], close_distance, "CALL")
    _, close_put = live_strike_for_distance(current_result["market_open"], close_distance, "PUT")
    eleven = reviews.get("11:00 AM", {})
    eleven_clear = bool(eleven.get("ready")) and not bool(eleven.get("flagged"))
    eleven_move = abs(float(eleven.get("review_price", 0)) - float(eleven.get("market_open", 0))) if eleven else float("nan")
    containment_limit = close_cfg.get("maximum_1100_absolute_move")
    envelope_multiplier = close_cfg.get("risk_envelope_multiplier")
    eleven_atr = float(eleven["atr"]) if eleven and eleven.get("atr") is not None else float("nan")
    risk_envelope = (
        eleven_move + float(envelope_multiplier) * eleven_atr
        if envelope_multiplier is not None and not math.isnan(eleven_atr)
        else None
    )
    if not close_cfg["operating"]:
        close_status = "RESEARCH ONLY — DO NOT ENTER"
        close_reason = "This symbol's Close distance is not an operating entry recommendation."
    elif close_cfg.get("allowed_reviews") and review_label not in close_cfg["allowed_reviews"]:
        close_status = "DO NOT ENTER"
        close_reason = f"Close is available only at {' or '.join(close_cfg['allowed_reviews'])} for {symbol}."
    elif overall != "ENTER":
        close_status = live_blocked_mode_status(overall)
        close_reason = description
    elif not eleven_clear:
        close_status = "DO NOT ENTER"
        close_reason = "Close is disabled because the 11:00 review was flagged or unavailable."
    elif containment_limit is not None and eleven_move >= float(containment_limit):
        close_status = "DO NOT ENTER"
        close_reason = f"The 11:00 move was {eleven_move:.2f}; it must be under {float(containment_limit):g}."
    elif envelope_multiplier is not None and (risk_envelope is None or risk_envelope >= close_distance):
        close_status = "DO NOT ENTER"
        close_reason = f"The 11:00 projected risk envelope was {risk_envelope:.2f}; it must be below {close_distance:.2f}."
    else:
        close_status = "ENTER"
        close_reason = "The symbol-specific Close requirements passed."
    modes["Close"] = {
        "status": close_status,
        "distance": close_distance,
        "call_strike": close_call,
        "put_strike": close_put,
        "reason": close_reason,
    }
    return {
        "result": overall,
        "description": description,
        "technical_clear": technical_clear,
        "modes": modes,
    }


def build_live_next_day_assessment(symbol, foundational, metrics, today_gate, next_gate):
    rules = LIVE_NEXT_DAY_RULES[symbol]
    sides = {}
    for side in ("call", "put"):
        side_rules = rules[side]
        extra = evaluate_live_next_day_tier(side_rules["extra_close"], metrics)
        regular = evaluate_live_next_day_tier(side_rules["regular_closer"], metrics)
        selected = None
        selected_name = None
        if extra["passed"]:
            selected, selected_name = extra, "Extra-Close"
        elif regular["passed"]:
            selected, selected_name = regular, "Regular Closer"
        elif rules.get("preferred_fallback") is not None:
            selected = {
                "distance": float(rules["preferred_fallback"]),
                "evidence": rules.get("preferred_fallback_evidence"),
                "passed": True,
                "conditions": [],
            }
            selected_name = "Preferred Fallback"
        if selected is None:
            strike = None
            result = "DO NOT ENTER"
            reason = "Neither approved closer tier qualified, and no separate Preferred 1DTE fallback is approved."
        else:
            _, strike = live_strike_for_distance(metrics["market_open"], selected["distance"], side)
            if not foundational["technical_clear"]:
                blocker = "FOUNDATIONAL FILTER"
            elif not today_gate["clear"]:
                blocker = "TODAY'S HEADLINE GATE"
            elif not next_gate["clear"]:
                blocker = "NEXT-TRADING-DAY RISK GATE"
            else:
                blocker = None
            if blocker:
                result = f"TOOL CONDITIONS PASSED — ENTRY BLOCKED BY {blocker}"
                reason = f"The {selected_name} conditions passed, but the {blocker.lower()} is not clear."
            else:
                result = "ENTER"
                reason = f"The {selected_name} conditions and both headline gates are clear."
        sides[side] = {
            "side": side.title(),
            "result": result,
            "selected_tier": selected_name,
            "selected_evidence": selected.get("evidence") if selected else None,
            "distance": selected["distance"] if selected else None,
            "strike": strike,
            "reason": reason,
            "tier_evaluations": {"Extra-Close": extra, "Regular Closer": regular},
        }
    overall = "ENTER — ONE OR MORE SIDES QUALIFY" if any(item["result"] == "ENTER" for item in sides.values()) else "DO NOT ENTER"
    return {"result": overall, "sides": sides}


def live_near_extreme(price, low, high, percent):
    span = high - low

    if span <= 0:
        return True

    return price <= low + span * percent or price >= high - span * percent


def build_live_15m_candles(one_minute_candles):
    if one_minute_candles.empty:
        return pd.DataFrame()

    indexed = one_minute_candles.set_index("timestamp_et")
    bars = indexed.resample(
        "15min",
        origin="start_day",
        offset="30min",
        label="left",
        closed="left",
    ).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        source_minutes=("close", "count"),
    )
    bars = bars.dropna(subset=["open", "high", "low", "close"]).reset_index()

    if bars.empty:
        return bars

    bars["trade_date"] = bars["timestamp_et"].dt.date
    bars = bars.sort_values("timestamp_et")
    previous_close = bars["close"].shift(1)
    true_range = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - previous_close).abs(),
            (bars["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    bars["true_range"] = true_range
    bars["atr_14"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return bars.reset_index(drop=True)


def select_live_review_window(day_15m, review_label):
    clocks = day_15m["timestamp_et"].dt.time

    if review_label == "11:00 AM":
        recent = day_15m[(clocks >= clock_time(9, 30)) & (clocks < clock_time(11, 0))].copy()
        full = recent.copy()
    elif review_label == "1:00 PM":
        recent = day_15m[(clocks >= clock_time(11, 30)) & (clocks < clock_time(13, 0))].copy()
        full = day_15m[(clocks >= clock_time(9, 30)) & (clocks < clock_time(13, 0))].copy()
    else:
        recent = day_15m[(clocks >= clock_time(12, 45)) & (clocks < clock_time(14, 15))].copy()
        full = day_15m[(clocks >= clock_time(9, 30)) & (clocks < clock_time(14, 15))].copy()

    return recent, full


def evaluate_live_technical_review(symbol, day_1m, day_15m, trade_date, review_label):
    cutoff = live_review_timestamp(trade_date, review_label)
    visible = day_1m[day_1m["timestamp_et"] < cutoff].copy()

    if visible.empty:
        return {"ready": False, "message": "No regular-session candles are available for this review."}

    first_timestamp = visible.iloc[0]["timestamp_et"]
    if first_timestamp.time() != clock_time(9, 30):
        return {
            "ready": False,
            "message": "The 9:30 AM opening candle is missing, so the fixed opening price cannot be verified.",
        }

    recent, full = select_live_review_window(day_15m, review_label)
    if recent.empty or len(recent) < 6:
        return {
            "ready": False,
            "message": f"The {review_label} review needs six completed 15-minute candles.",
        }

    recent = recent.tail(6).copy()
    if "source_minutes" in recent and (recent["source_minutes"] < 15).any():
        return {
            "ready": False,
            "message": (
                f"The {review_label} candle set is still incomplete or has a one-minute data gap. "
                "Wait briefly, then rerun the live check."
            ),
        }

    atr = recent.iloc[-1]["atr_14"]
    if pd.isna(atr):
        return {
            "ready": False,
            "message": "ATR(14) is unavailable because the live history did not include enough warm-up candles.",
        }

    rules = LIVE_FOUNDATIONAL_RULES[symbol]
    thresholds = rules[review_label]
    market_open = float(visible.iloc[0]["open"])
    review_price = float(recent.iloc[-1]["close"])
    signed_move = review_price - market_open
    move = abs(signed_move)
    bodies = (recent["close"] - recent["open"]).abs()
    max_body = float(bodies.max())
    churn = float(bodies.sum())
    near_recent = live_near_extreme(
        review_price,
        float(recent["low"].min()),
        float(recent["high"].max()),
        rules["near_extreme_percent"],
    )
    near_full = live_near_extreme(
        review_price,
        float(full["low"].min()),
        float(full["high"].max()),
        rules["near_extreme_percent"],
    )

    inclusive = symbol in {"XND"}
    atr_inclusive = symbol in {"SPY", "XND"}
    churn_inclusive = symbol in {"SPY", "XND"}
    impulse_triggered = max_body >= thresholds["impulse"] if inclusive else max_body > thresholds["impulse"]
    atr_threshold_met = float(atr) >= thresholds["atr"] if atr_inclusive else float(atr) > thresholds["atr"]
    combined_activity_gate = bool(thresholds.get("combined_activity_gate"))
    atr_triggered = atr_threshold_met and not combined_activity_gate
    churn_threshold_met = churn >= thresholds["churn"] if churn_inclusive else churn > thresholds["churn"]
    displacement_threshold_met = move >= thresholds["displacement"] if churn_inclusive else move > thresholds["displacement"]
    churn_triggered = churn_threshold_met and (
        displacement_threshold_met or (combined_activity_gate and atr_threshold_met)
    )

    triggers = []
    if impulse_triggered and near_recent:
        comparison = ">=" if inclusive else ">"
        triggers.append(
            f"Large impulse still holding: body {max_body:.2f} {comparison} "
            f"{thresholds['impulse']:.2f}, with price near the recent extreme."
        )
    if atr_triggered:
        comparison = ">=" if atr_inclusive else ">"
        triggers.append(f"Extreme ATR: {float(atr):.2f} {comparison} {thresholds['atr']:.2f}.")
    if churn_triggered and combined_activity_gate:
        if displacement_threshold_met:
            qualifying_context = f"movement {move:.2f} > {thresholds['displacement']:.2f}"
        else:
            qualifying_context = f"ATR {float(atr):.2f} > {thresholds['atr']:.2f}"
        triggers.append(
            f"Exceptional activity: churn {churn:.2f} > {thresholds['churn']:.2f} "
            f"with {qualifying_context}."
        )
    elif churn_triggered:
        comparison = ">=" if churn_inclusive else ">"
        triggers.append(
            f"Heavy churn plus displacement: churn {churn:.2f} {comparison} "
            f"{thresholds['churn']:.2f} and move {move:.2f} {comparison} "
            f"{thresholds['displacement']:.2f}."
        )

    persistent = thresholds.get("persistent_trend")
    if persistent is not None and move >= persistent and near_full:
        triggers.append(
            f"Persistent aggressive trend: move {move:.2f} >= {persistent:.2f}, "
            "with price near the full-session extreme."
        )

    flagged = bool(triggers)
    if flagged and review_label == "11:00 AM":
        decision = "WAIT UNTIL 1:00 PM"
    elif flagged and review_label == "1:00 PM":
        decision = "WAIT UNTIL 2:15 PM"
    elif flagged:
        decision = "SKIP THE DAY"
    else:
        decision = "CLEAR TO ENTER"

    return {
        "ready": True,
        "flagged": flagged,
        "decision": decision,
        "market_open": market_open,
        "review_price": review_price,
        "signed_move": signed_move,
        "move_from_open": move,
        "atr": float(atr),
        "reasons": triggers if triggers else ["No technical danger rule triggered."],
        "metrics": {
            "max_body": max_body,
            "churn": churn,
            "near_recent_extreme": near_recent,
            "near_full_extreme": near_full,
            "persistent_threshold": persistent,
        },
        "recent_bars": recent,
    }


async def download_tastytrade_candle_events(symbol, start_time):
    try:
        from tastytrade import DXLinkStreamer, Session
        from tastytrade.dxfeed import Candle
        from tastytrade.instruments import Equity
    except ImportError as exc:
        raise RuntimeError(
            "The tastytrade candle package is not installed. Add tastytrade==13.2.3 to requirements.txt."
        ) from exc

    provider_secret = get_tastytrade_secret_value("client_secret")
    refresh_token = get_tastytrade_secret_value("refresh_token")
    if not provider_secret or not refresh_token:
        raise RuntimeError("Tastytrade client_secret and refresh_token must be loaded in Streamlit Secrets.")

    streamer_symbol = symbol
    resolution_note = ""
    candles = []
    snapshot_complete = False
    snapshot_snipped = False

    async with Session(provider_secret, refresh_token) as session:
        try:
            instrument = await Equity.get(session, symbol)
            streamer_symbol = str(getattr(instrument, "streamer_symbol", "") or symbol).strip()
        except Exception as exc:
            resolution_note = f"Instrument lookup used the raw {symbol} symbol: {exc}"

        async with DXLinkStreamer(session) as streamer:
            await streamer.subscribe_candle(
                [streamer_symbol],
                "1m",
                start_time=start_time,
                extended_trading_hours=False,
                refresh_interval=0.1,
            )
            deadline = time.monotonic() + 55.0

            while len(candles) < 60000:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break

                try:
                    candle = await asyncio.wait_for(
                        streamer.get_event(Candle),
                        timeout=min(5.0, remaining),
                    )
                except TimeoutError:
                    break

                if not candle.remove:
                    candles.append(candle)

                if candle.snapshot_end or candle.snapshot_snip:
                    snapshot_complete = True
                    snapshot_snipped = bool(candle.snapshot_snip)
                    break

    if not snapshot_complete and not candles:
        raise RuntimeError(
            f"Tastytrade did not finish the {symbol} candle snapshot within the live-app limit. "
            "Choose a more recent date or tap RUN LIVE TECHNICAL CHECK again."
        )

    return {
        "candles": candles,
        "streamer_symbol": streamer_symbol,
        "snapshot_snipped": snapshot_snipped,
        "snapshot_incomplete": not snapshot_complete,
        "resolution_note": resolution_note,
    }


def candle_events_to_dataframe(candle_payload):
    rows = []

    for candle in candle_payload.get("candles", []):
        try:
            timestamp_et = pd.to_datetime(int(candle.time), unit="ms", utc=True).tz_convert(EASTERN_ZONE)
            open_price = float(candle.open)
            high_price = float(candle.high)
            low_price = float(candle.low)
            close_price = float(candle.close)
        except Exception:
            continue

        if min(open_price, high_price, low_price, close_price) <= 0:
            continue

        rows.append(
            {
                "timestamp_et": timestamp_et,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": safe_float(getattr(candle, "volume", 0), 0.0),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["timestamp_et", "open", "high", "low", "close", "volume"])

    frame = pd.DataFrame(rows).sort_values("timestamp_et")
    frame = frame.drop_duplicates(subset=["timestamp_et"], keep="last").reset_index(drop=True)
    clocks = frame["timestamp_et"].dt.time
    frame = frame[(clocks >= clock_time(9, 30)) & (clocks < clock_time(16, 0))].copy()
    frame["trade_date"] = frame["timestamp_et"].dt.date
    return frame.reset_index(drop=True)


def fetch_live_technical_analysis(
    symbol,
    review_label,
    trade_date,
    now_et,
    today_headline_status,
    next_headline_status,
):
    target_time = live_analysis_timestamp(trade_date, review_label)

    if trade_date > now_et.date():
        return {"error": "A future trading date cannot be analyzed."}
    if trade_date == now_et.date() and now_et < target_time:
        return {
            "error": (
                f"{review_label} is not ready yet. It will use only candles completed before "
                f"{format_live_clock(target_time)}."
            )
        }

    warmup_date = trade_date - timedelta(days=8)
    start_time = datetime.combine(warmup_date, clock_time(9, 30), tzinfo=EASTERN_ZONE)

    try:
        candle_payload = asyncio.run(download_tastytrade_candle_events(symbol, start_time))
    except Exception as exc:
        return {"error": f"Live/historical candle data unavailable for {symbol}: {exc}"}

    all_1m = candle_events_to_dataframe(candle_payload)
    if all_1m.empty:
        return {"error": f"Tastytrade returned no usable regular-session candles for {symbol}."}

    available_dates = sorted(all_1m["trade_date"].unique())
    all_15m = build_live_15m_candles(all_1m)
    day_1m = all_1m[all_1m["trade_date"] == trade_date].copy()
    day_15m = all_15m[all_15m["trade_date"] == trade_date].copy()
    if day_1m.empty or day_15m.empty:
        first_date = available_dates[0] if available_dates else "none"
        last_date = available_dates[-1] if available_dates else "none"
        return {
            "error": (
                f"NO DATA for {symbol} on {trade_date}. The returned Tastytrade candle set covered "
                f"{first_date} through {last_date}. Choose another trading day."
            )
        }

    movement = build_market_movement_assessment(
        symbol,
        all_1m,
        all_15m,
        trade_date,
        review_label,
        today_headline_status,
        fomc_day=trade_date in LIVE_FOMC_DATES,
        automatic_event=None,
        include_historical_outcome=False,
    )

    golden_review_label = applicable_live_golden_review(review_label)
    reviews = {}
    next_trading_date = get_live_next_trading_date(available_dates, trade_date)
    result = None
    golden_error = None
    today_gate = None
    next_gate = None
    foundational = None
    metrics = None
    next_day = None
    directional = None

    if golden_review_label:
        review_order = list(LIVE_REVIEW_TIMES)
        selected_index = review_order.index(golden_review_label)
        for label in review_order[: selected_index + 1]:
            label_time = live_review_timestamp(trade_date, label)
            if trade_date < now_et.date() or now_et >= label_time:
                reviews[label] = evaluate_live_technical_review(
                    symbol,
                    day_1m,
                    day_15m,
                    trade_date,
                    label,
                )

        result = reviews.get(golden_review_label)
        if not result:
            golden_error = f"The {golden_review_label} Golden review is not ready."
        elif not result.get("ready"):
            golden_error = result.get(
                "message",
                "The Golden technical review could not be completed.",
            )
        else:
            today_gate = build_live_headline_gate(
                trade_date,
                today_headline_status,
                golden_review_label,
                holding_window=False,
            )
            next_gate = build_live_headline_gate(
                next_trading_date,
                next_headline_status,
                golden_review_label,
                holding_window=True,
            )
            foundational = build_live_foundational_assessment(
                symbol,
                golden_review_label,
                result,
                reviews,
                today_gate,
            )
            metrics = build_live_morning_metrics(day_15m, result)
            next_day = build_live_next_day_assessment(
                symbol,
                foundational,
                metrics,
                today_gate,
                next_gate,
            )
            directional = build_live_directional_opportunity(
                symbol,
                day_1m,
                today_gate,
                reviews,
                exact_eleven_ready=(
                    trade_date < now_et.date()
                    or now_et >= datetime.combine(
                        trade_date,
                        clock_time(11, 1),
                        tzinfo=EASTERN_ZONE,
                    )
                ),
            )

    return {
        "symbol": symbol,
        "review_label": review_label,
        "golden_review_label": golden_review_label,
        "golden_error": golden_error,
        "trade_date": trade_date,
        "next_trading_date": next_trading_date,
        "movement": movement,
        "result": result,
        "reviews": reviews,
        "foundational": foundational,
        "directional": directional,
        "next_day": next_day,
        "today_gate": today_gate,
        "next_gate": next_gate,
        "metrics": metrics,
        "day_1m": day_1m,
        "day_15m": day_15m,
        "last_candle_time": day_1m["timestamp_et"].max(),
        "available_first_date": available_dates[0],
        "available_last_date": available_dates[-1],
        "streamer_symbol": candle_payload.get("streamer_symbol", symbol),
        "snapshot_snipped": candle_payload.get("snapshot_snipped", False),
        "snapshot_incomplete": candle_payload.get("snapshot_incomplete", False),
        "resolution_note": candle_payload.get("resolution_note", ""),
    }


def resample_live_chart_candles(day_1m, interval, cutoff):
    visible = day_1m[day_1m["timestamp_et"] < cutoff].copy()
    if interval == "1min" or visible.empty:
        return visible[["timestamp_et", "open", "high", "low", "close", "volume"]].copy()
    candles = visible.set_index("timestamp_et").resample(
        interval,
        origin="start_day",
        offset="30min",
        label="left",
        closed="left",
    ).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return candles.dropna(subset=["open", "high", "low", "close"]).reset_index()


def build_live_candlestick_chart(candles, symbol, trade_date, market_open, interval_label):
    frame = candles.copy()
    frame["Direction"] = frame["close"].ge(frame["open"]).map({True: "Up", False: "Down"})
    tooltip = [
        alt.Tooltip("timestamp_et:T", title="Time ET", format="%I:%M %p"),
        alt.Tooltip("open:Q", title="Open", format=",.2f"),
        alt.Tooltip("high:Q", title="High", format=",.2f"),
        alt.Tooltip("low:Q", title="Low", format=",.2f"),
        alt.Tooltip("close:Q", title="Close", format=",.2f"),
    ]
    x_axis = alt.X(
        "timestamp_et:T",
        title="Eastern Time",
        axis=alt.Axis(format="%I:%M %p", labelAngle=-45, tickCount=10),
    )
    price_scale = alt.Scale(zero=False, padding=12)
    base = alt.Chart(frame).encode(x=x_axis, tooltip=tooltip)
    wick = base.mark_rule().encode(
        y=alt.Y("low:Q", title="Price", scale=price_scale),
        y2="high:Q",
        color=alt.Color(
            "Direction:N",
            scale=alt.Scale(domain=["Up", "Down"], range=["#16A34A", "#DC2626"]),
            legend=None,
        ),
    )
    body_size = 3 if interval_label == "1 Minute" else 8 if interval_label == "5 Minute" else 14
    bodies = base.mark_bar(size=body_size).encode(
        y=alt.Y("open:Q", scale=price_scale),
        y2="close:Q",
        color=alt.Color(
            "Direction:N",
            scale=alt.Scale(domain=["Up", "Down"], range=["#16A34A", "#DC2626"]),
            legend=None,
        ),
    )
    open_line_data = pd.DataFrame({"open_reference": [float(market_open)]})
    open_line = alt.Chart(open_line_data).mark_rule(
        color="#2563EB",
        strokeDash=[7, 5],
        size=2,
    ).encode(y=alt.Y("open_reference:Q", scale=price_scale))
    return (wick + bodies + open_line).properties(
        height=470,
        title=f"{symbol} — {trade_date} — {interval_label}",
    ).interactive(bind_y=False)


def show_live_tool_status(message):
    if str(message).startswith(("ENTER", "CLEAR", "ELIGIBLE")):
        st.success(message)
    elif str(message).startswith(("WAIT", "REVIEW", "UNAVAILABLE")):
        st.warning(message)
    else:
        st.error(message)


def precise_movement_text(value):
    number = safe_float(value, None)
    if number is None or not math.isfinite(number):
        return "—"
    return f"{number:.8f}".rstrip("0").rstrip(".")


def render_live_market_movement(movement):
    st.subheader("Market Movement Strategy — Direction Neutral")
    st.caption(
        "Uses the locked symbol-specific rule for this exact checkpoint to estimate a "
        "historical price envelope. It does not predict direction, guarantee a maximum, "
        "choose an option contract, or carry a rule forward from another time."
    )

    status = movement.get("signal_status", "NO_SIGNAL_CONDITIONS")
    if status == "ACTIVE_CURRENT_CONFIRMED":
        st.success(status)
    elif status.startswith(("SECONDARY", "RESEARCH_ONLY")):
        st.warning(status)
    else:
        st.info(status)
    st.caption(movement.get("reason", ""))

    primary = movement.get("primary_results", {})
    ordered_targets = [
        target
        for target in (TARGET_OPEN, TARGET_FRESH)
        if target in primary
    ]
    if ordered_targets:
        columns = st.columns(len(ordered_targets))
        for column, target in zip(columns, ordered_targets):
            signal = primary[target]
            label = (
                "Closest Fixed-Open Ceiling"
                if target == TARGET_OPEN
                else "Closest Fresh-Movement Ceiling"
            )
            column.metric(label, f"${signal['ceiling_points']:g}")
            column.caption(
                f"{signal['target_label']} · anchor ${signal['anchor_price']:.2f} · "
                f"envelope ${signal['lower_boundary']:.2f} to "
                f"${signal['upper_boundary']:.2f}"
            )
            column.caption(f"{signal['rule_id']} · {signal['rule_class']}")

    combined = movement.get("combined_boundary")
    if combined:
        st.info(
            "Conservative combined boundary when both independent anchor families "
            f"qualify: ${combined['lower_boundary']:.2f} to "
            f"${combined['upper_boundary']:.2f}. The formulas remain separate."
        )

    research_results = movement.get("research_results", [])
    if research_results:
        st.warning(
            "Separately labeled research-only rules passed. They are shown for context "
            "and do not replace a current-confirmed operating rule."
        )
        st.dataframe(
            [
                {
                    "TARGET": signal["target_label"],
                    "CEILING": f"${signal['ceiling_points']:g}",
                    "EVIDENCE": signal["rule_class"],
                    "ANCHOR": f"${signal['anchor_price']:.4f}",
                    "LOWER BOUNDARY": f"${signal['lower_boundary']:.4f}",
                    "UPPER BOUNDARY": f"${signal['upper_boundary']:.4f}",
                    "RULE": signal["rule_id"],
                }
                for signal in research_results
            ],
            width="stretch",
            hide_index=True,
        )

    with st.expander("Why every movement rule passed or failed"):
        st.markdown("**Gate results — evaluated in mandatory order**")
        st.dataframe(
            [
                {
                    "GATE": gate["name"],
                    "RESULT": gate["status"],
                    "PASSED": gate["passed"],
                    "REASON": gate["reason"],
                }
                for gate in movement.get("gates", [])
            ],
            width="stretch",
            hide_index=True,
        )

        feature_order = ("O", "P", "M", "R", "R60", "A1", "A15", "G", "displacement")
        feature_names = {
            "O": "9:30 open (O)",
            "P": "Last completed one-minute close (P)",
            "M": "Maximum open distance so far (M / XND D)",
            "R": "Range since open (R)",
            "R60": "Recent 60-minute range (R60)",
            "A1": "One-minute ATR(14) (A1)",
            "A15": "Completed 15-minute ATR(14) (A15)",
            "G": "Absolute overnight gap (G)",
            "displacement": "Close displacement from open",
        }
        features = movement.get("features", {})
        st.markdown("**Full-precision rule inputs**")
        st.dataframe(
            [
                {
                    "INPUT": feature_names[key],
                    "VALUE": precise_movement_text(features.get(key)),
                }
                for key in feature_order
                if key in features
            ],
            width="stretch",
            hide_index=True,
        )
        st.caption(
            "Pass/fail uses full-precision values. Display rounding never changes a result."
        )

        candidates = movement.get("candidate_evaluations", [])
        st.markdown("**Exact-time rule results**")
        if not candidates:
            st.info(
                "No approved rule exists for this symbol at this exact checkpoint. "
                "A rule from another time is never interpolated or carried forward."
            )
        else:
            candidate_rows = []
            condition_rows = []
            for candidate in candidates:
                failed = [
                    item
                    for item in candidate["condition_results"]
                    if not item["passed"]
                ]
                why = (
                    "; ".join(
                        f"{item['feature']} {precise_movement_text(item['actual'])} "
                        f"> {precise_movement_text(item['threshold'])}"
                        for item in failed
                    )
                    if failed
                    else "All required AND conditions passed at full precision."
                )
                candidate_rows.append(
                    {
                        "TARGET": TARGET_LABELS[candidate["target_kind"]],
                        "TIER": (
                            f"${candidate['ceiling']:g}"
                            if candidate["target_kind"] != "ROUNDED_STRIKE_ONLY"
                            else "$1 strike-only; not a movement cap"
                        ),
                        "EVIDENCE": candidate["evidence_class"],
                        "DECISION": candidate["decision"],
                        "WHY": why,
                        "RULE": candidate["rule_id"],
                    }
                )
                for condition in candidate["condition_results"]:
                    condition_rows.append(
                        {
                            "RULE": candidate["rule_id"],
                            "CONDITION": condition["label"],
                            "REQUIREMENT": f"<= {precise_movement_text(condition['threshold'])}",
                            "ACTUAL": precise_movement_text(condition["actual"]),
                            "PASSED": condition["passed"],
                        }
                    )
            st.dataframe(candidate_rows, width="stretch", hide_index=True)
            st.markdown("**Condition-by-condition audit**")
            st.dataframe(condition_rows, width="stretch", hide_index=True)
            st.caption(
                "Every listed condition is required. Passing two conditions never "
                "overrides a failure on the third."
            )


def render_live_directional_section(opportunity):
    st.subheader("Directional Distance Opportunity — Separate Strategy")
    st.caption(
        "Uses the fixed 9:30 opening price and the exact 11:00 one-minute close. "
        "This is displayed beside the Golden filters but is not blended into them."
    )
    show_live_tool_status(opportunity["result"])
    st.caption(opportunity["reason"])
    if opportunity.get("review_price") is not None:
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("9:30 Open", f"{opportunity['market_open']:.2f}")
        d2.metric("Exact 11:00 Price", f"{opportunity['review_price']:.2f}")
        d3.metric("Signed Move", f"{opportunity['signed_move']:+.2f}")
        d4.metric("Direction / Side", f"{opportunity['direction']} → {opportunity['option_side']}")
    if opportunity.get("candidates"):
        rows = [
            {
                "CHOICE": item["label"],
                "RISK LEVEL": item["risk_level"],
                "DISTANCE FROM 9:30 OPEN": live_strike_text(item["distance_from_open"]),
                "SHORT STRIKE": live_strike_text(item["short_strike"]),
                "DISTANCE FROM 11:00 PRICE": live_strike_text(item["distance_from_1100_price"]),
                "FIVE-YEAR CLOSING TEST AFTER KNOWN SKIPS": item["history_note"],
            }
            for item in opportunity["candidates"]
        ]
        st.dataframe(rows, width="stretch", hide_index=True)
    context_col, gate_col = st.columns(2)
    context_col.metric("11:00 Foundational Context", opportunity.get("foundational_context", "UNAVAILABLE"))
    context_col.caption("Context only; it does not gate this separate strategy.")
    gate = opportunity["headline_gate"]
    gate_col.metric("Market-Wide Headline Gate", gate["status"])
    gate_col.caption(gate["reason"])
    st.caption(opportunity["product_note"])


def render_live_foundational_section(foundational):
    st.subheader("Foundational Golden Filter")
    show_live_tool_status(foundational["result"])
    st.caption(foundational["description"])
    rows = []
    for mode in ("Standard", "Preferred", "Close"):
        item = foundational["modes"][mode]
        rows.append(
            {
                "MODE": mode,
                "RESULT": item["status"],
                "DISTANCE": live_strike_text(item["distance"]),
                "CALL SHORT STRIKE": live_strike_text(item["call_strike"]),
                "PUT SHORT STRIKE": live_strike_text(item["put_strike"]),
                "DESCRIPTION": item["reason"],
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)


def render_live_next_day_section(next_day, trade_date, next_trading_date):
    st.subheader("Next Day Expiration Golden Filter — 1DTE")
    show_live_tool_status(next_day["result"])
    st.caption(
        f"Entry date: {trade_date} | Next trading-day expiration: {next_trading_date}. "
        "Extra-Close is tested first, then Regular Closer and any approved Preferred fallback."
    )
    rows = []
    for side_key in ("call", "put"):
        item = next_day["sides"][side_key]
        rows.append(
            {
                "SIDE": item["side"],
                "RESULT": item["result"],
                "SELECTED TIER": item["selected_tier"] or "None",
                "EVIDENCE": item.get("selected_evidence") or "—",
                "DISTANCE": live_strike_text(item["distance"]),
                "SHORT STRIKE": live_strike_text(item["strike"]),
                "DESCRIPTION": item["reason"],
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)
    with st.expander("Show 1DTE tier condition details"):
        for side_key in ("call", "put"):
            item = next_day["sides"][side_key]
            st.markdown(f"**{item['side']}**")
            detail_rows = []
            for tier_name, tier in item["tier_evaluations"].items():
                for condition in tier["conditions"]:
                    detail_rows.append(
                        {
                            "TIER": tier_name,
                            "CONDITION": condition["label"],
                            "ACTUAL": live_strike_text(condition["value"]),
                            "PASSED": condition["passed"],
                            "EVIDENCE": tier.get("evidence") or "—",
                        }
                    )
            st.dataframe(detail_rows, width="stretch", hide_index=True)


def render_live_technical_status_box(decision):
    if decision == "CLEAR TO ENTER":
        background, border, foreground = "#DCFCE7", "#22C55E", "#166534"
    elif decision.startswith("WAIT"):
        background, border, foreground = "#FEF3C7", "#F59E0B", "#92400E"
    else:
        background, border, foreground = "#FEE2E2", "#EF4444", "#991B1B"

    st.markdown(
        f"""
        <div style="background:{background};border:2px solid {border};color:{foreground};
                    border-radius:14px;padding:18px 20px;text-align:center;font-size:1.65rem;
                    font-weight:950;margin:10px 0 16px 0;">
            {decision}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_live_technical_entry_check():
    now_et = datetime.now(EASTERN_ZONE)
    default_label = default_live_review_label(now_et)
    review_labels = list(MOVEMENT_REVIEW_OPTIONS)

    st.title("Live Technical Entry Check")
    st.caption(
        "Step 2 — Tastytrade regular-session candles only. Mirrors the Research Engine's "
        "Market Movement, Directional Distance, Foundational, and Next Day Expiration "
        "assessments; it never submits an order."
    )
    st.warning(
        "Technical check only: a CLEAR result does not override the separate Step 1 headline-risk report."
    )

    with st.form("live_technical_assessment_form", clear_on_submit=False):
        control_col1, control_col2, control_col3, control_col4 = st.columns(4)
        with control_col1:
            symbol = st.selectbox("Symbol", LIVE_TECHNICAL_SYMBOLS, key="live_technical_symbol")
        with control_col2:
            selected_date = st.date_input(
                "Trading Date",
                value=now_et.date(),
                min_value=date(2001, 9, 9),
                max_value=now_et.date(),
                key="live_technical_date",
                help="Choose any past date. The app will report NO DATA if Tastytrade cannot return it.",
            )
        with control_col3:
            review_label = st.selectbox(
                "Analysis Checkpoint",
                review_labels,
                index=review_labels.index(default_label),
                key="live_technical_review_label",
            )
        with control_col4:
            chart_interval_label = st.selectbox(
                "Chart Timeframe",
                list(LIVE_CHART_INTERVALS),
                index=2,
                key="live_technical_chart_interval",
            )

        st.markdown("**Step 1 Headline Results — enter the conclusions from your separate phone report**")
        gate_col1, gate_col2 = st.columns(2)
        with gate_col1:
            today_headline_status = st.selectbox(
                "Selected trading day / 0DTE",
                LIVE_HEADLINE_OPTIONS,
                key="live_today_headline_status",
                help="Monitor allows entry when the technical engine is clear. Wait delays entry; Suggest skip blocks it.",
            )
        with gate_col2:
            next_headline_status = st.selectbox(
                "Next trading day / 1DTE holding window",
                LIVE_HEADLINE_OPTIONS,
                key="live_next_headline_status",
                help="The 1DTE tool requires both today's and the next trading day's headline gates to permit entry.",
            )
        run_clicked = st.form_submit_button(
            "RUN COMPLETE TECHNICAL ASSESSMENT",
            type="primary",
            width="stretch",
        )

    st.caption(
        "The Market Movement rule runs only at the exact selected checkpoint. Before "
        "11:00 AM it is the only strategy that runs. At and after 11:00 AM, the latest "
        "applicable Golden and Directional checkpoint also runs."
    )

    st.caption(
        f"Current Eastern time: {now_et.strftime('%A, %B %d, %Y at ')}"
        f"{format_live_clock(now_et, include_seconds=True)} | "
        "After-hours prices are excluded. The date picker has no short artificial lookback; returned history depends on Tastytrade."
    )

    request_key = (
        symbol,
        selected_date.isoformat(),
        review_label,
        chart_interval_label,
        today_headline_status,
        next_headline_status,
    )
    if run_clicked:
        with st.spinner(
            f"Pulling {symbol} one-minute candles for {selected_date} and running all technical tools..."
        ):
            payload = fetch_live_technical_analysis(
                symbol,
                review_label,
                selected_date,
                now_et,
                today_headline_status,
                next_headline_status,
            )
        st.session_state["live_technical_payload"] = payload
        st.session_state["live_technical_request_key"] = request_key

    payload = st.session_state.get("live_technical_payload")
    cached_key = st.session_state.get("live_technical_request_key")

    if not payload or cached_key != request_key:
        st.info("Choose the symbol, date, checkpoint, and headline results, then run the complete assessment.")
        return

    if payload.get("error"):
        st.error(payload["error"])
        if symbol in {"XSP", "XND"}:
            st.caption(
                "Index candle availability depends on the Tastytrade/DXLink entitlement for this exact symbol. "
                "The app will not substitute SPY, QQQ, NDX, or another instrument."
            )
        return

    st.caption(
        f"Showing completed assessment: {symbol} · {selected_date} · {review_label} · {chart_interval_label} | "
        f"Candle response coverage: {payload['available_first_date']} through {payload['available_last_date']}"
    )
    render_live_market_movement(payload["movement"])

    result = payload.get("result")
    golden_review_label = payload.get("golden_review_label")
    if golden_review_label is None:
        st.info(
            "Golden and Directional strategies do not load before 11:00 AM. "
            "The exact-time Market Movement result and chart remain available."
        )
    elif payload.get("golden_error"):
        st.error(
            f"{golden_review_label} Golden checkpoint unavailable: "
            f"{payload['golden_error']}"
        )
    else:
        st.markdown("---")
        st.subheader(f"Golden Technical Checkpoint — {golden_review_label}")
        render_live_technical_status_box(result["decision"])

        metric_col1, metric_col2, metric_col3, metric_col4, metric_col5, metric_col6 = st.columns(6)
        metric_col1.metric("9:30 Open", f"{result['market_open']:.2f}")
        metric_col2.metric("Review Price", f"{result['review_price']:.2f}")
        metric_col3.metric("Move From Open", f"{result['move_from_open']:.2f}")
        metric_col4.metric("ATR(14), 15m", f"{result['atr']:.2f}")
        metric_col5.metric("Largest 15m Body", f"{result['metrics']['max_body']:.2f}")
        metric_col6.metric("Six-Candle Churn", f"{result['metrics']['churn']:.2f}")

        direction = "ABOVE" if result["signed_move"] > 0 else "BELOW" if result["signed_move"] < 0 else "AT"
        st.write(
            f"**Golden checkpoint:** {golden_review_label} &nbsp; | &nbsp; "
            f"**Price is {direction} the open by {abs(result['signed_move']):.2f}**"
        )

        if result["flagged"]:
            st.subheader("Why the review was flagged")
        else:
            st.subheader("Technical rule result")
        for reason in result["reasons"]:
            st.write(f"• {reason}")

        st.subheader("Headline Gate Summary")
        today_gate_col, next_gate_col = st.columns(2)
        today_gate_col.metric("Selected Day / 0DTE", payload["today_gate"]["status"])
        today_gate_col.caption(payload["today_gate"]["reason"])
        next_gate_col.metric("Next Trading Day / 1DTE", payload["next_gate"]["status"])
        next_gate_col.caption(payload["next_gate"]["reason"])

        render_live_directional_section(payload["directional"])
        render_live_foundational_section(payload["foundational"])
        render_live_next_day_section(
            payload["next_day"],
            payload["trade_date"],
            payload["next_trading_date"],
        )

    target = live_analysis_timestamp(payload["trade_date"], review_label)
    chart_candles = resample_live_chart_candles(
        payload["day_1m"],
        LIVE_CHART_INTERVALS[chart_interval_label],
        target,
    )
    if not chart_candles.empty:
        st.subheader("Price Chart Through the Selected Checkpoint")
        st.caption("Green/red candles use the actual session price range. The dashed blue line is the fixed 9:30 opening price.")
        market_open = (
            result["market_open"]
            if result and result.get("ready")
            else safe_float(payload["movement"].get("features", {}).get("O"), None)
        )
        if market_open is None:
            market_open = float(payload["day_1m"].sort_values("timestamp_et").iloc[0]["open"])
        st.altair_chart(
            build_live_candlestick_chart(
                chart_candles,
                symbol,
                selected_date,
                market_open,
                chart_interval_label,
            ),
            width="stretch",
        )

    review_rows = []
    for label, review in payload["reviews"].items():
        review_rows.append(
            {
                "CHECKPOINT": label,
                "RESULT": review.get("decision") if review.get("ready") else review.get("message", "NOT READY"),
                "ATR": round(review.get("atr"), 2) if review.get("ready") else None,
                "MOVE FROM OPEN": round(review.get("move_from_open"), 2) if review.get("ready") else None,
            }
        )
    if review_rows:
        st.subheader("Golden Checkpoints Through the Selected Analysis Time")
        st.dataframe(review_rows, width="stretch", hide_index=True)

    if result and result.get("ready"):
        with st.expander("Show the six Golden 15-minute bars and calculation inputs"):
            detail = result["recent_bars"].copy()
            detail["Time ET"] = detail["timestamp_et"].dt.strftime("%I:%M %p").str.lstrip("0")
            detail["Body"] = (detail["close"] - detail["open"]).abs()
            detail = detail[["Time ET", "open", "high", "low", "close", "Body", "true_range", "atr_14"]]
            detail.columns = ["TIME ET", "OPEN", "HIGH", "LOW", "CLOSE", "BODY", "TRUE RANGE", "ATR(14)"]
            st.dataframe(detail, width="stretch", hide_index=True)

    st.caption(
        f"Tastytrade streamer symbol: {payload['streamer_symbol']} | "
        f"Last candle on selected date: {format_live_clock(payload['last_candle_time'])} | "
        "ATR uses Wilder smoothing: EWM alpha = 1/14."
    )
    if payload.get("snapshot_snipped"):
        st.warning("Tastytrade marked the candle history snapshot as limited. The calculation used the returned history only.")
    if payload.get("snapshot_incomplete"):
        st.warning(
            "The historical snapshot reached the live-app time limit. The selected session and ATR warm-up "
            "were complete enough to calculate, but the displayed response-coverage dates are not the API's full archive."
        )


# ==================================================
# OPTIONS OPPORTUNITY BOARD — TASTYTRADE READ-ONLY
# ==================================================

TASTYTRADE_BASE_URL = "https://api.tastyworks.com"

# Kept in display order so the scanner selector is grouped by instrument type.
# The API still receives only the raw ticker symbol.
OPTIONS_SYMBOL_CATALOG = [
    # Major symbols
    {"symbol": "QQQ", "instrument_type": "ETF"},
    {"symbol": "SPY", "instrument_type": "ETF"},
    {"symbol": "XSP", "instrument_type": "INDEX"},
    {"symbol": "XND", "instrument_type": "INDEX"},
    # Other ETFs
    {"symbol": "IWM", "instrument_type": "ETF"},
    {"symbol": "DIA", "instrument_type": "ETF"},
    {"symbol": "TLT", "instrument_type": "ETF"},
    # Other index options
    {"symbol": "SPXW", "instrument_type": "INDEX"},
    {"symbol": "NDXP", "instrument_type": "INDEX"},
    {"symbol": "RUTW", "instrument_type": "INDEX"},
    {"symbol": "MRUT", "instrument_type": "INDEX"},
    # Stocks
    {"symbol": "SOFI", "instrument_type": "STOCK"},
    {"symbol": "RKLB", "instrument_type": "STOCK"},
    {"symbol": "F", "instrument_type": "STOCK"},
]

OPTIONS_SYMBOL_LABEL_BY_TICKER = {
    item["symbol"]: f'{item["symbol"]} - {item["instrument_type"]}'
    for item in OPTIONS_SYMBOL_CATALOG
}
OPTIONS_SYMBOL_TICKER_BY_LABEL = {
    label: ticker
    for ticker, label in OPTIONS_SYMBOL_LABEL_BY_TICKER.items()
}
OPTIONS_SYMBOL_SELECTOR_OPTIONS = list(OPTIONS_SYMBOL_TICKER_BY_LABEL.keys())
OPTIONS_SYMBOL_DEFAULT_LABELS = [
    OPTIONS_SYMBOL_LABEL_BY_TICKER["QQQ"],
    OPTIONS_SYMBOL_LABEL_BY_TICKER["SPY"],
    OPTIONS_SYMBOL_LABEL_BY_TICKER["XSP"],
]


def normalize_options_selector_symbols(selected_values):
    """Convert older raw-ticker session values to the new readable labels."""
    if not isinstance(selected_values, list):
        return list(OPTIONS_SYMBOL_DEFAULT_LABELS)

    normalized_labels = []

    for selected_value in selected_values:
        value = str(selected_value or "").strip().upper()

        if selected_value in OPTIONS_SYMBOL_TICKER_BY_LABEL:
            label = selected_value
        elif value in OPTIONS_SYMBOL_LABEL_BY_TICKER:
            label = OPTIONS_SYMBOL_LABEL_BY_TICKER[value]
        else:
            continue

        if label not in normalized_labels:
            normalized_labels.append(label)

    return normalized_labels


def ensure_options_selector_state():
    state_key = "options_board_symbols"

    if state_key not in st.session_state:
        st.session_state[state_key] = list(OPTIONS_SYMBOL_DEFAULT_LABELS)
        return

    normalized_labels = normalize_options_selector_symbols(st.session_state.get(state_key))

    if normalized_labels != st.session_state.get(state_key):
        st.session_state[state_key] = normalized_labels


def get_options_tickers_from_labels(selected_labels):
    return [
        OPTIONS_SYMBOL_TICKER_BY_LABEL[label]
        for label in selected_labels
        if label in OPTIONS_SYMBOL_TICKER_BY_LABEL
    ]


def is_options_board_open():
    try:
        return st.query_params.get("options_board") == "1"
    except Exception:
        params = st.experimental_get_query_params()
        return params.get("options_board", ["0"])[0] == "1"


def get_tastytrade_secret_value(secret_name, default=""):
    try:
        tastytrade_secrets = st.secrets.get("tastytrade", {})
        value = tastytrade_secrets.get(secret_name, default)
        return str(value or "").strip()
    except Exception:
        return default


def get_tastytrade_credentials_status():
    client_id = get_tastytrade_secret_value("client_id")
    client_secret = get_tastytrade_secret_value("client_secret")
    refresh_token = get_tastytrade_secret_value("refresh_token")

    return {
        "client_id_loaded": bool(client_id),
        "client_secret_loaded": bool(client_secret),
        "refresh_token_loaded": bool(refresh_token),
    }


def get_tastytrade_access_token(force_refresh=False):
    now_epoch = time.time()
    cached_token = st.session_state.get("tastytrade_access_token")
    cached_expiration = float(st.session_state.get("tastytrade_access_token_expires_at", 0) or 0)

    if cached_token and not force_refresh and cached_expiration > now_epoch + 60:
        return cached_token, None

    client_id = get_tastytrade_secret_value("client_id")
    client_secret = get_tastytrade_secret_value("client_secret")
    refresh_token = get_tastytrade_secret_value("refresh_token")

    missing_fields = []

    if not client_id:
        missing_fields.append("client_id")
    if not client_secret:
        missing_fields.append("client_secret")
    if not refresh_token:
        missing_fields.append("refresh_token")

    if missing_fields:
        return None, f"Missing Tastytrade Streamlit secrets: {', '.join(missing_fields)}"

    token_url = f"{TASTYTRADE_BASE_URL}/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    try:
        response = requests.post(
            token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )

        if response.status_code >= 400:
            # Some OAuth servers prefer JSON payloads. Try once before surfacing the error.
            json_response = requests.post(
                token_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )

            if json_response.status_code < 400:
                response = json_response
            else:
                return None, f"Token request failed: {response.status_code} {response.text[:500]}"

        data = response.json()
        access_token = data.get("access_token") or data.get("access-token")
        expires_in = safe_float(data.get("expires_in", data.get("expires-in", 900)), 900)

        if not access_token:
            return None, f"Token response did not include an access token: {str(data)[:500]}"

        st.session_state["tastytrade_access_token"] = access_token
        st.session_state["tastytrade_access_token_expires_at"] = now_epoch + max(float(expires_in), 60)

        return access_token, None

    except Exception as exc:
        return None, f"Token request error: {exc}"


def tastytrade_api_get(path, params=None, force_token_refresh=False):
    access_token, token_error = get_tastytrade_access_token(force_refresh=force_token_refresh)

    if token_error:
        return None, token_error

    url = f"{TASTYTRADE_BASE_URL}{path}"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    try:
        response = requests.get(
            url,
            params=params or {},
            headers=headers,
            timeout=20,
        )

        if response.status_code == 401 and not force_token_refresh:
            return tastytrade_api_get(path, params=params, force_token_refresh=True)

        if response.status_code >= 400:
            return None, f"GET {path} failed: {response.status_code} {response.text[:500]}"

        return response.json(), None

    except Exception as exc:
        return None, f"GET {path} error: {exc}"


def extract_tastytrade_items(response_json):
    if not isinstance(response_json, dict):
        return []

    data = response_json.get("data")

    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return items
        if isinstance(items, dict):
            return [items]
        return [data]

    if isinstance(data, list):
        return data

    items = response_json.get("items")

    if isinstance(items, list):
        return items

    return []


def normalize_tastytrade_symbol_key(symbol):
    return re.sub(r"\s+", " ", str(symbol or "").strip())


def fetch_tastytrade_market_data(symbols_by_type):
    all_items = []
    errors = []

    instrument_type_aliases = {
        "stock": "equity",
        "stocks": "equity",
        "option": "equity-option",
        "options": "equity-option",
        "equity_option": "equity-option",
        "equity-options": "equity-option",
        "future_option": "future-option",
        "future-options": "future-option",
    }

    for requested_instrument_type, symbols in symbols_by_type.items():
        instrument_type = instrument_type_aliases.get(str(requested_instrument_type), str(requested_instrument_type))
        clean_symbols = [str(symbol).strip() for symbol in symbols if str(symbol).strip()]

        if not clean_symbols:
            continue

        for batch_start in range(0, len(clean_symbols), 95):
            symbol_batch = clean_symbols[batch_start:batch_start + 95]
            params = {instrument_type: ",".join(symbol_batch)}
            response_json, error = tastytrade_api_get("/market-data/by-type", params=params)

            if error:
                errors.append(error)
                continue

            all_items.extend(extract_tastytrade_items(response_json))

    market_data_by_symbol = {}

    for item in all_items:
        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol") or item.get("instrument-symbol")

        if symbol:
            market_data_by_symbol[str(symbol)] = item
            market_data_by_symbol[normalize_tastytrade_symbol_key(symbol)] = item

    return market_data_by_symbol, errors


def fetch_tastytrade_nested_option_chain(symbol):
    response_json, error = tastytrade_api_get(f"/option-chains/{symbol}/nested")

    if error:
        return None, error

    items = extract_tastytrade_items(response_json)

    if items:
        return items[0], None

    data = response_json.get("data") if isinstance(response_json, dict) else None

    if isinstance(data, dict):
        return data, None

    return None, f"No option chain data returned for {symbol}."


def get_tastytrade_expirations_from_chain(chain_data):
    if not isinstance(chain_data, dict):
        return []

    expirations = chain_data.get("expirations") or chain_data.get("expiration") or []

    if isinstance(expirations, list):
        return expirations

    return []


def normalize_tastytrade_expiration_date(expiration):
    if not isinstance(expiration, dict):
        return ""

    return str(
        expiration.get("expiration-date")
        or expiration.get("expiration_date")
        or expiration.get("expires-at", "")[:10]
        or ""
    )


def get_tastytrade_strikes_from_expiration(expiration):
    if not isinstance(expiration, dict):
        return []

    strikes = expiration.get("strikes") or expiration.get("strike") or []

    if isinstance(strikes, list):
        return strikes

    return []


def normalize_tastytrade_option_legs(expiration):
    expiration_date = normalize_tastytrade_expiration_date(expiration)
    strike_rows = []

    for strike_item in get_tastytrade_strikes_from_expiration(expiration):
        if not isinstance(strike_item, dict):
            continue

        strike_price = safe_float(
            strike_item.get("strike-price", strike_item.get("strike_price")),
            None,
        )

        if strike_price is None:
            continue

        call_symbol = (
            strike_item.get("call")
            or strike_item.get("call-symbol")
            or strike_item.get("call_symbol")
        )
        put_symbol = (
            strike_item.get("put")
            or strike_item.get("put-symbol")
            or strike_item.get("put_symbol")
        )

        if call_symbol or put_symbol:
            strike_rows.append({
                "expiration": expiration_date,
                "strike": float(strike_price),
                "call_symbol": call_symbol,
                "put_symbol": put_symbol,
            })

    return sorted(strike_rows, key=lambda row: row["strike"])


def tastytrade_quote_float(quote, field_name, default=0.0):
    if not isinstance(quote, dict):
        return default

    return safe_float(quote.get(field_name), default)


def get_tastytrade_quote_price(quote):
    if not isinstance(quote, dict):
        return 0.0

    for field_name in ["last", "mark", "mid", "close", "bid", "ask"]:
        value = safe_float(quote.get(field_name), 0.0)
        if value > 0:
            return value

    return 0.0


def get_tastytrade_quote_open_price(quote):
    if not isinstance(quote, dict):
        return 0.0

    for field_name in ["open", "open-price", "open_price", "day-open-price"]:
        value = safe_float(quote.get(field_name), 0.0)
        if value > 0:
            return value

    return 0.0


def calculate_tastytrade_spread_flag(short_quote, long_quote, credit, bid_ask_width):
    if not short_quote or not long_quote:
        return "Missing quote"

    if credit <= 0:
        return "No credit"

    if bid_ask_width >= 0.25:
        return "Wide quotes"

    if bid_ask_width >= 0.10:
        return "Medium quotes"

    return "Quoted"


def build_tastytrade_spread_rows(selected_symbols, selected_expiration_date, selected_sides, selected_widths):
    board_rows = []
    errors = []

    equity_quotes, equity_errors = fetch_tastytrade_market_data({"equity": selected_symbols})
    errors.extend(equity_errors)

    selected_expiration_date = str(selected_expiration_date or "").strip()

    for symbol in selected_symbols:
        symbol = str(symbol).upper().strip()
        underlying_quote = equity_quotes.get(symbol, {})
        current_price = get_tastytrade_quote_price(underlying_quote)
        open_price = get_tastytrade_quote_open_price(underlying_quote)

        chain_data, chain_error = fetch_tastytrade_nested_option_chain(symbol)

        if chain_error:
            errors.append(chain_error)
            continue

        expirations = get_tastytrade_expirations_from_chain(chain_data)
        expiration_dates = [normalize_tastytrade_expiration_date(exp) for exp in expirations]
        expiration_dates = [date for date in expiration_dates if date]

        target_dates = [selected_expiration_date] if selected_expiration_date else []

        if selected_expiration_date and selected_expiration_date not in expiration_dates:
            available_preview = ", ".join(expiration_dates[:12])
            if len(expiration_dates) > 12:
                available_preview += ", ..."
            errors.append(
                f"{symbol}: selected expiration {selected_expiration_date} was not found in the Tastytrade option chain. "
                f"Available expirations: {available_preview or 'none'}"
            )
            continue

        expiration_lookup = {
            normalize_tastytrade_expiration_date(expiration): expiration
            for expiration in expirations
        }

        for expiration_date in target_dates:
            expiration = expiration_lookup.get(expiration_date)

            if not expiration:
                continue

            strike_rows = normalize_tastytrade_option_legs(expiration)

            if not strike_rows:
                errors.append(f"{symbol} {expiration_date}: no strike rows found in nested option chain.")
                continue

            symbol_lookup_by_strike = {
                round(row["strike"], 6): row
                for row in strike_rows
            }

            needed_option_symbols = set()
            candidate_spreads = []

            for row in strike_rows:
                short_strike = float(row["strike"])

                for width in selected_widths:
                    width = float(width)

                    if "Put Credit" in selected_sides:
                        long_strike = round(short_strike - width, 6)
                        long_row = symbol_lookup_by_strike.get(long_strike)

                        if long_row and row.get("put_symbol") and long_row.get("put_symbol"):
                            short_symbol = row["put_symbol"]
                            long_symbol = long_row["put_symbol"]
                            needed_option_symbols.add(short_symbol)
                            needed_option_symbols.add(long_symbol)
                            candidate_spreads.append({
                                "symbol": symbol,
                                "expiration": expiration_date,
                                "side": "Put Credit",
                                "current_price": current_price,
                                "short_strike": short_strike,
                                "long_strike": float(long_strike),
                                "spread_width": width,
                                "short_symbol": short_symbol,
                                "long_symbol": long_symbol,
                            })

                    if "Call Credit" in selected_sides:
                        long_strike = round(short_strike + width, 6)
                        long_row = symbol_lookup_by_strike.get(long_strike)

                        if long_row and row.get("call_symbol") and long_row.get("call_symbol"):
                            short_symbol = row["call_symbol"]
                            long_symbol = long_row["call_symbol"]
                            needed_option_symbols.add(short_symbol)
                            needed_option_symbols.add(long_symbol)
                            candidate_spreads.append({
                                "symbol": symbol,
                                "expiration": expiration_date,
                                "side": "Call Credit",
                                "current_price": current_price,
                                "short_strike": short_strike,
                                "long_strike": float(long_strike),
                                "spread_width": width,
                                "short_symbol": short_symbol,
                                "long_symbol": long_symbol,
                            })

            option_quotes, option_errors = fetch_tastytrade_market_data({"equity-option": sorted(needed_option_symbols)})
            errors.extend(option_errors)

            if needed_option_symbols and not option_quotes:
                errors.append(
                    f"{symbol} {expiration_date}: option chain loaded, but no option bid/ask quotes returned. "
                    "This usually means the option market-data request needs adjustment or the account does not have API market-data access yet."
                )

            for spread in candidate_spreads:
                short_quote = (
                    option_quotes.get(spread["short_symbol"])
                    or option_quotes.get(normalize_tastytrade_symbol_key(spread["short_symbol"]))
                    or {}
                )
                long_quote = (
                    option_quotes.get(spread["long_symbol"])
                    or option_quotes.get(normalize_tastytrade_symbol_key(spread["long_symbol"]))
                    or {}
                )

                short_bid = tastytrade_quote_float(short_quote, "bid")
                short_ask = tastytrade_quote_float(short_quote, "ask")
                long_bid = tastytrade_quote_float(long_quote, "bid")
                long_ask = tastytrade_quote_float(long_quote, "ask")
                short_volume = tastytrade_quote_float(short_quote, "volume")
                long_volume = tastytrade_quote_float(long_quote, "volume")

                natural_credit = round(short_bid - long_ask, 4)
                short_mid = (short_bid + short_ask) / 2 if short_bid > 0 and short_ask > 0 else tastytrade_quote_float(short_quote, "mark")
                long_mid = (long_bid + long_ask) / 2 if long_bid > 0 and long_ask > 0 else tastytrade_quote_float(long_quote, "mark")
                mid_credit = round(short_mid - long_mid, 4)
                display_credit = natural_credit if natural_credit > 0 else mid_credit
                max_risk = round(float(spread["spread_width"]) - max(display_credit, 0), 4)

                if spread["side"] == "Put Credit":
                    distance_from_price = round(current_price - spread["short_strike"], 4) if current_price else 0.0
                    distance_from_open = round(open_price - spread["short_strike"], 4) if open_price else None
                else:
                    distance_from_price = round(spread["short_strike"] - current_price, 4) if current_price else 0.0
                    distance_from_open = round(spread["short_strike"] - open_price, 4) if open_price else None

                bid_ask_width = round(max(short_ask - short_bid, 0) + max(long_ask - long_bid, 0), 4)
                flag = calculate_tastytrade_spread_flag(short_quote, long_quote, natural_credit, bid_ask_width)

                board_rows.append({
                    "Symbol": spread["symbol"],
                    "Expiration": spread["expiration"],
                    "Side": spread["side"],
                    "Current": round(current_price, 4),
                    "Short Strike": spread["short_strike"],
                    "Long Strike": spread["long_strike"],
                    "Width": spread["spread_width"],
                    "Distance": distance_from_price,
                    "Credit": round(display_credit, 4),
                    "Max Risk": max_risk,
                    "Instant Credit": natural_credit,
                    "Short Bid": short_bid,
                    "Short Ask": short_ask,
                    "Long Bid": long_bid,
                    "Long Ask": long_ask,
                    "Short Vol": int(short_volume),
                    "Long Vol": int(long_volume),
                    "Quote Width": bid_ask_width,
                    "Flag": flag,
                    "Short Symbol": spread["short_symbol"],
                    "Long Symbol": spread["long_symbol"],
                    "_Open Price": round(open_price, 4) if open_price else None,
                    "_Distance From Open": distance_from_open,
                })

    board_rows = sorted(
        board_rows,
        key=lambda row: (
            -safe_float(row.get("Credit"), 0.0),
            -safe_float(row.get("Distance"), 0.0),
            str(row.get("Symbol", "")),
        ),
    )

    return board_rows, errors



def parse_options_spread_widths(widths_text):
    widths = []

    for raw_item in re.split(r"[,\s]+", str(widths_text or "")):
        cleaned = raw_item.strip()

        if not cleaned:
            continue

        try:
            width = float(cleaned)
        except Exception:
            continue

        if width <= 0:
            continue

        if width not in widths:
            widths.append(width)

    return widths


def normalize_options_credit_filter_value(value):
    value = safe_float(value, None)

    if value is None:
        return None

    return value


def parse_options_credit_range_filter(range_text):
    cleaned = str(range_text or "").strip().lower()

    if not cleaned:
        return None, None

    cleaned = (
        cleaned.replace("$", "")
        .replace("credits", "")
        .replace("credit", "")
        .replace("premiums", "")
        .replace("premium", "")
        .replace("–", "-")
        .replace("—", "-")
        .strip()
    )

    compact = re.sub(r"\s+", "", cleaned)
    compact = compact.replace("to", "-").replace(",", "-")

    number_pattern = r"\d+(?:\.\d+)?"

    range_match = re.fullmatch(
        rf"({number_pattern})-({number_pattern})",
        compact,
    )

    if range_match:
        min_credit = normalize_options_credit_filter_value(range_match.group(1))
        max_credit = normalize_options_credit_filter_value(range_match.group(2))

        if min_credit is None or max_credit is None:
            return None, "Credit Range Filter could not read one of the numbers."

        if min_credit > max_credit:
            min_credit, max_credit = max_credit, min_credit

        return {
            "min_credit": min_credit,
            "max_credit": max_credit,
            "display_text": f"{min_credit:g} to {max_credit:g}",
        }, None

    greater_match = re.fullmatch(
        rf">=?({number_pattern})|({number_pattern})\+",
        compact,
    )

    if greater_match:
        raw_value = greater_match.group(1) or greater_match.group(2)
        min_credit = normalize_options_credit_filter_value(raw_value)

        if min_credit is None:
            return None, "Credit Range Filter could not read the minimum credit."

        return {
            "min_credit": min_credit,
            "max_credit": None,
            "display_text": f">= {min_credit:g}",
        }, None

    less_match = re.fullmatch(
        rf"<=?({number_pattern})",
        compact,
    )

    if less_match:
        max_credit = normalize_options_credit_filter_value(less_match.group(1))

        if max_credit is None:
            return None, "Credit Range Filter could not read the maximum credit."

        return {
            "min_credit": None,
            "max_credit": max_credit,
            "display_text": f"<= {max_credit:g}",
        }, None

    single_match = re.fullmatch(rf"({number_pattern})", compact)

    if single_match:
        min_credit = normalize_options_credit_filter_value(single_match.group(1))

        if min_credit is None:
            return None, "Credit Range Filter could not read the credit."

        return {
            "min_credit": min_credit,
            "max_credit": None,
            "display_text": f">= {min_credit:g}",
        }, None

    return None, "Use a credit range like 0.05-0.10, 0.05 to 0.10, >=0.05, <=0.10, or 0.05+."


def apply_options_credit_range_filter(board_rows, credit_filter):
    if not credit_filter:
        return board_rows

    min_credit = credit_filter.get("min_credit")
    max_credit = credit_filter.get("max_credit")
    filtered_rows = []

    for row in board_rows:
        credit = safe_float(row.get("Credit"), None)

        if credit is None:
            continue

        if min_credit is not None and credit < min_credit:
            continue

        if max_credit is not None and credit > max_credit:
            continue

        filtered_rows.append(row)

    return filtered_rows


def format_options_number(value):
    number = safe_float(value, None)

    if number is None:
        return "—"

    if abs(number - round(number)) < 0.000001:
        return str(int(round(number)))

    return f"{number:.4f}".rstrip("0").rstrip(".")


def get_public_options_rows(board_rows):
    return [
        {
            key: value
            for key, value in row.items()
            if not str(key).startswith("_")
        }
        for row in board_rows
    ]


def is_out_of_money_credit_spread(row):
    current_price = safe_float(row.get("Current"), None)
    short_strike = safe_float(row.get("Short Strike"), None)
    if current_price is None or current_price <= 0 or short_strike is None:
        return False

    side = row.get("Side")
    if side == "Put Credit":
        return short_strike < current_price
    if side == "Call Credit":
        return short_strike > current_price
    return False


def get_positive_otm_instant_credit_rows(board_rows, symbol):
    rows = [
        row
        for row in board_rows
        if row.get("Symbol") == symbol
        and safe_float(row.get("Instant Credit"), 0.0) > 0
        and is_out_of_money_credit_spread(row)
    ]
    return sorted(
        rows,
        key=lambda row: (
            0 if row.get("Side") == "Put Credit" else 1,
            safe_float(row.get("Width"), 0.0),
            safe_float(row.get("Distance"), 0.0),
            safe_float(row.get("Short Strike"), 0.0),
        ),
    )


def render_instant_credit_calculations(board_rows, selected_symbols):
    st.markdown("---")
    st.subheader("All Positive OTM Instant Credits")
    st.caption(
        "Shows every selected-width spread with a positive natural credit (short-leg bid "
        "minus long-leg ask) whose short strike is out of the money at the current underlying "
        "price. Put short strike must be below current; Call short strike must be above current. "
        "Distance from the 9:30 open is informational and never filters a row."
    )

    for symbol in selected_symbols:
        st.markdown(f"### {symbol} Instant Credits")
        qualifying_rows = get_positive_otm_instant_credit_rows(board_rows, symbol)
        if qualifying_rows:
            summary_rows = [
                {
                    "TYPE": "PUT" if row.get("Side") == "Put Credit" else "CALL",
                    "SHORT STRIKE": format_options_number(row.get("Short Strike")),
                    "LONG STRIKE": format_options_number(row.get("Long Strike")),
                    "WIDTH": format_options_number(row.get("Width")),
                    "INSTANT CREDIT": format_options_number(row.get("Instant Credit")),
                    "DISTANCE FROM CURRENT": format_options_number(row.get("Distance")),
                    "DISTANCE FROM OPEN": format_options_number(row.get("_Distance From Open")),
                    "EXP": row.get("Expiration") or "—",
                }
                for row in qualifying_rows
            ]
            st.dataframe(
                summary_rows,
                width="stretch",
                hide_index=True,
            )
            widths = sorted({safe_float(row.get("Width"), 0.0) for row in qualifying_rows})
            st.caption(
                f"{len(qualifying_rows)} positive-credit OTM spreads shown. "
                f"Widths represented: {', '.join(format_options_number(width) for width in widths)}."
            )
        else:
            symbol_rows = [row for row in board_rows if row.get("Symbol") == symbol]
            current_is_available = any(safe_float(row.get("Current"), 0.0) > 0 for row in symbol_rows)

            if symbol_rows and not current_is_available:
                st.info(
                    f"{symbol}: the current underlying price was unavailable, so the app "
                    "could not safely determine which short strikes were OTM."
                )
            else:
                st.info(
                    f"{symbol}: no positive-credit OTM Call or Put spread is available "
                    "for the selected expiration, sides, and widths."
                )

def render_options_opportunity_board():
    st.markdown(
        """
        <style>
        .options-title {
            font-size: 1.45rem;
            font-weight: 950;
            margin-bottom: 0.15rem;
        }

        .options-help {
            font-size: 0.82rem;
            color: #5B6472;
            margin-bottom: 0.65rem;
        }

        .options-readonly-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            padding: 0.18rem 0.65rem;
            background: #DCFCE7;
            color: #166534;
            border: 1px solid #22C55E;
            font-size: 0.78rem;
            font-weight: 950;
            margin-bottom: 0.65rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="options-title">Options Opportunity Board</div>', unsafe_allow_html=True)
    st.markdown('<div class="options-readonly-badge">READ ONLY — no trade execution on this page</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="options-help">Tastytrade scanner for vertical credit spreads. Default sort is highest quoted credit/premium first. Filters control visibility only; no orders are sent.</div>',
        unsafe_allow_html=True,
    )

    credentials_status = get_tastytrade_credentials_status()

    status_col1, status_col2, status_col3 = st.columns(3)
    status_col1.metric("Client ID", "Loaded" if credentials_status["client_id_loaded"] else "Missing")
    status_col2.metric("Client Secret", "Loaded" if credentials_status["client_secret_loaded"] else "Missing")
    status_col3.metric("Refresh Token", "Loaded" if credentials_status["refresh_token_loaded"] else "Missing")

    control_col1, control_col2, control_col3, control_col4 = st.columns([1.45, 1.2, 1.2, 0.85])

    with control_col1:
        ensure_options_selector_state()
        selected_symbol_labels = st.multiselect(
            "Symbols",
            OPTIONS_SYMBOL_SELECTOR_OPTIONS,
            default=OPTIONS_SYMBOL_DEFAULT_LABELS,
            key="options_board_symbols",
            help="QQQ, SPY, XSP, and XND are listed first, followed by the remaining ETFs, indices, and stocks.",
        )
        selected_symbols = get_options_tickers_from_labels(selected_symbol_labels)

    with control_col2:
        selected_expiration_date = st.date_input(
            "Expiration Date",
            value=datetime.now().date(),
            key="options_board_expiration_date",
            help="Choose the exact option expiration date to match from Tastytrade. Today shows today's expirations; tomorrow shows tomorrow's expirations.",
        )

    selected_expiration_date_text = selected_expiration_date.isoformat()

    with control_col3:
        selected_sides = st.multiselect(
            "Sides",
            ["Put Credit", "Call Credit"],
            default=["Put Credit", "Call Credit"],
            key="options_board_sides",
        )

    with control_col4:
        max_rows = st.number_input(
            "Max Rows",
            min_value=50,
            max_value=10000,
            value=5000,
            step=50,
            key="options_board_max_rows",
        )

    width_col1, width_col2, width_col3 = st.columns([1.4, 1.35, 3.2])

    with width_col1:
        spread_widths_text = st.text_input(
            "Spread Widths",
            value=st.session_state.get("options_board_widths_text", "1,2,3"),
            key="options_board_widths_text",
            placeholder="1,2,3,5,10,20,50,100",
            help="Type any widths you want, separated by commas. Example: 1,2,3,5,10,20,50,100",
        )
        selected_widths = parse_options_spread_widths(spread_widths_text)

    with width_col2:
        credit_range_text = st.text_input(
            "Credit Range Filter",
            value=st.session_state.get("options_board_credit_range_filter", ""),
            key="options_board_credit_range_filter",
            placeholder="0.05-0.10",
            help="Optional. Blank shows all credits. Examples: 0.05-0.10, >=0.05, <=0.10, or 0.05+.",
        )
        credit_range_filter, credit_range_error = parse_options_credit_range_filter(credit_range_text)

    with width_col3:
        refresh_clicked = st.button(
            "REFRESH OPTIONS BOARD",
            key="options_board_refresh",
            type="primary",
            width="stretch",
        )

    if not selected_symbols:
        st.warning("Select at least one symbol.")
        return

    if not selected_sides:
        st.warning("Select Put Credit, Call Credit, or both.")
        return

    if not selected_widths:
        st.warning("Enter at least one valid spread width, like 1,2,3,5,10,20,50,100.")
        return

    options_board_cache_key = (
        tuple(selected_symbols),
        selected_expiration_date_text,
        tuple(selected_sides),
        tuple(selected_widths),
    )

    cached_options_board_key = st.session_state.get("options_board_cache_key")

    if refresh_clicked:
        st.session_state["options_board_force_refresh"] = True

    if (
        not refresh_clicked
        and cached_options_board_key == options_board_cache_key
        and "options_board_rows" in st.session_state
        and "options_board_errors" in st.session_state
    ):
        board_rows = st.session_state["options_board_rows"]
        errors = st.session_state["options_board_errors"]
    else:
        with st.spinner("Pulling Tastytrade option chains and quotes..."):
            board_rows, errors = build_tastytrade_spread_rows(
                selected_symbols=selected_symbols,
                selected_expiration_date=selected_expiration_date_text,
                selected_sides=selected_sides,
                selected_widths=selected_widths,
            )

        st.session_state["options_board_cache_key"] = options_board_cache_key
        st.session_state["options_board_rows"] = board_rows
        st.session_state["options_board_errors"] = errors

    for error in errors:
        st.error(error)

    if credit_range_error:
        st.warning(credit_range_error)

    filtered_board_rows = apply_options_credit_range_filter(board_rows, credit_range_filter)
    visible_board_rows = filtered_board_rows[: int(max_rows)]
    credit_filter_caption = "All credits"

    if credit_range_filter:
        credit_filter_caption = f"Credit filter: {credit_range_filter.get('display_text', str(credit_range_text))}"

    st.caption(
        f"Board rows shown: {len(visible_board_rows)} of {len(filtered_board_rows)} passing the board filter "
        f"({len(board_rows)} spreads scanned) | Default sort: Credit descending | "
        f"Symbols: {', '.join(selected_symbol_labels)} | Expiration: {selected_expiration_date_text} | "
        f"Widths: {', '.join(str(width) for width in selected_widths)} | "
        f"{credit_filter_caption}"
    )

    if not board_rows:
        st.info("No option spread rows loaded yet, or Tastytrade did not return quote/chain data for the current settings. Click REFRESH OPTIONS BOARD again after confirming credentials.")
        return

    if not visible_board_rows:
        st.info("No option spread rows pass the current Credit Range Filter.")
    else:
        st.dataframe(
            get_public_options_rows(visible_board_rows),
            width="stretch",
            hide_index=True,
        )

    render_instant_credit_calculations(board_rows, selected_symbols)


st.sidebar.markdown("### Live Trading Workflow")
selected_live_page = st.sidebar.radio(
    "Page",
    ["Step 2 — Technical Entry Check", "Step 3 — Options Opportunity Board"],
    key="live_app_page",
)

if selected_live_page == "Step 2 — Technical Entry Check":
    render_live_technical_entry_check()
else:
    render_options_opportunity_board()
