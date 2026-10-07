# IBKR Trader – vollständige Umbauanweisung

## Auftrag

Dieses Repository ist eine Kopie des bestehenden Kraken-Trader-Repositories. Daraus soll eine **eigenständige Interactive-Brokers-Trading-App für Home Assistant** entstehen.

Die Kraken-App bleibt vollständig unabhängig. Nicht einfach Begriffe umbenennen oder nur die API austauschen. Alle Kraken-spezifischen Annahmen müssen fachlich durch IBKR-Implementierungen ersetzt werden. Gute brokerunabhängige Konzepte dürfen übernommen und verbessert werden.

Ziel: ein **vollautonomes, modulares, selbstlernendes IBKR-Trading-System** mit Gemini, News, dynamischem Multi-Asset-Scanning, assetklassenspezifischer Analyse, Portfolio-Risk, Margin, Leverage, Short und sicherer automatischer Orderausführung.

Kein überladenes eigenes GUI: Home-Assistant-Konfiguration, Sensoren und strukturierte AppLogs sind die Hauptoberfläche.

## 1. Zielprozess

Der vollständige Zyklus muss sein:

IBKR-Verbindung → Account/Portfolio → Instrument Discovery → Datenqualität/Liquidität → Marktanalyse → News → Instrument-/Sektor-Mapping → Gemini → historische Lerndaten → Asset-Class-Strategie → Decision → Portfolio-/Risk-Analyse → Sizing → Order-Preflight → IBKR Order → Orderstatus/Fills → Portfolio-Reconciliation → Ergebnisbewertung → Learning → kontrollierte Recalibration.

Es muss immer unterschieden werden zwischen:

- Signal
- Decision
- Risk Approved
- Intent
- Order Submitted
- Order Accepted
- Partial Fill
- Filled
- Position Confirmed

Niemals `ORDER_SUBMITTED` als ausgeführten Trade melden.

## 2. IBKR-Adapter

Eine klar abgegrenzte `IBKRClient`-/Adapter-Schicht erstellen. Die übrige Anwendung darf nicht direkt von IBKR-API-Objekten abhängen.

Unterstützen:

- TWS/IB Gateway-Verbindung
- Reconnect/Heartbeat
- Account Summary
- Portfolio/Positions
- Orders/Open Orders
- Executions/Fills
- Contract Details
- Instrument Discovery
- Historical/Live Market Data
- Buying Power/Margin
- Shortability
- Trading Hours
- Market Rules
- Order Status
- Fees/Commissions, soweit verfügbar
- Fehler-/Warning-Events

IBKR unterstützt über seine APIs u.a. Aktien, Optionen, Futures, Forex, Bonds, Fonds und weitere Produkte. Contract Details enthalten u.a. ConId, Security Type, Exchange, Currency, Tick-/Size-Regeln, Handelszeiten, Expiry und weitere handelsrelevante Eigenschaften. Diese Daten sind die maßgebliche Quelle für die Instrumentmodellierung.

## 3. Kraken vollständig entfernen

Keine Kraken-Abhängigkeiten zurücklassen:

- REST/WebSocket
- Nonce/API-Key-Logik
- AssetPairs
- Kraken Futures-Endpunkte
- xStocks-Endpunkte
- Kraken Orderparameter
- Kraken Symbol-/Pair-Annahmen
- Kraken Leverage-/Margin-Regeln
- Kraken Gebührenmodell
- Kraken Statuscodes/IDs
- Kraken Rate-Limit-Annahmen
- Kraken Discovery
- Kraken Portfolio/Balance
- Kraken-spezifische Recovery-Logik

Keine Dummy-Adapter oder scheinbar funktionierenden Stubs.

## 4. Instrumentmodell

Das bisherige Kraken-Instrumentmodell reicht nicht.

IBKR-Instrumente müssen mindestens modellieren:

