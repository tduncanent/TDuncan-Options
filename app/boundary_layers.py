"""Qualify the added layers on an already completed 11 AM boundary forecast.

These names describe rule qualification, not a new probability estimate. The
forecast, rounded references, operating gates and actual-chain matching remain
owned by their existing modules. No candle, quote or historical outcome is
fetched or used here. Capture the names during Analyze, never on chain refresh.
"""
from __future__ import annotations

from calendar import monthrange
from collections.abc import Mapping
from datetime import date, time
from functools import lru_cache
import math

import pandas as pd

EASTERN = "America/New_York"
SYMBOLS = frozenset({"QQQ", "SPY", "XSP"})
ETF_SYMBOLS = frozenset({"QQQ", "SPY"})


def _positive(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


@lru_cache(maxsize=24)
def _month_sessions(year, month):
    """Use all scheduled NYSE sessions, including shortened sessions.

    Session labels are calendar dates (not midnight instants converted to ET).
    The existing calendar dependency includes holidays/announced closures. Do
    not derive these edges from price history, model dates or filtered trades.
    """
    import pandas_market_calendars as calendars

    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    sessions = calendars.get_calendar("NYSE").valid_days(first, last)
    return tuple(pd.Timestamp(day).date() for day in sessions)


def _month_position(session):
    try:
        sessions = _month_sessions(session.year, session.month)
        if not sessions or session not in sessions:
            return None
        return session == sessions[0], session == sessions[-1]
    except Exception:
        # A missing calendar blocks its added claim, not a valid lower layer.
        return None


def boundary_strategy_labels(forecast):
    """Return each level/side's strongest tier without choosing between levels.

    Morning Dir: 10:59 close > 9:30 open selects PUT; below selects CALL; equal
    selects neither. Month Guard: ETFs reject first and last monthly sessions;
    XSP 90 rejects only last, and XSP 95 has no calendar or Safety claim. ETF
    Safety additionally needs movement >= 0.05 prior ATR and locked-reference
    headroom >= 1.0 prior ATR. A farther actual contract cannot rescue that gate.
    """
    labels = {level: {side: f"Daily Price Boundary Strategy ({level}%)"
                      for side in ("CALL", "PUT")} for level in ("90", "95")}
    if (not isinstance(forecast, Mapping) or not forecast.get("available")
            or forecast.get("symbol") not in SYMBOLS
            or forecast.get("clock") != "11:00"):
        return labels
    try:
        session = pd.Timestamp(forecast.get("date"))
        last = pd.Timestamp(forecast.get("last_candle"))
        if pd.isna(session) or pd.isna(last):
            return labels
        session = session.date()
        last = last.tz_localize(EASTERN) if last.tzinfo is None else last.tz_convert(EASTERN)
        if (last.date() != session or last.time() != time(10, 59)
                or last.nanosecond != 0):
            return labels
    except (TypeError, ValueError, OverflowError):
        return labels

    opening = _positive(forecast.get("market_open"))
    price = _positive(forecast.get("review_price"))
    if opening is None or price is None or price == opening:
        return labels
    side = "PUT" if price > opening else "CALL"
    position = _month_position(session)
    symbol = forecast["symbol"]
    features = forecast.get("features")
    prior_atr = _positive(features.get("prior_daily_atr14")) if isinstance(features, Mapping) else None
    ranges = forecast.get("ranges")
    for level in ("90", "95"):
        band = ranges.get(level) if isinstance(ranges, Mapping) else None
        reference = _positive(band.get(f"{side.lower()}_strike")) if isinstance(band, Mapping) else None
        if reference is None:
            continue
        tier = f"{level}% + Morning Dir"
        month_pass = (position is not None and not position[1]
                      and (symbol == "XSP" or not position[0])
                      and not (symbol == "XSP" and level == "95"))
        if month_pass:
            tier += " + Month Guard"
            headroom = price - reference if side == "PUT" else reference - price
            if (symbol in ETF_SYMBOLS and prior_atr is not None
                    and abs(price - opening) / prior_atr >= 0.05
                    and headroom / prior_atr >= 1.0):
                tier += " + Safety"
        labels[level][side] = f"Daily Price Boundary Strategy ({tier})"
    return labels
