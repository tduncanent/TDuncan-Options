from __future__ import annotations

from datetime import datetime, time, timedelta
import math

import pandas as pd



EASTERN = "America/New_York"
ATR1_COLUMN = "movement_atr_1m"
TARGET_FRESH = "FRESH_REVIEW"
TARGET_OPEN = "TOTAL_OPEN"
TARGET_STRIKE_ONLY = "ROUNDED_STRIKE_ONLY"


def _time_label(value: time) -> str:
    return datetime.combine(datetime(2000, 1, 1), value).strftime("%I:%M %p").lstrip("0")


_review_clocks = [time(9, 40)]
_cursor = datetime(2000, 1, 1, 9, 45)
_last = datetime(2000, 1, 1, 15, 45)
while _cursor <= _last:
    _review_clocks.append(_cursor.time())
    _cursor += timedelta(minutes=15)

MOVEMENT_REVIEW_OPTIONS = tuple(_time_label(value) for value in _review_clocks)
MOVEMENT_REVIEW_CLOCKS = dict(zip(MOVEMENT_REVIEW_OPTIONS, _review_clocks))


FEATURE_LABELS = {
    "M": "Maximum distance from 9:30 open so far (M)",
    "D": "Maximum distance from 9:30 open so far (D)",
    "R": "Range since 9:30 (R)",
    "R60": "Most recent 60-minute range (R60)",
    "A1": "One-minute ATR(14) (A1)",
    "A15": "Completed 15-minute ATR(14) (A15)",
    "G": "Absolute overnight gap (G)",
}

TARGET_LABELS = {
    TARGET_OPEN: "Fixed-open total-session ceiling",
    TARGET_FRESH: "Fresh movement from this checkpoint",
    TARGET_STRIKE_ONLY: "Rounded-strike observation (not a movement ceiling)",
}


def _rule(
    rule_id: str,
    symbol: str,
    review_time: str,
    target_kind: str,
    ceiling: float,
    conditions: tuple[tuple[str, float], ...],
    rule_class: str,
    *,
    operating: bool,
    sample_total: int | None = None,
    holdout_total: int | None = None,
    confirmation_total: int | None = None,
    observed_max: float | None = None,
    warning: str = "",
    version: str = "1.0",
) -> dict:
    return {
        "rule_id": rule_id,
        "symbol": symbol,
        "review_time": review_time,
        "target_kind": target_kind,
        "ceiling": float(ceiling),
        "conditions": tuple(conditions),
        "rule_class": rule_class,
        "operating": bool(operating),
        "sample_total": sample_total,
        "holdout_total": holdout_total,
        "confirmation_total": confirmation_total,
        "observed_max": observed_max,
        "warning": warning,
        "version": version,
    }


XSP_RULES = (
    _rule("XSP-E0940-O7-v1", "XSP", "09:40", TARGET_OPEN, 7, (("M", 2.0), ("A1", 0.25), ("G", 2.5)), "LIMITED_SAMPLE_LOCKED", operating=True, sample_total=197, holdout_total=18, observed_max=6.96, warning="Early signal; the normal headline review has not been completed."),
    _rule("XSP-E1015-O7-v1", "XSP", "10:15", TARGET_OPEN, 7, (("M", 3.5), ("A15", 0.8), ("G", 4.0)), "CORE", operating=True, sample_total=279, holdout_total=34, observed_max=6.96, warning="Early signal; the normal headline review has not been completed."),
    _rule("XSP-E1030-O7-v1", "XSP", "10:30", TARGET_OPEN, 7, (("M", 3.5), ("A15", 0.8), ("G", 4.0)), "CORE", operating=True, sample_total=274, holdout_total=33, observed_max=6.35, warning="Early signal; the normal headline review has not been completed."),
    _rule("XSP-E1045-O7-v1", "XSP", "10:45", TARGET_OPEN, 7, (("M", 3.5), ("A15", 0.8), ("G", 4.0)), "CORE", operating=True, sample_total=276, holdout_total=33, observed_max=6.84, warning="Early signal; the normal headline review has not been completed."),
    _rule("XSP-R1100-O5-v1", "XSP", "11:00", TARGET_OPEN, 5, (("M", 1.5), ("A15", 0.7), ("G", 3.0)), "LIMITED_SAMPLE_LOCKED", operating=True, sample_total=99, holdout_total=6, observed_max=4.74, warning="Locked but limited-sample rule; retain the sample warning."),
    _rule("XSP-R1100-O7-v1", "XSP", "11:00", TARGET_OPEN, 7, (("M", 3.5), ("A15", 0.9), ("G", 4.0)), "CORE", operating=True, sample_total=362, holdout_total=48, observed_max=6.84),
    _rule("XSP-R1145-O5-v1", "XSP", "11:45", TARGET_OPEN, 5, (("M", 1.5), ("A15", 1.2), ("G", 3.0)), "CORE", operating=True, sample_total=173, holdout_total=22, observed_max=4.74),
    _rule("XSP-R1300-O4-v1", "XSP", "13:00", TARGET_OPEN, 4, (("M", 1.5), ("A15", 0.8), ("G", 4.0)), "LIMITED_SAMPLE_LOCKED", operating=True, sample_total=118, holdout_total=12, observed_max=3.69, warning="Locked but limited-sample rule; retain the sample warning."),
    _rule("XSP-R1300-P4-v1", "XSP", "13:00", TARGET_FRESH, 4, (("M", 1.5), ("A15", 1.1), ("G", 3.0)), "LIMITED_SAMPLE_LOCKED", operating=True, sample_total=128, holdout_total=14, observed_max=3.98, warning="Locked but limited-sample rule; retain the sample warning."),
    _rule("XSP-R1300-O8-v1", "XSP", "13:00", TARGET_OPEN, 8, (("M", 4.5), ("A15", 1.5), ("G", 3.0)), "CORE", operating=True, sample_total=663, holdout_total=109, observed_max=7.89),
    _rule("XSP-R1300-O9-v1", "XSP", "13:00", TARGET_OPEN, 9, (("M", 5.5), ("A15", 1.4), ("G", 4.0)), "CORE", operating=True, sample_total=755, holdout_total=127, observed_max=8.87),
    _rule("XSP-R1415-O4-v1", "XSP", "14:15", TARGET_OPEN, 4, (("M", 1.5), ("A15", 1.0), ("G", 4.5)), "LIMITED_SAMPLE_LOCKED", operating=True, sample_total=100, holdout_total=10, observed_max=3.74, warning="Locked but limited-sample rule; retain the sample warning."),
    _rule("XSP-R1415-P4-v1", "XSP", "14:15", TARGET_FRESH, 4, (("R60", 1.0), ("A15", 0.7), ("G", 4.0)), "CORE", operating=True, sample_total=172, holdout_total=21, observed_max=3.23),
    _rule("XSP-R1415-P6-v1", "XSP", "14:15", TARGET_FRESH, 6, (("R60", 1.0), ("A1", 0.15), ("G", 6.0)), "CORE", operating=True, sample_total=227, holdout_total=36, observed_max=5.08),
    _rule("XSP-R1415-O7-v1", "XSP", "14:15", TARGET_OPEN, 7, (("M", 4.5), ("A15", 1.3), ("G", 3.0)), "CORE", operating=True, sample_total=612, holdout_total=97, observed_max=6.65),
    _rule("XSP-R1415-P8-v1", "XSP", "14:15", TARGET_FRESH, 8, (("R60", 4.5), ("A1", 0.3), ("G", 10.0)), "CORE", operating=True, sample_total=931, holdout_total=177, observed_max=7.88),
    _rule("XSP-R1445-P3-v1", "XSP", "14:45", TARGET_FRESH, 3, (("R60", 2.0), ("A15", 0.6), ("G", 4.0)), "CORE", operating=True, sample_total=174, holdout_total=21, observed_max=2.88),
    _rule("XSP-R1500-O6-v1", "XSP", "15:00", TARGET_OPEN, 6, (("M", 3.5), ("A15", 1.2), ("G", 10.0)), "CORE", operating=True, sample_total=526, holdout_total=75, observed_max=5.42),
    _rule("XSP-R1515-P3-v1", "XSP", "15:15", TARGET_FRESH, 3, (("R60", 1.5), ("A15", 0.7), ("G", 3.0)), "CORE", operating=True, sample_total=287, holdout_total=41, observed_max=2.74),
    _rule("XSP-R1530-P2-v1", "XSP", "15:30", TARGET_FRESH, 2, (("R60", 1.0), ("A15", 0.7), ("G", 4.0)), "CORE", operating=True, sample_total=218, holdout_total=36, observed_max=1.88),
    _rule("XSP-R1545-P2S-v1", "XSP", "15:45", TARGET_FRESH, 2, (("R60", 1.0), ("A15", 0.7), ("G", 4.0)), "CORE", operating=True, sample_total=229, holdout_total=39, observed_max=1.97, warning="Strict locked $2 rule; never substitute the rejected broader candidate."),
    _rule("XSP-R1545-P3-v1", "XSP", "15:45", TARGET_FRESH, 3, (("R60", 3.0), ("A15", 1.4), ("G", 10.0)), "CORE", operating=True, sample_total=904, holdout_total=175, observed_max=2.81),
    _rule("XSP-X1530-S1-v1", "XSP", "15:30", TARGET_STRIKE_ONLY, 1, (("R60", 0.75), ("A15", 0.7), ("G", 4.0)), "EXPERIMENTAL_STRIKE_ONLY", operating=False, sample_total=108, holdout_total=26, observed_max=1.74, warning="Not a literal $1 movement ceiling; the underlying move reached $1.74."),
)


