"""A37 Krypto-Futures-Verfall: CME Bitcoin/Ether/Solana/XRP (inkl. Micro) und Deribit-Laufzeiten.

Regeln (selbst berechnet aus den veröffentlichten Kontraktregeln, Stand 1.11.2026):
- CME (Rulebook Kapitel 350 ff.): Handelsschluss 16:00 London am letzten Freitag des Kontraktmonats;
  ist das kein Geschäftstag in UK und USA, am vorhergehenden Tag, der in beiden Ländern Geschäftstag ist.
  Abrechnung zur CME CF Reference Rate (BRR, ETHUSD_RR usw.) dieses Tages.
- Deribit (Contract Introduction Policy): Verfall immer 08:00 UTC. Täglich, wöchentlich (jeden Freitag),
  monatlich (letzter Freitag) und quartalsweise (letzter Freitag im März, Juni, September, Dezember).
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import holidays

LONDON = ZoneInfo("Europe/London")
UTC = dt.timezone.utc
VERIFIED = "2026-11-01"
MONTH_CODE = "FGHJKMNQUVXZ"
CME = {
    "BTC": ("Bitcoin futures", "5 BTC", "CME CF Bitcoin Reference Rate (BRR)"),
    "MBT": ("Micro Bitcoin futures", "0.1 BTC", "CME CF Bitcoin Reference Rate (BRR)"),
    "ETH": ("Ether futures", "50 ETH", "CME CF Ether-Dollar Reference Rate"),
    "MET": ("Micro Ether futures", "0.1 ETH", "CME CF Ether-Dollar Reference Rate"),
    "SOL": ("Solana futures", "500 SOL", "CME CF Solana-Dollar Reference Rate"),
    "XRP": ("XRP futures", "50,000 XRP", "CME CF XRP-Dollar Reference Rate"),
}
SRC_CME = "CME Group Rulebook (crypto futures chapters, termination of trading), computed"
SRC_DERIBIT = "Deribit Contract Introduction Policy (expiries at 08:00 UTC), computed"


def _now(at: str | None) -> dt.datetime:
    if not at:
        return dt.datetime.now(UTC)
    try:
        t = dt.datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("'at' must be an ISO time, e.g. 2026-11-27T12:00:00Z")
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _last_friday(y: int, m: int) -> dt.date:
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    d = nxt - dt.timedelta(days=1)
    while d.weekday() != 4:
        d -= dt.timedelta(days=1)
    return d


def _hol(y: int):
    return holidays.country_holidays("GB", subdiv="ENG", years=[y - 1, y]), \
        holidays.financial_holidays("NYSE", years=[y - 1, y]) if hasattr(holidays, "financial_holidays") \
        else holidays.country_holidays("US", years=[y - 1, y])


def _business_both(d: dt.date, uk, us) -> bool:
    return d.weekday() < 5 and d not in uk and d not in us


def cme_last_trading_day(y: int, m: int) -> tuple[dt.date, str | None]:
    lf = _last_friday(y, m)
    uk, us = _hol(y)
    d, reason = lf, None
    if not _business_both(d, uk, us):
        reason = f"{lf.isoformat()} is a holiday ({uk.get(lf) or us.get(lf)}), moved to the previous business day"
        while not _business_both(d, uk, us):
            d -= dt.timedelta(days=1)
    return d, reason


def cme_expiries(product: str = "BTC", count: int = 6, at: str | None = None) -> dict:
    p = (product or "BTC").strip().upper()
    p = {"BITCOIN": "BTC", "ETHER": "ETH", "ETHEREUM": "ETH", "SOLANA": "SOL"}.get(p, p)
    if p not in CME:
        raise KeyError(f"Unknown CME crypto product '{product}'. Use one of: {', '.join(CME)}")
    if not 1 <= count <= 24:
        raise ValueError("count must be 1-24")
    now = _now(at)
    y, m = now.year, now.month
    out = []
    while len(out) < count:
        d, reason = cme_last_trading_day(y, m)
        t = dt.datetime(d.year, d.month, d.day, 16, 0, tzinfo=LONDON)
        if t > now:
            out.append({"contract": f"{p}{MONTH_CODE[m - 1]}{str(y)[-1]}", "month": f"{y}-{m:02d}",
                        "last_trading_day": d.isoformat(), "last_trade_london": t.isoformat(),
                        "last_trade_utc": t.astimezone(UTC).isoformat(),
                        "hours_left": round((t - now).total_seconds() / 3600, 1), "holiday_adjustment": reason})
        m += 1
        if m == 13:
            y, m = y + 1, 1
    name, size, settle = CME[p]
    return {"exchange": "CME", "product": p, "name": name, "contract_size": size, "final_settlement": settle,
            "rule": "Last Friday of the contract month, 16:00 London; if not a UK and US business day, the "
                    "preceding day that is.", "front": out[0], "expiries": out,
            "note": "CME lists the nearest consecutive months plus additional December contracts; far months "
                    "may not be listed yet.",
            "source": f"{SRC_CME} (verified {VERIFIED})"}


def deribit_expiries(kind: str = "all", count: int = 4, at: str | None = None) -> dict:
    k = (kind or "all").lower()
    if k not in ("all", "daily", "weekly", "monthly", "quarterly"):
        raise ValueError("kind must be all, daily, weekly, monthly or quarterly")
    if not 1 <= count <= 12:
        raise ValueError("count must be 1-12")
    now = _now(at)

    def at8(d):
        return dt.datetime(d.year, d.month, d.day, 8, 0, tzinfo=UTC)

    def tag(d: dt.date) -> str:
        if d == _last_friday(d.year, d.month):
            return "quarterly" if d.month in (3, 6, 9, 12) else "monthly"
        return "weekly" if d.weekday() == 4 else "daily"

    def code(d: dt.date) -> str:
        return f"{d.day}{d.strftime('%b').upper()}{d.strftime('%y')}"

    res = {}
    for kk in (["daily", "weekly", "monthly", "quarterly"] if k == "all" else [k]):
        lst, d = [], now.date()
        while len(lst) < count:
            if at8(d) > now:
                t = tag(d)
                ok = {"daily": True, "weekly": d.weekday() == 4, "monthly": t in ("monthly", "quarterly"),
                      "quarterly": t == "quarterly"}[kk]
                if ok:
                    lst.append({"expiry_utc": at8(d).isoformat(), "date": d.isoformat(), "code": code(d),
                                "type": t, "hours_left": round((at8(d) - now).total_seconds() / 3600, 1)})
            d += dt.timedelta(days=1)
        res[kk] = lst
    return {"exchange": "Deribit", "expiry_time_utc": "08:00", "expiries": res,
            "note": "Instrument names use the code, e.g. BTC-27NOV26. Not every date is listed for every coin; "
                    "a date gets the highest applicable type.",
            "source": f"{SRC_DERIBIT} (verified {VERIFIED})"}


def crypto_expiry(product: str = "BTC", count: int = 6, at: str | None = None, venue: str = "cme") -> dict:
    v = (venue or "cme").lower()
    if v == "deribit":
        return deribit_expiries(product if product.lower() in ("all", "daily", "weekly", "monthly", "quarterly")
                                else "all", min(count, 12), at)
    if v != "cme":
        raise ValueError("venue must be cme or deribit")
    return cme_expiries(product, count, at)
