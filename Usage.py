"""Analyze XAUUSD and backtest the gold SMC strategy from a running MT5 terminal."""

from pathlib import Path

from smart_money_concepts.backtest import run_backtest
from smart_money_concepts.runner import build_signals, format_summary, load_market, save_report
from smart_money_concepts.strategy import GoldSMCParams


def main():
    terminal = r"D:\mt5\terminal64.exe"
    params = GoldSMCParams(symbol="XAUUSD", execution_timeframe="M15", bias_timeframe="H1")
    spec, ltf, htf = load_market("XAUUSD", "M15", "H1", 4000, terminal)
    signals, strategy, engine, htf_engine = build_signals(ltf, htf, params, spec)
    print(f"XAUUSD close {ltf.iloc[-1]['close']:.2f}  H1 bias {htf_engine.swing_trend.bias}")
    engine.print_analysis_summary()
    result = run_backtest(ltf, signals, spec, params, initial_balance=10000)
    print(format_summary(result))
    print("filters", dict(strategy.rejections))
    save_report(result, Path("reports") / "xauusd_backtest.json")


if __name__ == "__main__":
    main()