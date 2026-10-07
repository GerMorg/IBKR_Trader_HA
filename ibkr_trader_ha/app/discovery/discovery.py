from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domain.models import CapabilityProfile, Contract, Instrument
from app.domain.states import AssetClass
from app.market.hours import is_liquid_now


SEC_TO_ASSET = {
    "STK": AssetClass.EQUITY,
    "CASH": AssetClass.FX,
    "FUT": AssetClass.FUTURES,
    "OPT": AssetClass.OPTION,
    "FOP": AssetClass.FUTURES_OPTION,
    "BOND": AssetClass.BOND,
    "FUND": AssetClass.FUND,
    "WAR": AssetClass.WARRANT,
}


class DiscoveryEngine:
    PROFILES = (
        ("STK", "STK.US.MAJOR", "MOST_ACTIVE"),
        ("STK", "STK.US.MAJOR", "TOP_PERC_GAIN"),
        ("STK", "STK.US.MAJOR", "TOP_PERC_LOSE"),
        ("FUT", "FUT.US", "MOST_ACTIVE"),
        ("CASH", "CASH.IDEALPRO", "MOST_ACTIVE"),
        ("BOND", "BOND.US", "MOST_ACTIVE"),
    )

    def __init__(self, ibkr: Any, config: Any) -> None:
        self.ibkr = ibkr
        self.config = config
        self._profile_index = 0
        self.last_errors: list[str] = []

    def discover(self) -> tuple[list[Instrument], dict[str, int]]:
        enabled = {
            AssetClass.EQUITY: self.config.asset_equities_enabled,
            AssetClass.ETF: self.config.asset_etfs_enabled,
            AssetClass.FX: self.config.asset_fx_enabled,
            AssetClass.FUTURES: self.config.asset_futures_enabled,
            AssetClass.OPTION: self.config.asset_options_enabled,
            AssetClass.BOND: self.config.asset_bonds_enabled,
            AssetClass.FUND: self.config.asset_funds_enabled,
            AssetClass.STRUCTURED: self.config.asset_structured_enabled,
        }
        rows: list[dict[str, Any]] = []
        for _ in range(self.config.scan_profiles_per_cycle):
            profile = self.PROFILES[self._profile_index % len(self.PROFILES)]
            self._profile_index += 1
            try:
                rows.extend(self.ibkr.scanner(*profile, rows=self.config.scan_max_results_per_profile))
            except Exception as exc:
                self.last_errors.append(f"{type(exc).__name__}:{str(exc)[:160]}")
        unique: dict[int, dict[str, Any]] = {}
        for row in rows:
            con_id = int(row.get("con_id", 0) or 0)
            if con_id > 0:
                unique[con_id] = row

        instruments: list[Instrument] = []
        stats = {"discovered": len(unique), "eligible": 0, "unsupported": 0}
        for row in unique.values():
            instrument = self.map_contract(row)
            if not enabled.get(instrument.asset_class, False):
                stats["unsupported"] += 1
                continue
            instruments.append(instrument)
            stats["eligible"] += int(instrument.capability.account_eligible)
        return instruments, stats

    @classmethod
    def map_contract(cls, row: dict[str, Any]) -> Instrument:
        sec = str(row.get("sec_type", "")).upper()
        asset = SEC_TO_ASSET.get(sec, AssetClass.UNKNOWN)
        long_name = str(row.get("long_name", ""))
        category = str(row.get("category", "")).lower()
        if sec == "STK" and ("etf" in long_name.lower() or "exchange traded fund" in category):
            asset = AssetClass.ETF
        if sec in {"WAR", "IOPT"}:
            asset = AssetClass.WARRANT
        if sec not in SEC_TO_ASSET and sec:
            asset = AssetClass.STRUCTURED if sec in {"CFD", "CMDTY"} else AssetClass.UNKNOWN

        contract = Contract(
            con_id=int(row["con_id"]),
            symbol=str(row.get("symbol", "")),
            local_symbol=str(row.get("local_symbol", row.get("symbol", ""))),
            security_type=sec,
            exchange=str(row.get("exchange", "SMART")),
            primary_exchange=str(row.get("primary_exchange", "")),
            currency=str(row.get("currency", "")),
            trading_class=str(row.get("trading_class", "")),
            multiplier=cls._d(row.get("multiplier"), "1"),
            min_tick=cls._d(row.get("min_tick"), "0.01"),
            size_increment=cls._d(row.get("size_increment"), "1"),
            min_size=cls._d(row.get("min_size"), "0"),
            trading_hours=str(row.get("trading_hours", "")),
            liquid_hours=str(row.get("liquid_hours", "")),
            time_zone_id=str(row.get("time_zone_id", "UTC") or "UTC"),
            expiry=str(row.get("contract_month", "")),
            contract_month=str(row.get("contract_month", "")),
            strike=cls._d(row.get("strike"), "0") if sec in {"OPT", "FOP"} else None,
            right=str(row.get("right", "")),
            underlying=str(row.get("underlying", row.get("symbol", ""))),
            underlying_con_id=int(row.get("under_con_id", 0) or 0) or None,
            market_rule_ids=tuple(
                int(x) for x in str(row.get("market_rule_ids", "")).split(",") if x.strip().isdigit()
            ),
            metadata=dict(row),
        )
        order_types = str(row.get("order_types", ""))
        supports_limit = "LMT" in order_types.upper() or not order_types
        cap = CapabilityProfile(
            can_long=asset not in {AssetClass.UNKNOWN, AssetClass.STRUCTURED},
            can_short=asset in {AssetClass.EQUITY, AssetClass.ETF, AssetClass.FX, AssetClass.FUTURES},
            can_margin=asset in {AssetClass.EQUITY, AssetClass.ETF, AssetClass.FX, AssetClass.FUTURES, AssetClass.OPTION},
            can_market_order="MKT" in order_types.upper() or not order_types,
            can_limit_order=supports_limit,
            can_stop="STP" in order_types.upper(),
            can_trailing="TRAIL" in order_types.upper(),
            can_bracket=True,
            can_fractional=asset in {AssetClass.EQUITY, AssetClass.ETF},
            supports_combo=asset in {AssetClass.OPTION, AssetClass.FUTURES_OPTION},
            market_data_available=True,
            historical_data_available=True,
            account_eligible=True,
            tradable_now=is_liquid_now(str(row.get("liquid_hours", "")), str(row.get("time_zone_id", "UTC") or "UTC")) if row.get("liquid_hours") else False,
            supported_by_strategy=asset in {
                AssetClass.EQUITY, AssetClass.ETF, AssetClass.FX, AssetClass.FUTURES,
                AssetClass.OPTION, AssetClass.FUTURES_OPTION, AssetClass.BOND, AssetClass.FUND
            },
            supported_by_risk=asset != AssetClass.UNKNOWN,
        )
        return Instrument(contract, asset, cap, str(row.get("sector", "")), str(row.get("industry", "")), long_name)

    @staticmethod
    def _d(value: Any, default: str) -> Decimal:
        try:
            return Decimal(str(value if value not in (None, "") else default))
        except Exception:
            return Decimal(default)


    def discover_options(
        self,
        underlyings: list[tuple[Instrument, Decimal]],
    ) -> list[Instrument]:
        """Discover a bounded set of liquid option contracts for already ranked underlyings."""
        if not self.config.asset_options_enabled:
            return []
        out: list[Instrument] = []
        seen: set[int] = set()
        today = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y%m%d")
        for underlying, last_price in underlyings[: self.config.max_option_underlyings]:
            if underlying.asset_class not in {AssetClass.EQUITY, AssetClass.ETF, AssetClass.FUTURES}:
                continue
            sec_type = "STK" if underlying.asset_class in {AssetClass.EQUITY, AssetClass.ETF} else "FUT"
            try:
                chains = self.ibkr.option_chain(
                    underlying.contract.con_id, underlying.symbol, sec_type
                )
            except Exception as exc:
                self.last_errors.append(
                    f"OPTION_CHAIN:{underlying.symbol}:{type(exc).__name__}:{str(exc)[:120]}"
                )
                continue
            for chain in chains:
                expiries = [
                    x for x in chain.get("expirations", [])
                    if str(x) >= today and len(str(x)) == 8 and str(x).isdigit()
                ]
                expiries = sorted(expiries)[:2]
                strikes = sorted(
                    (Decimal(str(x)) for x in chain.get("strikes", [])),
                    key=lambda strike: abs(strike - last_price),
                )[:3]
                for expiry in expiries:
                    for strike in strikes:
                        for right in ("C", "P"):
                            if len(out) >= self.config.max_option_contracts:
                                return out
                            query = {
                                "symbol": underlying.symbol,
                                "security_type": "FOP" if sec_type == "FUT" else "OPT",
                                "exchange": str(chain.get("exchange") or "SMART"),
                                "primary_exchange": underlying.contract.primary_exchange,
                                "currency": underlying.currency,
                                "trading_class": str(chain.get("trading_class", underlying.contract.trading_class)),
                                "contract_month": expiry,
                                "expiry": expiry,
                                "strike": strike,
                                "right": right,
                                "multiplier": chain.get("multiplier", underlying.contract.multiplier),
                                "under_con_id": underlying.contract.con_id,
                            }
                            try:
                                details = self.ibkr.contract_details(query)
                            except Exception as exc:
                                self.last_errors.append(
                                    f"OPTION_CONTRACT:{underlying.symbol}:{type(exc).__name__}:{str(exc)[:120]}"
                                )
                                continue
                            if not details:
                                continue
                            item = self.map_contract(details[0])
                            if item.contract.con_id in seen:
                                continue
                            seen.add(item.contract.con_id)
                            out.append(
                                Instrument(
                                    item.contract,
                                    item.asset_class,
                                    item.capability,
                                    underlying.sector,
                                    underlying.industry,
                                    f"{underlying.description} option",
                                )
                            )
        return out
