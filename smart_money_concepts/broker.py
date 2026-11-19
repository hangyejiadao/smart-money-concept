"""Order sizing and MetaTrader 5 execution for the gold strategy."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .mt5_data import MT5Connection, SymbolSpec


def pick_filling_mode(filling_mask: int, mt5) -> int:
    """Map symbol_info.filling_mode bits to an order_send filling type.

    Bit 1 is FOK and bit 2 is IOC. Forex and metals on this terminal advertise IOC.
    """
    if filling_mask & 2:
        return mt5.ORDER_FILLING_IOC
    if filling_mask & 1:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def normalize_volume(raw: float, spec: SymbolSpec) -> Optional[float]:
    """Floor volume to the symbol step. Never round up, so risk is not increased."""
    if raw <= 0 or spec.volume_step <= 0:
        return None
    steps = math.floor((float(raw) + 1e-12) / spec.volume_step)
    volume = round(steps * spec.volume_step, 8)
    if volume + 1e-9 < spec.volume_min:
        return None
    return min(volume, spec.volume_max)


def volume_for_risk(
    equity: float,
    risk_percent: float,
    entry: float,
    stop: float,
    spec: SymbolSpec,
) -> Optional[float]:
    risk_money = float(equity) * float(risk_percent) / 100.0
    distance = abs(float(entry) - float(stop))
    if risk_money <= 0 or distance <= 0:
        return None
    loss_per_lot = spec.price_to_money(distance, 1.0)
    if loss_per_lot <= 0:
        return None
    return normalize_volume(risk_money / loss_per_lot, spec)


@dataclass
class OrderPlan:
    symbol: str
    side: str
    volume: float
    price: float
    stop: float
    take_profit: float
    comment: str


class MT5Broker:
    def __init__(self, connection: MT5Connection, magic: int = 161211, deviation_points: int = 30):
        self.connection = connection
        self.magic = int(magic)
        self.deviation_points = int(deviation_points)

    @property
    def mt5(self):
        if self.connection.mt5 is None:
            raise RuntimeError("MetaTrader 5 connection is not open")
        return self.connection.mt5

    def positions(self, symbol: str):
        found = self.mt5.positions_get(symbol=symbol)
        if not found:
            return []
        return [item for item in found if int(item.magic) == self.magic]

    def account_equity(self) -> float:
        info = self.mt5.account_info()
        if info is None:
            raise RuntimeError(f"account_info failed: {self.mt5.last_error()}")
        return float(info.equity)

    def send(self, plan: OrderPlan, spec: SymbolSpec) -> object:
        mt5 = self.mt5
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": plan.symbol,
            "volume": float(plan.volume),
            "type": mt5.ORDER_TYPE_BUY if plan.side == "buy" else mt5.ORDER_TYPE_SELL,
            "price": float(plan.price),
            "sl": float(plan.stop),
            "tp": float(plan.take_profit),
            "deviation": self.deviation_points,
            "magic": self.magic,
            "comment": plan.comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": pick_filling_mode(spec.filling_mode, mt5),
        }
        check = mt5.order_check(request)
        if check is None or check.retcode != 0:
            detail = mt5.last_error() if check is None else (check.retcode, check.comment)
            raise RuntimeError(f"order_check rejected the request: {detail}")
        result = mt5.order_send(request)
        if result is None or result.retcode not in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL):
            detail = mt5.last_error() if result is None else (result.retcode, result.comment)
            raise RuntimeError(f"order_send failed: {detail}")
        return result

    def close_all(self, symbol: str, spec: SymbolSpec, comment: str = "smc-gold-flat") -> list:
        closed = []
        for position in self.positions(symbol):
            tick = self.mt5.symbol_info_tick(symbol)
            if tick is None:
                raise RuntimeError(f"symbol_info_tick failed: {self.mt5.last_error()}")
            is_buy = int(position.type) == int(self.mt5.POSITION_TYPE_BUY)
            request = {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "position": int(position.ticket),
                "volume": float(position.volume),
                "type": self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY,
                "price": float(tick.bid if is_buy else tick.ask),
                "deviation": self.deviation_points,
                "magic": self.magic,
                "comment": comment[:31],
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": pick_filling_mode(spec.filling_mode, self.mt5),
            }
            result = self.mt5.order_send(request)
            if result is None or result.retcode not in (
                self.mt5.TRADE_RETCODE_DONE,
                self.mt5.TRADE_RETCODE_DONE_PARTIAL,
            ):
                detail = self.mt5.last_error() if result is None else (result.retcode, result.comment)
                raise RuntimeError(f"failed to close ticket {position.ticket}: {detail}")
            closed.append(result)
        return closed