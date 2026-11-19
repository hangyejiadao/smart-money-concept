"""MetaTrader 5 data access for the gold SMC fork."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator, Optional

import pandas as pd

TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
    "W1": 604800,
}


@dataclass(frozen=True)
class SymbolSpec:
    name: str
    point: float
    digits: int
    tick_size: float
    tick_value: float
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    filling_mode: int
    stops_level: int
    spread: int

    @classmethod
    def gold_default(cls, name: str = "XAUUSD") -> "SymbolSpec":
        # XAUUSD on the connected DecodeGlobal terminal: 100 oz, $1 per 0.01 per lot.
        return cls(
            name=name,
            point=0.01,
            digits=2,
            tick_size=0.01,
            tick_value=1.0,
            contract_size=100.0,
            volume_min=0.01,
            volume_max=50.0,
            volume_step=0.01,
            filling_mode=2,
            stops_level=0,
            spread=20,
        )

    def round_price(self, price: float) -> float:
        return round(float(price), self.digits)

    def price_to_money(self, price_distance: float, volume: float) -> float:
        if self.tick_size <= 0:
            raise ValueError("tick_size must be positive")
        return abs(float(price_distance)) / self.tick_size * self.tick_value * float(volume)


def import_mt5():
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise RuntimeError(
            "The MetaTrader5 package is not installed in this interpreter. "
            "Use a Windows CPython install, for example D:\\Python312\\python.exe."
        ) from exc
    return mt5


class MT5Connection:
    """Owns one initialize/shutdown cycle so live polling does not reconnect every tick."""

    def __init__(self, terminal_path: Optional[str] = None):
        self.terminal_path = terminal_path
        self.mt5 = None

    def __enter__(self) -> "MT5Connection":
        mt5 = import_mt5()
        kwargs = {"path": self.terminal_path} if self.terminal_path else {}
        if not mt5.initialize(**kwargs):
            raise RuntimeError(f"mt5.initialize failed: {mt5.last_error()}")
        self.mt5 = mt5
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.mt5 is not None:
            self.mt5.shutdown()
            self.mt5 = None


@contextmanager
def mt5_session(terminal_path: Optional[str] = None) -> Iterator[object]:
    with MT5Connection(terminal_path) as connection:
        yield connection.mt5


class MT5DataFeed:
    def __init__(self, terminal_path: Optional[str] = None, connection: Optional[MT5Connection] = None):
        self.terminal_path = terminal_path
        self.connection = connection

    def _using(self, fn: Callable):
        if self.connection is not None and self.connection.mt5 is not None:
            return fn(self.connection.mt5)
        with mt5_session(self.terminal_path) as mt5:
            return fn(mt5)

    def ensure_symbol(self, mt5, symbol: str) -> None:
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"Unable to select {symbol}: {mt5.last_error()}")

    def copy_rates(self, symbol: str, timeframe: str, count: int, closed_only: bool = True) -> pd.DataFrame:
        timeframe = timeframe.upper()
        if timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(f"Unsupported timeframe {timeframe}. Choose from {', '.join(TIMEFRAME_SECONDS)}")

        def _read(mt5):
            self.ensure_symbol(mt5, symbol)
            tf = getattr(mt5, f"TIMEFRAME_{timeframe}")
            start = 1 if closed_only else 0
            rates = mt5.copy_rates_from_pos(symbol, tf, start, int(count))
            if rates is None or len(rates) == 0:
                raise RuntimeError(
                    f"copy_rates_from_pos returned no bars for {symbol} {timeframe}: {mt5.last_error()}"
                )
            frame = pd.DataFrame(rates)
            frame["time"] = pd.to_datetime(frame["time"], unit="s")
            return frame.set_index("time").sort_index().rename(columns={"tick_volume": "volume"})

        return self._using(_read)

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        def _read(mt5):
            self.ensure_symbol(mt5, symbol)
            info = mt5.symbol_info(symbol)
            if info is None:
                raise RuntimeError(f"symbol_info failed for {symbol}: {mt5.last_error()}")
            return SymbolSpec(
                name=info.name,
                point=float(info.point),
                digits=int(info.digits),
                tick_size=float(info.trade_tick_size),
                tick_value=float(info.trade_tick_value),
                contract_size=float(info.trade_contract_size),
                volume_min=float(info.volume_min),
                volume_max=float(info.volume_max),
                volume_step=float(info.volume_step),
                filling_mode=int(info.filling_mode),
                stops_level=int(info.trade_stops_level),
                spread=int(info.spread),
            )

        return self._using(_read)

    def tick(self, symbol: str):
        def _read(mt5):
            self.ensure_symbol(mt5, symbol)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                raise RuntimeError(f"symbol_info_tick failed for {symbol}: {mt5.last_error()}")
            return tick

        return self._using(_read)

    def account(self):
        def _read(mt5):
            info = mt5.account_info()
            if info is None:
                raise RuntimeError(f"account_info failed: {mt5.last_error()}")
            return info

        return self._using(_read)