- con_id
- symbol/local_symbol
- security_type
- exchange/primary_exchange
- currency
- trading_class
- multiplier
- min_tick/market_rule
- min_size/size_increment
- trading_hours/liquid_hours
- expiry/contract_month
- strike/right
- underlying/underlying_con_id
- margin characteristics
- shortability
- order capabilities
- market-data availability
- account eligibility/ineligibility reason
- Assetklasse
- Sektor/Industry, soweit verfügbar

Contract Details müssen als Quelle der Wahrheit für handelstechnische Eigenschaften verwendet werden.

## 5. Assetklassen

Von Anfang an architektonisch unterstützen:

### Aktien
Bewertung aus Trend, Momentum, Volatilität, Relative Strength, Volumen/Liquidität, Breakouts, Fundamentaldaten soweit zuverlässig, Bewertung, Dividenden, Earnings/Event-Risiko, Sektor, Marktregime, News, Gemini und historischer Performance.

Trading: Long, Short sofern shortable, Exit, Rebalancing; Positionsgröße portfolio- und liquiditätsabhängig.

### ETFs
Zusätzlich Underlying-/Index-Exposure, Struktur, Liquidität, Spread, Tracking-/Sektor-/Regionenrisiken.

### FX
Trend/Momentum, Volatilität, Zins-/Makroumfeld, relative Währungsstärke, Zentralbank-News, Session/Handelszeit, Spread und Liquidität. Korrekte Basis-/Quote-Währungs- und Portfolio-Umrechnung.

### Futures
Eigene Logik für Contract Month, Expiry, Multiplier, Tick Value, Tick Size, Initial/Maintenance Margin, Settlement, Liquidität und Rollrisiko. Eigene Sizing-/Risk-Logik und Rollprozess.

### Optionen / Futures Options
Eigene Bewertungs- und Risk-Logik für Underlying, Strike, Expiry, Call/Put, IV, Delta, Gamma, Theta, Vega, Rho, Open Interest, Volume, Bid/Ask, Spread, Time-to-Expiry, Moneyness, Volatilitätsregime und Eventrisiko.

Unterstützen, soweit Konto und Contract es erlauben:
- Long Call
- Long Put
- gedeckte/definierte Short-Strategien
- Exit
- ausgewählte Multi-Leg-Strategien

Keine ungedeckten Short-Optionen automatisch freigeben. Vor Order maximale Verluste, Margin, Liquidität, Assignment-/Exercise-Risiko prüfen.

### Bonds
Eigene Logik für Yield, Duration, Maturity, Credit Risk, Spread, Liquidität, Zinsumfeld, Bonität, News und Makro. Stückelung, Preisnotierung und Mindestgrößen berücksichtigen.

### Fonds / Mutual Funds
Nur handeln, wenn Ordermechanik, Mindestanlage, Datenqualität, Handelszeit und NAV-Mechanik ausreichend bekannt sind. Keine Aktien-Intraday-Logik anwenden.

### Warrants / strukturierte Produkte / weitere IBKR-Instrumente
Erkennen und klassifizieren. Nur automatisch handeln, wenn Contract Details, Liquidität, Preisbildung und Risk ausreichend verstanden werden. Sonst `ANALYSIS_ONLY`.

Unbekannte Instrumente niemals automatisch handeln.

## 6. Capability-System

Jedes Instrument erhält ein Capability-Profil, z.B.:

- can_long
- can_short
- can_margin
- can_market_order
- can_limit_order
- can_stop
- can_trailing
- can_bracket
- can_fractional
- supports_combo
- market_data_available
- historical_data_available
- account_eligible
- tradable_now
- supported_by_strategy
- supported_by_risk

Blockierungsgründe müssen konkret sein, z.B.:

`SHORT_NOT_AVAILABLE`, `MARGIN_NOT_AVAILABLE`, `MARKET_DATA_UNAVAILABLE`, `ACCOUNT_INELIGIBLE`, `OUTSIDE_TRADING_HOURS`, `UNSUPPORTED_CONTRACT`, `INSUFFICIENT_LIQUIDITY`, `OPTION_DATA_INCOMPLETE`.

