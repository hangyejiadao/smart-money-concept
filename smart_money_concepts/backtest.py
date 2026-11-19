"""Bar backtest for the gold SMC strategy.

Signals are created on a closed bar and filled at the next bar open. MetaTrader
OHLC is bid, so buys pay the bar spread and shorts pay the spread on exit.
If stop and target are both touched in one bar, the stop is assumed to fill first.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import pandas as pd

from .broker import volume_for_risk
from .mt5_data import SymbolSpec
from .strategy import GoldSMCParams, Signal


@dataclass
class Trade:
    side: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry: float
    exit: float
    stop: float
    take_profit: float
    volume: float
    pnl: float
    r_multiple: float
    reason: str
    exit_reason: str

    def to_dict(self) -> dict:
        item = asdict(self)
        item["entry_time"] = str(self.entry_time)
        item["exit_time"] = str(self.exit_time)
        return item


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: pd.Series
    initial_balance: float
    final_balance: float

    def summary(self) -> dict:
        trades = self.trades
        pnl = [trade.pnl for trade in trades]
        wins = [value for value in pnl if value > 0]
        losses = [value for value in pnl if value <= 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        equity = self.equity_curve
        peak = equity.cummax()
        drawdown = equity - peak
        max_dd = float(drawdown.min()) if len(drawdown) else 0.0
        max_dd_pct = float((drawdown / peak.replace(0, pd.NA)).min() * 100) if len(equity) else 0.0
        net = self.final_balance - self.initial_balance
        return {
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(trades) * 100) if trades else 0.0,
            "net_pnl": net,
            "return_pct": net / self.initial_balance * 100 if self.initial_balance else 0.0,
            "profit_factor": (gross_profit / gross_loss) if gross_loss else float("inf") if gross_profit else 0.0,
            "max_drawdown": max_dd,
            "max_drawdown_pct": max_dd_pct if pd.notna(max_dd_pct) else 0.0,
            "average_r": (sum(trade.r_multiple for trade in trades) / len(trades)) if trades else 0.0,
            "longs": sum(1 for trade in trades if trade.side == "buy"),
            "shorts": sum(1 for trade in trades if trade.side == "sell"),
            "final_balance": self.final_balance,
        }


def run_backtest(
    frame: pd.DataFrame,
    signals: list[Signal],
    spec: SymbolSpec,
    params: GoldSMCParams,
    initial_balance: float = 10000.0,
) -> BacktestResult:
    pending: dict[int, Signal] = {}
    for signal in signals:
        fill_index = signal.bar_index + 1
        if fill_index < len(frame):
            pending.setdefault(fill_index, signal)

    equity = float(initial_balance)
    curve = []
    trades: list[Trade] = []
    position = None

    for index in range(len(frame)):
        row = frame.iloc[index]
        bar_time = frame.index[index]
        spread = _spread_price(row, spec)
        slip = params.slippage_points * spec.point

        if position is None and index in pending:
            position = _open_position(pending[index], row, bar_time, equity, spread, slip, spec, params)
        if position is not None and _friday_flat(bar_time, params):
            exit_price = _market_exit(position["side"], float(row["open"]), spread, slip)
            closed = _close_trade(position, exit_price, bar_time, "friday_flat", spec)
            equity += closed.pnl
            trades.append(closed)
            position = None
        if position is not None:
            exit_fill = _exit_on_bar(position, row, bar_time, spread, slip, spec, params)
            if exit_fill is not None:
                equity += exit_fill.pnl
                trades.append(exit_fill)
                position = None
            else:
                position["bars_held"] += 1
        curve.append(equity)

    if position is not None:
        last = frame.iloc[-1]
        last_time = frame.index[-1]
        spread = _spread_price(last, spec)
        exit_price = _market_exit(position["side"], float(last["close"]), spread, params.slippage_points * spec.point)
        closed = _close_trade(position, exit_price, last_time, "end", spec)
        equity += closed.pnl
        trades.append(closed)
        curve[-1] = equity

    equity_curve = pd.Series(curve, index=frame.index[: len(curve)], name="equity")
    return BacktestResult(trades, equity_curve, initial_balance, equity)



def _friday_flat(bar_time, params: GoldSMCParams) -> bool:
    if not params.flat_friday:
        return False
    ts = pd.Timestamp(bar_time)
    hour = ts.hour + ts.minute / 60.0
    return ts.weekday() == 4 and hour >= params.friday_cutoff_hour

def _spread_price(row, spec: SymbolSpec) -> float:
    raw = float(row["spread"]) if "spread" in row and pd.notna(row["spread"]) else float(spec.spread)
    return raw * spec.point


def _open_position(signal, row, bar_time, equity, spread, slip, spec, params):
    open_price = float(row["open"])
    if signal.side == "buy":
        entry = open_price + spread + slip
        if signal.stop >= entry:
            return None
    else:
        entry = open_price - slip
        if signal.stop <= entry:
            return None
    stop = spec.round_price(signal.stop)
    risk = abs(entry - stop)
    points = risk / spec.point
    if points < params.min_sl_points or points > params.max_sl_points:
        return None
    if signal.side == "buy":
        take_profit = spec.round_price(entry + params.reward_multiple * risk)
    else:
        take_profit = spec.round_price(entry - params.reward_multiple * risk)
    volume = volume_for_risk(equity, params.risk_percent, entry, stop, spec)
    if volume is None:
        return None
    return {
        "side": signal.side,
        "entry_time": bar_time,
        "entry": entry,
        "stop": stop,
        "take_profit": take_profit,
        "volume": volume,
        "reason": signal.reason,
        "risk_money": spec.price_to_money(risk, volume),
        "bars_held": 0,
    }


def _exit_on_bar(position, row, bar_time, spread, slip, spec, params):
    high = float(row["high"])
    low = float(row["low"])
    open_price = float(row["open"])
    side = position["side"]
    if position["bars_held"] >= params.max_hold_bars:
        return _close_trade(position, _market_exit(side, open_price, spread, slip), bar_time, "max_hold", spec)

    if side == "buy":
        gap_stop = open_price <= position["stop"]
        gap_tp = open_price >= position["take_profit"]
        hit_stop = low <= position["stop"]
        hit_tp = high >= position["take_profit"]
        if gap_stop:
            return _close_trade(position, open_price, bar_time, "gap_stop", spec)
        if gap_tp and not hit_stop:
            return _close_trade(position, open_price, bar_time, "gap_tp", spec)
        if hit_stop:
            return _close_trade(position, position["stop"], bar_time, "stop", spec)
        if hit_tp:
            return _close_trade(position, position["take_profit"], bar_time, "target", spec)
        return None

    ask_open = open_price + spread
    ask_high = high + spread
    ask_low = low + spread
    if ask_open >= position["stop"]:
        return _close_trade(position, ask_open + slip, bar_time, "gap_stop", spec)
    if ask_open <= position["take_profit"] and ask_high < position["stop"]:
        return _close_trade(position, ask_open + slip, bar_time, "gap_tp", spec)
    if ask_high >= position["stop"]:
        return _close_trade(position, position["stop"], bar_time, "stop", spec)
    if ask_low <= position["take_profit"]:
        return _close_trade(position, position["take_profit"], bar_time, "target", spec)
    return None


def _market_exit(side: str, bid: float, spread: float, slip: float) -> float:
    if side == "buy":
        return bid - slip
    return bid + spread + slip


def _close_trade(position, exit_price: float, exit_time, exit_reason: str, spec: SymbolSpec) -> Trade:
    if position["side"] == "buy":
        pnl = spec.price_to_money(exit_price - position["entry"], position["volume"])
        if exit_price < position["entry"]:
            pnl = -pnl
    else:
        pnl = spec.price_to_money(position["entry"] - exit_price, position["volume"])
        if exit_price > position["entry"]:
            pnl = -pnl
    risk = position["risk_money"] or 1.0
    return Trade(
        side=position["side"],
        entry_time=pd.Timestamp(position["entry_time"]),
        exit_time=pd.Timestamp(exit_time),
        entry=float(position["entry"]),
        exit=float(exit_price),
        stop=float(position["stop"]),
        take_profit=float(position["take_profit"]),
        volume=float(position["volume"]),
        pnl=float(pnl),
        r_multiple=float(pnl / risk),
        reason=position["reason"],
        exit_reason=exit_reason,
    )