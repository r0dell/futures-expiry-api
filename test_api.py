"""Prüft die API gegen bekannte Verfallsregeln. Start: python -m pytest -q"""
from fastapi.testclient import TestClient

from app import app

c = TestClient(app)


def get(path, **params):
    r = c.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def by_symbol(res, sym):
    return next(x for x in res["contracts"] if x["symbol"] == sym)


def test_products():
    codes = {p["code"] for p in get("/v1/products")}
    assert {"ES", "MNQ", "FDAX", "FSMI"} <= codes


def test_es_dec_2026_third_friday_0930_et():
    r = get("/v1/roll-calendar", product="ES", year=2026)
    z = by_symbol(r, "ESZ6")
    assert z["last_trading_day"] == "2026-12-18"
    assert z["trading_ends"]["utc"].startswith("2026-12-18T14:30")
    assert z["roll_date"] == "2026-12-10"  # Donnerstag, 8 Tage vorher


def test_es_june_2026_juneteenth_moves_to_thursday():
    # 19.6.2026 ist 3. Freitag und NYSE-Feiertag (Juneteenth)
    m = by_symbol(get("/v1/roll-calendar", product="ES", year=2026), "ESM6")
    assert m["last_trading_day"] == "2026-06-18" and m["moved_for_holiday"]


def test_fdax_june_2026_not_moved():
    m = by_symbol(get("/v1/roll-calendar", product="FDAX", year=2026), "FDAXM6")
    assert m["last_trading_day"] == "2026-06-19" and not m["moved_for_holiday"]
    assert m["trading_ends"]["local"].startswith("2026-06-19T13:00")
    assert m["roll_official"] is False


def test_fsmi_closes_0900_frankfurt():
    m = by_symbol(get("/v1/roll-calendar", product="FSMI", year=2027), "FSMIM7")
    assert m["last_trading_day"] == "2027-06-18"
    assert m["trading_ends"]["utc"].startswith("2027-06-18T07:00")


def test_fesx_closes_1200():
    h = by_symbol(get("/v1/roll-calendar", product="FESX", year=2027), "FESXH7")
    assert h["trading_ends"]["local"].startswith("2027-03-19T12:00")


def test_front_month_before_and_after_roll():
    before = get("/v1/front-month", product="ES", at="2026-12-09T15:00:00Z")
    assert before["front_contract"] == "ESZ6" and before["most_active_contract"] == "ESZ6"
    after = get("/v1/front-month", product="ES", at="2026-12-11T15:00:00Z")
    assert after["front_contract"] == "ESZ6" and after["most_active_contract"] == "ESH7"
    assert after["after_roll_date"] is True


def test_front_month_after_expiry():
    r = get("/v1/front-month", product="NQ", at="2026-12-18T15:00:00Z")
    assert r["front_contract"] == "NQH7"


def test_expirations_count():
    r = get("/v1/expirations", product="MNQ", count=3, at="2026-10-18T12:00:00Z")
    assert [x["symbol"] for x in r["contracts"]] == ["MNQZ6", "MNQH7", "MNQM7"]


def test_errors():
    assert c.get("/v1/front-month", params={"product": "XX"}).status_code == 404
    assert c.get("/v1/front-month", params={"product": "ES", "at": "2026-12-11T15:00:00"}).status_code == 400
    assert c.get("/v1/roll-calendar", params={"product": "ES", "year": 1990}).status_code == 400