Keine pauschalen Gates, die ganze Assetklassen unbeabsichtigt ausschließen.

## 7. Discovery und Scanner

Kein statischer Trading-Universe.

Pipeline:

Universe → Eligibility → Market Data → Liquidity/Spread → Volatility/Opportunity → News Relevance → Technical Pre-score → Asset-Class Deep Analysis → Gemini → Portfolio-aware Decision.

Vorfilterung darf nicht zu aggressiv sein. Für jede Stufe zählen und loggen:

- discovered
- eligible
- data-ready
- candidate
- deep-analyzed
- decision-ready
- approved
- blocked
- traded

`NOT_TRADABLE`, `NOT_SUPPORTED`, `DATA_INCOMPLETE`, `LOW_PRIORITY`, `ANALYSIS_ONLY` und `TRADE_CANDIDATE` unterscheiden.

## 8. Strategiearchitektur

Gemeinsamer Decision-Rahmen:

- LONG
- SHORT
- HOLD
- EXIT
- REBALANCE
- NO_ACTION

Assetklassenspezifische Module:

- EquityStrategy
- ETFStrategy
- FXStrategy
- FuturesStrategy
- OptionsStrategy
- BondStrategy
- weitere spezialisierte Strategien

Standardisierte Ausgabe:

- direction
- confidence
- expected_return
- expected_risk
- net_edge
- holding_period
- target_position
- rationale
- feature_snapshot
- data_quality
- invalidation_conditions

Beispielhafte Faktoren:

`Equity = technical + momentum + fundamental + news + regime`

`ETF = technical + underlying + flow/liquidity + news + regime`

`FX = technical + macro + rates + news + volatility`

`Futures = technical + macro + term structure + volatility + margin`

`Options = underlying + IV + Greeks + liquidity + expiry + event risk`

`Bonds = yield + duration + credit + rates + liquidity + macro`

Gewichtungen müssen konfigurierbar und lernfähig sein.

## 9. News und Gemini

News müssen echte Entscheidungsfeatures sein, nicht nur Logs.

News-Pipeline:

News → Deduplication → Source Quality → Timestamp → Entity Extraction → Instrument/Sector/Asset Mapping → Sentiment → Impact → Confidence → Decay → Strategy Feature → Decision.

Speichern:

- Quelle
- Zeitpunkt
- betroffene Instrumente/Sektoren
- Assetklasse
- Sentiment
- Impact
- Decay
- Gemini Interpretation
- späteres Ergebnis

Gemini ist die einzige externe KI.

Gemini darf News, Regime und qualitative Faktoren interpretieren, Szenarien erzeugen und Lernfeedback analysieren. Gemini darf aber niemals deterministische Risk-Gates umgehen.

Bei Gemini-Ausfall: deterministisch weiterarbeiten, sofern Mindestdaten reichen, sonst `NO_ACTION`/`ANALYSIS_ONLY`.

## 10. Risk Engine

Portfolio- und assetklassenbewusst prüfen:

- positive equity
- daily loss
- max drawdown
- position limit
- gross exposure
- net exposure
- open positions
- cash reserve
- margin availability
- maintenance margin
- leverage
- shortability
- liquidity
- spread
- transaction costs
- concentration
- correlation
- sector exposure
- currency exposure
- event risk
- volatility regime
- data quality
- market hours
- order size/minimums

Jeder Block muss einen exakten Grund liefern.

Leverage niemals pauschal annehmen. Tatsächliche IBKR-Margin-/Contract-Anforderungen, Portfolio, Volatilität, Liquidität und konfigurierte Obergrenzen berücksichtigen.

Short nur nach echter Shortability-/Account-/Margin-Prüfung.

