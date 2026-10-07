from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domain.models import Instrument, MarketSnapshot, NewsFeature, Signal
from app.domain.states import AssetClass, DecisionAction

D = Decimal


class Strategy:
    version = "0.1"

    def evaluate(
        self,
        instrument: Instrument,
        snapshot: MarketSnapshot,
        features: dict[str, D],
        regime: str,
        news_impact_bps: D,
        gemini_impact_bps: D,
    ) -> tuple[Signal, Signal]:
        raise NotImplementedError

    @staticmethod
    def _pair(
        instrument: Instrument,
        features: dict[str, D],
        regime: str,
        base_score: D,
        confidence: D,
        cost_bps: D,
        rationale: str,
    ) -> tuple[Signal, Signal]:
        score = max(D("-1"), min(D("1"), base_score))
        magnitude = abs(score)
        long_edge = max(D("0"), magnitude * D("140")) if score > 0 else D("0")
        short_edge = max(D("0"), magnitude * D("140")) if score < 0 else D("0")
        long_conf = confidence if score > 0 else max(D("0.05"), confidence - D("0.20"))
        short_conf = confidence if score < 0 else max(D("0.05"), confidence - D("0.20"))
        common = {
            "trend": features.get("trend", D("0")),
            "momentum": features.get("momentum", D("0")),
            "volatility": features.get("volatility", D("99")),
            "news_impact_bps": features.get("news_impact_bps", D("0")),
            "gemini_impact_bps": features.get("gemini_impact_bps", D("0")),
        }
        return (
            Signal(
                instrument.contract.con_id, DecisionAction.LONG, long_conf,
                magnitude * D("0.02"), max(D("0.005"), features.get("volatility", D("5")) / D("100")),
                long_edge, cost_bps, 24, D("0"), rationale, common, D("0.95"),
                ("trend reversal", "data quality deterioration"),
            ),
            Signal(
                instrument.contract.con_id, DecisionAction.SHORT, short_conf,
                magnitude * D("0.02"), max(D("0.005"), features.get("volatility", D("5")) / D("100")),
                short_edge, cost_bps, 24, D("0"), rationale, common, D("0.95"),
                ("shortability deterioration", "data quality deterioration"),
            ),
        )


class EquityStrategy(Strategy):
    version = "equity-v1"

    def evaluate(self, instrument: Instrument, snapshot: MarketSnapshot, features: dict[str, D], regime: str, news_impact_bps: D, gemini_impact_bps: D) -> tuple[Signal, Signal]:
        tech = features.get("trend", D("0")) * D("0.35") + features.get("momentum", D("0")) * D("0.35")
        news = (news_impact_bps + gemini_impact_bps) / D("100") * D("0.30")
        score = max(D("-1"), min(D("1"), tech + news))
        conf = max(D("0.10"), min(D("0.95"), D("0.55") + abs(score) * D("0.35") - features.get("volatility", D("5")) / D("100")))
        return self._pair(instrument, {**features, "news_impact_bps": news_impact_bps, "gemini_impact_bps": gemini_impact_bps}, regime, score, conf, max(D("8"), snapshot.spread_bps), "Trend + momentum + news/regime equity model.")


class ETFStrategy(EquityStrategy):
    version = "etf-v1"

    def evaluate(self, instrument: Instrument, snapshot: MarketSnapshot, features: dict[str, D], regime: str, news_impact_bps: D, gemini_impact_bps: D) -> tuple[Signal, Signal]:
        nav_gap = D("0")
        if snapshot.etf_nav and snapshot.etf_nav > 0:
            nav_gap = (snapshot.last / snapshot.etf_nav - D("1")) * D("100")
        features = {**features, "etf_nav_gap_pct": nav_gap}
        return super().evaluate(instrument, snapshot, features, regime, news_impact_bps, gemini_impact_bps)


