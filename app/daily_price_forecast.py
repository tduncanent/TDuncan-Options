"""Symbol-specific daily price forecasts using frozen, prior-date models.

No fitting occurs in Streamlit. The portable JSON trees reproduce the research
HistGradientBoosting median model without adding a scikit-learn dependency.
Forecast inputs never include a candle at or after the selected checkpoint.
Historical outcome is computed separately and never participates in prediction.
"""
from __future__ import annotations

from functools import lru_cache
import gzip
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

def outward_strike(boundary, side, increment):
    scaled = float(boundary) / increment
    return float((math.ceil(scaled - 1e-10) if side == "call" else math.floor(scaled + 1e-10)) * increment)


MODEL_DIRECTORY = Path(__file__).resolve().parent / "forecast_assets"
SUPPORTED_SYMBOLS = ("XSP", "SPY", "QQQ", "XND")
STRATEGY_NAME = "Daily Price Boundary Strategy"
CHECKPOINTS = ("09:40",) + tuple(
    f"{m // 60:02d}:{m % 60:02d}" for m in range(585, 946, 15)
)
LEVELS = {"90": "90% boundary", "95": "95% stress boundary", "typical": "Typical range — lower confidence"}


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else math.nan
    except (TypeError, ValueError):
        return math.nan


@lru_cache(maxsize=8)
def _read_bundle(path: str, mtime_ns: int) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as source:
        bundle = json.load(source)
    if bundle.get("schema_version") != 1 or bundle.get("symbol") not in SUPPORTED_SYMBOLS:
        raise ValueError("Unsupported forecast model bundle.")
    return bundle


def model_bundle(symbol="XSP") -> dict:
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"No researched model for {symbol}.")
    path = MODEL_DIRECTORY / f"{symbol.lower()}_daily_forecast_v1.json.gz"
    bundle = _read_bundle(str(path), path.stat().st_mtime_ns)
    if bundle["symbol"] != symbol:
        raise ValueError("Forecast model symbol does not match the selected symbol.")
    return bundle


def select_fold(bundle: dict, trade_date) -> dict | None:
    day = str(pd.Timestamp(trade_date).date())
    return next((fold for fold in bundle["folds"] if fold["valid_from"] <= day <= fold["valid_through"]), None)


@lru_cache(maxsize=512)
def standard_session(day: str) -> bool:
    import pandas_market_calendars as market_calendars
    schedule = market_calendars.get_calendar("NYSE").schedule(start_date=day, end_date=day)
    return bool(len(schedule) == 1 and (
        schedule.iloc[0].market_close - schedule.iloc[0].market_open
    ) == pd.Timedelta(minutes=390))


def tree_prediction(model: dict, values: np.ndarray) -> float:
    result = float(model["baseline"])
    # Node fields: leaf flag, value, feature index, numeric threshold, left, right.
    # Training-median imputation makes all runtime values finite.
    for tree in model["trees"]:
        index = 0
        while not tree[index][0]:
            node = tree[index]
            index = node[4] if values[node[2]] <= node[3] else node[5]
        result += tree[index][1]
    return result