## 11. Order Engine

Nur Contract-kompatible IBKR-Ordertypen verwenden.

Je nach Contract:

- Market
- Limit
- Stop
- Stop Limit
- Trailing
- Bracket
- weitere geeignete IBKR-Typen

Vor Submit:

1. Contract validieren
2. Trading Hours
3. Market Data
4. Position/Target
5. Quantity
6. Price
7. Tick Size
8. Min Size
9. Margin
10. Risk
11. Duplicate/Idempotency
12. Submit

Danach ACK/Submitted/Partial Fill/Filled/Cancelled/Rejected/Error getrennt verarbeiten.

## 12. Recovery und Reconciliation

Nach Neustart:

Connect → lokale Daten laden → IBKR-Zustand abfragen → Orders reconciliieren → Positions reconciliieren → Cash/Margin reconciliieren → erst dann Trading fortsetzen.

Persistente Intent-ID, Broker Order ID, Contract ID, Status, Timestamps und Execution IDs verwenden.

Bei widersprüchlichem Zustand:

`RECOVERY_REQUIRED`

und keine neuen riskanten Orders.

Doppelorders nach Neustart müssen ausgeschlossen werden.

## 13. Portfolio

Mindestens:

- cash
- available funds
- buying power
- equity
- gross exposure
- net exposure
- margin used
- maintenance margin
- unrealized PnL
- realized PnL
- daily PnL
- currency exposure
- asset-class exposure
- sector exposure
- concentration

Entscheidungen müssen portfolio-aware sein. Ein gutes Einzelsignal kann wegen Korrelation, Konzentration oder Margin trotzdem `NO_ACTION` ergeben.

## 14. Kosten

Berücksichtigen:

- commissions
- exchange/regulatory fees
- spread
- slippage
- financing
- margin costs
- borrow costs, soweit verfügbar
- options-/futures-spezifische Kosten

Entscheidungsgröße ist `expected_net_edge_after_costs`, nicht Bruttoertrag.

## 15. Learning und Recalibration

Für jede Entscheidung speichern:

- Marktbedingungen
- Features
- News
- Gemini
- Decision
- Confidence
- Position Size
- Risk State
- Order
- Execution
- Slippage
- Fees
- Outcome
- Holding Period
- MFE/MAE
- Exit Reason

Performance nach Assetklasse, Strategie, Regime, News-Typ und Confidence-Bereich auswerten.

Lernfähig sind z.B.:

- Signalgewichtungen
- technische Feature-Gewichte
- News-Gewicht
- Confidence Thresholds
- Holding Period
- Entry/Exit Thresholds
- Positionsgrößen
- Asset-Class-Parameter

Aber niemals automatisch Sicherheits-/Brokergrenzen lockern.

Parameteränderungen versionieren, Mindest-Sample-Größe verwenden, Out-of-Sample testen, Regressionen erkennen und bei Verschlechterung rollbacken.

## 16. Marktregime

Mindestens erkennen:

- trend
- range
- high volatility
- low volatility
- risk-on
- risk-off
- crisis/event

Strategiegewichtungen dürfen regimeabhängig angepasst werden.

## 17. Autonomie und Sicherheit

Automatisch:

- scannen
- analysieren
- lernen
- überwachen
- Orders verwalten
- Positionen überwachen
- reconnecten
- Zustand rekonstruieren
- recalibrieren

Immer vorhanden:

- Kill Switch
- maximale Ordergröße
- maximaler Tagesverlust
- maximale Margin
- maximale Leverage
- maximale Orderzahl
- maximale Positionszahl
- Emergency Stop bei Connection-/State-Inkonsistenz

Secrets niemals ins Repository oder in Logs.

## 18. Home Assistant

Nur notwendige Konfiguration:

- IBKR connection
- paper/live
- trading enabled
- risk limits
- learning
- Gemini
- news
- scan interval
- Asset-Class enable/disable
- safety limits

