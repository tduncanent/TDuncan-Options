"""Historical Rare Golden Fingerprint rules, evaluated on completed daily bars."""
from __future__ import annotations
from datetime import date
import math
import numpy as np
import pandas as pd

RULES = {'QQQ': {'strike_increment': 1.0, 'rare': {'open_distance': 9.0, 'review_distance': 10.0, 'minimum_signed_move': 0.0, 'maximum_atr': 3.0, 'maximum_age': None}}, 'SPY': {'strike_increment': 1.0, 'rare': {'open_distance': 6.0, 'review_distance': 7.0, 'minimum_signed_move': 0.0, 'maximum_atr': 1.5, 'maximum_age': 5}}, 'XSP': {'strike_increment': 1.0, 'rare': {'open_distance': 6.0, 'review_distance': 8.0, 'minimum_signed_move': 1.0, 'maximum_atr': 1.0, 'maximum_age': None}}, 'XND': {'strike_increment': 1.0, 'rare': {'open_distance': 5.0, 'review_distance': 5.0, 'minimum_signed_move': 0.0, 'maximum_atr': 1.23, 'maximum_age': None}}}

def outward_strike(boundary: float, side: str, increment: float) -> float:
    """Round a call up or a put down, never inward toward the market."""
    if increment <= 0:
        raise ValueError("Strike increment must be positive.")
    scaled = float(boundary) / float(increment)
    if side.lower() == "call":
        rounded = math.ceil(scaled - 1e-10) * increment
    elif side.lower() == "put":
        rounded = math.floor(scaled + 1e-10) * increment
    else:
        raise ValueError(f"Unsupported option side: {side}")
    return round(float(rounded), 8)

def _entry_block_reason(
    foundational: dict,
    today_gate: dict,
    next_gate: dict,
) -> str | None:
    if not foundational["technical_clear"]:
        return "FOUNDATIONAL FILTER"
    if not today_gate["clear"]:
        return "TODAY'S HEADLINE GATE"
    if not next_gate["clear"]:
        return "NEXT-TRADING-DAY RISK GATE"
    return None

def parabolic_sar(
    high: pd.Series,
    low: pd.Series,
    step: float = 0.02,
    maximum: float = 0.20,
) -> pd.Series:
    highs = high.to_numpy(dtype=float)
    lows = low.to_numpy(dtype=float)
    output = np.full(len(highs), np.nan)
    if len(highs) < 2:
        return pd.Series(output, index=high.index)

    bullish = True
    sar = lows[0]
    extreme = highs[0]
    acceleration = step
    output[0] = sar

    for index in range(1, len(highs)):
        sar = sar + acceleration * (extreme - sar)
        if bullish:
            sar = min(sar, lows[index - 1])
            if index >= 2:
                sar = min(sar, lows[index - 2])
            if lows[index] < sar:
                bullish = False
                sar = extreme
                extreme = lows[index]
                acceleration = step
            elif highs[index] > extreme:
                extreme = highs[index]
                acceleration = min(maximum, acceleration + step)
        else:
            sar = max(sar, highs[index - 1])
            if index >= 2:
                sar = max(sar, highs[index - 2])
            if highs[index] > sar:
                bullish = True
                sar = extreme
                extreme = highs[index]
                acceleration = step
            elif lows[index] < extreme:
                extreme = lows[index]
                acceleration = min(maximum, acceleration + step)
        output[index] = sar
    return pd.Series(output, index=high.index)

def add_daily_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]

    df["sma20"] = close.rolling(20).mean()
    deviation = close.rolling(20).std(ddof=0)
    df["bb_upper"] = df["sma20"] + 2 * deviation
    df["bb_lower"] = df["sma20"] - 2 * deviation
    df["bb_width"] = df["bb_upper"] - df["bb_lower"]

    lowest = low.rolling(14).min()
    highest = high.rolling(14).max()
    span = (highest - lowest).replace(0, np.nan)
    df["stoch_k"] = 100 * (close - lowest) / span
    df["stoch_d"] = df["stoch_k"].rolling(3).mean()
    df["momentum10"] = close - close.shift(10)

    ema13 = close.ewm(span=13, adjust=False).mean()
    df["bull_power"] = high - ema13
    df["bear_power"] = low - ema13
    df["psar"] = parabolic_sar(high, low)
    df["psar_bull"] = df["psar"] < low

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr14"] = true_range.ewm(alpha=1 / 14, adjust=False).mean()
    return df