def _hourly_daily_history(prior_hourly: pd.DataFrame, selected_date) -> pd.DataFrame:
    """Seven clock-hour RTH bars reproduce a full session's OHLC.

    The feed is requested with tho=true and its default clock-hour alignment:
    09:00 contains only 09:30–09:59; 15:00 ends at 16:00. No minute candles
    are invented. Today's hourly bars and shortened sessions are excluded.
    """
    columns = ["day_open", "day_high", "day_low", "day_close"]
    if prior_hourly is None or prior_hourly.empty:
        return pd.DataFrame(columns=columns)
    frame = prior_hourly.copy()
    frame["timestamp_et"] = pd.to_datetime(frame.timestamp_et, utc=True).dt.tz_convert("America/New_York")
    frame = frame[frame.timestamp_et.dt.date < selected_date].sort_values("timestamp_et")
    frame = frame.drop_duplicates("timestamp_et", keep="last")
    frame["trade_date"] = frame.timestamp_et.dt.date
    if frame.empty:
        return pd.DataFrame(columns=columns)
    import pandas_market_calendars as calendars
    schedule = calendars.get_calendar("NYSE").schedule(
        start_date=frame.trade_date.min(), end_date=frame.trade_date.max()
    )
    full_sessions = set(schedule.index[(schedule.market_close - schedule.market_open) == pd.Timedelta(minutes=390)].date)
    records = []
    for session, bars in frame.groupby("trade_date", sort=True):
        expected = pd.date_range(f"{session} 09:00", periods=7, freq="h", tz="America/New_York")
        if not pd.DatetimeIndex(bars.timestamp_et).equals(expected) or session not in full_sessions:
            continue
        prices = bars[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
        if (not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any()
                or (prices.high < prices[["open", "close", "low"]].max(axis=1)).any()
                or (prices.low > prices[["open", "close", "high"]].min(axis=1)).any()):
            continue
        records.append({"trade_date": session, "day_open": float(prices.iloc[0].open),
                        "day_high": float(prices.high.max()), "day_low": float(prices.low.min()),
                        "day_close": float(prices.iloc[-1].close)})
    if not records:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(records).set_index("trade_date").sort_index()


def _prior_features(prior: pd.DataFrame, prior_hourly=None, selected_date=None) -> dict:
    daily = prior.groupby("trade_date", sort=True).agg(
        count=("close", "size"), first=("timestamp_et", "first"), last=("timestamp_et", "last"),
        day_open=("open", "first"), day_high=("high", "max"),
        day_low=("low", "min"), day_close=("close", "last"),
    )
    complete = daily[
        daily["count"].eq(390) & daily["first"].dt.strftime("%H:%M").eq("09:30")
        & daily["last"].dt.strftime("%H:%M").eq("15:59")
    ].copy()
    minute_count = len(complete)
    hourly = _hourly_daily_history(prior_hourly, selected_date) if selected_date is not None else pd.DataFrame()
    hourly_count = len(hourly)
    overlap_count = 0
    if hourly_count:
        overlap = complete.index.intersection(hourly.index)
        fields = ["day_open", "day_high", "day_low", "day_close"]
        if len(overlap) == 0:
            raise ValueError("Longer hourly history was returned, but no complete prior day overlaps the minute feed to verify its regular-session OHLC.")
        matches = np.isclose(complete.loc[overlap, fields].to_numpy(float),
                             hourly.loc[overlap, fields].to_numpy(float), atol=1e-6, rtol=0).all(axis=1)
        if not matches.all():
            first_mismatch = overlap[np.flatnonzero(~matches)[0]]
            raise ValueError(f"Hourly and one-minute regular-session OHLC disagree on {first_mismatch}; the longer history is not used until its session data can be verified.")
        overlap_count = len(overlap)
        # Minute data take precedence on overlapping verified sessions.
        complete = pd.concat([hourly, complete[fields]])
        complete = complete[~complete.index.duplicated(keep="last")].sort_index()
    if len(complete) < 30:
        raise ValueError(f"At least 30 complete prior sessions are needed for the researched volatility inputs; "
                         f"received {minute_count} from one-minute history and {hourly_count} from hourly history "
                         f"({len(complete)} distinct complete sessions).")
    complete["day_range"] = complete.day_high - complete.day_low
    complete["day_max_open_dist"] = np.maximum(
        complete.day_high - complete.day_open, complete.day_open - complete.day_low
    )
    complete["day_close_abs_move"] = (complete.day_close - complete.day_open).abs()
    result = {"prior_history_info": {"complete_sessions": len(complete), "minute_sessions": minute_count,
                                    "hourly_sessions": hourly_count, "verified_overlap_sessions": overlap_count,
                                    "first_date": str(complete.index[0]), "last_date": str(complete.index[-1])}}
    for window in (3, 5, 10, 20, 60):
        for column, short in (("day_max_open_dist", "maxdist"), ("day_range", "range")):
            sample = complete[column].tail(window)
            for label, value in (("median", sample.median()), ("mean", sample.mean()),
                                 ("q80", sample.quantile(.8)), ("q90", sample.quantile(.9))):
                result[f"prior_{short}_{label}_{window}"] = float(value)
    for column in ("day_max_open_dist", "day_range", "day_close_abs_move"):
        result[f"previous_{column}"] = float(complete.iloc[-1][column])
    tr = pd.concat([
        complete.day_range, (complete.day_high - complete.day_close.shift()).abs(),
        (complete.day_low - complete.day_close.shift()).abs(),
    ], axis=1).max(axis=1)
    result["prior_daily_atr14"] = float(tr.ewm(alpha=1/14, adjust=False, min_periods=5).mean().iloc[-1])
    if result["prior_daily_atr14"] <= 0 or result["prior_maxdist_median_20"] <= 0:
        raise ValueError("Prior-session volatility inputs must be positive.")
    return result


def forecast_features(history: pd.DataFrame, trade_date, clock: str, input_mode="source_indicators", prior_hourly=None) -> tuple[dict, pd.DataFrame]:
    """Reproduce research schema 2 from prior days and completed current bars."""
    selected = pd.Timestamp(trade_date).date()
    cutoff = pd.Timestamp(f"{selected} {clock}", tz="America/New_York")
    opening = pd.Timestamp(f"{selected} 09:30", tz="America/New_York")
    past = history[history.timestamp_et < cutoff].sort_values("timestamp_et").copy()
    past["timestamp_et"] = past.timestamp_et.dt.tz_convert("America/New_York")
    past = past[(past.timestamp_et.dt.hour * 60 + past.timestamp_et.dt.minute).between(570, 959)]
    past["trade_date"] = past.timestamp_et.dt.date
    visible = past[past.trade_date == selected].copy()
    expected = pd.date_range(opening, cutoff, freq="min", inclusive="left")
    if len(visible) != len(expected) or not pd.DatetimeIndex(visible.timestamp_et).equals(expected):
        raise ValueError(f"Need every completed one-minute candle from 09:30 through {(cutoff-pd.Timedelta(minutes=1)).strftime('%H:%M')} ET; found {len(visible)} of {len(expected)}.")
    ohlc = visible[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(ohlc.to_numpy()).all() or (ohlc <= 0).any().any():
        raise ValueError("A required OHLC price is missing, nonfinite, or nonpositive.")
    if (ohlc.high < ohlc[["open", "close", "low"]].max(axis=1)).any() or (ohlc.low > ohlc[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("One or more candles have inconsistent OHLC prices.")
    prior = past[past.trade_date < selected]
    if prior.empty:
        raise ValueError("Prior-session history is unavailable.")
    prior_values = _prior_features(prior, prior_hourly, selected)
    close = ohlc.close.to_numpy(float)
    opening_price, price = float(ohlc.iloc[0].open), float(close[-1])
    high, low = float(ohlc.high.max()), float(ohlc.low.min())
    max_seen, span = max(high-opening_price, opening_price-low), high-low
    elapsed = len(visible)
    gap = opening_price - float(prior.iloc[-1].close)
    last = {str(k).lower(): v for k, v in visible.iloc[-1].items()}
    # Missing optional source indicators use the same prior-training medians as
    # the research. Never substitute a differently calculated indicator silently.
    source = lambda key: _number(last.get(key, math.nan))
    atr = source("atr")
    if input_mode == "causal_atr_only":
        previous = past.close.shift(1)
        tr = pd.concat([past.high-past.low, (past.high-previous).abs(),
                        (past.low-previous).abs()], axis=1).max(axis=1)
        atr = float(tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1])
        source = lambda key: math.nan
    row = {
        "feature_schema_version": 2, "elapsed_minutes": elapsed, "minutes_remaining": 390-elapsed,
        "day_open": opening_price, "review_price": price, "gap": gap, "abs_gap": abs(gap),
        "signed_move": price-opening_price, "abs_move": abs(price-opening_price),
        "up_from_open_so_far": high-opening_price, "down_from_open_so_far": opening_price-low,
        "max_open_dist_so_far": max_seen, "range_so_far": span,
        "range_position": (price-low)/span if span else .5,
        "distance_below_high": high-price, "distance_above_low": price-low,
        "mean_abs_1m_change": float(np.abs(np.diff(close)).mean()),
        "std_1m_change": float(np.diff(close).std(ddof=0)),
        "q90_abs_1m_change": float(np.quantile(np.abs(np.diff(close)), .90)),
        "max_1m_range_so_far": float((ohlc.high-ohlc.low).max()),
        "mean_1m_range_so_far": float((ohlc.high-ohlc.low).mean()),
        "source_atr1": atr, "bollinger_width": source("upper")-source("lower"),
        "basis_distance": price-source("basis"), "psar_distance": price-source("parabolicsar"),
        "momentum": source("mom"), "stoch_k": source("%k"), "stoch_d": source("%d"),
        "weekday": selected.weekday(), "month": selected.month,
        "used_fraction_of_prior20_median": max_seen/prior_values["prior_maxdist_median_20"],
        "range_to_prior_atr": span/prior_values["prior_daily_atr14"],
        "max_seen_per_sqrt_minute": max_seen/math.sqrt(elapsed),
        "range_per_sqrt_minute": span/math.sqrt(elapsed),
        "brownian_projected_max": max_seen*math.sqrt(390/elapsed),
        "max_seen_pct": max_seen/opening_price, "range_pct": span/opening_price,
        "gap_pct": gap/opening_price, "atr1_pct": atr/opening_price,
        "max_seen_to_prior_atr": max_seen/prior_values["prior_daily_atr14"],
        "abs_move_to_prior_atr": abs(price-opening_price)/prior_values["prior_daily_atr14"],
        "atr1_to_prior_atr": atr/prior_values["prior_daily_atr14"],
        "minutes_since_high": elapsed-1-int(ohlc.high.to_numpy().argmax()),
        "minutes_since_low": elapsed-1-int(ohlc.low.to_numpy().argmin()),
        **prior_values,
    }
    for count in (5, 10, 15, 30, 60):
        block = ohlc.iloc[:min(count, elapsed)]
        row[f"opening_range_{count}"] = float(block.high.max()-block.low.min())
        row[f"opening_abs_net_{count}"] = abs(float(block.iloc[-1].close-block.iloc[0].open))
    five = ohlc.assign(block=np.arange(elapsed)//5).groupby("block").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    bodies = (five.close-five.open).abs()
    row.update(max_5m_body=float(bodies.max()), sum_5m_body=float(bodies.sum()),
               mean_5m_range=float((five.high-five.low).mean()),
               five_minute_efficiency=abs(price-opening_price)/float(bodies.sum()) if bodies.sum() else 0.)
    changes = np.diff(close)
    signs = np.sign(changes[changes != 0])
    row["sign_change_rate"] = float(np.mean(signs[1:] != signs[:-1])) if len(signs) > 1 else 0.
    for count in (5, 10, 15, 30, 60, 90):
        sample, segment = close[-min(count, elapsed):], ohlc.tail(count)
        net = float(sample[-1]-sample[0])
        travel = float(np.abs(np.diff(sample)).sum())
        for name, value in (
            ("range", float(segment.high.max()-segment.low.min())), ("net", net), ("abs_net", abs(net)),
            ("slope", float(np.polyfit(np.arange(len(sample), dtype=float), sample, 1)[0])),
            ("efficiency", abs(net)/travel if travel else 0.), ("rv", float(np.diff(sample).std(ddof=0))),
        ):
            row[f"{name}_{count}"] = value
    return row, visible


def predict_ranges(bundle: dict, fold: dict, features: dict, clock: str) -> dict:
    values = np.array([_number(features.get(name)) for name in bundle["features"]])
    values = np.where(np.isfinite(values), values, np.asarray(fold["medians"], dtype=float))
    targets = {}
    for target, model in fold["models"].items():
        point = max(0., tree_prediction(model, values))
        minimum = features["max_open_dist_so_far"] if target == "total_from_open" else 0.
        point += minimum
        targets[target] = {"typical": point}
        for level in ("90", "95"):
            targets[target][level] = max(minimum, point + model["adjustments"][clock][level])
    result = {}
    for level, label in LEVELS.items():
        total, remaining = targets["total_from_open"][level], targets["remaining_from_review"][level]
        lower = min(features["day_open"]-total, features["review_price"]-remaining)
        upper = max(features["day_open"]+total, features["review_price"]+remaining)
        result[level] = {
            "label": label, "lower": lower, "upper": upper,
            "put_strike": outward_strike(lower, "put", 1.),
            "call_strike": outward_strike(upper, "call", 1.),
            "total_distance": total, "remaining_distance": remaining,
            "coverage": bundle["validation"]["by_time"][clock][level],
        }
    return result


def historical_outcome(history: pd.DataFrame, trade_date, clock: str, ranges: dict) -> dict:
    selected = pd.Timestamp(trade_date).date()
    cutoff = pd.Timestamp(f"{selected} {clock}", tz="America/New_York")
    closing = pd.Timestamp(f"{selected} 16:00", tz="America/New_York")
    future = history[(history.timestamp_et >= cutoff) & (history.timestamp_et < closing)].sort_values("timestamp_et")
    future = future.copy()
    future["timestamp_et"] = future.timestamp_et.dt.tz_convert("America/New_York")
    expected = pd.date_range(cutoff, closing, freq="min", inclusive="left")
    if len(future) != len(expected) or not pd.DatetimeIndex(future.timestamp_et).equals(expected):
        return {"available": False, "reason": "The complete checkpoint-to-16:00 minute path is unavailable; no success/failure grade is assigned."}
    prices = future[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    if (not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any()
            or (prices.high < prices[["open", "close", "low"]].max(axis=1)).any()
            or (prices.low > prices[["open", "close", "high"]].min(axis=1)).any()):
        return {"available": False, "reason": "Future prices are incomplete or inconsistent; outcome is not graded."}
    low, high = float(prices.low.min()), float(prices.high.max())
    return {
        "available": True, "low": low, "high": high, "close": float(prices.iloc[-1].close),
        "levels": {level: {"put_held": low >= band["lower"], "call_held": high <= band["upper"],
                            "both_held": low >= band["lower"] and high <= band["upper"]}
                   for level, band in ranges.items()},
    }


def build_daily_price_forecast(symbol, history, trade_date, review_clock, headline_gate, prior_hourly=None) -> dict:
    clock = review_clock.strftime("%H:%M")
    base = {"strategy": STRATEGY_NAME, "symbol": symbol, "date": str(trade_date), "clock": clock,
            "available": False, "ranges": {}}
    if symbol not in SUPPORTED_SYMBOLS:
        return {**base, "status": "NOT RESEARCHED", "reason": f"No daily forecasting model has been researched for {symbol}. Models and percentages are never borrowed from another symbol."}
    if clock not in CHECKPOINTS:
        return {**base, "status": "OUTCOME CHECKPOINT", "reason": "No new forecast is issued after the regular session. Select 09:40 or a 15-minute checkpoint from 09:45 through 15:45 ET."}
    try:
        if not standard_session(str(pd.Timestamp(trade_date).date())):
            return {**base, "status": "SESSION NOT RESEARCHED", "reason": "This is a closed or shortened trading session. The full-session model and its accuracy figures are not applied to it."}
        bundle = model_bundle(symbol)
        fold = select_fold(bundle, trade_date)
        if fold is None:
            first = bundle["folds"][0]["valid_from"]
            last = bundle["folds"][-1]["valid_through"]
            return {**base, "status": "NO PRIOR-DATE MODEL", "reason": f"Prior-date models for {symbol} cover {first} through {last}. Earlier dates are initial training/calibration; later dates require an updated model."}
        features, visible = forecast_features(history, trade_date, clock, bundle.get("input_mode", "source_indicators"), prior_hourly)
        ranges = predict_ranges(bundle, fold, features, clock)
    except (OSError, ValueError, KeyError) as exc:
        return {**base, "status": "FORECAST UNAVAILABLE", "reason": str(exc)}
    gate = dict(headline_gate)
    return {
        **base, "available": True,
        "status": "PRICE REFERENCES AVAILABLE" if gate["clear"] else "REFERENCE ONLY — " + gate["status"],
        "reason": "Daily statistical forecast; not a technical pass or a guarantee of a maximum.",
        "headline_gate": gate, "pre_headline": clock < "11:00", "ranges": ranges,
        "market_open": features["day_open"], "review_price": features["review_price"],
        "last_candle": str(visible.iloc[-1].timestamp_et), "features": features,
        "prior_history": features.get("prior_history_info", {}),
        "model_window": {k: fold[k] for k in ("valid_from", "valid_through", "training_through", "calibration_through")},
        "model_version": bundle["model_version"], "input_mode": bundle.get("input_mode"),
        "training_days": fold["training_days"], "calibration_days": fold["calibration_days"],
        "validation": bundle["validation"]["population"],
        "checkpoint_accuracy": bundle["validation"]["by_time"],
        "validation_periods": bundle["validation"].get("periods", []),
        "outcome": historical_outcome(history, trade_date, clock, ranges),
    }


import streamlit as st
ETF_SYMBOLS = frozenset({"QQQ", "SPY"})

def _display_number(value):
    return "—" if value is None or pd.isna(value) else f"{float(value):,.8f}".rstrip("0").rstrip(".")

precise_movement_text = _display_number

def render_daily_price_forecast(forecast: dict) -> None:
    st.subheader("Daily Price Boundary Strategy — Daily Forecast")
    if not forecast.get("available"):
        st.info(f"{forecast.get('status', 'UNAVAILABLE')} — {forecast.get('reason', '')}")
        return
    st.caption(
        f"{forecast['symbol']} · {forecast['clock']} ET · completed candles only · "
        "forecast endpoint 4:00 PM ET. A new estimate for this day, independent "
        "of whether another strategy passes."
    )
    primary = forecast["ranges"]["90"]
    lower = math.floor(primary["lower"] * 100) / 100
    upper = math.ceil(primary["upper"] * 100) / 100
    st.markdown(f"**90%-target price boundary: ${lower:,.2f} to ${upper:,.2f}**")
    left, right, accuracy = st.columns(3)
    left.metric("PUT short-strike reference: at or below", _display_number(primary["put_strike"]))
    right.metric("CALL short-strike reference: at or above", _display_number(primary["call_strike"]))
    coverage = primary["coverage"]
    accuracy.metric("Historical both-boundary coverage", f"{coverage['both_rate']:.1%}")
    substantial_periods = [period for period in forecast.get("validation_periods", []) if period["days"] >= 90]
    if substantial_periods:
        weakest = min(substantial_periods, key=lambda period: period["by_time"][forecast["clock"]]["90"])
        weakest_rate = weakest["by_time"][forecast["clock"]]["90"]
        if weakest_rate < .9:
            st.warning(
                f"Performance varies by period: the weakest test period with at least 90 sessions "
                f"held both boundaries {weakest_rate:.1%} of the time at this checkpoint "
                f"({weakest['first_test']}–{weakest['last_test']}, {weakest['days']} sessions). "
                "The 90% target was not maintained in every market regime."
            )
    st.caption(
        f"At this checkpoint: PUT/lower boundary held {coverage['put_count']}/{coverage['days']} "
        f"({coverage['put_rate']:.1%}); CALL/upper boundary held {coverage['call_count']}/{coverage['days']} "
        f"({coverage['call_rate']:.1%}); both held {coverage['both_count']}/{coverage['days']}. "
        "These are unrounded price-boundary containment results, not option profit or assignment probabilities. "
        "Strike references are rounded outward; listed contracts and credits remain in the independent chain table."
    )
    gate = forecast["headline_gate"]
    if not gate.get("clear"):
        st.warning(f"{forecast['status']}. {gate.get('reason', '')} The forecast is a reference, not entry approval.")
    elif forecast.get("pre_headline"):
        st.info("This is before the usual 11:00 headline review. The forecast does not waive your headline rules.")
    if forecast["symbol"] in ETF_SYMBOLS:
        st.caption("Regular-session forecast only. No validated 5:30 PM boundary or after-hours accuracy is supplied.")
    with st.expander("95% stress boundary and typical range"):
        rows = []
        for level in ("95", "typical"):
            band = forecast["ranges"][level]
            evidence = band["coverage"]
            rows.append({"Range": band["label"],
                         "Lower price": f"${math.floor(band['lower']*100)/100:,.2f}",
                         "Upper price": f"${math.ceil(band['upper']*100)/100:,.2f}",
                         "PUT reference": _display_number(band["put_strike"]),
                         "CALL reference": _display_number(band["call_strike"]),
                         "Both held historically": f"{evidence['both_count']}/{evidence['days']} ({evidence['both_rate']:.1%})"})
        st.dataframe(rows, width="stretch", hide_index=True)
        st.caption("The typical range is a point-estimate range, not a calibrated 90% or 95% boundary. It is not automatically selected in the final summary.")
    with st.expander("Forecast inputs, method, and accuracy at every checkpoint"):
        features = forecast["features"]
        prior = forecast.get("prior_history", {})
        if prior:
            st.caption(f"Prior volatility inputs: {prior['complete_sessions']} complete sessions, "
                       f"{prior['first_date']} through {prior['last_date']}. "
                       f"Minute history supplied {prior['minute_sessions']}; hourly regular-session history supplied "
                       f"{prior['hourly_sessions']}, with {prior['verified_overlap_sessions']} overlapping sessions checked. "
                       "Overlaps count once. Today's price structure and ATR still use one-minute candles.")
        st.dataframe([
            {"Input": "9:30 open", "Value": _display_number(features["day_open"])},
            {"Input": "Last completed price", "Value": _display_number(features["review_price"])},
            {"Input": "Range so far", "Value": _display_number(features["range_so_far"])},
            {"Input": "One-minute ATR input", "Value": precise_movement_text(features["source_atr1"])},
            {"Input": "Prior daily ATR(14)", "Value": _display_number(features["prior_daily_atr14"])},
        ], width="stretch", hide_index=True)
        window = forecast["model_window"]
        population = forecast["validation"]
        st.write(
            f"Model {forecast['model_version']}: trained on {forecast['training_days']} earlier sessions through "
            f"{window['training_through']}, calibrated on {forecast['calibration_days']} separate earlier sessions "
            f"through {window['calibration_through']}. Last input candle: {forecast['last_candle']}."
        )
        st.write(
            "The model uses today's completed price structure plus prior-session volatility. "
            "It estimates total movement from the open and remaining movement from the checkpoint, "
            "then uses the farther lower and upper prices from those two anchors. "
            "Calibration is specific to the selected time. A calm late session can still retain a wide "
            "boundary if substantial movement already happened earlier. No future candle is an input."
        )
        st.caption(
            f"Retrospective validation: {population['tested_days']} unseen test sessions from "
            f"{population['first_test']} through {population['last_test']}; "
            f"{population['initial_training_calibration_days']} initial sessions reserved for training/calibration. "
            "No headline or other strategy-pass filter was applied. Shortened/incomplete sessions are excluded. "
            "The percentages below are research statistics across the test history, not information available "
            "on each historical date and not a promise for today's market. Later checkpoints need not improve monotonically."
        )
        rows = []
        for clock, levels in forecast["checkpoint_accuracy"].items():
            stats = levels["90"]
            rows.append({"Checkpoint ET": clock, "Test days": stats["days"],
                         "PUT held": f"{stats['put_rate']:.1%}",
                         "CALL held": f"{stats['call_rate']:.1%}",
                         "Both held": f"{stats['both_rate']:.1%}"})
        st.dataframe(rows, width="stretch", hide_index=True)
        st.markdown("**Coverage by test period at the selected checkpoint**")
        st.dataframe([{"First test": period["first_test"], "Last test": period["last_test"],
                       "Test days": period["days"],
                       "90%-target: both held": f"{period['by_time'][forecast['clock']]['90']:.1%}",
                       "95%-target: both held": f"{period['by_time'][forecast['clock']]['95']:.1%}"}
                      for period in forecast.get("validation_periods", [])], width="stretch", hide_index=True)
        st.caption("Short final periods have much less evidence. A small-sample 100% result is not a guarantee.")
    with st.expander("What happened afterward — forecast boundary check"):
        outcome = forecast["outcome"]
        if not outcome.get("available"):
            st.info(outcome.get("reason", "Outcome unavailable."))
        else:
            st.write(f"Subsequent low ${outcome['low']:,.2f}; high ${outcome['high']:,.2f}; last regular-session close ${outcome['close']:,.2f}.")
            st.dataframe([{"Boundary": forecast["ranges"][level]["label"],
                           "PUT/lower": "HELD" if item["put_held"] else "BREACHED",
                           "CALL/upper": "HELD" if item["call_held"] else "BREACHED",
                           "Both": "HELD" if item["both_held"] else "BREACHED"}
                          for level, item in outcome["levels"].items()], width="stretch", hide_index=True)
            st.caption("This is a price-path check through the regular session, not a filled-trade P&L or official settlement/assignment result.")