Sinnvolle Sensoren:

- connection
- equity/cash/buying power
- margin
- positions
- daily/total PnL
- current cycle
- discovered/candidate/analyzed instruments
- decisions
- approved/blocked orders
- last trade
- learning/model status
- news/Gemini status
- market regime
- risk state

Keine Sensorflut und keine GUI-Seiten mit nicht implementierten Aktionen.

## 19. AppLogs

Chronologisch und strukturiert:

`CYCLE_START`
`UNIVERSE_DISCOVERY`
`INSTRUMENT_FILTER`
`MARKET_DATA`
`NEWS_FETCH`
`NEWS_MAPPING`
`ANALYSIS`
`GEMINI_ANALYSIS`
`DECISION`
`PORTFOLIO_RISK`
`RISK_EVALUATION`
`ORDER_PRECHECK`
`ORDER_SUBMIT`
`ORDER_STATUS`
`EXECUTION`
`PORTFOLIO_RECONCILIATION`
`LEARNING`
`CYCLE_COMPLETE`

Fehlercodes z.B.:

`IBKR_CONNECT_FAILED`
`CONTRACT_DISCOVERY_FAILED`
`MARKET_DATA_UNAVAILABLE`
`NEWS_MAPPING_FAILED`
`GEMINI_UNAVAILABLE`
`RISK_BLOCKED`
`SHORT_NOT_AVAILABLE`
`MARGIN_INSUFFICIENT`
`ORDER_REJECTED`
`ORDER_PARTIAL_FILL`
`RECONCILIATION_REQUIRED`

## 20. Österreichisches Reporting

Keine individuelle Steuerberatung. Daten aber vollständig für spätere österreichische Steuer-/Reporting-Auswertung speichern:

- Kauf/Verkauf
- Zeitpunkt
- Instrument
- Menge
- Preis
- Währung
- Gebühren
- Realized PnL
- FX-Konvertierung
- Corporate Actions
- Dividenden
- Zinsen
- Assetklasse

Eine verständliche österreichische Steuer-Info/Hilfe soll vorhanden sein.

## 21. Datenbank

Modular mindestens für:

- instruments/contracts
- market snapshots/candles
- news/news links
- decisions/intents
- orders/executions
- positions
- portfolio snapshots
- risk events
- learning samples
- model/parameter versions
- cycle runs
- errors/recovery

SQLite darf verwendet werden, muss aber transaktionssicher und performant betrieben werden. Große Batch-Schreibvorgänge in expliziten Transaktionen.

## 22. Performance

Großes IBKR-Universum nicht bei jedem Zyklus teuer komplett analysieren.

Verwenden:

- Caching/TTL
- inkrementelle Discovery
- Priorisierung
- sichere Parallelisierung
- begrenzte Gemini-Aufrufe
- gespeicherte Contract Details
- gespeicherte Features
- intelligente Re-Analyse

Korrektheit niemals zugunsten von Performance opfern.

## 23. Fehlerverhalten

Jede externe Abhängigkeit muss separat ausfallen können.

IBKR offline:
- keine neuen Orders
- Positionen intern überwachen
- reconnect

Gemini offline:
- deterministischer Fallback oder `NO_ACTION`

News offline:
- technische Analyse weiter möglich, News-abhängige Strategien abwerten

Datenbankfehler:
- keine neuen riskanten Orders
- Recovery

Keine stillen Fallbacks und keine Fake-Daten.

## 24. Tests

Unit Tests mindestens für:

- Contract Mapping
- Asset-Class Detection
- Sizing
- Risk
- Margin
- Leverage
- Shortability
- Optionsdaten/Greeks
- Futures Sizing
- Order Translation
- Tick Rounding
- Currency Conversion
- News Mapping
- Learning
- Idempotency

Integration Tests:

- IBKR Connection Mock
- Account
- Positions
- Contract Discovery
- Market Data
- Order Lifecycle
- Reconnect
- Reconciliation

