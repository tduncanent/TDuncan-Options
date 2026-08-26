import asyncio
import re
import time
from datetime import datetime, time as clock_time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


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


def default_live_review_label(now_et):
    if now_et.time() >= LIVE_REVIEW_TIMES["2:15 PM"]:
        return "2:15 PM"
    if now_et.time() >= LIVE_REVIEW_TIMES["1:00 PM"]:
        return "1:00 PM"
    return "11:00 AM"


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
            deadline = time.monotonic() + 25.0

            while len(candles) < 6000:
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

    if not snapshot_complete:
        raise RuntimeError(
            f"Tastytrade did not finish the {symbol} candle snapshot. Tap RUN LIVE TECHNICAL CHECK again."
        )

    return {
        "candles": candles,
        "streamer_symbol": streamer_symbol,
        "snapshot_snipped": snapshot_snipped,
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


def fetch_live_technical_analysis(symbol, review_label, now_et):
    trade_date = now_et.date()
    target_time = live_review_timestamp(trade_date, review_label)

    if now_et.weekday() >= 5:
        return {"error": "Today is not a regular weekday trading session."}

    if now_et < target_time:
        return {
            "error": (
                f"{review_label} is not ready yet. It will use only candles completed before "
                f"{format_live_clock(target_time)}."
            )
        }

    start_time = (now_et - timedelta(days=8)).replace(hour=9, minute=30, second=0, microsecond=0)

    try:
        candle_payload = asyncio.run(download_tastytrade_candle_events(symbol, start_time))
    except Exception as exc:
        return {"error": f"Live candle data unavailable for {symbol}: {exc}"}

    all_1m = candle_events_to_dataframe(candle_payload)
    if all_1m.empty:
        return {"error": f"Tastytrade returned no usable regular-session candles for {symbol}."}

    all_15m = build_live_15m_candles(all_1m)
    day_1m = all_1m[all_1m["trade_date"] == trade_date].copy()
    day_15m = all_15m[all_15m["trade_date"] == trade_date].copy()
    if day_1m.empty or day_15m.empty:
        return {"error": f"Tastytrade returned no regular-session candle set for {symbol} today."}

    reviews = {}
    review_order = list(LIVE_REVIEW_TIMES)
    selected_index = review_order.index(review_label)

    for label in review_order[: selected_index + 1]:
        if now_et >= live_review_timestamp(trade_date, label):
            reviews[label] = evaluate_live_technical_review(symbol, day_1m, day_15m, trade_date, label)

    result = reviews.get(review_label)
    if not result:
        return {"error": f"The {review_label} review is not ready."}
    if not result.get("ready"):
        return {"error": result.get("message", "The technical review could not be completed.")}

    return {
        "symbol": symbol,
        "review_label": review_label,
        "trade_date": trade_date,
        "result": result,
        "reviews": reviews,
        "day_15m": day_15m,
        "last_candle_time": day_1m["timestamp_et"].max(),
        "streamer_symbol": candle_payload.get("streamer_symbol", symbol),
        "snapshot_snipped": candle_payload.get("snapshot_snipped", False),
        "resolution_note": candle_payload.get("resolution_note", ""),
    }


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
    review_labels = list(LIVE_REVIEW_TIMES)

    st.title("Live Technical Entry Check")
    st.caption(
        "Step 2 — Tastytrade regular-session candles only. Uses the Research Engine's "
        "Foundational rules and completed 15-minute candles; it never submits an order."
    )
    st.warning(
        "Technical check only: a CLEAR result does not override the separate Step 1 headline-risk report."
    )

    control_col1, control_col2, control_col3 = st.columns([1.0, 1.15, 1.35])
    with control_col1:
        symbol = st.selectbox(
            "Symbol",
            LIVE_TECHNICAL_SYMBOLS,
            key="live_technical_symbol",
        )
    with control_col2:
        review_label = st.selectbox(
            "Technical Checkpoint",
            review_labels,
            index=review_labels.index(default_label),
            key="live_technical_review_label",
        )
    with control_col3:
        run_clicked = st.button(
            "RUN LIVE TECHNICAL CHECK",
            key="run_live_technical_check",
            type="primary",
            width="stretch",
        )

    st.caption(
        f"Current Eastern time: {now_et.strftime('%A, %B %d, %Y at ')}"
        f"{format_live_clock(now_et, include_seconds=True)} | "
        "After-hours prices are excluded."
    )

    request_key = (symbol, review_label, now_et.date().isoformat())
    if run_clicked:
        with st.spinner(f"Pulling {symbol} one-minute candles from Tastytrade and calculating ATR..."):
            payload = fetch_live_technical_analysis(symbol, review_label, now_et)
        st.session_state["live_technical_payload"] = payload
        st.session_state["live_technical_request_key"] = request_key

    payload = st.session_state.get("live_technical_payload")
    cached_key = st.session_state.get("live_technical_request_key")

    if not payload or cached_key != request_key:
        st.info("Choose the symbol and checkpoint, then tap RUN LIVE TECHNICAL CHECK.")
        return

    if payload.get("error"):
        st.error(payload["error"])
        if symbol in {"XSP", "XND"}:
            st.caption(
                "Index candle availability depends on the Tastytrade/DXLink entitlement for this exact symbol. "
                "The app will not substitute SPY, QQQ, NDX, or another instrument."
            )
        return

    result = payload["result"]
    render_live_technical_status_box(result["decision"])

    metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
    metric_col1.metric("9:30 Open", f"{result['market_open']:.2f}")
    metric_col2.metric("Review Price", f"{result['review_price']:.2f}")
    metric_col3.metric("Move From Open", f"{result['move_from_open']:.2f}")
    metric_col4.metric("ATR(14), 15m", f"{result['atr']:.2f}")
    metric_col5.metric("Largest 15m Body", f"{result['metrics']['max_body']:.2f}")

    direction = "ABOVE" if result["signed_move"] > 0 else "BELOW" if result["signed_move"] < 0 else "AT"
    st.write(
        f"**Checkpoint:** {review_label} &nbsp; | &nbsp; "
        f"**Price is {direction} the open by {abs(result['signed_move']):.2f}** &nbsp; | &nbsp; "
        f"**Six-candle churn:** {result['metrics']['churn']:.2f}"
    )

    if result["flagged"]:
        st.subheader("Why the review was flagged")
    else:
        st.subheader("Technical rule result")
    for reason in result["reasons"]:
        st.write(f"• {reason}")

    rules = LIVE_FOUNDATIONAL_RULES[symbol]
    distance_col1, distance_col2, distance_col3 = st.columns(3)
    distance_col1.metric("Standard Distance", f"{rules['standard_distance']:g}")
    distance_col2.metric("Preferred Distance", f"{rules['preferred_distance']:g}")
    distance_col3.metric("Close Distance", f"{rules['closer_distance']:g}", help="Reference only; Close has additional symbol-specific and headline requirements.")
    if symbol == "XND":
        st.caption("XND's 5-point Close distance is research-only and is not an operating entry recommendation.")
    else:
        st.caption("Close distance is reference-only here; its additional headline and symbol-specific requirements still apply.")

    target = live_review_timestamp(payload["trade_date"], review_label)
    chart_bars = payload["day_15m"]
    chart_bars = chart_bars[
        (chart_bars["timestamp_et"] >= live_review_timestamp(payload["trade_date"], "11:00 AM").replace(hour=9, minute=30))
        & (chart_bars["timestamp_et"] < target)
    ].copy()
    if not chart_bars.empty:
        chart_frame = chart_bars.set_index("timestamp_et")[["close"]].rename(columns={"close": "15m Close"})
        chart_frame["9:30 Open"] = result["market_open"]
        st.subheader("Completed 15-Minute Candles Used")
        st.line_chart(chart_frame, height=300)

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
        st.subheader("Today's Technical Checkpoints Through This Review")
        st.dataframe(review_rows, width="stretch", hide_index=True)

    with st.expander("Show the six 15-minute bars and calculation inputs"):
        detail = result["recent_bars"].copy()
        detail["Time ET"] = detail["timestamp_et"].dt.strftime("%I:%M %p").str.lstrip("0")
        detail["Body"] = (detail["close"] - detail["open"]).abs()
        detail = detail[["Time ET", "open", "high", "low", "close", "Body", "true_range", "atr_14"]]
        detail.columns = ["TIME ET", "OPEN", "HIGH", "LOW", "CLOSE", "BODY", "TRUE RANGE", "ATR(14)"]
        st.dataframe(detail, width="stretch", hide_index=True)

    st.caption(
        f"Tastytrade streamer symbol: {payload['streamer_symbol']} | "
        f"Latest candle received: {format_live_clock(payload['last_candle_time'])} | "
        "ATR uses Wilder smoothing: EWM alpha = 1/14."
    )
    if payload.get("snapshot_snipped"):
        st.warning("Tastytrade marked the candle history snapshot as limited. The calculation used the returned history only.")


# ==================================================
# OPTIONS OPPORTUNITY BOARD — TASTYTRADE READ-ONLY
# ==================================================

TASTYTRADE_BASE_URL = "https://api.tastyworks.com"

# Kept in display order so the scanner selector is grouped by instrument type.
# The API still receives only the raw ticker symbol.
OPTIONS_SYMBOL_CATALOG = [
    # ETFs
    {"symbol": "QQQ", "instrument_type": "ETF"},
    {"symbol": "SPY", "instrument_type": "ETF"},
    {"symbol": "IWM", "instrument_type": "ETF"},
    {"symbol": "DIA", "instrument_type": "ETF"},
    {"symbol": "TLT", "instrument_type": "ETF"},
    # Index options
    {"symbol": "XSP", "instrument_type": "INDEX"},
    {"symbol": "XND", "instrument_type": "INDEX"},
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
    OPTIONS_SYMBOL_LABEL_BY_TICKER["XND"],
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


def build_tastytrade_spread_rows(selected_symbols, selected_expiration_date, selected_sides, selected_widths, max_rows):
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

    if max_rows and len(board_rows) > int(max_rows):
        board_rows = board_rows[:int(max_rows)]

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


def select_farthest_instant_credit_row(board_rows, symbol, side):
    candidates = []

    for row in board_rows:
        if row.get("Symbol") != symbol or row.get("Side") != side:
            continue

        natural_credit = safe_float(row.get("Instant Credit"), 0.0)
        distance_from_open = safe_float(row.get("_Distance From Open"), None)

        if natural_credit <= 0 or distance_from_open is None or distance_from_open < 0:
            continue

        candidates.append(row)

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda row: (
            safe_float(row.get("_Distance From Open"), 0.0),
            safe_float(row.get("Instant Credit"), 0.0),
            safe_float(row.get("Width"), 0.0),
        ),
    )


def render_instant_credit_calculations(board_rows, selected_symbols):
    st.markdown("---")
    st.subheader("Instant Credit Calculations")
    st.caption(
        "For each selected symbol, this shows the farthest Call and Put spread from today's open "
        "that has a positive natural credit (short bid minus long ask)."
    )

    for symbol in selected_symbols:
        st.markdown(f"### {symbol} Instant Credits")
        summary_rows = []

        for side, type_label in [("Call Credit", "CALL"), ("Put Credit", "PUT")]:
            best_row = select_farthest_instant_credit_row(board_rows, symbol, side)

            if not best_row:
                continue

            summary_rows.append({
                "TYPE": type_label,
                "STRIKES": (
                    f'{format_options_number(best_row.get("Short Strike"))} - '
                    f'{format_options_number(best_row.get("Long Strike"))}'
                ),
                "DISTANCE FROM OPEN": format_options_number(best_row.get("_Distance From Open")),
                "INSTANT CREDIT": f'{safe_float(best_row.get("Instant Credit"), 0.0):.2f}',
            })

        if summary_rows:
            st.dataframe(
                summary_rows,
                width="stretch",
                hide_index=True,
            )
        else:
            symbol_rows = [row for row in board_rows if row.get("Symbol") == symbol]
            open_is_available = any(safe_float(row.get("_Open Price"), 0.0) > 0 for row in symbol_rows)

            if symbol_rows and not open_is_available:
                st.info(f"{symbol}: today's opening price was unavailable, so distance-from-open calculations could not be completed.")
            else:
                st.info(f"{symbol}: no instant-credit Call or Put spread is available for the current selections.")

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
            help="Ordered by group: ETFs, index options, then stocks. The scanner uses the raw ticker behind each label.",
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
        int(max_rows),
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
                max_rows=int(max_rows),
            )

        st.session_state["options_board_cache_key"] = options_board_cache_key
        st.session_state["options_board_rows"] = board_rows
        st.session_state["options_board_errors"] = errors

    for error in errors:
        st.error(error)

    if credit_range_error:
        st.warning(credit_range_error)

    visible_board_rows = apply_options_credit_range_filter(board_rows, credit_range_filter)
    credit_filter_caption = "All credits"

    if credit_range_filter:
        credit_filter_caption = f"Credit filter: {credit_range_filter.get('display_text', str(credit_range_text))}"

    st.caption(
        f"Rows shown: {len(visible_board_rows)} of {len(board_rows)} | Default sort: Credit descending | "
        f"Symbols: {', '.join(selected_symbol_labels)} | Expiration: {selected_expiration_date_text} | "
        f"Widths: {', '.join(str(width) for width in selected_widths)} | "
        f"{credit_filter_caption}"
    )

    if not board_rows:
        st.info("No option spread rows loaded yet, or Tastytrade did not return quote/chain data for the current settings. Click REFRESH OPTIONS BOARD again after confirming credentials.")
        return

    if not visible_board_rows:
        st.info("No option spread rows pass the current Credit Range Filter.")
        return

    st.dataframe(
        get_public_options_rows(visible_board_rows),
        width="stretch",
        hide_index=True,
    )

    render_instant_credit_calculations(visible_board_rows, selected_symbols)


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
