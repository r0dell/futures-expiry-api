# Futures Expiry API (v0.1)

Verfallstermine, letzter Handelszeitpunkt und Rollover-Daten für Index-Futures von CME und Eurex.

| Endpunkt | Liefert | Preis |
|---|---|---|
| `/v1/front-month?product=ES` | Front-Kontrakt, meistgehandelter Kontrakt nach Roll-Tag, Tage bis Verfall | 0.0205 USDC |
| `/v1/expirations?product=NQ&count=4` | nächste Kontrakte mit Symbol, letztem Handelstag, Handelsende, Roll-Tag | 0.0205 USDC |
| `/v1/roll-calendar?product=FDAX&year=2027` | alle vier Verfälle eines Jahres | 0.0405 USDC |
| `/v1/crypto-expiry?product=BTC` / `?venue=deribit&product=weekly` | Krypto-Futures: CME BTC/MBT/ETH/MET/SOL/XRP (letzter Freitag 16:00 London, feiertagsbereinigt UK+USA) und Deribit-Verfälle (08:00 UTC) | 0.0305 USDC |
| `/v1/products`, `/docs`, `/health` | Produktliste, Doku | gratis |

Produkte: ES, MES, NQ, MNQ, YM, MYM, RTY, M2K (CME) · FDAX, FDXM, FESX, FSMI (Eurex).

## Regeln (aus den öffentlichen Kontraktspezifikationen)

- **CME:** Handel endet am 3. Freitag des Kontraktmonats um 9:30 ET. Ist die NYSE geschlossen, gilt der Handelstag davor (z. B. Juni 2026: Juneteenth → 18.6.).
- **Eurex:** letzter Handelstag = 3. Freitag, sonst der Eurex-Handelstag davor. Handelsschluss FDAX/FDXM 13:00, FESX 12:00, FSMI 09:00 (Frankfurt).
- **Roll-Tag:** Konvention, 8 Kalendertage vor Verfall (Donnerstag). Kein Börsentermin.
- **Krypto (A37):** CME: letzter Freitag des Monats 16:00 London; kein Geschäftstag in UK und USA → Tag davor. Deribit: täglich, freitags, letzter Freitag (Monat), letzter Freitag Mär/Jun/Sep/Dez (Quartal), immer 08:00 UTC.
- Feiertage: Open-Source-Bibliotheken `exchange_calendars` und `holidays`.

Bezahlung über x402 (USDC auf Base), siehe `paid_app.py`. Tests: `python -m pytest -q`.