Jeder gefundene Fehler wird als Regression Test festgehalten.

End-to-End:

`Discovery → Analysis → Decision → Risk → Intent → Order → Fill → Position → Learning`

Test-/Paper-Pfad und Live-Pfad müssen möglichst denselben Decision-/Risk-Code verwenden.

## 25. CI/CD

Vor Merge:

- formatting
- lint
- type checks
- unit tests
- integration tests
- security scan
- container build
- Home Assistant structure validation
- startup smoke test
- import/compile checks

Keine rote CI auf `main`.

Nach Reparaturen CI erneut prüfen. Nur vollständig grün mergen.

## 26. Entwicklungsreihenfolge

1. Repository analysieren und Kraken-Abhängigkeiten inventarisieren.
2. IBKR Adapter und Domainmodelle.
3. Contract-/Instrument-Discovery.
4. Account/Portfolio/Margin/Positions.
5. Market Data.
6. Asset-Class Strategy Layer.
7. News + Gemini.
8. Risk/Sizing.
9. Order/Execution/Reconciliation.
10. Learning/Recalibration.
11. HA Integration.
12. Tests, CI, Performance, Cleanup.

Nicht viele halbfertige Pfade gleichzeitig als fertig markieren.

## 27. Abnahme

Fertig erst wenn:

1. Keine Kraken-Abhängigkeiten mehr vorhanden.
2. IBKR stabil angebunden.
3. Account/Portfolio korrekt gelesen.
4. Contracts korrekt erkannt.
5. Assetklassen korrekt unterschieden.
6. Aktien, ETFs, FX, Futures, Optionen und Bonds eigene sinnvolle Bewertungs-/Risklogik besitzen.
7. Short korrekt geprüft wird.
8. Margin korrekt geprüft wird.
9. Leverage korrekt geprüft wird.
10. News tatsächlich Entscheidungen beeinflussen.
11. Gemini tatsächlich integriert ist.
12. Learning reale Outcomes speichert.
13. Recalibration kontrolliert funktioniert.
14. Keine Order ohne vollständige Risk-Prüfung gesendet wird.
15. Keine falsche Erfolgsmeldung entsteht.
16. Neustart keine Doppelorder erzeugt.
17. Portfolio nach Neustart reconciled wird.
18. HA Sensoren sinnvoll sind.
19. AppLogs den gesamten Prozess zeigen.
20. unbekannte/ungeeignete Instrumente niemals automatisch gehandelt werden.
21. keine Assetklasse durch überstrenge Vorfilter unbeabsichtigt verschwindet.
22. CI vollständig grün ist.
23. Container/HA-Installation funktioniert.
24. Die App autonom laufen kann.

## 28. Grundregel

Nicht fragen:

„Wie kann der Kraken-Code mit möglichst wenig Änderungen auf IBKR gebracht werden?“

Sondern:

**„Wie muss dieser Teil bei IBKR fachlich korrekt funktionieren?“**

Danach den bestehenden Code wiederverwenden, soweit sinnvoll.

Keine Workarounds nur für grüne Tests. Keine Dummy-Daten. Keine Dummy-Orderausführung. Keine pauschalen Gates. Keine stillen Fallbacks.

## Endziel

**IBKR Autonomous Modular Self-Learning Trader für Home Assistant**

mit vollständiger IBKR-Anbindung, dynamischem Multi-Asset-Scanning, assetklassenspezifischer Analyse, Gemini, News, Portfolio-aware Decision Making, Margin, Leverage, Short, Options-/Futures-/Bond-spezifischer Logik, autonomer Orderausführung, Reconciliation, Learning, Recalibration, Fehleranalyse und minimaler Wartung.

Die Anwendung soll kein Kraken-Trader mit ausgetauschtem Broker sein, sondern ein fachlich korrekter, eigenständiger IBKR-Trader.
