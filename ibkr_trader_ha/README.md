# IBKR Trader HA

Standalone Home Assistant App für einen vollautonomen Interactive-Brokers-Trader.

## Architektur

Die Anwendung ist in Domain, IBKR-Adapter, Discovery/Market Data, Strategie, News/Gemini, Portfolio/Risk, Execution, Persistence, Learning und Home-Assistant-Observability getrennt. Nur app/ibkr kennt native ibapi-Objekte.

Der automatische Prozess ist:

IBKR → Account/Portfolio → Discovery → Datenqualität → Analyse → News → Gemini → Decision → Risk/Sizing → Intent → Preflight → Order → Fill → Reconciliation → Learning.

Unbekannte oder nicht ausreichend verstandene Instrumente werden maximal ANALYSIS_ONLY.

## Sicherer Start

Standardmäßig ist trading_enabled=false und kill_switch=true. Zuerst die IBKR-Verbindung im Paper-Konto validieren und erst nach erfolgreicher Reconciliation den Live-Modus bewusst aktivieren.

Weitere Details stehen in DOCS.md.
