"""Smart Money Concepts adapted for MetaTrader 5 gold."""

from .smc import SmartMoneyConcepts
from .strategy import GoldSMCParams, GoldSMCStrategy

__version__ = "0.2.0"
__all__ = ["SmartMoneyConcepts", "GoldSMCParams", "GoldSMCStrategy"]