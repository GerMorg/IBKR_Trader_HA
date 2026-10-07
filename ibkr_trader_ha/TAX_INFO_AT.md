# Österreichische Steuer-Hilfe – technische Einordnung

**Stand der Recherche: 7. Oktober 2026**

Diese Datei ist eine technische Orientierung für das Reporting der App und ersetzt keine individuelle Steuerberatung.

Für Privatvermögen behandelt das österreichische BMF Kapitalerträge grundsätzlich im Rahmen der Kapitaleinkünfte. Der besondere Steuersatz beträgt derzeit grundsätzlich 27,5 % für sonstige Kapitaleinkünfte; für Zinsen aus Sparbüchern und Girokonten nennt das BMF 25 %. Bei ausländischen Einkünften, bei denen kein österreichischer KESt-Abzug erfolgt, kann eine Aufnahme in die Einkommensteuerveranlagung erforderlich sein.

Für die App bedeutet das: IBKR-Transaktionen dürfen nicht nur als Trading-PnL gespeichert werden. Für spätere Prüfung müssen zumindest Transaktion, Zeitpunkt, Contract, Menge, Preis, Währung, Gebühren, FX-Umrechnung, Realized PnL, Dividenden/Zinsen und Corporate Actions erhalten bleiben.

Der österreichische Verlustausgleich ist nicht beliebig. Das BMF beschreibt insbesondere Einschränkungen danach, welche Kapitalerträge gleichartig besteuert werden. Deshalb erzeugt die App technische Rohdaten und Summen, aber keine automatische steuerliche Endklassifikation für jeden Sonderfall.

Für ausländische Broker ist außerdem zu berücksichtigen, dass nicht automatisch ein österreichischer KESt-Abzug durch die depotführende Stelle angenommen werden darf. Die App markiert Reports deshalb als READY_FOR_REVIEW statt als steuerlich fertig.

## Offizielle Quellen

- BMF: Allgemeine Informationen zu Einkünften aus Kapitalvermögen
  https://www.bmf.gv.at/themen/steuern/sparen-veranlagen/information-zu-einkuenften-aus-kapitalvermoegen.html

- BMF: Besteuerung inländischer sowie im Inland bezogener Kapitalerträge
  https://www.bmf.gv.at/themen/steuern/sparen-veranlagen/besteuerung-kapitalertraege-inland.html

- BMF: Verluste aus der Veräußerung von Kapitalvermögen und Derivaten
  https://www.bmf.gv.at/themen/steuern/sparen-veranlagen/verluste-aus-veraeusserung-von-kapitalvermoegen-und-derivaten.html

- BMF: Steuerbuch 2026
  https://www.bmf.gv.at/dam/jcr%3A436f8c01-38e0-41bf-b904-c0e62a862bf1/251117_Steuerbuch2026_DE_BF.pdf