def prepare_daily_history(history: pd.DataFrame) -> pd.DataFrame:
    """Build causal daily indicators once for reuse across assessments."""
    if history.empty:
        return pd.DataFrame()
    daily = history.groupby("trade_date", sort=True).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    daily.index = pd.DatetimeIndex(pd.to_datetime(daily.index))
    return add_daily_indicators(daily)

def daily_history_before(history: pd.DataFrame, trade_date: date) -> pd.DataFrame:
    prior = history[history["trade_date"] < trade_date].copy()
    return prepare_daily_history(prior)

def _signal_flags(daily: pd.DataFrame) -> pd.DataFrame:
    df = daily.copy()
    stoch_k = df["stoch_k"]
    stoch_d = df["stoch_d"]
    momentum = df["momentum10"]
    raw = (
        (stoch_k > stoch_k.shift(1))
        & (stoch_d > stoch_d.shift(1))
        & (momentum > momentum.shift(1))
        & (df["bull_power"] > df["bull_power"].shift(1))
        & (df["bear_power"] > df["bear_power"].shift(1))
        & (df["close"] > df["open"])
        & (df["close"] > df["close"].shift(1))
    )
    sma50 = df["close"].rolling(50).mean()
    trend = (df["close"] > sma50) & (sma50 > sma50.shift(10))
    not_exhausted = ~((stoch_k >= 80) & (stoch_d >= 80))
    df["eligible_signal"] = raw & trend & df["psar_bull"] & not_exhausted
    df["angle_date"] = df.index.to_series().shift(1)
    df["angle_close"] = df["close"].shift(1)
    return df

def _weekly_gate(daily: pd.DataFrame, trade_date: date) -> bool | None:
    weekly = daily[["open", "high", "low", "close", "volume"]].resample("W-FRI").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    if weekly.empty:
        return None
    weekly = add_daily_indicators(weekly)
    weekly["sma10"] = weekly["close"].rolling(10).mean()
    weekly["confirmed_downswing"] = (
        (weekly["close"] < weekly["sma10"])
        & (weekly["sma10"] < weekly["sma10"].shift(2))
        & (~weekly["psar_bull"])
    )
    timestamp = pd.Timestamp(trade_date)
    prior_friday = (timestamp.to_period("W-FRI") - 1).end_time.normalize()
    if prior_friday not in weekly.index:
        return None
    value = weekly.loc[prior_friday, "confirmed_downswing"]
    if pd.isna(value):
        return None
    return not bool(value)

def active_fingerprint_state(
    daily: pd.DataFrame,
    trade_date: date,
    maximum_age: int | None,
) -> dict:
    if len(daily) < 61:
        return {
            "ready": False,
            "active": False,
            "reason": "At least 61 completed daily sessions are required.",
        }

    signals = _signal_flags(daily)
    active = None
    dates = list(daily.index)
    for index, signal_date in enumerate(dates):
        if active is not None:
            prior_close = float(daily.iloc[index - 1]["close"]) if index > 0 else float("nan")
            age = index - active["signal_index"]
            if (
                (maximum_age is not None and age > maximum_age)
                or prior_close <= active["boundary"]
            ):
                active = None

        if bool(signals.loc[signal_date, "eligible_signal"]):
            active = {
                "signal_index": index,
                "signal_date": signal_date,
                "angle_date": signals.loc[signal_date, "angle_date"],
                "boundary": float(signals.loc[signal_date, "angle_close"]),
            }

    if active is not None:
        selected_index = len(dates)
        age = selected_index - active["signal_index"]
        prior_close = float(daily.iloc[-1]["close"])
        if (
            (maximum_age is not None and age > maximum_age)
            or prior_close <= active["boundary"]
        ):
            active = None

    if active is None:
        return {
            "ready": True,
            "active": False,
            "reason": "No eligible bullish daily fingerprint regime is active.",
            "weekly_gate": _weekly_gate(daily, trade_date),
        }

    return {
        "ready": True,
        "active": True,
        "signal_date": active["signal_date"].date(),
        "angle_date": active["angle_date"].date(),
        "age": len(dates) - active["signal_index"],
        "signal_boundary": active["boundary"],
        "prior_close": float(daily.iloc[-1]["close"]),
        "weekly_gate": _weekly_gate(daily, trade_date),
        "reason": "An eligible bullish daily fingerprint regime is active.",
    }

