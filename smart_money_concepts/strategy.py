"""XAUUSD Smart Money Concepts continuation strategy.

Bias comes from the higher-timeframe swing structure. The execution timeframe
must print an internal BOS/CHoCH in the same direction after price has tapped
a bullish or bearish order block or fair value gap in discount or premium.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional, Sequence

import pandas as pd

from .mt5_data import TIMEFRAME_SECONDS


@dataclass
class GoldSMCParams:
    symbol: str = "XAUUSD"
    execution_timeframe: str = "M15"
    bias_timeframe: str = "H1"
    risk_percent: float = 0.5
    reward_multiple: float = 2.0
    sl_atr_buffer: float = 0.20
    min_sl_points: int = 80
    max_sl_points: int = 2500
    max_spread_points: int = 40
    max_long_location: float = 0.62
    min_short_location: float = 0.38
    zone_lookback: int = 8
    cooldown_bars: int = 4
    max_hold_bars: int = 48
    session_filter: bool = True
    session_start_hour: float = 9.0
    session_end_hour: float = 22.0
    flat_friday: bool = True
    friday_cutoff_hour: float = 21.0
    use_order_block: bool = True
    use_fvg: bool = True
    require_zone: bool = True
    magic: int = 161211
    deviation_points: int = 30
    comment: str = "smc-gold"
    slippage_points: float = 2.0


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: str
    bar_index: int
    time: pd.Timestamp
    stop: float
    reward_multiple: float
    reason: str
    atr: float


@dataclass
class GoldSMCStrategy:
    params: GoldSMCParams = field(default_factory=GoldSMCParams)
    rejections: Counter = field(default_factory=Counter)

    def generate(
        self,
        ltf_snapshots: Sequence[dict],
        htf_snapshots: Optional[Sequence[dict]] = None,
        point: float = 0.01,
    ) -> list[Signal]:
        self.rejections = Counter()
        if not ltf_snapshots:
            return []
        biases = align_bias(
            ltf_snapshots,
            htf_snapshots or [],
            self.params.execution_timeframe,
            self.params.bias_timeframe,
        )
        signals: list[Signal] = []
        recent_long = None
        recent_short = None
        cooldown_until = -1

        for index, snap in enumerate(ltf_snapshots):
            long_zone = tapped_zone(snap, 1, self.params)
            short_zone = tapped_zone(snap, -1, self.params)
            if long_zone is not None:
                recent_long = (index, long_zone)
            if short_zone is not None:
                recent_short = (index, short_zone)
            if recent_long is not None and index - recent_long[0] > self.params.zone_lookback:
                recent_long = None
            if recent_short is not None and index - recent_short[0] > self.params.zone_lookback:
                recent_short = None
            if index < cooldown_until:
                self.rejections["cooldown"] += 1
                continue

            signal = self._signal_at(index, snap, biases[index], recent_long, recent_short, point)
            if signal is None:
                continue
            signals.append(signal)
            cooldown_until = index + self.params.cooldown_bars

        return signals

    def _signal_at(self, index, snap, htf_bias, recent_long, recent_short, point) -> Optional[Signal]:
        params = self.params
        if snap["atr"] <= 0:
            self.rejections["atr"] += 1
            return None
        if not in_session(snap["time"], params):
            self.rejections["session"] += 1
            return None
        if snap["spread"] > params.max_spread_points:
            self.rejections["spread"] += 1
            return None

        bullish_break = latest_internal_break(snap, "bullish")
        bearish_break = latest_internal_break(snap, "bearish")
        if bullish_break and bearish_break:
            self.rejections["both_breaks"] += 1
            return None
        if not bullish_break and not bearish_break:
            self.rejections["no_break"] += 1
            return None

        side = "buy" if bullish_break else "sell"
        if side == "buy" and (snap["swing_bias"] != 1 or htf_bias != 1):
            self.rejections["bias"] += 1
            return None
        if side == "sell" and (snap["swing_bias"] != -1 or htf_bias != -1):
            self.rejections["bias"] += 1
            return None

        location = range_location(snap["close"], snap["trailing_top"], snap["trailing_bottom"])
        if location is None:
            self.rejections["range"] += 1
            return None
        span = float(snap["trailing_top"]) - float(snap["trailing_bottom"])
        if span < max(8.0 * snap["atr"], 50.0 * point):
            self.rejections["range"] += 1
            return None
        if side == "buy" and location > params.max_long_location:
            self.rejections["premium_discount"] += 1
            return None
        if side == "sell" and location < params.min_short_location:
            self.rejections["premium_discount"] += 1
            return None

        recent = recent_long if side == "buy" else recent_short
        zone = None if recent is None else recent[1]
        if zone is None:
            if params.require_zone:
                self.rejections["zone"] += 1
                return None
            zone_low = snap["low"] if side == "buy" else snap["close"]
            zone_high = snap["close"] if side == "buy" else snap["high"]
            zone = ("structure", zone_low, zone_high)

        buffer = max(params.sl_atr_buffer * snap["atr"], 2.0 * point)
        if side == "buy":
            stop = min(zone[1], snap["low"]) - buffer
        else:
            stop = max(zone[2], snap["high"]) + buffer
        distance_points = abs(snap["close"] - stop) / point
        if distance_points < params.min_sl_points or distance_points > params.max_sl_points:
            self.rejections["stop_distance"] += 1
            return None

        kind = bullish_break["type"] if side == "buy" else bearish_break["type"]
        zone_name = "discount" if location <= 0.5 else "equilibrium" if location < params.max_long_location else "premium"
        if side == "sell":
            zone_name = "premium" if location >= 0.5 else "equilibrium"
        reason = f"{params.bias_timeframe} swing + {params.execution_timeframe} {kind} {side} from {zone[0]} in {zone_name}"
        return Signal(
            symbol=params.symbol,
            side=side,
            bar_index=index,
            time=pd.Timestamp(snap["time"]),
            stop=float(stop),
            reward_multiple=params.reward_multiple,
            reason=reason,
            atr=float(snap["atr"]),
        )


def align_bias(ltf_snapshots, htf_snapshots, ltf_timeframe: str, htf_timeframe: str) -> list[int]:
    """Use only higher-timeframe bars that are closed by the execution bar close."""
    if not htf_snapshots:
        return [snap["swing_bias"] for snap in ltf_snapshots]
    ltf_delta = pd.Timedelta(seconds=TIMEFRAME_SECONDS[ltf_timeframe.upper()])
    htf_delta = pd.Timedelta(seconds=TIMEFRAME_SECONDS[htf_timeframe.upper()])
    cursor = -1
    biases = []
    for snap in ltf_snapshots:
        ltf_close = pd.Timestamp(snap["time"]) + ltf_delta
        while cursor + 1 < len(htf_snapshots):
            htf_close = pd.Timestamp(htf_snapshots[cursor + 1]["time"]) + htf_delta
            if htf_close <= ltf_close:
                cursor += 1
            else:
                break
        biases.append(0 if cursor < 0 else int(htf_snapshots[cursor]["swing_bias"]))
    return biases


def in_session(timestamp, params: GoldSMCParams) -> bool:
    if not params.session_filter:
        return True
    ts = pd.Timestamp(timestamp)
    hour = ts.hour + ts.minute / 60.0
    start = params.session_start_hour
    end = params.session_end_hour
    inside = start <= hour < end if start <= end else hour >= start or hour < end
    if not inside:
        return False
    if params.flat_friday and ts.weekday() == 4 and hour >= params.friday_cutoff_hour:
        return False
    return True


def latest_internal_break(snap: dict, direction: str) -> Optional[dict]:
    matches = [
        item for item in snap.get("breaks", [])
        if item.get("internal") and item.get("direction") == direction
    ]
    return matches[-1] if matches else None


def tapped_zone(snap: dict, bias: int, params: GoldSMCParams):
    low = snap["low"]
    high = snap["high"]
    close = snap["close"]
    found = []
    blocks = []
    if params.use_order_block:
        blocks.extend(snap.get("swing_order_blocks", []))
        blocks.extend(snap.get("internal_order_blocks", []))
    for block in blocks:
        if int(block["bias"]) != bias:
            continue
        if bias == 1 and low <= block["high"] and close >= block["low"]:
            found.append(("ob", float(block["low"]), float(block["high"])))
        if bias == -1 and high >= block["low"] and close <= block["high"]:
            found.append(("ob", float(block["low"]), float(block["high"])))
    if params.use_fvg:
        for gap in snap.get("fair_value_gaps", []):
            if int(gap["bias"]) != bias:
                continue
            if bias == 1 and low <= gap["top"] and close >= gap["bottom"]:
                found.append(("fvg", float(gap["bottom"]), float(gap["top"])))
            if bias == -1 and high >= gap["bottom"] and close <= gap["top"]:
                found.append(("fvg", float(gap["bottom"]), float(gap["top"])))
    if not found:
        return None
    kind = "+".join(sorted({item[0] for item in found}))
    return kind, min(item[1] for item in found), max(item[2] for item in found)


def range_location(price, top, bottom) -> Optional[float]:
    if top is None or bottom is None or top <= bottom:
        return None
    return (float(price) - float(bottom)) / (float(top) - float(bottom))