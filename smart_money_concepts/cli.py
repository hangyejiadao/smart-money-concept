"""Command line for the XAUUSD MetaTrader 5 SMC strategy."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

if "--show" not in sys.argv:
    os.environ.setdefault("MPLBACKEND", "Agg")

from .mt5_data import MT5Connection
from .runner import build_signals, format_summary, load_market, run_live_once, save_report
from .strategy import GoldSMCParams


def default_terminal() -> str | None:
    candidate = Path(r"D:\mt5\terminal64.exe")
    return str(candidate) if candidate.exists() else None


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="M15", help="Execution timeframe")
    parser.add_argument("--htf", default="H1", help="Bias timeframe")
    parser.add_argument("--bars", type=int, default=4000)
    parser.add_argument("--terminal", default=default_terminal())
    parser.add_argument("--risk", type=float, default=0.5, help="Percent of equity risked per trade")
    parser.add_argument("--rr", type=float, default=2.0, help="Reward multiple")
    parser.add_argument("--no-session-filter", action="store_true")


def params_from(args) -> GoldSMCParams:
    return GoldSMCParams(
        symbol=args.symbol,
        execution_timeframe=args.timeframe.upper(),
        bias_timeframe=args.htf.upper(),
        risk_percent=args.risk,
        reward_multiple=args.rr,
        session_filter=not args.no_session_filter,
    )


def command_analyze(args) -> int:
    spec, ltf, htf = load_market(args.symbol, args.timeframe, args.htf, args.bars, args.terminal)
    _signals, _strategy, ltf_engine, htf_engine = build_signals(ltf, htf, params_from(args), spec)
    print(f"HTF {args.htf} swing bias: {htf_engine.swing_trend.bias}")
    chart = args.chart or str(Path("reports") / f"{args.symbol}_{args.timeframe}_smc.png")
    Path(chart).parent.mkdir(parents=True, exist_ok=True)
    ltf_engine.visualize_smc(bars_to_show=min(args.bars, 300), show=args.show, save_path=chart)
    return 0


def command_backtest(args) -> int:
    spec, ltf, htf = load_market(args.symbol, args.timeframe, args.htf, args.bars, args.terminal)
    params = params_from(args)
    signals, strategy, _ltf_engine, _htf_engine = build_signals(ltf, htf, params, spec)
    from .backtest import run_backtest

    result = run_backtest(ltf, signals, spec, params, initial_balance=args.balance)
    print(f"{args.symbol} {args.timeframe} bars={len(ltf)} signals={len(signals)} range={ltf.index[0]} -> {ltf.index[-1]}")
    print(format_summary(result))
    if strategy.rejections:
        print("filters:", dict(strategy.rejections))
    report = Path(args.report)
    save_report(result, report)
    print(f"report: {report.resolve()}")
    if result.trades:
        last = result.trades[-5:]
        print("last trades:")
        for trade in last:
            print(
                f"  {trade.entry_time} {trade.side} {trade.volume:.2f} "
                f"{trade.entry:.2f}->{trade.exit:.2f} pnl={trade.pnl:.2f} {trade.exit_reason}"
            )
    return 0


def command_live(args) -> int:
    if args.send and not args.confirm_live:
        print("Refusing to send orders. Pass both --send and --confirm-live.")
        return 2
    params = params_from(args)
    with MT5Connection(args.terminal) as connection:
        info = connection.mt5.account_info()
        if info is not None and int(info.trade_mode) == int(connection.mt5.ACCOUNT_TRADE_MODE_REAL) and args.send:
            print("This MetaTrader account is a real-money account.")
        while True:
            run_live_once(params, args.bars, args.terminal, args.send, connection)
            if not args.watch:
                return 0
            time.sleep(args.poll)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="XAUUSD Smart Money Concepts strategy for MetaTrader 5")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Load gold bars and print the SMC structure")
    add_common(analyze)
    analyze.add_argument("--chart", default="")
    analyze.add_argument("--show", action="store_true")
    analyze.set_defaults(func=command_analyze)

    backtest = sub.add_parser("backtest", help="Backtest the gold SMC rules on closed MT5 bars")
    add_common(backtest)
    backtest.add_argument("--balance", type=float, default=10000.0)
    backtest.add_argument("--report", default=str(Path("reports") / "xauusd_backtest.json"))
    backtest.set_defaults(func=command_backtest)

    live = sub.add_parser("live", help="Evaluate the latest closed bar. Orders are dry-run unless explicitly confirmed.")
    add_common(live)
    live.add_argument("--send", action="store_true")
    live.add_argument("--confirm-live", action="store_true")
    live.add_argument("--watch", action="store_true")
    live.add_argument("--poll", type=float, default=15.0)
    live.set_defaults(func=command_live)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())