"""Shared analyze/backtest/live flow for XAUUSD."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .backtest import run_backtest
from .broker import MT5Broker, volume_for_risk
from .mt5_data import MT5Connection, MT5DataFeed, SymbolSpec, TIMEFRAME_SECONDS
from .smc import SmartMoneyConcepts
from .strategy import GoldSMCParams, GoldSMCStrategy, Signal


def analyze_frame(frame: pd.DataFrame, symbol: str, timeframe: str, swing_length: int = 50, internal_length: int = 5):
    engine = SmartMoneyConcepts(symbol=symbol, timeframe=timeframe, df=frame)
    engine.swings_length_input = swing_length
    engine.internal_length_input = internal_length
    engine.prepare_data()
    engine.run_smc_analysis()
    return engine


def htf_count_for(ltf: pd.DataFrame, ltf_timeframe: str, htf_timeframe: str, padding: int = 160) -> int:
    if ltf.empty:
        return padding
    seconds = max((ltf.index[-1] - ltf.index[0]).total_seconds(), 0)
    return int(seconds / TIMEFRAME_SECONDS[htf_timeframe.upper()]) + padding


def build_signals(ltf, htf, params: GoldSMCParams, spec: SymbolSpec):
    ltf_engine = analyze_frame(ltf, params.symbol, params.execution_timeframe)
    htf_engine = analyze_frame(htf, params.symbol, params.bias_timeframe)
    strategy = GoldSMCStrategy(params)
    signals = strategy.generate(ltf_engine.snapshots, htf_engine.snapshots, point=spec.point)
    return signals, strategy, ltf_engine, htf_engine


def load_market(symbol: str, ltf_timeframe: str, htf_timeframe: str, bars: int, terminal_path: str | None):
    feed = MT5DataFeed(terminal_path)
    spec = feed.symbol_spec(symbol)
    ltf = feed.copy_rates(symbol, ltf_timeframe, bars, closed_only=True)
    htf_bars = htf_count_for(ltf, ltf_timeframe, htf_timeframe)
    htf = feed.copy_rates(symbol, htf_timeframe, htf_bars, closed_only=True)
    return spec, ltf, htf


def format_summary(result) -> str:
    stats = result.summary()
    lines = [
        f"trades: {stats['trades']}  longs: {stats['longs']}  shorts: {stats['shorts']}",
        f"win rate: {stats['win_rate']:.1f}%  average R: {stats['average_r']:.2f}",
        f"net pnl: {stats['net_pnl']:.2f}  return: {stats['return_pct']:.2f}%",
        f"profit factor: {stats['profit_factor']:.2f}  max drawdown: {stats['max_drawdown']:.2f} ({stats['max_drawdown_pct']:.2f}%)",
        f"final balance: {stats['final_balance']:.2f}",
    ]
    return "\n".join(lines)


def save_report(result, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": result.summary(),
        "trades": [trade.to_dict() for trade in result.trades],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def plan_from_signal(signal: Signal, tick, spec: SymbolSpec, params: GoldSMCParams, equity: float):
    spread_points = (float(tick.ask) - float(tick.bid)) / spec.point
    if spread_points > params.max_spread_points:
        return None, f"spread {spread_points:.0f} points is above {params.max_spread_points}"
    if signal.side == "buy":
        entry = float(tick.ask)
        if signal.stop >= entry:
            return None, "stop is not below the ask"
        take_profit = entry + params.reward_multiple * (entry - signal.stop)
    else:
        entry = float(tick.bid)
        if signal.stop <= entry:
            return None, "stop is not above the bid"
        take_profit = entry - params.reward_multiple * (signal.stop - entry)
    stop = spec.round_price(signal.stop)
    take_profit = spec.round_price(take_profit)
    min_stop = spec.stops_level * spec.point
    if abs(entry - stop) < max(min_stop, params.min_sl_points * spec.point):
        return None, "stop is closer than the minimum distance"
    volume = volume_for_risk(equity, params.risk_percent, entry, stop, spec)
    if volume is None:
        return None, (
            f"risk {params.risk_percent:.2f}% of equity {equity:.2f} is below the minimum lot {spec.volume_min}"
        )
    from .broker import OrderPlan

    plan = OrderPlan(
        symbol=params.symbol,
        side=signal.side,
        volume=volume,
        price=spec.round_price(entry),
        stop=stop,
        take_profit=take_profit,
        comment=params.comment,
    )
    return plan, "ok"


def latest_signal(signals: list[Signal], last_index: int) -> Signal | None:
    fresh = [item for item in signals if item.bar_index == last_index]
    return fresh[-1] if fresh else None


def run_live_once(params: GoldSMCParams, bars: int, terminal_path: str | None, send: bool, connection: MT5Connection):
    feed = MT5DataFeed(terminal_path, connection)
    spec = feed.symbol_spec(params.symbol)
    ltf = feed.copy_rates(params.symbol, params.execution_timeframe, bars, closed_only=True)
    htf = feed.copy_rates(
        params.symbol,
        params.bias_timeframe,
        htf_count_for(ltf, params.execution_timeframe, params.bias_timeframe),
        closed_only=True,
    )
    signals, strategy, ltf_engine, _htf_engine = build_signals(ltf, htf, params, spec)
    signal = latest_signal(signals, len(ltf_engine.snapshots) - 1)
    broker = MT5Broker(connection, magic=params.magic, deviation_points=params.deviation_points)
    account = connection.mt5.account_info()
    print(
        f"account {account.login} {account.server} equity={account.equity:.2f} {account.currency} "
        f"trade_mode={account.trade_mode}"
    )
    print(
        f"{params.symbol} swing={ltf_engine.swing_trend.bias} internal={ltf_engine.internal_trend.bias} "
        f"close={ltf.iloc[-1]['close']:.2f} bar={ltf.index[-1]}"
    )
    if params.flat_friday:
        now = pd.Timestamp(ltf.index[-1])
        hour = now.hour + now.minute / 60.0
        if now.weekday() == 4 and hour >= params.friday_cutoff_hour and broker.positions(params.symbol):
            print("Friday cutoff reached; existing strategy positions should be closed.")
            if send:
                broker.close_all(params.symbol, spec)
            return None
    if signal is None:
        print("No new gold SMC signal on the latest closed bar.")
        if strategy.rejections:
            print("recent filter counts:", dict(strategy.rejections))
        return None
    print(f"signal: {signal.side} stop={signal.stop:.2f} reason={signal.reason}")
    tick = feed.tick(params.symbol)
    plan, status = plan_from_signal(signal, tick, spec, params, float(account.equity))
    if plan is None:
        print(f"signal not tradable: {status}")
        return None
    print(
        f"plan: {plan.side} {plan.volume:.2f} {plan.symbol} @ {plan.price:.2f} "
        f"sl={plan.stop:.2f} tp={plan.take_profit:.2f}"
    )
    if broker.positions(params.symbol):
        print("strategy position already open; not adding a second one.")
        return plan
    if not send:
        print("dry-run only. Re-run with --send --confirm-live to submit this order.")
        return plan
    result = broker.send(plan, spec)
    print(f"order sent: retcode={result.retcode} order={result.order} deal={result.deal}")
    return plan