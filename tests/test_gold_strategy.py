import unittest
from datetime import datetime, timedelta

import pandas as pd

from smart_money_concepts.backtest import run_backtest
from smart_money_concepts.broker import normalize_volume, volume_for_risk
from smart_money_concepts.mt5_data import SymbolSpec
from smart_money_concepts.smc import SmartMoneyConcepts
from smart_money_concepts.strategy import GoldSMCParams, GoldSMCStrategy, Signal


def spec():
    return SymbolSpec.gold_default()


def snap(**overrides):
    base = {
        "index": 0,
        "time": pd.Timestamp("2026-11-18 12:00:00"),
        "open": 2300.0,
        "high": 2304.0,
        "low": 2296.0,
        "close": 2302.0,
        "atr": 4.0,
        "spread": 18,
        "swing_bias": 1,
        "internal_bias": 1,
        "breaks": [{"internal": True, "direction": "bullish", "type": "CHOCH", "break_bar_index": 0}],
        "swing_order_blocks": [{"high": 2300.0, "low": 2294.0, "bias": 1}],
        "internal_order_blocks": [],
        "fair_value_gaps": [],
        "trailing_top": 2360.0,
        "trailing_bottom": 2260.0,
        "premium_bottom": 2355.0,
        "discount_top": 2265.0,
    }
    base.update(overrides)
    return base


class VolumeTests(unittest.TestCase):
    def test_volume_floors_and_rejects_dust(self):
        self.assertEqual(normalize_volume(0.037, spec()), 0.03)
        self.assertIsNone(normalize_volume(0.009, spec()))

    def test_risk_uses_gold_tick_value(self):
        # $50 risk, $5 stop, $1 per 0.01 per lot => 0.10 lot.
        volume = volume_for_risk(10000, 0.5, 2300, 2295, spec())
        self.assertEqual(volume, 0.10)


class StrategyTests(unittest.TestCase):
    def test_long_signal_in_discount_after_internal_choch(self):
        params = GoldSMCParams(session_filter=False)
        signals = GoldSMCStrategy(params).generate([snap()], point=0.01)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].side, "buy")
        self.assertLess(signals[0].stop, 2296.0)

    def test_rejects_long_in_premium_and_against_bias(self):
        params = GoldSMCParams(session_filter=False)
        premium = snap(close=2358.0, low=2354.0, high=2360.0, open=2355.0)
        against = snap(swing_bias=-1)
        strategy = GoldSMCStrategy(params)
        self.assertEqual(strategy.generate([premium], point=0.01), [])
        self.assertEqual(strategy.generate([against], point=0.01), [])
        self.assertGreater(strategy.rejections["bias"] + strategy.rejections["premium_discount"], 0)

    def test_missing_zone_is_rejected_without_crashing(self):
        params = GoldSMCParams(session_filter=False)
        bare = snap(swing_order_blocks=[], fair_value_gaps=[], low=2290.0, high=2292.0, close=2291.0, open=2290.5)
        signals = GoldSMCStrategy(params).generate([bare], point=0.01)
        self.assertEqual(signals, [])
    def test_htf_bias_does_not_use_an_unclosed_bar(self):
        params = GoldSMCParams(session_filter=False, execution_timeframe="M15", bias_timeframe="H1")
        ltf = snap(time=pd.Timestamp("2026-11-18 12:15:00"))
        htf = [snap(time=pd.Timestamp("2026-11-18 12:00:00"), swing_bias=-1)]
        signals = GoldSMCStrategy(params).generate([ltf], htf, point=0.01)
        self.assertEqual(signals, [])


class BacktestTests(unittest.TestCase):
    def test_next_bar_fill_and_stop_priority(self):
        index = pd.date_range("2026-11-18 12:00", periods=3, freq="15min")
        frame = pd.DataFrame(
            {
                "open": [2300.0, 2302.0, 2302.0],
                "high": [2304.0, 2320.0, 2308.0],
                "low": [2298.0, 2294.0, 2288.0],
                "close": [2302.0, 2310.0, 2291.0],
                "spread": [20, 20, 20],
            },
            index=index,
        )
        signal = Signal("XAUUSD", "buy", 0, index[0], 2295.0, 2.0, "test", 4.0)
        params = GoldSMCParams(risk_percent=0.5, reward_multiple=2.0, slippage_points=0, min_sl_points=10)
        result = run_backtest(frame, [signal], spec(), params, initial_balance=10000)
        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade.exit_reason, "stop")
        self.assertLess(trade.pnl, 0)
        self.assertAlmostEqual(trade.entry, 2302.20, places=2)

    def test_target_pnl_is_positive_for_long(self):
        index = pd.date_range("2026-11-18 12:00", periods=3, freq="15min")
        frame = pd.DataFrame(
            {
                "open": [2300.0, 2301.0, 2301.0],
                "high": [2302.0, 2320.0, 2320.0],
                "low": [2299.0, 2300.5, 2300.5],
                "close": [2301.0, 2318.0, 2318.0],
                "spread": [10, 10, 10],
            },
            index=index,
        )
        signal = Signal("XAUUSD", "buy", 0, index[0], 2296.0, 2.0, "test", 4.0)
        params = GoldSMCParams(risk_percent=0.5, slippage_points=0, min_sl_points=10, max_sl_points=5000)
        result = run_backtest(frame, [signal], spec(), params, 10000)
        self.assertEqual(result.trades[0].exit_reason, "target")
        self.assertGreater(result.trades[0].pnl, 0)
        self.assertAlmostEqual(result.final_balance, 10000 + result.trades[0].pnl, places=6)


class AnalysisTests(unittest.TestCase):
    def test_detector_runs_on_a_rising_gold_path(self):
        start = datetime(2026, 10, 1, 8, 0)
        rows = []
        price = 2200.0
        for i in range(180):
            price += 1.5 if i % 18 < 13 else -0.8
            rows.append((start + timedelta(minutes=15 * i), price - 1, price + 1.2, price - 1.4, price, 15))
        frame = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "spread"]).set_index("time")
        engine = SmartMoneyConcepts(symbol="XAUUSD", timeframe="M15", df=frame)
        engine.swings_length_input = 5
        engine.internal_length_input = 3
        engine.prepare_data()
        engine.run_smc_analysis()
        self.assertEqual(len(engine.snapshots), len(frame))
        self.assertGreater(len(engine.structure_breaks), 0)
        self.assertEqual(engine.swing_trend.bias, 1)


if __name__ == "__main__":
    unittest.main()