SPY_RULES = (
    _rule("SPY-R9-0940-v1", "SPY", "09:40", TARGET_FRESH, 9, (("M", 2.0), ("A1", 0.25), ("G", 3.0)), "CORE_PRIMARY", operating=True, sample_total=625, holdout_total=22, observed_max=8.76),
    _rule("SPY-OPEN9-0940-v1", "SPY", "09:40", TARGET_OPEN, 9, (("M", 2.0), ("A1", 0.25), ("G", 3.0)), "CORE_PRIMARY", operating=True, sample_total=625, holdout_total=22, observed_max=8.95),
    _rule("SPY-R8-0945-v1", "SPY", "09:45", TARGET_FRESH, 8, (("M", 1.5), ("A15", 0.7), ("G", 5.0)), "CORE_PRIMARY", operating=True, sample_total=624, holdout_total=24, observed_max=7.84),
    _rule("SPY-OPEN8-0945-v1", "SPY", "09:45", TARGET_OPEN, 8, (("M", 1.0), ("A15", 0.7), ("G", 4.0)), "CORE_PRIMARY", operating=True, sample_total=558, holdout_total=21, observed_max=7.44),
    _rule("SPY-L7-0945-v1", "SPY", "09:45", TARGET_FRESH, 7, (("M", 1.0), ("A15", 0.7), ("G", 1.0)), "LIMITED_PRIMARY", operating=False, sample_total=362, holdout_total=16, observed_max=6.77, warning="Research-only limited alternative; it cannot replace the core $8 rule."),
    _rule("SPY-L6-1015-v1", "SPY", "10:15", TARGET_FRESH, 6, (("M", 1.0), ("A15", 0.9), ("G", 2.5)), "LIMITED_PRIMARY", operating=False, sample_total=487, holdout_total=14, observed_max=5.93, warning="Research-only limited alternative."),
    _rule("SPY-R7-1100-v1", "SPY", "11:00", TARGET_FRESH, 7, (("M", 4.0), ("A15", 1.5), ("G", 0.5)), "CORE_PRIMARY", operating=True, sample_total=350, holdout_total=29, observed_max=6.82),
    _rule("SPY-OPEN7-1130-v1", "SPY", "11:30", TARGET_OPEN, 7, (("M", 5.0), ("A1", 0.15), ("G", 3.5)), "CORE_PRIMARY", operating=True, sample_total=661, holdout_total=21, observed_max=6.74),
    _rule("SPY-R6-1145-v1", "SPY", "11:45", TARGET_FRESH, 6, (("M", 1.5), ("A15", 1.2), ("G", 3.0)), "CORE_PRIMARY", operating=True, sample_total=547, holdout_total=22, observed_max=5.53),
    _rule("SPY-OPEN6-1145-v1", "SPY", "11:45", TARGET_OPEN, 6, (("M", 1.5), ("A15", 1.2), ("G", 3.0)), "CORE_PRIMARY", operating=True, sample_total=547, holdout_total=22, observed_max=5.51),
    _rule("SPY-S9-1230-v1", "SPY", "12:30", TARGET_FRESH, 9, (("M", 4.5), ("A15", 1.7), ("G", 4.0)), "SECONDARY_VALIDATED", operating=False, sample_total=1409, confirmation_total=53, observed_max=8.965, warning="Secondary-validated result; keep separate from the primary channel."),
    _rule("SPY-R4-1330-v1", "SPY", "13:30", TARGET_FRESH, 4, (("R60", 1.5), ("A15", 1.5), ("G", 0.5)), "CORE_PRIMARY", operating=True, sample_total=296, holdout_total=20, observed_max=3.93),
    _rule("SPY-R3-1445-v1", "SPY", "14:45", TARGET_FRESH, 3, (("R60", 1.5), ("A15", 0.6), ("G", 5.0)), "CORE_PRIMARY", operating=True, sample_total=607, holdout_total=21, observed_max=2.88),
    _rule("SPY-OPEN4-1500-v1", "SPY", "15:00", TARGET_OPEN, 4, (("M", 2.5), ("A1", 0.15), ("G", 2.0)), "CORE_PRIMARY", operating=True, sample_total=559, holdout_total=22, observed_max=3.685),
    _rule("SPY-S5-1500-v1", "SPY", "15:00", TARGET_OPEN, 5, (("M", 3.0), ("A1", 0.2), ("G", 8.0)), "SECONDARY_VALIDATED", operating=False, sample_total=914, confirmation_total=21, observed_max=4.85, warning="Secondary-validated result; keep separate from the primary channel."),
    _rule("SPY-OPEN5-1515-v1", "SPY", "15:15", TARGET_OPEN, 5, (("M", 3.5), ("A1", 0.2), ("G", 10.0)), "CORE_PRIMARY", operating=True, sample_total=986, holdout_total=68, observed_max=4.77),
    _rule("SPY-R2-1530-v1", "SPY", "15:30", TARGET_FRESH, 2, (("R60", 1.0), ("A15", 0.7), ("G", 3.0)), "CORE_PRIMARY", operating=True, sample_total=611, holdout_total=35, observed_max=1.955),
    _rule("SPY-S4-1530-v1", "SPY", "15:30", TARGET_FRESH, 4, (("R60", 2.0), ("A15", 1.2), ("G", 12.0)), "SECONDARY_VALIDATED", operating=False, sample_total=1366, confirmation_total=61, observed_max=4.0, warning="Secondary fallback only when the core $2 rule does not pass."),
    _rule("SPY-OPEN3-1545-v1", "SPY", "15:45", TARGET_OPEN, 3, (("M", 2.0), ("A15", 1.2), ("G", 5.0)), "CORE_PRIMARY", operating=True, sample_total=521, holdout_total=20, observed_max=2.87),
)


