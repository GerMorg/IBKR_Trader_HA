from __future__ import annotations

from decimal import Decimal

from app.domain.models import Instrument, MarketSnapshot, Signal
from app.domain.states import AssetClass
from .strategies import BondStrategy, EquityStrategy, ETFStrategy, FXStrategy, FuturesStrategy, OptionsStrategy, Strategy


class StrategyDispatcher:
    def __init__(self) -> None:
        self.strategies: dict[AssetClass, Strategy] = {
            AssetClass.EQUITY: EquityStrategy(),
            AssetClass.ETF: ETFStrategy(),
            AssetClass.FX: FXStrategy(),
            AssetClass.FUTURES: FuturesStrategy(),
            AssetClass.OPTION: OptionsStrategy(),
            AssetClass.FUTURES_OPTION: OptionsStrategy(),
            AssetClass.BOND: BondStrategy(),
            AssetClass.FUND: BondStrategy(),
        }

    def evaluate(
        self,
        instrument: Instrument,
        snapshot: MarketSnapshot,
        features: dict[str, Decimal],
        regime: str,
        news_impact_bps: Decimal,
        gemini_impact_bps: Decimal,
    ) -> tuple[Signal, Signal] | None:
        strategy = self.strategies.get(instrument.asset_class)
        if strategy is None:
            return None
        return strategy.evaluate(instrument, snapshot, features, regime, news_impact_bps, gemini_impact_bps)