class FXStrategy(Strategy):
    version = "fx-v1"

    def evaluate(self, instrument: Instrument, snapshot: MarketSnapshot, features: dict[str, D], regime: str, news_impact_bps: D, gemini_impact_bps: D) -> tuple[Signal, Signal]:
        score = features.get("trend", D("0")) * D("0.40") + features.get("momentum", D("0")) * D("0.20") + (news_impact_bps + gemini_impact_bps) / D("100") * D("0.40")
        conf = max(D("0.1"), min(D("0.9"), D("0.60") + abs(score) * D("0.25") - features.get("volatility", D("5")) / D("150")))
        return self._pair(instrument, {**features, "news_impact_bps": news_impact_bps, "gemini_impact_bps": gemini_impact_bps}, regime, score, conf, max(D("3"), snapshot.spread_bps), "FX trend + relative strength + macro/news model.")


class FuturesStrategy(Strategy):
    version = "futures-v1"

    def evaluate(self, instrument: Instrument, snapshot: MarketSnapshot, features: dict[str, D], regime: str, news_impact_bps: D, gemini_impact_bps: D) -> tuple[Signal, Signal]:
        basis = D(str(instrument.contract.metadata.get("basis_bps", "0") or "0"))
        score = features.get("trend", D("0")) * D("0.30") + features.get("momentum", D("0")) * D("0.25") - basis / D("100") * D("0.10") + (news_impact_bps + gemini_impact_bps) / D("100") * D("0.35")
        conf = max(D("0.1"), min(D("0.9"), D("0.55") + abs(score) * D("0.30") - features.get("volatility", D("5")) / D("100")))
        return self._pair(instrument, {**features, "news_impact_bps": news_impact_bps, "gemini_impact_bps": gemini_impact_bps}, regime, score, conf, max(D("6"), snapshot.spread_bps), "Futures trend + term-structure + volatility model.")


class OptionsStrategy(Strategy):
    version = "options-v1"

    def evaluate(self, instrument: Instrument, snapshot: MarketSnapshot, features: dict[str, D], regime: str, news_impact_bps: D, gemini_impact_bps: D) -> tuple[Signal, Signal]:
        required = [snapshot.implied_volatility, snapshot.delta, snapshot.gamma, snapshot.vega, snapshot.theta]
        if any(v is None for v in required):
            return self._pair(instrument, features, regime, D("0"), D("0.05"), D("9999"), "Option data incomplete.")
        iv = snapshot.implied_volatility or D("0")
        delta = snapshot.delta or D("0")
        risk_penalty = max(D("0"), iv - D("0.80"))
        score = delta * D("0.50") + (news_impact_bps + gemini_impact_bps) / D("100") * D("0.30") - risk_penalty * D("0.20")
        conf = max(D("0.10"), min(D("0.90"), D("0.55") + abs(score) * D("0.35") - risk_penalty / D("2")))
        return self._pair(instrument, {**features, "news_impact_bps": news_impact_bps, "gemini_impact_bps": gemini_impact_bps, "iv": iv}, regime, score, conf, max(D("12"), snapshot.spread_bps), "Underlying + IV + Greeks + event-risk option model.")


class BondStrategy(Strategy):
    version = "bond-v1"

    def evaluate(self, instrument: Instrument, snapshot: MarketSnapshot, features: dict[str, D], regime: str, news_impact_bps: D, gemini_impact_bps: D) -> tuple[Signal, Signal]:
        yield_value = D(str(instrument.contract.metadata.get("yield", "0") or "0"))
        duration = D(str(instrument.contract.metadata.get("duration", "5") or "5"))
        rates_bias = (news_impact_bps + gemini_impact_bps) / D("100")
        score = features.get("trend", D("0")) * D("0.20") + (yield_value / D("10")) * D("0.30") - (duration / D("30")) * rates_bias * D("0.10") + rates_bias * D("0.40")
        conf = max(D("0.10"), min(D("0.85"), D("0.50") + abs(score) * D("0.25")))
        return self._pair(instrument, {**features, "news_impact_bps": news_impact_bps, "gemini_impact_bps": gemini_impact_bps}, regime, score, conf, max(D("8"), snapshot.spread_bps), "Yield + duration + rates/news bond model.")