QQQ_RULES = (
    _rule("QQQ-S16-0940-v1", "QQQ", "09:40", TARGET_FRESH, 16, (("M", 1.5), ("A1", 0.65), ("G", 10.0)), "SECONDARY_VALIDATED", operating=True, sample_total=1337, confirmation_total=18, observed_max=15.46),
    _rule("QQQ-OPEN16-0940-v1", "QQQ", "09:40", TARGET_OPEN, 16, (("M", 1.5), ("A1", 0.65), ("G", 10.0)), "SECONDARY_VALIDATED", operating=True, sample_total=1337, confirmation_total=18, observed_max=15.17),
    _rule("QQQ-S15-0945-v1", "QQQ", "09:45", TARGET_FRESH, 15, (("M", 1.5), ("A15", 3.2), ("G", 12.0)), "SECONDARY_VALIDATED", operating=True, sample_total=1241, confirmation_total=21, observed_max=14.96),
    _rule("QQQ-R12-1000-v1", "QQQ", "10:00", TARGET_FRESH, 12, (("M", 1.5), ("A15", 3.1), ("G", 10.0)), "CORE_PRIMARY", operating=True, sample_total=943, holdout_total=38, observed_max=11.87),
    _rule("QQQ-R11-1015-v1", "QQQ", "10:15", TARGET_FRESH, 11, (("R60", 5.5), ("A1", 0.3), ("G", 8.0)), "CORE_PRIMARY", operating=True, sample_total=887, holdout_total=20, observed_max=10.66, warning="Validated, but no qualifying 2026 occurrence was observed."),
    _rule("QQQ-OPEN10-1015-v1", "QQQ", "10:15", TARGET_OPEN, 10, (("M", 5.5), ("A1", 0.3), ("G", 4.0)), "CORE_PRIMARY", operating=True, sample_total=869, holdout_total=20, observed_max=9.9),
    _rule("QQQ-R10-1100-v1", "QQQ", "11:00", TARGET_FRESH, 10, (("R60", 6.0), ("A15", 1.9), ("G", 2.5)), "CORE_PRIMARY", operating=True, sample_total=1251, holdout_total=84, observed_max=9.92),
    _rule("QQQ-OPEN9-1100-v1", "QQQ", "11:00", TARGET_OPEN, 9, (("M", 4.0), ("A15", 1.3), ("G", 2.0)), "CORE_PRIMARY", operating=True, sample_total=947, holdout_total=48, observed_max=8.89),
    _rule("QQQ-OPEN8-1115-v1", "QQQ", "11:15", TARGET_OPEN, 8, (("M", 2.5), ("A15", 1.1), ("G", 4.0)), "CORE_PRIMARY", operating=True, sample_total=776, holdout_total=24, observed_max=7.97),
    _rule("QQQ-R6L-1230-v1", "QQQ", "12:30", TARGET_FRESH, 6, (("M", 2.0), ("A15", 1.5), ("G", 2.5)), "LIMITED_PRIMARY", operating=False, sample_total=511, holdout_total=10, observed_max=5.89, warning="Research-only limited alternative; it cannot replace the core $7 result."),
    _rule("QQQ-R7-1230-v1", "QQQ", "12:30", TARGET_FRESH, 7, (("M", 8.5), ("A15", 1.2), ("G", 2.5)), "CORE_PRIMARY", operating=True, sample_total=1071, holdout_total=54, observed_max=6.84),
    _rule("QQQ-OPEN7-1245-v1", "QQQ", "12:45", TARGET_OPEN, 7, (("M", 3.0), ("A1", 0.25), ("G", 2.5)), "CORE_PRIMARY", operating=True, sample_total=786, holdout_total=27, observed_max=6.26),
    _rule("QQQ-R8-1315-v1", "QQQ", "13:15", TARGET_FRESH, 8, (("M", 11.5), ("A15", 1.6), ("G", 2.5)), "CORE_PRIMARY", operating=True, sample_total=1260, holdout_total=89, observed_max=7.9),
    _rule("QQQ-R5-1330-v1", "QQQ", "13:30", TARGET_FRESH, 5, (("M", 4.0), ("A15", 1.9), ("G", 0.5)), "LIMITED_PRIMARY", operating=False, sample_total=321, holdout_total=11, observed_max=4.84, warning="Research-only limited rule."),
    _rule("QQQ-R7-1345-v1", "QQQ", "13:45", TARGET_FRESH, 7, (("R60", 6.5), ("A15", 1.7), ("G", 2.5)), "CORE_PRIMARY", operating=True, sample_total=1292, holdout_total=96, observed_max=6.92),
    _rule("QQQ-R9-1400-v1", "QQQ", "14:00", TARGET_FRESH, 9, (("M", 15.0), ("A15", 2.2), ("G", 2.5)), "CORE_PRIMARY", operating=True, sample_total=1335, holdout_total=111, observed_max=8.85),
    _rule("QQQ-R6-1415-v1", "QQQ", "14:15", TARGET_FRESH, 6, (("R60", 1.0), ("A15", 1.3), ("G", 8.0)), "CORE_PRIMARY", operating=True, sample_total=657, holdout_total=28, observed_max=5.73),
    _rule("QQQ-OPEN6-1415-v1", "QQQ", "14:15", TARGET_OPEN, 6, (("M", 3.0), ("A1", 0.25), ("G", 10.0)), "CORE_PRIMARY", operating=True, sample_total=844, holdout_total=38, observed_max=5.82),
    _rule("QQQ-R4-1445-v1", "QQQ", "14:45", TARGET_FRESH, 4, (("R60", 1.5), ("A15", 0.9), ("G", 8.0)), "CORE_PRIMARY", operating=True, sample_total=957, holdout_total=49, observed_max=3.97),
    _rule("QQQ-R4-1500-v1", "QQQ", "15:00", TARGET_FRESH, 4, (("R60", 1.0), ("A15", 1.0), ("G", 6.0)), "CORE_PRIMARY", operating=True, sample_total=658, holdout_total=36, observed_max=3.26),
    _rule("QQQ-R3-1515-v1", "QQQ", "15:15", TARGET_FRESH, 3, (("R60", 2.5), ("A1", 0.15), ("G", 2.0)), "CORE_PRIMARY", operating=True, sample_total=709, holdout_total=40, observed_max=2.84),
    _rule("QQQ-R2-1530-v1", "QQQ", "15:30", TARGET_FRESH, 2, (("R60", 1.0), ("A15", 1.0), ("G", 2.5)), "CORE_PRIMARY", operating=True, sample_total=607, holdout_total=27, observed_max=2.0),
    _rule("QQQ-R3-1530-v1", "QQQ", "15:30", TARGET_FRESH, 3, (("M", 9.0), ("A15", 0.9), ("G", 8.0)), "CORE_PRIMARY", operating=True, sample_total=1114, holdout_total=66, observed_max=2.955),
    _rule("QQQ-OPEN4L-1530-v1", "QQQ", "15:30", TARGET_OPEN, 4, (("M", 2.5), ("A15", 1.4), ("G", 10.0)), "LIMITED_PRIMARY", operating=False, sample_total=613, holdout_total=16, observed_max=3.78, warning="Research-only limited fixed-open rule."),
    _rule("QQQ-OPEN5-1530-v1", "QQQ", "15:30", TARGET_OPEN, 5, (("M", 3.5), ("A1", 0.15), ("G", 8.0)), "CORE_PRIMARY", operating=True, sample_total=683, holdout_total=29, observed_max=4.39),
    _rule("QQQ-R2-1545-v1", "QQQ", "15:45", TARGET_FRESH, 2, (("R60", 1.5), ("A15", 0.9), ("G", 2.5)), "CORE_PRIMARY", operating=True, sample_total=838, holdout_total=43, observed_max=2.0),
    _rule("QQQ-R3-1545-v1", "QQQ", "15:45", TARGET_FRESH, 3, (("R60", 4.0), ("A1", 0.35), ("G", 5.0)), "CORE_PRIMARY", operating=True, sample_total=1569, holdout_total=148, observed_max=2.96),
)


