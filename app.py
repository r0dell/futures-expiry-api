"""HTTP-API für Verfallstermine und Rollover von Index-Futures.

Start:  uvicorn app:app --port 8000
Doku:   http://localhost:8000/docs
"""
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

import crypto
import engine

app = FastAPI(
    title="Futures Expiry API",
    version="0.1.0",
    description=(
        "Expiration dates, last trading times and roll dates for CME and Eurex equity index "
        "futures (ES, NQ, YM, RTY and micros; FDAX, FDXM, FESX, FSMI) and crypto futures (CME bitcoin, ether, "
        "solana, XRP; Deribit daily/weekly/monthly/quarterly). Computed from the "
        "published exchange rules and holiday calendars. Every response names its source."
    ),
)


def _run(fn, *args):
    try:
        return fn(*args)
    except engine.UnknownProduct as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/v1/products", summary="List supported futures products")
def products():
    return engine.list_products()


@app.get("/v1/front-month", summary="Front contract and most active contract at a given time (default: now)")
def front_month(product: str = Query(..., examples=["ES", "FDAX"]),
                at: Optional[datetime] = Query(None, description="ISO time with offset, e.g. 2026-12-11T15:00:00Z")):
    return _run(engine.front_month, product, at)


@app.get("/v1/expirations", summary="Next contract expirations with last trading time and roll date")
def expirations(product: str = Query(..., examples=["NQ"]),
                count: int = Query(4, ge=1, le=12),
                at: Optional[datetime] = None):
    return _run(engine.upcoming, product, at, count)


@app.get("/v1/roll-calendar", summary="All four quarterly expirations and roll dates of a year")
def roll_calendar(product: str = Query(..., examples=["FESX"]),
                  year: int = Query(..., examples=[2027])):
    return _run(engine.roll_calendar, product, year)


@app.get("/v1/crypto-expiry", summary="A37: CME crypto futures (BTC, ETH, SOL, XRP, micros) or Deribit expiries")
def crypto_expiry(product: str = Query("BTC", examples=["BTC", "ETH", "MBT"]),
                  venue: str = Query("cme", examples=["cme", "deribit"]),
                  count: int = Query(6, ge=1, le=24), at: Optional[str] = None):
    try:
        return crypto.crypto_expiry(product, count, at, venue)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'\""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True, "data": engine.DATA_VERSION}
