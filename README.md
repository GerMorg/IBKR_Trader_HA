# IBKR Trader HA

A standalone Home Assistant App for autonomous Interactive Brokers trading.

The implementation is a clean IBKR domain/application design derived from the proven structure of the earlier Kraken application, but it contains no Kraken integration. The IBKR adapter is isolated from domain and strategy code so that broker-native API objects never leak into the decision, risk, learning, or persistence layers.

See [IBKR Trader specification](IBKR_Trader_Umbauanweisung.md) and [application documentation](ibkr_trader_ha/DOCS.md).