def _xnd_primary_rules() -> tuple[dict, ...]:
    fresh = (
        ("11:00", 5, (("D", 4.25), ("A15", 1.1), ("G", 1.5)), 805, 44, 4.9159),
        ("11:15", 5, (("R60", 3.25), ("A1", 0.3), ("G", 1.5)), 806, 44, 4.8011),
        ("11:30", 5, (("R60", 1.5), ("A15", 1.05), ("G", 8.0)), 858, 46, 4.7970),
        ("11:45", 5, (("D", 4.5), ("A15", 2.15), ("G", 1.5)), 811, 46, 4.9036),
        ("12:00", 5, (("D", 6.0), ("A15", 2.05), ("G", 8.0)), 1014, 85, 4.8991),
        ("12:15", 4, (("D", 4.5), ("A15", 0.6), ("G", 1.5)), 674, 20, 3.9442),
        ("12:30", 5, (("D", 6.0), ("A15", 1.9), ("G", 8.0)), 1014, 85, 4.8637),
        ("12:45", 5, (("D", 6.0), ("A15", 1.9), ("G", 8.0)), 1014, 85, 4.8011),
        ("13:00", 5, (("D", 5.0), ("A15", 0.95), ("G", 8.0)), 1028, 92, 4.7539),
        ("13:15", 5, (("D", 5.0), ("A15", 1.2), ("G", 8.0)), 1052, 98, 4.6986),
        ("13:30", 3, (("D", 5.0), ("A15", 0.7), ("G", 1.25)), 718, 37, 2.9930),
        ("13:45", 5, (("D", 5.0), ("A15", 1.2), ("G", 8.0)), 1053, 99, 4.6781),
        ("14:00", 4, (("D", 5.0), ("A15", 0.9), ("G", 1.5)), 830, 54, 3.6285),
        ("14:15", 5, (("D", 6.0), ("A15", 1.2), ("G", 8.0)), 1067, 106, 4.2886),
        ("14:30", 3, (("R60", 1.75), ("A1", 0.125), ("G", 5.0)), 912, 75, 2.8659),
        ("14:45", 4, (("D", 6.0), ("A15", 0.9), ("G", 8.0)), 1045, 101, 3.6613),
        ("15:00", 2, (("R", 3.75), ("A15", 0.5), ("G", 5.0)), 758, 27, 1.9598),
        ("15:15", 2, (("R", 3.0), ("A15", 0.5), ("G", 5.0)), 707, 23, 1.4637),
        ("15:30", 3, (("R", 6.5), ("A15", 1.15), ("G", 8.0)), 1064, 106, 2.3698),
        ("15:45", 1, (("R60", 1.0), ("A1", 0.075), ("G", 4.0)), 522, 22, 0.8569),
    )
    total_open = (
        ("11:00", 5, (("D", 2.25), ("A1", 0.175), ("G", 5.0)), 817, 32, 4.9487),
        ("11:15", 5, (("D", 2.25), ("A1", 0.175), ("G", 5.0)), 829, 39, 4.9077),
        ("11:30", 4, (("D", 3.25), ("A1", 0.125), ("G", 1.5)), 618, 18, 3.9319),
        ("11:45", 4, (("D", 2.0), ("A15", 0.75), ("G", 1.5)), 657, 21, 3.9565),
        ("12:00", 4, (("D", 2.0), ("A15", 0.75), ("G", 1.5)), 648, 21, 3.6121),
        ("12:15", 4, (("D", 2.0), ("A15", 0.7), ("G", 1.5)), 633, 20, 3.6121),
        ("12:30", 4, (("D", 2.5), ("A15", 0.7), ("G", 1.5)), 699, 27, 3.8417),
        ("12:45", 4, (("D", 3.0), ("A15", 0.65), ("G", 1.5)), 698, 24, 3.9565),
        ("13:00", 4, (("D", 3.0), ("A15", 0.65), ("G", 1.5)), 714, 28, 3.9565),
        ("13:15", 4, (("D", 3.0), ("A15", 0.65), ("G", 1.5)), 718, 30, 3.8417),
        ("13:30", 4, (("D", 3.0), ("A15", 0.65), ("G", 1.5)), 720, 29, 3.8417),
        ("13:45", 4, (("D", 2.75), ("A15", 1.2), ("G", 1.5)), 755, 38, 3.9196),
        ("14:00", 4, (("D", 2.75), ("A15", 1.15), ("G", 1.5)), 751, 35, 3.9196),
        ("14:15", 7, (("D", 6.0), ("A15", 0.9), ("G", 8.0)), 1040, 97, 6.3673),
        ("14:30", 4, (("D", 2.75), ("A1", 0.15), ("G", 5.0)), 861, 58, 3.7105),
        ("14:45", 3, (("D", 2.0), ("A1", 0.125), ("G", 5.0)), 646, 28, 2.7839),
        ("15:00", 3, (("D", 2.25), ("A1", 0.125), ("G", 5.0)), 710, 33, 2.8208),
        ("15:15", 4, (("D", 2.75), ("A15", 1.15), ("G", 8.0)), 888, 62, 3.6859),
        ("15:30", 4, (("D", 3.25), ("A15", 1.15), ("G", 3.0)), 923, 68, 3.6859),
        ("15:45", 4, (("D", 3.5), ("A15", 1.15), ("G", 3.0)), 944, 74, 3.8417),
    )
    rules = []
    for clock, ceiling, conditions, total, confirmation, observed in fresh:
        rules.append(_rule(f"XND-FRESH-{clock.replace(':', '')}-{ceiling:g}-v1", "XND", clock, TARGET_FRESH, ceiling, conditions, "CURRENT_CONFIRMED", operating=True, sample_total=total, confirmation_total=confirmation, observed_max=observed))
    for clock, ceiling, conditions, total, confirmation, observed in total_open:
        rules.append(_rule(f"XND-OPEN-{clock.replace(':', '')}-{ceiling:g}-v1", "XND", clock, TARGET_OPEN, ceiling, conditions, "CURRENT_CONFIRMED", operating=True, sample_total=total, confirmation_total=confirmation, observed_max=observed))
    return tuple(rules)