def assess_rare(
    symbol: str,
    review_label: str,
    foundational: dict,
    metrics: dict,
    today_gate: dict,
    next_gate: dict,
    fingerprint_state: dict,
) -> dict:
    rules = RULES[symbol]
    rare = rules["rare"]
    increment = float(rules["strike_increment"])

    if not fingerprint_state.get("ready"):
        return {
            "tool": "Rare Golden Fingerprint",
            "result": "DO NOT ENTER — DAILY HISTORY UNAVAILABLE",
            "description": fingerprint_state.get("reason", "Daily history is unavailable."),
            "fingerprint": fingerprint_state,
            "conditions": [],
            "boundary": None,
            "strike": None,
        }

    if not fingerprint_state.get("active"):
        return {
            "tool": "Rare Golden Fingerprint",
            "result": "NO ACTIVE FINGERPRINT",
            "description": fingerprint_state.get(
                "reason", "No eligible bullish daily fingerprint regime is active."
            ),
            "fingerprint": fingerprint_state,
            "conditions": [],
            "boundary": None,
            "strike": None,
        }

    boundary = max(
        float(metrics["market_open"]) - float(rare["open_distance"]),
        float(metrics["review_price"]) - float(rare["review_distance"]),
    )
    strike = outward_strike(boundary, "put", increment)
    weekly_gate = fingerprint_state.get("weekly_gate")
    conditions = [
        {
            "label": "Prior completed week is not in a confirmed downswing",
            "value": weekly_gate,
            "passed": weekly_gate is True,
        },
        {
            "label": "Original fingerprint boundary remains intact at the current review",
            "value": float(metrics["review_price"]),
            "threshold": float(fingerprint_state["signal_boundary"]),
            "passed": float(metrics["review_price"]) > float(fingerprint_state["signal_boundary"]),
        },
        {
            "label": "Foundational technical review is clear at the current review",
            "value": foundational["technical_clear"],
            "passed": foundational["technical_clear"],
        },
        {
            "label": (
                f"{symbol} is at least {float(rare['minimum_signed_move']):g} "
                "points above its open"
            ),
            "value": float(metrics["signed_move"]),
            "threshold": float(rare["minimum_signed_move"]),
            "passed": float(metrics["signed_move"]) >= float(rare["minimum_signed_move"]),
        },
        {
            "label": f"15-minute ATR is no more than {float(rare['maximum_atr']):g}",
            "value": float(metrics["atr"]),
            "threshold": float(rare["maximum_atr"]),
            "passed": (
                not math.isnan(float(metrics["atr"]))
                and float(metrics["atr"]) <= float(rare["maximum_atr"])
            ),
        },
    ]
    technical_pass = all(item["passed"] for item in conditions)

    if not technical_pass:
        failed = [item["label"] for item in conditions if not item["passed"]]
        result = "DO NOT ENTER"
        description = "Failed conditions: " + "; ".join(failed) + "."
    else:
        blocker = _entry_block_reason(foundational, today_gate, next_gate)
        if blocker:
            result = f"TOOL CONDITIONS PASSED — ENTRY BLOCKED BY {blocker}"
            description = f"The Rare conditions passed, but the {blocker.lower()} is not clear."
        else:
            result = "ENTER"
            description = "All Rare Golden Fingerprint conditions and both event gates are clear."

    return {
        "tool": "Rare Golden Fingerprint",
        "result": result,
        "description": description,
        "fingerprint": fingerprint_state,
        "conditions": conditions,
        "boundary": boundary,
        "strike": strike,
        "distance_rule": {
            "open_distance": float(rare["open_distance"]),
            "review_distance": float(rare["review_distance"]),
        },
    }
