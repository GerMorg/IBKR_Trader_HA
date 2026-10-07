# IBKR Trader HA – Dokumentation

## Betriebsmodell

Die App verwendet TWS oder IB Gateway als einzige Broker-Schnittstelle. Die Verbindung ist absichtlich über eine lokale oder private LAN-Adresse konfigurierbar. Der empfohlene sichere Erststart ist Paper-Trading mit kill_switch=true und trading_enabled=false.

Übliche IBKR-Ports sind TWS live 7496/paper 7497 sowie IB Gateway live 4001/paper 4002. Die App erzwingt keinen festen Port; der konfigurierte Port muss zum tatsächlich laufenden TWS/IB Gateway passen. Die IBKR API muss dort aktiviert und für die Quell-IP der App erreichbar sein.

Die App verwendet die IBKR Contract Details als maßgebliche Quelle für Handelsregeln. Scanner liefern zunächst Contracts; Marktdaten werden danach separat angefordert. Dadurch wird nicht aus einem Scanner-Ergebnis fälschlich auf handelbare Marktparameter geschlossen.

## Sicherheitsmodell

kill_switch blockiert jede neue Ordersubmission. trading_enabled muss ebenfalls aktiv sein. Live-Trading erfordert trading_mode=live. Zusätzlich verlangt die App vor neuen Orders ein deterministisches Risk-Ergebnis und standardmäßig einen erfolgreichen IBKR-What-If-Margincheck.

Gemini darf niemals Risk-Gates, Broker-Capabilities oder Sicherheitsgrenzen verändern.

## Prozess

Jeder Zyklus läuft über Discovery, Datenqualität, News, Features, Regime, Asset-Class-Strategie, Gemini, Decision, Portfolio-Risk, Sizing, Preflight, Submission, Status/Fills, Reconciliation und Learning.

Der Lebenszyklus wird mit eindeutigen Zuständen protokolliert. ORDER_SUBMITTED bedeutet nicht FILLED.

## Home Assistant

Die App hat bewusst kein eigenes GUI. Die Konfiguration erfolgt über die Home-Assistant-App-Konfiguration. Persistente Reports liegen unter /config/reports/tax; Diagnostik erfolgt über Sensoren und strukturierte AppLogs.

## Datenhaltung

SQLite liegt standardmäßig unter /data/ibkr_trader.db. Brokerzustand und lokale Intents werden nach Neustarts reconciliiert. Ein widersprüchlicher Zustand führt zu RECOVERY_REQUIRED; in diesem Zustand werden keine neuen riskanten Orders abgeschickt.

## Österreichisches Reporting

Die App speichert die für eine spätere österreichische steuerliche Auswertung relevanten Transaktionsdaten: Zeitpunkt, Contract, Menge, Preis, Währung, Kosten, Realized PnL, FX-Umrechnung, Dividenden/Zinsen und Corporate Actions soweit von IBKR verfügbar. Die Reports sind technische Datenauswertungen und keine individuelle Steuerberatung.