XND_EARLY_RULES = (
    _rule("XND-EARLY-FRESH-0940-15-v1", "XND", "09:40", TARGET_FRESH, 15, (("D", 2.5), ("A1", 0.6), ("G", 10.0)), "SECONDARY_PRE_HEADLINE", operating=False, holdout_total=254, confirmation_total=133, observed_max=14.4757),
    _rule("XND-EARLY-FRESH-0945-16-v1", "XND", "09:45", TARGET_FRESH, 16, (("D", 3.25), ("A15", 2.4), ("G", 10.0)), "SECONDARY_PRE_HEADLINE", operating=False, holdout_total=255, confirmation_total=134, observed_max=15.2573),
    _rule("XND-EARLY-FRESH-1000-15-v1", "XND", "10:00", TARGET_FRESH, 15, (("R60", 4.5), ("A1", 0.575), ("G", 10.0)), "SECONDARY_PRE_HEADLINE", operating=False, holdout_total=255, confirmation_total=134, observed_max=14.3945),
    _rule("XND-EARLY-FRESH-1015-13-v1", "XND", "10:15", TARGET_FRESH, 13, (("D", 5.5), ("A15", 1.65), ("G", 10.0)), "SECONDARY_PRE_HEADLINE", operating=False, holdout_total=253, confirmation_total=132, observed_max=12.5840),
    _rule("XND-EARLY-FRESH-1030-13-v1", "XND", "10:30", TARGET_FRESH, 13, (("R60", 5.0), ("A1", 0.525), ("G", 10.0)), "SECONDARY_PRE_HEADLINE", operating=False, holdout_total=254, confirmation_total=133, observed_max=12.0708),
    _rule("XND-EARLY-FRESH-1045-12-v1", "XND", "10:45", TARGET_FRESH, 12, (("D", 5.5), ("A15", 1.7), ("G", 10.0)), "SECONDARY_PRE_HEADLINE", operating=False, holdout_total=254, confirmation_total=133, observed_max=11.8818),
    _rule("XND-EARLY-FRESH-0940-7-v1", "XND", "09:40", TARGET_FRESH, 7, (("D", 0.5), ("A1", 0.275), ("G", 4.0)), "LIMITED", operating=False, sample_total=510, confirmation_total=12, observed_max=6.2197, warning="Secondary limited early result; not equivalent to a post-headline current-confirmed rule."),
    _rule("XND-EARLY-FRESH-0945-7-v1", "XND", "09:45", TARGET_FRESH, 7, (("D", 0.5), ("A15", 1.15), ("G", 5.0)), "LIMITED", operating=False, sample_total=406, confirmation_total=9, observed_max=6.2197, warning="Secondary limited early result; not equivalent to a post-headline current-confirmed rule."),
    _rule("XND-EARLY-OPEN-1015-4-v1", "XND", "10:15", TARGET_OPEN, 4, (("D", 2.0), ("A1", 0.125), ("G", 1.5)), "DORMANT", operating=False, sample_total=271, confirmation_total=0, observed_max=3.4768, warning="Dormant: no qualifying 2026 occurrence; never activate automatically."),
)


XND_LIMITED_RULES = (
    _rule("XND-LIMITED-FRESH-1100-3-v1", "XND", "11:00", TARGET_FRESH, 3, (("D", 1.25), ("A15", 0.4), ("G", 1.5)), "DORMANT", operating=False, holdout_total=25, confirmation_total=0, observed_max=1.9680),
    _rule("XND-LIMITED-FRESH-1230-3-v1", "XND", "12:30", TARGET_FRESH, 3, (("R60", 1.0), ("A15", 0.6), ("G", 1.0)), "LIMITED", operating=False, holdout_total=61, confirmation_total=12, observed_max=2.1853),
    _rule("XND-LIMITED-FRESH-1315-3-v1", "XND", "13:15", TARGET_FRESH, 3, (("D", 3.75), ("A15", 0.5), ("G", 1.5)), "LIMITED", operating=False, holdout_total=67, confirmation_total=8, observed_max=2.0623),
    _rule("XND-LIMITED-FRESH-1345-2-v1", "XND", "13:45", TARGET_FRESH, 2, (("D", 2.5), ("A15", 0.75), ("G", 0.25)), "LIMITED", operating=False, holdout_total=20, confirmation_total=7, observed_max=1.9475),
    _rule("XND-LIMITED-FRESH-1400-2-v1", "XND", "14:00", TARGET_FRESH, 2, (("D", 3.5), ("A15", 0.6), ("G", 0.25)), "LIMITED", operating=False, holdout_total=20, confirmation_total=6, observed_max=1.8655),
    _rule("XND-LIMITED-FRESH-1415-2-v1", "XND", "14:15", TARGET_FRESH, 2, (("D", 2.75), ("A15", 0.75), ("G", 0.25)), "LIMITED", operating=False, holdout_total=21, confirmation_total=7, observed_max=1.7261),
    _rule("XND-SPARSE-FRESH-1430-2-v1", "XND", "14:30", TARGET_FRESH, 2, (("R60", 0.5), ("A15", 0.35), ("G", 2.5)), "SPARSE", operating=False, holdout_total=31, confirmation_total=3, observed_max=0.8159),
    _rule("XND-LIMITED-FRESH-1445-2-v1", "XND", "14:45", TARGET_FRESH, 2, (("R", 3.75), ("A15", 0.45), ("G", 4.0)), "LIMITED", operating=False, holdout_total=79, confirmation_total=14, observed_max=1.2833),
    _rule("XND-LIMITED-FRESH-1530-1-v1", "XND", "15:30", TARGET_FRESH, 1, (("R60", 0.5), ("A15", 0.35), ("G", 4.0)), "LIMITED", operating=False, holdout_total=46, confirmation_total=6, observed_max=0.7421),
)


RULES_BY_SYMBOL = {
    "XSP": XSP_RULES,
    "SPY": SPY_RULES,
    "QQQ": QQQ_RULES,
    "XND": _xnd_primary_rules() + XND_EARLY_RULES + XND_LIMITED_RULES,
}


