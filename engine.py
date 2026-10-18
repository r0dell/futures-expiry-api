"""Verfallstermine und Rollover-Daten für Index-Futures (CME, Eurex).

Alle Termine werden aus den öffentlichen Kontraktspezifikationen der Börsen
berechnet, nicht aus lizenzierten Kursdaten:

- CME Aktienindex-Futures: quartalsweise (H, M, U, Z). Handel endet am 3. Freitag
  des Kontraktmonats um 9:30 ET (Eröffnung NYSE). Ist das kein NYSE-Handelstag,
  gilt der Handelstag davor.
- Eurex Index-Futures: quartalsweise. Letzter Handelstag = Schlussabrechnungstag
  = 3. Freitag des Monats, falls Eurex-Handelstag, sonst der Handelstag davor.
  Handelsschluss im verfallenden Kontrakt: FDAX/FDXM 13:00, FESX 12:00,
  FSMI 09:00 (Ortszeit Frankfurt).
- Rollover: Konvention der Händler, kein Börsentermin. CME veröffentlicht den
  Roll-Tag 8 Kalendertage vor Verfall (ein Donnerstag); für Eurex wird dieselbe
  Konvention verwendet und als solche gekennzeichnet.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xc
import pandas as pd

DATA_VERSION = f"exchange_calendars {xc.__version__}"
MONTH_CODES = {3: "H", 6: "M", 9: "U", 12: "Z"}
UTC = dt.timezone.utc


class UnknownProduct(ValueError):
    pass


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    exchange: str
    calendar: str
    tz: str
    last_trade_time: dt.time
    roll_rule: str
    roll_official: bool
    spec_url: str


_CME_EQ = "https://www.cmegroup.com/markets/equities.html"
_CME = dict(exchange="CME Group", calendar="XNYS", tz="America/New_York",
            last_trade_time=dt.time(9, 30), roll_rule="Convention: 8 calendar days before expiration (Thursday), as used by CME roll calendars; some traders roll on Monday of expiration week",
            roll_official=False)
_EUREX = dict(exchange="Eurex", calendar="XEUR", tz="Europe/Berlin",
              roll_rule="Convention: 8 calendar days before expiration (Thursday); Eurex publishes no official roll date",
              roll_official=False)

PRODUCTS = {p.code: p for p in [
    Product("ES", "E-mini S&P 500", spec_url="https://www.cmegroup.com/markets/equities/sp/e-mini-sandp500.contractSpecs.html", **_CME),
    Product("MES", "Micro E-mini S&P 500", spec_url=_CME_EQ, **_CME),
    Product("NQ", "E-mini Nasdaq-100", spec_url=_CME_EQ, **_CME),
    Product("MNQ", "Micro E-mini Nasdaq-100", spec_url=_CME_EQ, **_CME),
    Product("YM", "E-mini Dow ($5)", spec_url=_CME_EQ, **_CME),
    Product("MYM", "Micro E-mini Dow", spec_url=_CME_EQ, **_CME),
    Product("RTY", "E-mini Russell 2000", spec_url=_CME_EQ, **_CME),
    Product("M2K", "Micro E-mini Russell 2000", spec_url=_CME_EQ, **_CME),
    Product("FDAX", "DAX Futures", last_trade_time=dt.time(13, 0), spec_url="https://www.eurex.com/ex-en/markets/idx/dax/DAX-Futures-139902", **_EUREX),
    Product("FDXM", "Mini-DAX Futures", last_trade_time=dt.time(13, 0), spec_url="https://www.eurex.com/ex-en/markets/idx/dax/Mini-DAX-Futures-139894", **_EUREX),
    Product("FESX", "EURO STOXX 50 Index Futures", last_trade_time=dt.time(12, 0), spec_url="https://www.eurex.com/ex-en/markets/idx/stx/euro-stoxx-50-derivatives/products/EURO-STOXX-50-Index-Futures-160088", **_EUREX),
    Product("FSMI", "SMI Futures", last_trade_time=dt.time(9, 0), spec_url="https://www.eurex.com/ex-en/markets/idx/country/six/SMI-Futures-34674", **_EUREX),
]}


def get_product(code: str) -> Product:
    p = PRODUCTS.get((code or "").upper().strip())
    if not p:
        raise UnknownProduct(f"Unknown product '{code}'. Use one of: {', '.join(PRODUCTS)}")
    return p


@lru_cache(maxsize=8)
def _calendar(name: str):
    today = dt.date.today()
    return xc.get_calendar(name, start="2020-01-02", end=f"{today.year + 5}-12-31")


def _third_friday(year: int, month: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(4 - d.weekday()) % 7)  # erster Freitag
    return d + dt.timedelta(days=14)


def last_trading_day(p: Product, year: int, month: int) -> dt.date:
    cal = _calendar(p.calendar)
    d = _third_friday(year, month)
    while not cal.is_session(pd.Timestamp(d)):
        d -= dt.timedelta(days=1)
    return d


def _iso(d: dt.datetime, tz: str) -> dict:
    return {"utc": d.astimezone(UTC).isoformat(), "local": d.astimezone(ZoneInfo(tz)).isoformat()}


def contract(p: Product, year: int, month: int) -> dict:
    ltd = last_trading_day(p, year, month)
    tz = ZoneInfo(p.tz)
    end = dt.datetime.combine(ltd, p.last_trade_time, tz)
    roll = _third_friday(year, month) - dt.timedelta(days=8)
    return {
        "symbol": f"{p.code}{MONTH_CODES[month]}{year % 10}",
        "symbol_long": f"{p.code}{MONTH_CODES[month]}{year}",
        "contract_month": f"{year}-{month:02d}",
        "last_trading_day": ltd.isoformat(),
        "trading_ends": _iso(end, p.tz),
        "moved_for_holiday": ltd != _third_friday(year, month),
        "roll_date": roll.isoformat(),
        "roll_official": p.roll_official,
    }


def _quarters_from(year: int, month: int):
    m = ((month - 1) // 3 + 1) * 3
    y = year
    while True:
        yield y, m
        m += 3
        if m > 12:
            m, y = 3, y + 1


def _now(at: dt.datetime | None) -> dt.datetime:
    if at is None:
        return dt.datetime.now(UTC)
    if at.tzinfo is None:
        raise ValueError("Time 'at' needs a UTC offset, e.g. 2026-11-27T15:00:00Z")
    return at


def upcoming(code: str, at: dt.datetime | None = None, count: int = 4) -> dict:
    p = get_product(code)
    now = _now(at)
    if not 1 <= count <= 12:
        raise ValueError("count must be between 1 and 12")
    out = []
    for y, m in _quarters_from(now.year, now.month):
        c = contract(p, y, m)
        if dt.datetime.fromisoformat(c["trading_ends"]["utc"]) > now:
            out.append(c)
        if len(out) == count:
            break
    return {"product": p.code, "name": p.name, "exchange": p.exchange, "timezone": p.tz,
            "contracts": out, "source": source(p)}


def front_month(code: str, at: dt.datetime | None = None) -> dict:
    p = get_product(code)
    now = _now(at)
    nxt = upcoming(code, now, 2)["contracts"]
    front, second = nxt[0], nxt[1]
    local_today = now.astimezone(ZoneInfo(p.tz)).date()
    rolled = local_today >= dt.date.fromisoformat(front["roll_date"])
    active = second if rolled else front
    ends = dt.datetime.fromisoformat(front["trading_ends"]["utc"])
    return {
        "product": p.code, "name": p.name, "exchange": p.exchange, "timezone": p.tz,
        "at": _iso(now, p.tz),
        "front_contract": front["symbol"],
        "most_active_contract": active["symbol"],
        "after_roll_date": rolled,
        "days_to_expiration": round((ends - now).total_seconds() / 86400, 2),
        "front": front, "next": second,
        "source": source(p),
    }


def roll_calendar(code: str, year: int) -> dict:
    p = get_product(code)
    if not 2020 <= year <= dt.date.today().year + 5:
        raise ValueError(f"year must be between 2020 and {dt.date.today().year + 5}")
    return {"product": p.code, "name": p.name, "exchange": p.exchange, "timezone": p.tz, "year": year,
            "contracts": [contract(p, year, m) for m in (3, 6, 9, 12)], "source": source(p)}


def list_products() -> list[dict]:
    return [{"code": p.code, "name": p.name, "exchange": p.exchange, "timezone": p.tz,
             "cycle": "quarterly (H M U Z)", "last_trade_time_local": p.last_trade_time.strftime("%H:%M"),
             "spec_url": p.spec_url} for p in PRODUCTS.values()]


def source(p: Product) -> dict:
    return {"rules": p.spec_url, "holidays": f"{DATA_VERSION} ({p.calendar})",
            "roll": p.roll_rule,
            "note": "Computed from published exchange rules; verify against the exchange before trading."}