def prepare_movement_history(history: pd.DataFrame) -> pd.DataFrame:
    """Attach continuous one-minute Wilder ATR without changing source precision."""
    if history.empty:
        return history.copy()
    if ATR1_COLUMN in history.columns:
        return history
    prepared = history.sort_values("timestamp_et").reset_index(drop=True).copy()
    previous_close = prepared["close"].shift(1)
    true_range = pd.concat(
        [
            prepared["high"] - prepared["low"],
            (prepared["high"] - previous_close).abs(),
            (prepared["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    prepared[ATR1_COLUMN] = true_range.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14,
    ).mean()
    return prepared


def _canonical_clock(review_label: str) -> tuple[str, time]:
    if review_label in MOVEMENT_REVIEW_CLOCKS:
        clock = MOVEMENT_REVIEW_CLOCKS[review_label]
        return clock.strftime("%H:%M"), clock
    parsed = datetime.strptime(str(review_label).strip(), "%H:%M").time()
    return parsed.strftime("%H:%M"), parsed


def _finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _passes_maximum(actual: float, threshold: float) -> bool:
    tolerance = 1e-12 * max(1.0, abs(float(threshold)))
    return _finite(actual) and float(actual) <= float(threshold) + tolerance


def evaluate_rule(rule: dict, features: dict) -> dict:
    conditions = []
    for feature, threshold in rule["conditions"]:
        actual = features.get(feature)
        passed = _passes_maximum(actual, threshold)
        conditions.append(
            {
                "feature": feature,
                "label": FEATURE_LABELS[feature],
                "operator": "<=",
                "threshold": float(threshold),
                "actual": float(actual) if _finite(actual) else None,
                "passed": passed,
            }
        )
    result = dict(rule)
    result["condition_results"] = conditions
    result["technical_pass"] = all(item["passed"] for item in conditions)
    result["selected"] = False
    return result


def _near_extreme(price: float, low: float, high: float) -> bool:
    span = float(high) - float(low)
    if span <= 0:
        return True
    return bool(
        float(price) <= float(low) + 0.30 * span
        or float(price) >= float(high) - 0.30 * span
    )


def _foundation_checkpoint(review_clock: time) -> tuple[str, time] | None:
    if review_clock < time(11, 0):
        return None
    if review_clock < time(13, 0):
        return "11:00 AM", time(11, 0)
    if review_clock < time(14, 15):
        return "1:00 PM", time(13, 0)
    return "2:15 PM", time(14, 15)


def _foundation_result(
    symbol: str,
    day_1m: pd.DataFrame,
    day_15m: pd.DataFrame,
    trade_date,
    review_clock: time,
) -> dict:
    checkpoint = _foundation_checkpoint(review_clock)
    if checkpoint is None:
        return {
            "required": False,
            "ready": True,
            "clear": True,
            "checkpoint": "Not required before 11:00 AM",
            "triggers": [],
            "metrics": {},
        }

    checkpoint_label, checkpoint_clock = checkpoint
    windows = {
        "11:00 AM": (time(9, 30), time(11, 0)),
        "1:00 PM": (time(11, 30), time(13, 0)),
        "2:15 PM": (time(12, 45), time(14, 15)),
    }
    start_clock, end_clock = windows[checkpoint_label]
    bar_times = day_15m["timestamp_et"].dt.time
    window = day_15m[(bar_times >= start_clock) & (bar_times < end_clock)].copy()
    if len(window) != 6:
        return {
            "required": True,
            "ready": False,
            "clear": False,
            "checkpoint": checkpoint_label,
            "triggers": [],
            "metrics": {},
            "reason": f"{checkpoint_label} requires exactly six completed 15-minute bars; found {len(window)}.",
        }

    cutoff = pd.Timestamp(datetime.combine(pd.Timestamp(trade_date).date(), checkpoint_clock), tz=EASTERN)
    completed_minutes = day_1m[day_1m["timestamp_et"] < cutoff].copy()
    if completed_minutes.empty:
        return {
            "required": True,
            "ready": False,
            "clear": False,
            "checkpoint": checkpoint_label,
            "triggers": [],
            "metrics": {},
            "reason": f"No completed one-minute bar is available for {checkpoint_label}.",
        }

    review_price = float(completed_minutes.iloc[-1]["close"])
    market_open = float(day_1m.iloc[0]["open"])
    displacement = abs(review_price - market_open)
    max_body = float((window["close"] - window["open"]).abs().max())
    churn = float((window["close"] - window["open"]).abs().sum())
    atr15 = window.iloc[-1].get("atr_14")
    if not _finite(atr15):
        return {
            "required": True,
            "ready": False,
            "clear": False,
            "checkpoint": checkpoint_label,
            "triggers": [],
            "metrics": {},
            "reason": f"Completed 15-minute ATR is unavailable at {checkpoint_label}.",
        }
    atr15 = float(atr15)
    near_recent = _near_extreme(
        review_price,
        float(window["low"].min()),
        float(window["high"].max()),
    )
    near_full = _near_extreme(
        review_price,
        float(completed_minutes["low"].min()),
        float(completed_minutes["high"].max()),
    )
    triggers = []

    if symbol == "XSP":
        if checkpoint_label == "11:00 AM":
            if max_body > 3.30 and near_recent:
                triggers.append("Impulse: body > 3.30 and price near the recent outer 30% extreme.")
            if churn > 7.75 and (displacement > 4.25 or atr15 > 2.25):
                triggers.append("Combined activity: churn > 7.75 and displacement > 4.25 or A15 > 2.25.")
        elif checkpoint_label == "1:00 PM":
            if max_body > 3.20 and near_recent:
                triggers.append("Impulse: body > 3.20 and price near the recent outer 30% extreme.")
            if atr15 > 2.80:
                triggers.append("ATR: A15 > 2.80.")
            if churn > 5.25 and displacement > 4.00:
                triggers.append("Churn/displacement: churn > 5.25 and displacement > 4.00.")
            if displacement >= 9.00 and near_full:
                triggers.append("Persistent trend: displacement >= 9.00 and price near the full-range extreme.")
        else:
            if max_body > 4.00 and near_recent:
                triggers.append("Impulse: body > 4.00 and price near the recent outer 30% extreme.")
            if atr15 > 2.60:
                triggers.append("ATR: A15 > 2.60.")
            if churn > 3.50 and displacement > 4.00:
                triggers.append("Churn/displacement: churn > 3.50 and displacement > 4.00.")
            if displacement >= 9.00 and near_full:
                triggers.append("Persistent trend: displacement >= 9.00 and price near the full-range extreme.")

    elif symbol == "SPY":
        thresholds = {
            "11:00 AM": (3.25, 2.30, 6.00, 2.00),
            "1:00 PM": (3.50, 3.10, 4.00, 5.00),
            "2:15 PM": (2.25, 2.30, 3.00, 10.00),
        }[checkpoint_label]
        impulse, atr_limit, churn_limit, displacement_limit = thresholds
        if max_body >= impulse and near_recent:
            triggers.append(f"Impulse: body >= {impulse:.2f} and price near the recent outer 30% extreme.")
        if atr15 >= atr_limit:
            triggers.append(f"ATR: A15 >= {atr_limit:.2f}.")
        if churn >= churn_limit and displacement >= displacement_limit:
            triggers.append(f"Churn/displacement: churn >= {churn_limit:.2f} and displacement >= {displacement_limit:.2f}.")

    elif symbol == "QQQ":
        if max_body > 3.20 and near_recent:
            triggers.append("Impulse: body > 3.20 and price near the recent outer 30% extreme.")
        if atr15 > 5.00:
            triggers.append("ATR: A15 > 5.00.")
        if churn > 11.90 and displacement > 4.00:
            triggers.append("Churn/displacement: churn > 11.90 and displacement > 4.00.")
        if checkpoint_label in {"1:00 PM", "2:15 PM"} and displacement >= 15.00 and near_full:
            triggers.append("Persistent trend: displacement >= 15.00 and price near the full-range extreme.")

    elif symbol == "XND":
        if checkpoint_label == "11:00 AM":
            if max_body >= 1.25 and near_recent:
                triggers.append("Impulse: body >= 1.25 and price near the recent outer 30% extreme.")
            if atr15 >= 2.25:
                triggers.append("ATR: A15 >= 2.25.")
            if churn >= 1.00 and displacement >= 4.50:
                triggers.append("Churn/displacement: churn >= 1.00 and displacement >= 4.50.")
        elif checkpoint_label == "1:00 PM":
            if max_body >= 2.00 and near_recent:
                triggers.append("Impulse: body >= 2.00 and price near the recent outer 30% extreme.")
            if atr15 >= 1.25:
                triggers.append("ATR: A15 >= 1.25.")
            if churn >= 1.50 and displacement >= 3.00:
                triggers.append("Churn/displacement: churn >= 1.50 and displacement >= 3.00.")
        else:
            table_version = (
                (max_body >= 1.75 and near_recent)
                or atr15 >= 1.50
                or (churn >= 1.50 and displacement >= 3.50)
            )
            prose_version = (
                (max_body > 2.00 and near_recent)
                or atr15 >= 1.25
                or (churn >= 1.50 and displacement > 3.00)
            )
            if table_version:
                triggers.append("XND 2:15 table version flagged (conservative union).")
            if prose_version:
                triggers.append("XND 2:15 prose version flagged (conservative union).")

    return {
        "required": True,
        "ready": True,
        "clear": not triggers,
        "checkpoint": checkpoint_label,
        "triggers": triggers,
        "metrics": {
            "max_body": max_body,
            "churn": churn,
            "atr15": atr15,
            "displacement": displacement,
            "near_recent_extreme": near_recent,
            "near_full_extreme": near_full,
        },
    }


def _headline_gate(status: str, review_clock: time) -> dict:
    if review_clock < time(11, 0):
        return {
            "name": "Headline review",
            "status": "NOT REQUIRED — PRE-HEADLINE RISK",
            "passed": True,
            "reason": "Before 11:00, the signal remains explicitly pre-headline risk.",
        }
    if status == "Not reviewed":
        return {
            "name": "Headline review",
            "status": "BLOCKED — UNRESEARCHED",
            "passed": False,
            "reason": "At or after 11:00, an unresearched headline status cannot be treated as clear.",
            "reason_code": "NO_SIGNAL_UNRESEARCHED",
        }
    if status == "Wait — hold entry until next review":
        return {
            "name": "Headline review",
            "status": "BLOCKED — WAIT",
            "passed": False,
            "reason": "The current headline review requires waiting until a later review.",
            "reason_code": "NO_SIGNAL_HEADLINE",
        }
    if status in {"Suggest skip", "Risk found — skip"}:
        return {
            "name": "Headline review",
            "status": "BLOCKED — FULL-DAY SKIP",
            "passed": False,
            "reason": "The headline review requires skipping this session.",
            "reason_code": "NO_SIGNAL_HEADLINE",
        }
    if status in {"Clear", "Monitor — entry allowed"}:
        return {
            "name": "Headline review",
            "status": "PASS — MONITOR" if status.startswith("Monitor") else "PASS — CLEAR",
            "passed": True,
            "reason": "Monitor remains entry-permitted." if status.startswith("Monitor") else "Headline review is clear.",
        }
    return {
        "name": "Headline review",
        "status": "BLOCKED — UNKNOWN STATUS",
        "passed": False,
        "reason": f"Unsupported headline status: {status!r}.",
        "reason_code": "NO_SIGNAL_UNRESEARCHED",
    }


def _session_features(
    history: pd.DataFrame,
    bars15: pd.DataFrame,
    trade_date,
    review_clock: time,
    required_features: set[str],
) -> tuple[dict, pd.DataFrame, pd.DataFrame, list[str]]:
    selected_date = pd.Timestamp(trade_date).date()
    day = history[history["trade_date"] == selected_date].sort_values("timestamp_et").copy()
    day15 = bars15[bars15["trade_date"] == selected_date].sort_values("timestamp_et").copy()
    errors = []
    if day.empty:
        return {}, day, day15, ["No one-minute data exists for the selected date."]

    cutoff = pd.Timestamp(datetime.combine(selected_date, review_clock), tz=EASTERN)
    session_open_time = pd.Timestamp(datetime.combine(selected_date, time(9, 30)), tz=EASTERN)
    visible = day[(day["timestamp_et"] >= session_open_time) & (day["timestamp_et"] < cutoff)].copy()
    expected_count = int((cutoff - session_open_time).total_seconds() // 60)
    minute_keys = visible["timestamp_et"].dt.floor("min")
    if len(visible) != expected_count or minute_keys.nunique() != expected_count:
        errors.append(
            f"Expected {expected_count} complete one-minute bars from 9:30 through the minute before the checkpoint; found {len(visible)}."
        )
    if visible.empty:
        return {}, day, day15, errors or ["No completed minute exists before the checkpoint."]
    if visible.iloc[0]["timestamp_et"].floor("min") != session_open_time:
        errors.append("The exact 9:30 opening bar is missing.")
    expected_last = cutoff - pd.Timedelta(minutes=1)
    if visible.iloc[-1]["timestamp_et"].floor("min") != expected_last:
        errors.append(f"The completed {expected_last.strftime('%I:%M %p').lstrip('0')} bar is missing.")
    finite_ohlc = visible[["open", "high", "low", "close"]].apply(
        lambda column: column.map(_finite)
    )
    if not finite_ohlc.all().all():
        errors.append("One or more required OHLC values are missing or nonfinite.")

    prior = history[history["trade_date"] < selected_date].sort_values("timestamp_et")
    prior_close = float(prior.iloc[-1]["close"]) if not prior.empty else None
    if not _finite(prior_close):
        errors.append("The previous regular-session close is unavailable.")

    market_open = float(visible.iloc[0]["open"])
    review_price = float(visible.iloc[-1]["close"])
    max_open_distance = max(
        float(visible["high"].max()) - market_open,
        market_open - float(visible["low"].min()),
        0.0,
    )
    recent = visible.tail(60)
    completed15 = day15[
        day15["timestamp_et"] + pd.Timedelta(minutes=15) <= cutoff
    ].copy()
    atr15 = completed15.iloc[-1].get("atr_14") if not completed15.empty else None
    atr1 = visible.iloc[-1].get(ATR1_COLUMN)
    features = {
        "O": market_open,
        "P": review_price,
        "M": max_open_distance,
        "D": max_open_distance,
        "R": float(visible["high"].max() - visible["low"].min()),
        "R60": float(recent["high"].max() - recent["low"].min()),
        "A1": float(atr1) if _finite(atr1) else None,
        "A15": float(atr15) if _finite(atr15) else None,
        "G": abs(market_open - float(prior_close)) if _finite(prior_close) else None,
        "displacement": abs(review_price - market_open),
    }
    for feature in required_features:
        if not _finite(features.get(feature)):
            errors.append(f"Required feature {feature} is unavailable at this checkpoint.")
    return features, day, day15, list(dict.fromkeys(errors))


def _historical_outcome(
    evaluation: dict,
    features: dict,
    day: pd.DataFrame,
    cutoff: pd.Timestamp,
) -> dict:
    if evaluation["target_kind"] == TARGET_OPEN:
        anchor = float(features["O"])
        observed = max(
            float(day["high"].max()) - anchor,
            anchor - float(day["low"].min()),
            0.0,
        )
    elif evaluation["target_kind"] == TARGET_FRESH:
        anchor = float(features["P"])
        future = day[day["timestamp_et"] >= cutoff]
        observed = (
            max(
                float(future["high"].max()) - anchor,
                anchor - float(future["low"].min()),
                0.0,
            )
            if not future.empty
            else 0.0
        )
    else:
        return {"available": False}
    ceiling = float(evaluation["ceiling"])
    return {
        "available": True,
        "observed_movement": observed,
        "literal_breach": observed > ceiling + 1e-12,
    }


def _signal(evaluation: dict, features: dict, day: pd.DataFrame, cutoff: pd.Timestamp) -> dict:
    anchor_type = "FIXED_OPEN" if evaluation["target_kind"] == TARGET_OPEN else "REVIEW_PRICE"
    anchor_price = float(features["O"] if anchor_type == "FIXED_OPEN" else features["P"])
    ceiling = float(evaluation["ceiling"])
    return {
        "rule_id": evaluation["rule_id"],
        "rule_version": evaluation["version"],
        "target_kind": evaluation["target_kind"],
        "target_label": TARGET_LABELS[evaluation["target_kind"]],
        "anchor_type": anchor_type,
        "anchor_price": anchor_price,
        "ceiling_points": ceiling,
        "lower_boundary": anchor_price - ceiling,
        "upper_boundary": anchor_price + ceiling,
        "rule_class": evaluation["rule_class"],
        "evidence_class": evaluation["evidence_class"],
        "sample_total": evaluation.get("sample_total"),
        "holdout_total": evaluation.get("holdout_total"),
        "confirmation_total": evaluation.get("confirmation_total"),
        "observed_max": evaluation.get("observed_max"),
        "warning": evaluation.get("warning", ""),
        "historical_outcome": _historical_outcome(evaluation, features, day, cutoff),
    }


def build_market_movement_assessment(
    symbol: str,
    history: pd.DataFrame,
    bars15: pd.DataFrame,
    trade_date,
    review_label: str,
    headline_status: str,
    *,
    fomc_day: bool = False,
    automatic_event: dict | None = None,
    include_historical_outcome: bool = False,
) -> dict:
    """Evaluate the approved exact-time, direction-neutral movement rules."""
    selected_date = pd.Timestamp(trade_date).date()
    canonical_clock, review_clock = _canonical_clock(review_label)
    rules = [
        rule
        for rule in RULES_BY_SYMBOL.get(symbol, ())
        if rule["review_time"] == canonical_clock
    ]
    if symbol not in RULES_BY_SYMBOL:
        return {
            "active": False,
            "symbol": symbol,
            "trade_date": str(selected_date),
            "review_time_et": review_label,
            "signal_status": "NOT_CONFIGURED_FOR_SYMBOL",
            "reason": f"Market Movement Strategy is currently configured only for XSP, SPY, QQQ, and XND; {symbol} is unchanged.",
            "gates": [],
            "features": {},
            "primary_results": {},
            "research_results": [],
            "candidate_evaluations": [],
        }

    history = prepare_movement_history(history)
    required_features = {feature for rule in rules for feature, _ in rule["conditions"]}
    if review_clock >= time(11, 0):
        required_features.add("A15")
    features, day, day15, data_errors = _session_features(
        history,
        bars15,
        selected_date,
        review_clock,
        required_features,
    )
    gates = [
        {
            "name": "Data readiness",
            "status": "PASS" if not data_errors else "BLOCKED",
            "passed": not data_errors,
            "reason": "All required completed bars and features are available." if not data_errors else " ".join(data_errors),
            "reason_code": None if not data_errors else "NO_SIGNAL_INCOMPLETE_DATA",
        }
    ]
    if data_errors:
        return {
            "active": True,
            "symbol": symbol,
            "trade_date": str(selected_date),
            "review_time_et": review_label,
            "pre_headline_risk": review_clock < time(11, 0),
            "signal_status": "NO_SIGNAL_INCOMPLETE_DATA",
            "reason": gates[0]["reason"],
            "gates": gates,
            "features": features,
            "primary_results": {},
            "research_results": [],
            "candidate_evaluations": [],
        }

    fomc = bool(fomc_day)
    gates.append(
        {
            "name": "FOMC exclusion",
            "status": "BLOCKED" if fomc else "PASS",
            "passed": not fomc,
            "reason": "Scheduled FOMC decision day." if fomc else "Not a scheduled FOMC decision day.",
            "reason_code": "NO_SIGNAL_FOMC" if fomc else None,
        }
    )
    automatic_block = bool(automatic_event and automatic_event.get("automatic_skip"))
    gates.append(
        {
            "name": "Automatic event exclusion",
            "status": "BLOCKED" if automatic_block else "PASS",
            "passed": not automatic_block,
            "reason": str(automatic_event.get("description")) if automatic_block else "No automatic full-day exclusion is recorded.",
            "reason_code": "NO_SIGNAL_HEADLINE" if automatic_block else None,
        }
    )
    gates.append(_headline_gate(headline_status, review_clock))

    foundation = _foundation_result(
        symbol,
        day,
        day15,
        selected_date,
        review_clock,
    )
    if not foundation["required"]:
        gates.append(
            {
                "name": "Foundation checkpoint",
                "status": "NOT REQUIRED — PRE-11:00",
                "passed": True,
                "reason": "The signal remains pre-headline risk and does not inherit a post-11:00 Foundation clearance.",
            }
        )
    elif not foundation["ready"]:
        gates.append(
            {
                "name": "Foundation checkpoint",
                "status": "BLOCKED — DATA UNAVAILABLE",
                "passed": False,
                "reason": foundation.get("reason", "Foundation inputs are unavailable."),
                "reason_code": "NO_SIGNAL_INCOMPLETE_DATA",
            }
        )
    elif not foundation["clear"]:
        gates.append(
            {
                "name": "Foundation checkpoint",
                "status": f"BLOCKED — {foundation['checkpoint']} FLAGGED",
                "passed": False,
                "reason": " ".join(foundation["triggers"]),
                "reason_code": "NO_SIGNAL_FOUNDATION",
            }
        )
    else:
        gates.append(
            {
                "name": "Foundation checkpoint",
                "status": f"PASS — {foundation['checkpoint']} CLEAR",
                "passed": True,
                "reason": "No applicable Foundation trigger fired.",
            }
        )

    blocker = next((gate for gate in gates if not gate["passed"]), None)
    evaluated = []
    for rule in rules:
        item = evaluate_rule(rule, features)
        item["evidence_class"] = (
            "SECONDARY_PRE_HEADLINE"
            if review_clock < time(11, 0)
            else rule["rule_class"]
        )
        evaluated.append(item)

    selected = {}
    if blocker is None:
        for target_kind in (TARGET_OPEN, TARGET_FRESH):
            passing = sorted(
                (
                    item
                    for item in evaluated
                    if item["target_kind"] == target_kind
                    and item["operating"]
                    and item["technical_pass"]
                ),
                key=lambda item: (item["ceiling"], item["rule_id"]),
            )
            if passing:
                passing[0]["selected"] = True
                selected[target_kind] = passing[0]

    cutoff = pd.Timestamp(datetime.combine(selected_date, review_clock), tz=EASTERN)
    primary_results = {
        target: _signal(item, features, day, cutoff)
        for target, item in selected.items()
    }
    if not include_historical_outcome:
        for signal in primary_results.values():
            signal["historical_outcome"] = {"available": False}
    research_results = (
        [
            _signal(item, features, day, cutoff)
            for item in evaluated
            if item["technical_pass"]
            and not item["operating"]
            and item["target_kind"] in {TARGET_OPEN, TARGET_FRESH}
        ]
        if blocker is None
        else []
    )
    if not include_historical_outcome:
        for signal in research_results:
            signal["historical_outcome"] = {"available": False}

    for item in evaluated:
        if blocker is not None:
            item["decision"] = f"BLOCKED BY {blocker['name'].upper()}"
        elif item["selected"]:
            item["decision"] = "PASS — SELECTED"
        elif item["technical_pass"] and item["operating"]:
            item["decision"] = "PASS — LARGER TIER NOT SELECTED"
        elif item["technical_pass"]:
            item["decision"] = "PASS — RESEARCH ONLY"
        else:
            item["decision"] = "FAIL — ONE OR MORE CONDITIONS"

    if blocker is not None:
        status = blocker.get("reason_code") or "NO_SIGNAL_HEADLINE"
        reason = blocker["reason"]
    elif primary_results:
        status = "SECONDARY_PRE_HEADLINE" if review_clock < time(11, 0) else "ACTIVE_CURRENT_CONFIRMED"
        reason = "The smallest passing exact rule was selected independently for each available anchor family."
    elif research_results:
        status = "SECONDARY_PRE_HEADLINE" if review_clock < time(11, 0) else "RESEARCH_ONLY"
        reason = "No operating rule passed, but one or more separately labeled research-only rules met all exact conditions."
    elif not rules:
        status = "NO_SIGNAL_CONDITIONS"
        reason = "No approved rule exists for this symbol at this exact checkpoint. Rules from another time are not carried forward or interpolated."
    else:
        status = "NO_SIGNAL_CONDITIONS"
        reason = "Every available exact-time rule failed at least one required AND condition."

    combined_boundary = None
    if TARGET_OPEN in primary_results and TARGET_FRESH in primary_results:
        combined_boundary = {
            "lower_boundary": min(
                primary_results[TARGET_OPEN]["lower_boundary"],
                primary_results[TARGET_FRESH]["lower_boundary"],
            ),
            "upper_boundary": max(
                primary_results[TARGET_OPEN]["upper_boundary"],
                primary_results[TARGET_FRESH]["upper_boundary"],
            ),
            "meaning": "Farther boundary from the two independently validated anchor families; the formulas were not blended.",
        }

    return {
        "active": True,
        "symbol": symbol,
        "trade_date": str(selected_date),
        "review_time_et": review_label,
        "pre_headline_risk": review_clock < time(11, 0),
        "signal_status": status,
        "reason": reason,
        "gates": gates,
        "foundation": foundation,
        "features": features,
        "primary_results": primary_results,
        "research_results": research_results,
        "candidate_evaluations": evaluated,
        "combined_boundary": combined_boundary,
        "calculation_standard": "Completed bars only; full-precision inclusive <= comparisons; all conditions joined by AND.",
    }


